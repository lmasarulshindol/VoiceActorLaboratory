"""
メインウィンドウ。台本エリア・録音ボタン・テイク一覧を表示する。
"""
import tempfile
import typing
from pathlib import Path
import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QTimer, QByteArray
from PyQt6.QtGui import QAction, QShortcut, QKeySequence, QColor, QCloseEvent, QShowEvent
from PyQt6.QtMultimedia import QMediaDevices, QAudioDevice
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QPlainTextEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMessageBox,
    QLabel,
    QMenu,
    QAbstractItemView,
    QComboBox,
    QToolBar,
    QSpinBox,
    QApplication,
    QStyle,
    QWidgetAction,
    QDialog,
    QDialogButtonBox,
    QRadioButton,
    QCheckBox,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from src.project import Project, TakeInfo
from src.recorder import Recorder
from src.playback import Playback
from src.script_template import DEFAULT_SCRIPT_TEMPLATE
from src.script_format import suggest_take_basename
import src.storage as storage
from src.ui.settings import (
    get_theme,
    get_script_font_size,
    set_script_font_size,
    add_recent_project,
    get_export_use_friendly_names,
    set_export_use_friendly_names,
    get_export_last_dir,
    set_export_last_dir,
    get_main_window_geometry,
    set_main_window_geometry,
    get_input_device_id,
    set_input_device_id,
    get_output_device_id,
    set_output_device_id,
    get_waveform_design,
)
from src.ui.waveform_widget import WaveformWidget
from src.ui.settings_dialog import SettingsDialog
from src.ui.theme_colors import (
    CARD_BG_DARK,
    CARD_BORDER_DARK,
    TAKE_LIST_HIGHLIGHT_LIGHT,
    TAKE_LIST_HIGHLIGHT_DARK,
)
from src.ui.theme_loader import apply_app_theme


class ScriptEdit(QPlainTextEdit):
    """台本エリア。.txt ファイルのドラッグ＆ドロップで台本を開く。"""
    def __init__(self, parent: QWidget | None = None, on_file_dropped: typing.Callable[[str], None] | None = None):
        super().__init__(parent)
        self._on_file_dropped = on_file_dropped
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".txt") and self._on_file_dropped:
                self._on_file_dropped(path)
        e.acceptProposedAction()


class MainWindow(QMainWindow):
    """VoiceActorLaboratory のメインウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self._project = Project()
        self._recorder = Recorder()
        self._playback = Playback()
        self._playback.get_player().playbackStateChanged.connect(self._on_playback_state_changed)
        self._recording_timer = QTimer(self)
        self._recording_timer.timeout.connect(self._on_recording_tick)
        self._playback_position_timer = QTimer(self)
        self._playback_position_timer.timeout.connect(self._on_playback_position_tick)
        self._playing_take_id: str | None = None
        self._loaded_take_id: str | None = None
        self._playback_duration_seconds: float = 0.0
        self._last_playback_was_playing: bool = False
        self._theme_applied_on_show = False  # 初回表示時にテーマを再適用するため
        self._build_ui()
        self._setup_shortcuts()
        geo = get_main_window_geometry()
        if geo:
            self.restoreGeometry(QByteArray(geo))
        self._update_ui_state()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # 初回表示時: プラットフォームの描画でツールバーコンボのスタイルが上書きされることがあるため再適用
        if not self._theme_applied_on_show:
            self._theme_applied_on_show = True
            self._apply_theme(get_theme())

    def _build_ui(self) -> None:
        self.setWindowTitle("Voice Actor Laboratory")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

        # 一行目: 全体機能（新規プロジェクト・台本読み込み・エクスポート等）
        toolbar = QToolBar("全体")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)
        style = self.style()
        act_new = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), "新規プロジェクト", self)
        act_new.setToolTip("新規プロジェクト … フォルダを選んで新しい練習用プロジェクトを作成")
        act_new.triggered.connect(self._on_new_project)
        toolbar.addAction(act_new)
        act_open = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "開く", self)
        act_open.setToolTip("開く … 既存のプロジェクトフォルダを開く")
        act_open.triggered.connect(self._on_open_project)
        toolbar.addAction(act_open)
        act_open_script = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "台本を開く", self)
        act_open_script.setToolTip("台本を開く … テキストファイルから台本を読み込む")
        act_open_script.triggered.connect(self._on_open_script)
        toolbar.addAction(act_open_script)
        act_new_script = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "台本を新規作成", self)
        act_new_script.setToolTip("台本を新規作成 … 入力例を台本エリアに挿入する")
        act_new_script.triggered.connect(self._on_new_script)
        toolbar.addAction(act_new_script)
        act_save_script = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "台本を保存", self)
        act_save_script.setToolTip("台本を保存 … 編集中の台本をプロジェクトに保存")
        act_save_script.triggered.connect(self._on_save_script)
        toolbar.addAction(act_save_script)
        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" 録音:"))
        self._input_device_combo = QComboBox()
        self._input_device_combo.setToolTip("録音に使うマイクを選択")
        self._input_device_combo.setMinimumWidth(180)
        toolbar.addWidget(self._input_device_combo)
        toolbar.addWidget(QLabel(" 再生:"))
        self._output_device_combo = QComboBox()
        self._output_device_combo.setToolTip("再生に使うスピーカーを選択")
        self._output_device_combo.setMinimumWidth(180)
        toolbar.addWidget(self._output_device_combo)
        toolbar.addSeparator()
        act_export = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon), "エクスポート", self)
        act_export.setToolTip("エクスポート … テイクをWAVファイルとして保存先にコピー")
        act_export.triggered.connect(self._on_export_takes)
        toolbar.addAction(act_export)

        # メニュー
        menubar = self.menuBar()
        file_menu = menubar.addMenu("ファイル")
        file_menu.addAction(act_new)
        file_menu.addAction(act_open)
        file_menu.addAction(act_open_script)
        file_menu.addAction(act_new_script)
        file_menu.addAction(act_save_script)
        file_menu.addAction(act_export)
        self._recent_menu = file_menu.addMenu("最近開いたプロジェクト")
        help_menu = menubar.addMenu("ヘルプ")
        act_howto = QAction("使い方", self)
        act_howto.setToolTip("録音〜再生までの手順を表示")
        act_howto.triggered.connect(self._on_show_howto)
        help_menu.addAction(act_howto)
        act_about = QAction("このアプリについて", self)
        act_about.triggered.connect(self._on_show_about)
        help_menu.addAction(act_about)
        view_menu = menubar.addMenu("表示")
        act_theme_light = QAction("テーマ: ライト", self)
        act_theme_light.triggered.connect(lambda: self._apply_theme("light"))
        view_menu.addAction(act_theme_light)
        act_theme_dark = QAction("テーマ: ダーク", self)
        act_theme_dark.triggered.connect(lambda: self._apply_theme("dark"))
        view_menu.addSeparator()
        act_settings = QAction("設定...", self)
        act_settings.setToolTip("波形デザインなどを変更")
        act_settings.triggered.connect(self._on_show_settings)
        view_menu.addAction(act_settings)
        view_menu.addSeparator()
        self._font_spin = QSpinBox()
        self._font_spin.setRange(12, 24)
        self._font_spin.setValue(get_script_font_size())
        self._font_spin.valueChanged.connect(self._on_script_font_size_changed)
        font_action = QWidgetAction(self)
        font_action.setDefaultWidget(self._font_spin)
        view_menu.addAction(font_action)

        # 中央: はじめにパネル（プロジェクトなし） or 分割（台本 | テイク）
        self._stacked = QStackedWidget()

        # はじめにパネル（カード化・隠れないよう最小サイズと余白を厳密に）
        welcome = QWidget()
        welcome.setMinimumWidth(400)
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setSpacing(20)
        welcome_layout.setContentsMargins(24, 24, 24, 24)
        welcome_title = QLabel("はじめに")
        welcome_title.setObjectName("heading")
        welcome_layout.addWidget(welcome_title)
        # カード1: 新規プロジェクト
        card1 = QFrame()
        card1.setObjectName("welcomeCard")
        card1.setFrameShape(QFrame.Shape.StyledPanel)
        card1.setMinimumHeight(140)
        card1_layout = QVBoxLayout(card1)
        card1_layout.setContentsMargins(16, 14, 16, 14)
        card1_layout.setSpacing(6)
        card1_icon = QLabel("📁")
        card1_icon.setStyleSheet("font-size: 22pt;")
        card1_icon.setMinimumHeight(28)
        card1_layout.addWidget(card1_icon)
        card1_title = QLabel("新規プロジェクト作成")
        card1_title.setObjectName("heading")
        card1_title.setWordWrap(True)
        card1_title.setMinimumWidth(200)
        card1_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card1_layout.addWidget(card1_title)
        card1_body = QLabel("保存先フォルダを選択")
        card1_body.setObjectName("body")
        card1_body.setWordWrap(True)
        card1_body.setMinimumWidth(200)
        card1_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card1_layout.addWidget(card1_body)
        btn_new_from_welcome = QPushButton("新規プロジェクトを作成")
        btn_new_from_welcome.setObjectName("accentButton")
        btn_new_from_welcome.setMinimumHeight(36)
        btn_new_from_welcome.setToolTip("保存先フォルダを選んでプロジェクトを作成します")
        btn_new_from_welcome.clicked.connect(self._on_new_project)
        card1_layout.addWidget(btn_new_from_welcome, alignment=Qt.AlignmentFlag.AlignLeft)
        welcome_layout.addWidget(card1)
        # カード2: 録音
        card2 = QFrame()
        card2.setObjectName("welcomeCard")
        card2.setFrameShape(QFrame.Shape.StyledPanel)
        card2.setMinimumHeight(110)
        card2_layout = QVBoxLayout(card2)
        card2_layout.setContentsMargins(16, 14, 16, 14)
        card2_layout.setSpacing(6)
        card2_icon = QLabel("🎤")
        card2_icon.setStyleSheet("font-size: 22pt;")
        card2_icon.setMinimumHeight(28)
        card2_layout.addWidget(card2_icon)
        card2_title = QLabel("録音")
        card2_title.setObjectName("heading")
        card2_title.setWordWrap(True)
        card2_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card2_layout.addWidget(card2_title)
        card2_body = QLabel("台本を確認して録音開始（F9）→ 停止（F10）で1テイク追加")
        card2_body.setObjectName("body")
        card2_body.setWordWrap(True)
        card2_body.setMinimumWidth(200)
        card2_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card2_layout.addWidget(card2_body)
        welcome_layout.addWidget(card2)
        # カード3: 再生
        card3 = QFrame()
        card3.setObjectName("welcomeCard")
        card3.setFrameShape(QFrame.Shape.StyledPanel)
        card3.setMinimumHeight(110)
        card3_layout = QVBoxLayout(card3)
        card3_layout.setContentsMargins(16, 14, 16, 14)
        card3_layout.setSpacing(6)
        card3_icon = QLabel("▶")
        card3_icon.setStyleSheet("font-size: 22pt;")
        card3_icon.setMinimumHeight(28)
        card3_layout.addWidget(card3_icon)
        card3_title = QLabel("再生")
        card3_title.setObjectName("heading")
        card3_title.setWordWrap(True)
        card3_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card3_layout.addWidget(card3_title)
        card3_body = QLabel("テイク一覧でダブルクリックで再生")
        card3_body.setObjectName("body")
        card3_body.setWordWrap(True)
        card3_body.setMinimumWidth(200)
        card3_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card3_layout.addWidget(card3_body)
        welcome_layout.addWidget(card3)
        # カード4: 最近開いたプロジェクト
        card4 = QFrame()
        card4.setObjectName("welcomeCard")
        card4.setFrameShape(QFrame.Shape.StyledPanel)
        card4.setMinimumHeight(100)
        card4_layout = QVBoxLayout(card4)
        card4_layout.setContentsMargins(16, 14, 16, 14)
        card4_layout.setSpacing(6)
        card4_title = QLabel("最近開いたプロジェクト")
        card4_title.setObjectName("heading")
        card4_title.setWordWrap(True)
        card4_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card4_layout.addWidget(card4_title)
        self._welcome_recent_container = QWidget()
        self._welcome_recent_layout = QVBoxLayout(self._welcome_recent_container)
        self._welcome_recent_layout.setContentsMargins(0, 6, 0, 0)
        self._welcome_recent_layout.setSpacing(6)
        card4_layout.addWidget(self._welcome_recent_container)
        welcome_layout.addWidget(card4)
        welcome_layout.addStretch()
        self._stacked.addWidget(welcome)

        # 二行目: 左＝録音制御＋台本、右＝再生制御＋テイク一覧
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左: 録音制御エリア（赤丸⇔一時停止、四角停止）＋台本
        script_widget = QWidget()
        script_layout = QVBoxLayout(script_widget)
        script_layout.setContentsMargins(0, 0, 0, 0)
        rec_controls = QHBoxLayout()
        self._record_toggle_btn = QPushButton("●")
        self._record_toggle_btn.setObjectName("recordToggleBtn")
        self._record_toggle_btn.setFixedSize(44, 44)
        self._record_toggle_btn.setToolTip("録音開始 … 録音を開始（F9）")
        self._record_toggle_btn.clicked.connect(self._on_record_toggle)
        rec_controls.addWidget(self._record_toggle_btn)
        self._record_stop_btn = QPushButton("■")
        self._record_stop_btn.setObjectName("recordStopBtn")
        self._record_stop_btn.setFixedSize(44, 44)
        self._record_stop_btn.setToolTip("録音停止 … 録音を止めてテイクとして保存（F10）")
        self._record_stop_btn.clicked.connect(self._on_record_stop)
        self._record_stop_btn.setEnabled(False)
        rec_controls.addWidget(self._record_stop_btn)
        self._recording_label = QLabel("")
        self._recording_label.setObjectName("recordingLabel")
        rec_controls.addWidget(self._recording_label)
        rec_controls.addStretch()
        script_layout.addLayout(rec_controls)
        self._record_waveform = WaveformWidget()
        self._record_waveform.set_design_id(get_waveform_design())
        script_layout.addWidget(self._record_waveform)
        script_label = QLabel("台本")
        script_label.setObjectName("heading")
        script_layout.addWidget(script_label)
        self._script_edit = ScriptEdit(self, on_file_dropped=self._load_script_from_path)
        self._script_edit.setPlaceholderText("台本を入力。メニュー［台本を新規作成］で例を挿入できます。.txt をドロップしても開けます。")
        self._script_edit.cursorPositionChanged.connect(self._highlight_current_line)
        script_layout.addWidget(self._script_edit)
        splitter.addWidget(script_widget)

        # 右: 再生制御エリア（▶⇔一時停止、■停止）＋テイク一覧
        take_panel = QWidget()
        take_layout = QVBoxLayout(take_panel)
        take_layout.setContentsMargins(0, 0, 0, 0)
        play_controls = QHBoxLayout()
        self._play_pause_btn = QPushButton("▶")
        self._play_pause_btn.setObjectName("playPauseBtn")
        self._play_pause_btn.setFixedSize(44, 44)
        self._play_pause_btn.setToolTip("再生 … 選択したテイクを再生")
        self._play_pause_btn.clicked.connect(self._on_play_pause_toggle)
        play_controls.addWidget(self._play_pause_btn)
        self._play_stop_btn = QPushButton("■")
        self._play_stop_btn.setObjectName("playStopBtn")
        self._play_stop_btn.setFixedSize(44, 44)
        self._play_stop_btn.setToolTip("停止 … 再生を停止")
        self._play_stop_btn.clicked.connect(self._on_playback_stop)
        self._play_stop_btn.setEnabled(False)
        play_controls.addWidget(self._play_stop_btn)
        play_controls.addWidget(QLabel(" 速度:"))
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.5x", "1.0x", "1.25x", "1.5x"])
        self._speed_combo.setCurrentIndex(1)
        self._speed_combo.setToolTip("再生速度 … 0.5x〜1.5x")
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        play_controls.addWidget(self._speed_combo)
        self._playback_time_label = QLabel("0:00 / 0:00")
        self._playback_time_label.setToolTip("現在時刻 / 総時間")
        self._playback_time_label.setMinimumWidth(100)
        play_controls.addWidget(self._playback_time_label)
        play_controls.addStretch()
        take_layout.addLayout(play_controls)
        self._playback_waveform = WaveformWidget()
        self._playback_waveform.set_design_id(get_waveform_design())
        self._playback_waveform.set_seekable(True)
        self._playback_waveform.seekRequested.connect(self._on_playback_seek_requested)
        take_layout.addWidget(self._playback_waveform)
        take_label = QLabel("テイク一覧")
        take_label.setObjectName("heading")
        take_layout.addWidget(take_label)
        self._take_list_hint = QLabel("録音開始でテイクが追加されます")
        self._take_list_hint.setObjectName("caption")
        take_layout.addWidget(self._take_list_hint)
        self._take_list = QListWidget()
        self._take_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._take_list.itemDoubleClicked.connect(self._on_take_double_clicked)
        take_layout.addWidget(self._take_list)
        splitter.addWidget(take_panel)
        splitter.setSizes([500, 400])

        self._stacked.addWidget(splitter)

        # 2ペイン: サイドバー | メイン（_stacked）
        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(12)
        sb_heading = QLabel("プロジェクト")
        sb_heading.setObjectName("heading")
        sidebar_layout.addWidget(sb_heading)
        btn_new_sb = QPushButton("新規")
        btn_new_sb.setToolTip("新規プロジェクトを作成")
        btn_new_sb.clicked.connect(self._on_new_project)
        sidebar_layout.addWidget(btn_new_sb)
        btn_open_sb = QPushButton("開く")
        btn_open_sb.setToolTip("プロジェクトフォルダを開く")
        btn_open_sb.clicked.connect(self._on_open_project)
        sidebar_layout.addWidget(btn_open_sb)
        sb_recent_heading = QLabel("最近開いたプロジェクト")
        sb_recent_heading.setObjectName("heading")
        sidebar_layout.addWidget(sb_recent_heading)
        self._sidebar_recent_container = QWidget()
        self._sidebar_recent_layout = QVBoxLayout(self._sidebar_recent_container)
        self._sidebar_recent_layout.setContentsMargins(0, 4, 0, 0)
        self._sidebar_recent_layout.setSpacing(4)
        sidebar_layout.addWidget(self._sidebar_recent_container)
        sidebar_layout.addStretch()
        sb_settings_heading = QLabel("設定")
        sb_settings_heading.setObjectName("heading")
        sidebar_layout.addWidget(sb_settings_heading)
        btn_settings_sb = QPushButton("設定...")
        btn_settings_sb.clicked.connect(self._on_show_settings)
        sidebar_layout.addWidget(btn_settings_sb)
        btn_theme_light_sb = QPushButton("テーマ: ライト")
        btn_theme_light_sb.clicked.connect(lambda: self._apply_theme("light"))
        sidebar_layout.addWidget(btn_theme_light_sb)
        btn_theme_dark_sb = QPushButton("テーマ: ダーク")
        btn_theme_dark_sb.clicked.connect(lambda: self._apply_theme("dark"))
        sidebar_layout.addWidget(btn_theme_dark_sb)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(self._stacked, 1)
        self.setCentralWidget(root)
        self._stacked.setCurrentIndex(0)  # 起動時は「はじめに」

        # コンテキストメニュー
        self._take_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._take_list.customContextMenuRequested.connect(self._on_take_context_menu)

        # ステータスバー（左: メッセージ、右: ショートカット常時表示）
        self.statusBar().showMessage("新規プロジェクトまたはプロジェクトを開いてから、台本を入力・録音できます。")
        self._shortcut_label = QLabel("F9 録音 | F10 停止 | Space 再生 | ←→ シーク")
        self._shortcut_label.setObjectName("shortcutLabel")
        self.statusBar().addPermanentWidget(self._shortcut_label)

        self._update_recent_menu()
        self._fill_input_devices()
        self._fill_output_devices()
        self._input_device_combo.currentIndexChanged.connect(self._on_input_device_changed)
        self._output_device_combo.currentIndexChanged.connect(self._on_output_device_changed)
        self._apply_device_selections()
        # テーマはデバイス投入後に適用し、showEvent で初回表示時にも再適用（ツールバーコンボの色ずれ防止）
        self._apply_theme(get_theme())
        self._apply_script_font_size(get_script_font_size())

    def _fill_input_devices(self) -> None:
        """録音入力デバイス一覧をセレクトに反映する。"""
        self._input_device_combo.blockSignals(True)
        self._input_device_combo.clear()
        try:
            devices = sd.query_devices()
            default_in = sd.default.device[0] if hasattr(sd.default, "device") else None
            self._input_device_combo.addItem("（デフォルト）", None)
            for i in range(len(devices)):
                d = sd.query_devices(i)
                max_in = getattr(d, "max_input_channels", 0) or (d.get("max_input_channels", 0) if isinstance(d, dict) else 0)
                if max_in > 0:
                    name = getattr(d, "name", d.get("name", str(d)) if isinstance(d, dict) else str(d))
                    self._input_device_combo.addItem(name, i)
            saved = get_input_device_id()
            idx = self._input_device_combo.findData(saved)
            if idx >= 0:
                self._input_device_combo.setCurrentIndex(idx)
            elif default_in is not None:
                idx = self._input_device_combo.findData(default_in)
                if idx >= 0:
                    self._input_device_combo.setCurrentIndex(idx)
        except Exception:
            self._input_device_combo.addItem("（取得失敗）", None)
        self._input_device_combo.blockSignals(False)

    def _fill_output_devices(self) -> None:
        """再生出力デバイス一覧をセレクトに反映する。"""
        self._output_device_combo.blockSignals(True)
        self._output_device_combo.clear()
        try:
            devices = QMediaDevices.audioOutputs()
            self._output_device_combo.addItem("（デフォルト）", None)
            for d in devices:
                desc = d.description() if hasattr(d, "description") else str(d.id().toHex() if hasattr(d.id(), "toHex") else d.id())
                self._output_device_combo.addItem(desc, d)
            saved_id = get_output_device_id()
            if saved_id:
                for i in range(self._output_device_combo.count()):
                    dev = self._output_device_combo.itemData(i)
                    if dev is not None and self._audio_device_id_string(dev) == saved_id:
                        self._output_device_combo.setCurrentIndex(i)
                        break
            else:
                for i in range(self._output_device_combo.count()):
                    dev = self._output_device_combo.itemData(i)
                    if dev is not None and getattr(dev, "isDefault", lambda: False)():
                        self._output_device_combo.setCurrentIndex(i)
                        break
        except Exception:
            self._output_device_combo.addItem("（取得失敗）", None)
        self._output_device_combo.blockSignals(False)

    def _audio_device_id_string(self, device: QAudioDevice) -> str:
        """QAudioDevice の ID を保存用文字列にする。"""
        try:
            bid = device.id()
            if hasattr(bid, "data"):
                return bid.data().hex()
            return ""
        except Exception:
            return ""

    def _on_input_device_changed(self, index: int) -> None:
        device_id = self._input_device_combo.itemData(index)
        set_input_device_id(device_id)
        self._recorder.set_input_device(device_id)

    def _on_output_device_changed(self, index: int) -> None:
        device = self._output_device_combo.itemData(index)
        if device is not None:
            set_output_device_id(self._audio_device_id_string(device))
            self._playback.set_output_device(device)
        else:
            set_output_device_id(None)
            self._playback.set_output_device(None)

    def _apply_device_selections(self) -> None:
        """保存済みの録音・再生デバイスを Recorder/Playback に適用する。"""
        idx = self._input_device_combo.currentIndex()
        if idx >= 0:
            device_id = self._input_device_combo.itemData(idx)
            self._recorder.set_input_device(device_id)
        idx = self._output_device_combo.currentIndex()
        if idx >= 0:
            device = self._output_device_combo.itemData(idx)
            self._playback.set_output_device(device)

    def closeEvent(self, event: QCloseEvent) -> None:
        """終了時に未保存台本を確認し、ウィンドウ位置・サイズを保存する。"""
        if self._project.has_project_dir() and self._script_edit.toPlainText() != self._project.script_text:
            box = QMessageBox(self)
            box.setWindowTitle("台本の保存")
            box.setText("台本を保存していません。保存しますか？")
            box.setStandardButtons(
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel
            )
            box.setDefaultButton(QMessageBox.StandardButton.Save)
            box.setButtonText(QMessageBox.StandardButton.Save, "保存する")
            box.setButtonText(QMessageBox.StandardButton.Discard, "破棄して終了")
            box.setButtonText(QMessageBox.StandardButton.Cancel, "キャンセル")
            ret = box.exec()
            if ret == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if ret == QMessageBox.StandardButton.Save:
                storage.save_script(self._project.project_dir, self._script_edit.toPlainText())
                self._project.script_text = self._script_edit.toPlainText()
        set_main_window_geometry(bytes(self.saveGeometry()))
        super().closeEvent(event)

    def _setup_shortcuts(self) -> None:
        """録音 F9/Ctrl+R・停止 F10。再生 Space・左右シーク。テイク一覧でDelete削除・Enter再生。"""
        QShortcut(QKeySequence("F9"), self, self._on_record_toggle)
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_record_toggle)
        QShortcut(QKeySequence("F10"), self, self._on_record_stop)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, self._on_record_stop)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._on_play_pause_toggle)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._on_seek_backward)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._on_seek_forward)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self._take_list, self._on_take_list_delete_key)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self._take_list, self._on_take_list_enter_play)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self._take_list, self._on_take_list_enter_play)

    def _format_duration(self, seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def _on_recording_tick(self) -> None:
        """録音中タイマー: 経過時間表示と波形更新。"""
        sec = self._recorder.get_buffer_duration_seconds()
        self._recording_label.setText(self._format_duration(sec))
        if self.statusBar():
            self.statusBar().showMessage(f"録音中 {self._format_duration(sec)}")
        samples = self._recorder.get_visualization_samples(max_seconds=10.0)
        self._record_waveform.set_samples(samples)
        self._record_waveform.set_position_seconds(None)
        self._record_waveform.set_duration_seconds(0.0)

    def _update_ui_state(self) -> None:
        has_project = self._project.has_project_dir()
        rec = self._recorder.is_recording
        paused = self._recorder.is_paused
        # 録音トグル: 未録音＝赤丸(開始)、録音中＝一時停止、一時停止中＝赤丸(再開)
        self._record_toggle_btn.setEnabled(has_project)
        if not rec:
            self._record_toggle_btn.setText("●")
            self._record_toggle_btn.setToolTip("録音開始 … 録音を開始（F9）")
        elif paused:
            self._record_toggle_btn.setText("●")
            self._record_toggle_btn.setToolTip("録音再開 … 一時停止から再開")
        else:
            self._record_toggle_btn.setText("‖")
            self._record_toggle_btn.setToolTip("一時停止 … 録音を一時停止")
        self._record_stop_btn.setEnabled(rec)
        if rec:
            if not self._recording_timer.isActive():
                self._recording_timer.start(100)
        else:
            self._recording_timer.stop()
            self._recording_label.setText("")
        # 再生トグル: 停止中＝▶、再生中＝‖、一時停止中＝▶
        has_takes = len(self._project.takes) > 0
        if self._playback.is_playing:
            self._play_pause_btn.setText("‖")
            self._play_pause_btn.setToolTip("一時停止 … 再生を一時停止")
            self._play_pause_btn.setEnabled(True)
        else:
            self._play_pause_btn.setText("▶")
            self._play_pause_btn.setToolTip("再生 … 選択したテイクを再生")
            self._play_pause_btn.setEnabled(has_project and has_takes)
        self._play_stop_btn.setEnabled(self._playback.is_playing or self._playback.is_paused)
        self._refresh_take_list_highlight()
        sb = self.statusBar()
        if sb:
            if rec:
                sb.showMessage(f"録音中 {self._format_duration(self._recorder.get_buffer_duration_seconds())}")
            elif self._playback.is_playing:
                sb.showMessage("再生中")
            elif self._project.has_project_dir():
                sb.showMessage(self._project.project_dir)
            else:
                sb.showMessage("新規プロジェクトまたはプロジェクトを開いてから、台本を入力・録音できます。")

    def _refresh_take_list(self) -> None:
        self._take_list.clear()
        for i, t in enumerate(self._project.takes):
            fav = "★ " if t.favorite else ""
            adopted = "  [採用]" if t.adopted else ""
            dur_sec = storage.get_wav_duration_seconds(self._project.project_dir, t.wav_filename)
            dur_str = f"  {self._format_duration(dur_sec)}" if dur_sec > 0 else ""
            line = f"{fav}{t.display_name(i)}{dur_str}  {t.memo}{adopted}"
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            self._take_list.addItem(item)
        if self._project.takes:
            self._take_list_hint.setText("ダブルクリックで再生／右クリックでメモ・採用・削除")
        else:
            self._take_list_hint.setText("録音開始でテイクが追加されます")
        self._refresh_take_list_highlight()

    def _refresh_take_list_highlight(self) -> None:
        """再生中のテイク行をハイライトする。テーマに合わせた色で視認性を確保。"""
        dark = get_theme() == "dark"
        base = QColor(CARD_BG_DARK) if dark else self._take_list.palette().base()
        highlight = QColor(TAKE_LIST_HIGHLIGHT_DARK) if dark else QColor(TAKE_LIST_HIGHLIGHT_LIGHT)
        for i in range(self._take_list.count()):
            item = self._take_list.item(i)
            take_id = item.data(Qt.ItemDataRole.UserRole)
            if take_id == self._playing_take_id:
                item.setBackground(highlight)
            else:
                item.setBackground(base)
    def _on_speed_changed(self, index: int) -> None:
        rates = [0.5, 1.0, 1.25, 1.5]
        if 0 <= index < len(rates):
            self._playback.set_speed(rates[index])

    def _apply_theme(self, theme: str) -> None:
        """QSS とパレットは theme_loader で一括適用。波形・テイクハイライト・カードの影のみここで行う。"""
        apply_app_theme(theme)
        dark = theme == "dark"
        self._record_waveform.set_dark_theme(dark)
        self._playback_waveform.set_dark_theme(dark)
        self._refresh_take_list_highlight()
        for frame in self.findChildren(QFrame):
            if frame.objectName() == "welcomeCard":
                if dark:
                    frame.setGraphicsEffect(None)
                else:
                    shadow = QGraphicsDropShadowEffect()
                    shadow.setBlurRadius(12)
                    shadow.setXOffset(0)
                    shadow.setYOffset(2)
                    shadow.setColor(QColor(0, 0, 0, 76))
                    frame.setGraphicsEffect(shadow)

    def _apply_script_font_size(self, size: int) -> None:
        from PyQt6.QtGui import QFont
        f = self._script_edit.font()
        f.setPointSize(size)
        self._script_edit.setFont(f)

    def _on_script_font_size_changed(self, value: int) -> None:
        set_script_font_size(value)
        self._apply_script_font_size(value)

    def _highlight_current_line(self) -> None:
        try:
            from PyQt6.QtGui import QColor
            from PyQt6.QtWidgets import QPlainTextEdit
            cursor = self._script_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine)
            cursor.movePosition(cursor.MoveOperation.EndOfLine, cursor.MoveMode.KeepAnchor)
            extra = QPlainTextEdit.ExtraSelection()
            extra.cursor = cursor
            extra.format.setBackground(QColor(255, 255, 200))
            self._script_edit.setExtraSelections([extra])
        except (TypeError, AttributeError):
            self._script_edit.setExtraSelections([])

    def _update_recent_menu(self) -> None:
        from src.ui.settings import get_recent_projects
        self._recent_menu.clear()
        for path in get_recent_projects():
            if not path:
                continue
            act = QAction(Path(path).name or path, self)
            act.triggered.connect(lambda checked=False, p=path: self._open_recent_project(p))
            self._recent_menu.addAction(act)
        if not self._recent_menu.actions():
            self._recent_menu.addAction("（なし）").setEnabled(False)
        self._update_welcome_recent_list()
        self._update_sidebar_recent_list()

    def _update_sidebar_recent_list(self) -> None:
        """サイドバーに表示する「最近開いたプロジェクト」を更新する。"""
        from src.ui.settings import get_recent_projects
        while self._sidebar_recent_layout.count():
            item = self._sidebar_recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for path in get_recent_projects():
            if not path:
                continue
            name = Path(path).name or path
            btn = QPushButton(name)
            btn.setObjectName("recentProjectButton")
            btn.setToolTip(path)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, p=path: self._open_recent_project(p))
            self._sidebar_recent_layout.addWidget(btn)

    def _update_welcome_recent_list(self) -> None:
        """はじめにパネルに表示する「最近開いたプロジェクト」を更新する。"""
        from src.ui.settings import get_recent_projects
        # 既存の子ウィジェットを削除
        while self._welcome_recent_layout.count():
            item = self._welcome_recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for path in get_recent_projects():
            if not path:
                continue
            name = Path(path).name or path
            btn = QPushButton(name)
            btn.setObjectName("recentProjectButton")
            btn.setToolTip(path)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, p=path: self._open_recent_project(p))
            self._welcome_recent_layout.addWidget(btn)

    def _open_recent_project(self, path: str) -> None:
        if not Path(path).is_dir():
            QMessageBox.warning(self, "エラー", "プロジェクトフォルダが見つかりません。")
            return
        proj = storage.load_project(path)
        if proj is None:
            QMessageBox.warning(self, "エラー", "プロジェクトを読み込めませんでした。")
            return
        self._project = proj
        self._reset_playback_ui()
        self._script_edit.setPlainText(self._project.script_text)
        self._refresh_take_list()
        self._update_ui_state()
        self._switch_to_main_view()
        self.statusBar().showMessage(self._project.project_dir)

    def _switch_to_main_view(self) -> None:
        """プロジェクト作成/打開後、メイン（台本・テイク）画面に切り替える。"""
        self._stacked.setCurrentIndex(1)

    def _on_show_about(self) -> None:
        """ヘルプ「このアプリについて」ダイアログを表示する。"""
        from src import __version__
        QMessageBox.about(
            self,
            "このアプリについて",
            f"Voice Actor Laboratory\nバージョン {__version__}\n\n声優向け 録音・再生・比較アプリです。",
        )

    def _on_show_howto(self) -> None:
        """ヘルプ「使い方」ダイアログを表示する。"""
        text = (
            "【録音 → 再生までの流れ】\n\n"
            "1. 新規プロジェクト … ツールバー「新規プロジェクト」で保存先フォルダを選ぶ\n"
            "2. 台本 … 自動で例が入ります。そのまま録音してOK\n"
            "3. 録音 … 「録音開始」（F9）→「録音停止」で1テイク追加\n"
            "4. 再生 … テイク一覧でダブルクリックで再生\n\n"
            "※ 既存のプロジェクトは「開く」または「最近開いたプロジェクト」から。"
        )
        QMessageBox.information(self, "使い方", text)

    def _on_new_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "新規プロジェクトの保存先を選択")
        if not path:
            return
        self._project = storage.create_project(path)
        self._reset_playback_ui()
        storage.save_script(path, DEFAULT_SCRIPT_TEMPLATE)
        self._project.script_text = DEFAULT_SCRIPT_TEMPLATE
        self._script_edit.setPlainText(DEFAULT_SCRIPT_TEMPLATE)
        add_recent_project(path)
        self._update_recent_menu()
        self._refresh_take_list()
        self._update_ui_state()
        self._switch_to_main_view()
        self.statusBar().showMessage(path)
        QMessageBox.information(self, "プロジェクト", f"プロジェクトを作成しました。\n「録音開始」（F9）で録音できます。")

    def _on_open_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "プロジェクトフォルダを選択")
        if not path:
            return
        proj = storage.load_project(path)
        if proj is None:
            QMessageBox.warning(self, "エラー", "プロジェクトを読み込めませんでした。")
            return
        self._project = proj
        self._reset_playback_ui()
        add_recent_project(path)
        self._update_recent_menu()
        self._script_edit.setPlainText(self._project.script_text)
        self._refresh_take_list()
        self._update_ui_state()
        self._switch_to_main_view()
        self.statusBar().showMessage(path)

    def _load_script_from_path(self, path: str) -> None:
        """指定パスのテキストを台本として読み込む。ドロップ・メニュー「台本を開く」の共通処理。"""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"台本を読み込めませんでした: {e}")
            return
        self._project.set_script(path, text)
        self._script_edit.setPlainText(text)
        if self._project.has_project_dir():
            storage.save_script(self._project.project_dir, text)
        if self.statusBar():
            self.statusBar().showMessage(f"台本を読み込みました: {path}")

    def _on_open_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "台本を開く", "", "テキスト (*.txt);;すべて (*)")
        if path:
            self._load_script_from_path(path)

    def _on_new_script(self) -> None:
        """台本エリアに入力例（テンプレート）を表示する。プロジェクト打開時は保存も行う。"""
        self._script_edit.setPlainText(DEFAULT_SCRIPT_TEMPLATE)
        self._project.script_text = DEFAULT_SCRIPT_TEMPLATE
        if self._project.has_project_dir():
            storage.save_script(self._project.project_dir, DEFAULT_SCRIPT_TEMPLATE)
            self.statusBar().showMessage("台本を入力例で置き換え、保存しました。")
        else:
            self.statusBar().showMessage("入力例を表示しました。プロジェクトを開いた状態で「台本を保存」で保存できます。")

    def _on_save_script(self) -> None:
        """UIで編集中の台本をプロジェクトに保存する。プロジェクト未打開の場合は新規作成を促す。"""
        text = self._script_edit.toPlainText()
        if self._project.has_project_dir():
            storage.save_script(self._project.project_dir, text)
            self._project.script_text = text
            self.statusBar().showMessage("台本を保存しました。")
        else:
            QMessageBox.information(
                self,
                "台本を保存",
                "プロジェクトを開いていません。先に「新規プロジェクト」または「プロジェクトを開く」でフォルダを指定してください。",
            )

    def _on_record_toggle(self) -> None:
        """録音開始 / 一時停止 / 再開の切り替え。"""
        if not self._project.has_project_dir():
            QMessageBox.warning(self, "録音", "先にプロジェクトを新規作成するか開いてください。")
            return
        try:
            if not self._recorder.is_recording:
                self._recorder.start()
                self._recording_timer.start(100)
                self._on_recording_tick()
            elif self._recorder.is_paused:
                self._recorder.resume()
                self._recording_timer.start(100)
                self._on_recording_tick()
            else:
                self._recorder.pause()
            self._update_ui_state()
        except Exception as e:
            QMessageBox.warning(self, "録音エラー", str(e))

    def _on_record_stop(self) -> None:
        if not self._recorder.is_recording:
            return
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        import os
        os.close(fd)
        take_added = False
        try:
            if self._recorder.stop_and_save(tmp):
                script_text = self._script_edit.toPlainText()
                cursor_pos = self._script_edit.textCursor().position()
                existing = [t.wav_filename for t in self._project.takes]
                preferred_basename = suggest_take_basename(script_text, cursor_pos, existing)
                take = storage.add_take_from_file(
                    self._project.project_dir,
                    tmp,
                    memo="",
                    favorite=False,
                    preferred_basename=preferred_basename,
                )
                self._project.add_take(take)
                self._refresh_take_list()
                take_added = True
        finally:
            Path(tmp).unlink(missing_ok=True)
        self._recording_timer.stop()
        self._record_waveform.set_samples(np.array([], dtype=np.float32))
        self._update_ui_state()
        if self.statusBar():
            if take_added:
                self.statusBar().showMessage("1テイクを追加しました")
            else:
                self.statusBar().showMessage(self._project.project_dir or "準備完了")

    def _on_take_double_clicked(self, item: QListWidgetItem) -> None:
        take_id = item.data(Qt.ItemDataRole.UserRole)
        t = self._project.get_take(take_id)
        if t is None:
            return
        wav_path = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
        self._playing_take_id = take_id
        self._loaded_take_id = take_id
        self._load_playback_waveform(wav_path)
        self._playback.play(wav_path)
        self._playback_position_timer.start(80)
        self._update_ui_state()

    def _on_play_pause_toggle(self) -> None:
        """再生 ⇔ 一時停止の切り替え。"""
        if self._playback.is_playing:
            self._playback.pause()
        elif self._playback.is_paused:
            self._playback.get_player().play()
        else:
            item = self._take_list.currentItem()
            if item is None:
                item = self._take_list.item(0)
            if item is not None:
                take_id = item.data(Qt.ItemDataRole.UserRole)
                if (
                    self._playback_duration_seconds > 0
                    and self._loaded_take_id is not None
                    and take_id == self._loaded_take_id
                ):
                    pos_sec = self._playback_waveform.get_position_seconds()
                    self._playback.seek_to_position_ms(int(pos_sec * 1000))
                    self._playback.get_player().play()
                    self._playing_take_id = take_id
                    self._playback_position_timer.start(80)
                else:
                    self._on_take_double_clicked(item)
        self._update_ui_state()

    def _on_playback_seek_requested(self, ratio: float) -> None:
        """波形クリック・ドラッグでシーク。"""
        if self._playback_duration_seconds <= 0:
            return
        duration_ms = int(self._playback_duration_seconds * 1000)
        ms = max(0, min(duration_ms, int(ratio * duration_ms)))
        self._playback.seek_to_position_ms(ms)
        self._playback_waveform.set_position_seconds(ms / 1000.0)
        if self._playback.is_playing or self._playback.is_paused:
            self._playback.get_player().play()
        self._update_ui_state()

    def _on_seek_backward(self) -> None:
        """左キー: 5秒戻る。"""
        if self._playback_duration_seconds <= 0:
            return
        cur = self._playback.get_player().position()
        new_ms = max(0, cur - 5000)
        self._playback.seek_to_position_ms(new_ms)
        self._playback_waveform.set_position_seconds(new_ms / 1000.0)
        if self._playback.is_playing or self._playback.is_paused:
            self._playback.get_player().play()
        self._update_ui_state()

    def _on_seek_forward(self) -> None:
        """右キー: 5秒進む。"""
        if self._playback_duration_seconds <= 0:
            return
        duration_ms = int(self._playback_duration_seconds * 1000)
        cur = self._playback.get_player().position()
        new_ms = min(duration_ms, cur + 5000)
        self._playback.seek_to_position_ms(new_ms)
        self._playback_waveform.set_position_seconds(new_ms / 1000.0)
        if self._playback.is_playing or self._playback.is_paused:
            self._playback.get_player().play()
        self._update_ui_state()

    def _reset_playback_ui(self) -> None:
        """再生まわりを未ロード状態に戻す。プロジェクト打開時などに呼ぶ。"""
        self._playback.stop()
        self._playback_position_timer.stop()
        self._playing_take_id = None
        self._loaded_take_id = None
        self._playback_duration_seconds = 0.0
        self._playback_waveform.set_samples(np.array([], dtype=np.float32))
        self._playback_waveform.set_duration_seconds(0.0)
        self._playback_waveform.set_position_seconds(None)
        self._playback_time_label.setText("0:00 / 0:00")
        self._update_ui_state()

    def _on_playback_stop(self) -> None:
        """再生を停止する。"""
        self._playback.stop()
        self._playback_position_timer.stop()
        self._playing_take_id = None
        self._playback_waveform.set_position_seconds(None)
        if self._playback_duration_seconds > 0:
            self._playback_time_label.setText(
                f"0:00 / {self._format_duration(self._playback_duration_seconds)}"
            )
        self._update_ui_state()

    def _on_playback_state_changed(self) -> None:
        now_playing = self._playback.is_playing
        now_stopped = not now_playing and not self._playback.is_paused
        if self._last_playback_was_playing and now_stopped:
            if self.statusBar():
                self.statusBar().showMessage("再生が終わりました")
        self._last_playback_was_playing = now_playing
        if now_stopped:
            self._playback_position_timer.stop()
            self._playing_take_id = None
            self._playback_waveform.set_position_seconds(None)
        self._update_ui_state()

    def _on_playback_position_tick(self) -> None:
        """再生位置を波形に反映し、時刻ラベルを更新。"""
        pos_ms = max(0, self._playback.get_player().position())
        pos_sec = pos_ms / 1000.0
        self._playback_waveform.set_position_seconds(pos_sec)
        if self._playback_duration_seconds > 0:
            total_str = self._format_duration(self._playback_duration_seconds)
            self._playback_time_label.setText(
                f"{self._format_duration(pos_sec)} / {total_str}"
            )
        else:
            self._playback_time_label.setText("0:00 / 0:00")

    def _load_playback_waveform(self, wav_path: str) -> None:
        """WAV を読み込み再生用波形にセット。"""
        try:
            import soundfile as sf
            data, sr = sf.read(wav_path, dtype="float32")
            if data.ndim > 1:
                data = data[:, 0]
            duration = len(data) / float(sr)
            self._playback_duration_seconds = duration
            self._playback_waveform.set_samples(data)
            self._playback_waveform.set_duration_seconds(duration)
            self._playback_waveform.set_position_seconds(0.0)
            self._playback_time_label.setText(
                f"0:00 / {self._format_duration(duration)}"
            )
        except Exception:
            self._playback_duration_seconds = 0.0
            self._playback_waveform.set_samples(np.array([], dtype=np.float32))
            self._playback_waveform.set_duration_seconds(0.0)
            self._playback_waveform.set_position_seconds(None)
            self._playback_time_label.setText("0:00 / 0:00")

    def _on_show_settings(self) -> None:
        """設定ダイアログを表示し、OK なら波形デザインを反映。"""
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            design = get_waveform_design()
            self._record_waveform.set_design_id(design)
            self._playback_waveform.set_design_id(design)

    def _on_take_context_menu(self, pos: typing.Any) -> None:
        item = self._take_list.itemAt(pos)
        if not item:
            return
        take_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        t = self._project.get_take(take_id)
        fav_label = "お気に入り解除" if (t and t.favorite) else "お気に入りに追加"
        act_fav = QAction(fav_label, self)
        def toggle_fav():
            ti = self._project.get_take(take_id)
            if ti:
                storage.update_take_meta(self._project.project_dir, take_id, favorite=not ti.favorite)
                self._project = storage.load_project(self._project.project_dir) or self._project
                self._refresh_take_list()
        act_fav.triggered.connect(toggle_fav)
        menu.addAction(act_fav)
        adopted_label = "採用を解除" if (t and t.adopted) else "採用にする"
        act_adopted = QAction(adopted_label, self)
        def toggle_adopted():
            ti = self._project.get_take(take_id)
            if ti:
                storage.update_take_meta(self._project.project_dir, take_id, adopted=not ti.adopted)
                self._project = storage.load_project(self._project.project_dir) or self._project
                self._refresh_take_list()
        act_adopted.triggered.connect(toggle_adopted)
        menu.addAction(act_adopted)
        act_memo = QAction("メモを編集", self)
        def edit_memo():
            ti = self._project.get_take(take_id)
            if not ti:
                return
            from PyQt6.QtWidgets import QInputDialog
            new_memo, ok = QInputDialog.getMultiLineText(self, "メモ", "メモ:", ti.memo)
            if ok and new_memo is not None:
                storage.update_take_meta(self._project.project_dir, take_id, memo=new_memo)
                self._project = storage.load_project(self._project.project_dir) or self._project
                self._refresh_take_list()
        act_memo.triggered.connect(edit_memo)
        menu.addAction(act_memo)
        act_del = QAction("テイクを削除", self)
        act_del.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        def delete_take():
            if QMessageBox.question(
                self, "確認", "このテイクを削除しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            if storage.delete_take(self._project.project_dir, take_id):
                self._project = storage.load_project(self._project.project_dir) or self._project
                self._refresh_take_list()
            else:
                QMessageBox.warning(self, "エラー", "削除に失敗しました。")
        act_del.triggered.connect(delete_take)
        menu.addAction(act_del)
        menu.exec(self._take_list.mapToGlobal(pos))

    def _on_take_list_delete_key(self) -> None:
        """テイク一覧にフォーカスがあるときにDeleteで選択テイクを削除。"""
        if not self._project.has_project_dir() or not self._project.takes:
            return
        items = [self._take_list.item(i) for i in range(self._take_list.count()) if self._take_list.item(i).isSelected()]
        if not items:
            cur = self._take_list.currentItem()
            if cur:
                items = [cur]
        if not items:
            return
        take_ids = [it.data(Qt.ItemDataRole.UserRole) for it in items if it and it.data(Qt.ItemDataRole.UserRole)]
        if not take_ids:
            return
        n = len(take_ids)
        msg = f"選択した{n}件のテイクを削除しますか？" if n > 1 else "このテイクを削除しますか？"
        if QMessageBox.question(
            self, "確認", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        ok_count = 0
        for take_id in take_ids:
            if storage.delete_take(self._project.project_dir, take_id):
                ok_count += 1
        if ok_count > 0:
            self._project = storage.load_project(self._project.project_dir) or self._project
            self._refresh_take_list()
        if ok_count < n:
            QMessageBox.warning(self, "エラー", f"{n - ok_count}件の削除に失敗しました。")

    def _on_take_list_enter_play(self) -> None:
        """テイク一覧でEnterを押したときに選択または現在のテイクを再生。"""
        if not self._project.has_project_dir() or not self._project.takes:
            return
        item = self._take_list.currentItem()
        if not item:
            item = self._take_list.item(0)
        if item:
            self._on_take_double_clicked(item)

    def _on_export_takes(self) -> None:
        if not self._project.has_project_dir():
            QMessageBox.warning(self, "エクスポート", "プロジェクトを開いてください。")
            return
        selected_ids = [
            self._take_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._take_list.count())
            if self._take_list.item(i).isSelected()
        ]
        adopted = self._project.get_adopted_take()
        adopted_ids = [adopted.id] if adopted else []
        if not self._project.takes:
            QMessageBox.information(self, "エクスポート", "テイクがありません。")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("エクスポート")
        layout = QVBoxLayout(dlg)
        grp = QButtonGroup(dlg)
        r_all = QRadioButton("全テイク")
        r_selected = QRadioButton("選択したテイク")
        r_adopted = QRadioButton("採用テイクのみ")
        if adopted_ids:
            r_adopted.setEnabled(True)
        else:
            r_adopted.setEnabled(False)
            r_adopted.setToolTip("採用テイクがありません")
        if selected_ids:
            r_selected.setChecked(True)
        elif adopted_ids:
            r_adopted.setChecked(True)
        else:
            r_all.setChecked(True)
        grp.addButton(r_all)
        grp.addButton(r_selected)
        grp.addButton(r_adopted)
        layout.addWidget(r_all)
        layout.addWidget(r_selected)
        layout.addWidget(r_adopted)
        friendly = QCheckBox("ファイル名を「プロジェクト名_Take1.wav」形式にする")
        friendly.setChecked(get_export_use_friendly_names())
        layout.addWidget(friendly)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if r_all.isChecked():
            take_ids = [t.id for t in self._project.takes]
        elif r_selected.isChecked() and selected_ids:
            take_ids = selected_ids
        elif r_adopted.isChecked() and adopted_ids:
            take_ids = adopted_ids
        else:
            take_ids = [t.id for t in self._project.takes]
        set_export_use_friendly_names(friendly.isChecked())
        dest = QFileDialog.getExistingDirectory(
            self, "エクスポート先を選択", directory=get_export_last_dir() or ""
        )
        if not dest:
            return
        set_export_last_dir(dest)
        paths = storage.export_takes(
            self._project.project_dir,
            take_ids,
            dest,
            use_friendly_names=friendly.isChecked(),
        )
        QMessageBox.information(self, "エクスポート", f"{len(paths)} 件をエクスポートしました。")