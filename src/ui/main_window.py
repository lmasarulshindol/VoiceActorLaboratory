"""
メインウィンドウ。台本エリア・録音ボタン・テイク一覧を表示する。
"""
import subprocess
import sys
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
    get_last_project_dialog_dir,
    set_last_project_dialog_dir,
    get_last_script_dialog_dir,
    set_last_script_dialog_dir,
    get_main_window_geometry,
    set_main_window_geometry,
    get_main_window_splitter_sizes,
    set_main_window_splitter_sizes,
    get_last_session_project_path,
    set_last_session_project_path,
    get_input_device_id,
    set_input_device_id,
    get_output_device_id,
    set_output_device_id,
    get_waveform_design,
    get_recording_mode,
    set_recording_mode,
    get_auto_play_after_record,
    set_auto_play_after_record,
    get_take_list_filter,
    set_take_list_filter,
    get_take_list_sort,
    set_take_list_sort,
    get_confirm_before_delete_take,
)
from src.ui.waveform_widget import WaveformWidget
from src.ui.settings_dialog import SettingsDialog
from src.ui.find_replace_dialog import FindReplaceDialog
from src.ui.script_edit_with_line_numbers import ScriptEditWithLineNumbers
from src.ui.theme_colors import (
    CARD_BG_DARK,
    CARD_BORDER_DARK,
    TAKE_LIST_HIGHLIGHT_LIGHT,
    TAKE_LIST_HIGHLIGHT_DARK,
    TAKE_LIST_SELECTED_LIGHT,
    TAKE_LIST_SELECTED_DARK,
)
from src.ui.theme_loader import apply_app_theme
from src.script_format import suggest_take_basename, get_current_line_text, get_current_line_number, get_current_section


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
            # 複数ファイルがドロップされた場合は先頭1つのみ扱う
            path = urls[0].toLocalFile()
            lower = path.lower()
            if (lower.endswith(".txt") or lower.endswith(".md")) and self._on_file_dropped:
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
        self._playback.get_player().errorOccurred.connect(self._on_playback_error)
        self._recording_timer = QTimer(self)
        self._recording_timer.timeout.connect(self._on_recording_tick)
        self._playback_position_timer = QTimer(self)
        self._playback_position_timer.timeout.connect(self._on_playback_position_tick)
        self._playing_take_id: str | None = None
        self._loaded_take_id: str | None = None
        self._playback_duration_seconds: float = 0.0
        self._last_playback_was_playing: bool = False
        self._theme_applied_on_show = False  # 初回表示時にテーマを再適用するため
        self._last_added_take_id: str | None = None  # 最後に追加されたテイクID
        self._new_take_ids: set[str] = set()  # NEWバッジを表示するテイクIDのセット
        self._new_take_timer = QTimer(self)  # NEWバッジの自動削除用タイマー
        self._new_take_timer.setSingleShot(True)
        self._new_take_timer.timeout.connect(self._clear_new_badges)
        self._recording_blink_timer = QTimer(self)  # 録音ボタンの点滅用タイマー
        self._recording_blink_state = False  # 録音ボタンの点滅状態
        self._recording_blink_timer.timeout.connect(self._on_recording_blink_tick)
        self._ab_compare_queue: list[str] = []  # A/B比較で連続再生するテイクIDのキュー
        self._build_ui()
        self._setup_shortcuts()
        geo = get_main_window_geometry()
        if geo:
            try:
                self.restoreGeometry(QByteArray(geo))
            except Exception:
                pass
        self._update_ui_state()
        # 前回開いていたプロジェクトを復元（ウィンドウ表示後に実行）
        QTimer.singleShot(0, self._restore_last_session)

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
        edit_menu = menubar.addMenu("編集")
        act_find = QAction("検索...", self)
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.setToolTip("台本内を検索（Ctrl+F）")
        act_find.triggered.connect(self._on_find)
        edit_menu.addAction(act_find)
        act_replace = QAction("置換...", self)
        act_replace.setShortcut(QKeySequence("Ctrl+H"))
        act_replace.setToolTip("台本内を検索して置換（Ctrl+H）")
        act_replace.triggered.connect(self._on_replace_dialog)
        edit_menu.addAction(act_replace)
        help_menu = menubar.addMenu("ヘルプ")
        act_howto = QAction("使い方", self)
        act_howto.setToolTip("録音〜再生までの手順を表示")
        act_howto.triggered.connect(self._on_show_howto)
        help_menu.addAction(act_howto)
        act_shortcuts = QAction("キーボードショートカット", self)
        act_shortcuts.setToolTip("ショートカット一覧を表示")
        act_shortcuts.triggered.connect(self._on_show_shortcuts)
        help_menu.addAction(act_shortcuts)
        help_menu.addSeparator()
        act_restart = QAction("アプリを再起動", self)
        act_restart.setToolTip("アプリケーションを再起動します")
        act_restart.triggered.connect(self._on_restart_app)
        help_menu.addAction(act_restart)
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

        # 中央エリア: 台本とテイク一覧を左右分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左: 台本エリア
        script_widget = QWidget()
        script_layout = QVBoxLayout(script_widget)
        script_layout.setContentsMargins(0, 0, 0, 0)
        
        script_label = QLabel("台本")
        script_label.setObjectName("heading")
        script_layout.addWidget(script_label)
        script_edit_factory = lambda p: ScriptEdit(p, on_file_dropped=self._load_script_from_path)
        self._script_container = ScriptEditWithLineNumbers(self, script_edit_factory=script_edit_factory)
        self._script_edit = self._script_container.script_edit()
        self._script_edit.setPlaceholderText("台本を入力。メニュー［台本を新規作成］で例を挿入できます。.txt / .md をドロップしても開けます。")
        self._script_edit.cursorPositionChanged.connect(self._highlight_current_line)
        self._script_edit.cursorPositionChanged.connect(self._update_current_line_preview)
        self._script_edit.cursorPositionChanged.connect(self._update_status_script_position)
        self._script_edit.textChanged.connect(self._update_window_title)
        script_layout.addWidget(self._script_container)
        
        # 個別モード時の現在行セリフプレビューエリア
        self._current_line_preview_frame = QFrame()
        self._current_line_preview_frame.setObjectName("currentLinePreview")
        self._current_line_preview_frame.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout = QVBoxLayout(self._current_line_preview_frame)
        preview_layout.setContentsMargins(12, 8, 12, 8)
        preview_layout.setSpacing(4)
        preview_label = QLabel("現在のセリフ")
        preview_label.setObjectName("heading")
        preview_layout.addWidget(preview_label)
        self._current_line_preview = QPlainTextEdit()
        self._current_line_preview.setReadOnly(True)
        self._current_line_preview.setPlaceholderText("カーソル位置のセリフがここに表示されます")
        self._current_line_preview.setMaximumHeight(100)
        self._current_line_preview.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(255, 255, 200, 0.1);
                border: 1px solid rgba(255, 255, 200, 0.3);
                border-radius: 4px;
                padding: 8px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        preview_layout.addWidget(self._current_line_preview)
        script_layout.addWidget(self._current_line_preview_frame)
        self._current_line_preview_frame.setVisible(False)  # 初期状態は非表示
        
        splitter.addWidget(script_widget)

        # 右: テイク一覧エリア
        take_panel = QWidget()
        take_layout = QVBoxLayout(take_panel)
        take_layout.setContentsMargins(0, 0, 0, 0)
        
        take_label = QLabel("テイク一覧")
        take_label.setObjectName("heading")
        take_layout.addWidget(take_label)
        # フィルタ・ソート
        take_filter_sort_row = QHBoxLayout()
        take_filter_sort_row.addWidget(QLabel("表示:"))
        self._take_filter_combo = QComboBox()
        self._take_filter_combo.addItem("すべて", "all")
        self._take_filter_combo.addItem("お気に入りのみ", "favorite")
        self._take_filter_combo.addItem("採用のみ", "adopted")
        self._take_filter_combo.setToolTip("一覧に表示するテイクを絞り込み")
        take_filter_sort_row.addWidget(self._take_filter_combo)
        take_filter_sort_row.addWidget(QLabel("並び:"))
        self._take_sort_combo = QComboBox()
        self._take_sort_combo.addItem("日付（新しい順）", "date_desc")
        self._take_sort_combo.addItem("日付（古い順）", "date_asc")
        self._take_sort_combo.addItem("お気に入り優先", "favorite_first")
        self._take_sort_combo.addItem("採用優先", "adopted_first")
        self._take_sort_combo.setToolTip("テイクの並び順")
        take_filter_sort_row.addWidget(self._take_sort_combo)
        take_filter_sort_row.addStretch()
        take_layout.addLayout(take_filter_sort_row)
        self._take_filter_combo.currentIndexChanged.connect(self._on_take_filter_sort_changed)
        self._take_sort_combo.currentIndexChanged.connect(self._on_take_filter_sort_changed)
        idx_f = self._take_filter_combo.findData(get_take_list_filter())
        if idx_f >= 0:
            self._take_filter_combo.setCurrentIndex(idx_f)
        idx_s = self._take_sort_combo.findData(get_take_list_sort())
        if idx_s >= 0:
            self._take_sort_combo.setCurrentIndex(idx_s)
        self._take_list_hint = QLabel("録音開始でテイクが追加されます")
        self._take_list_hint.setObjectName("caption")
        take_layout.addWidget(self._take_list_hint)
        self._take_list = QListWidget()
        self._take_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._take_list.itemDoubleClicked.connect(self._on_take_double_clicked)
        self._take_list.currentItemChanged.connect(self._on_take_list_selection_changed)
        take_layout.addWidget(self._take_list)
        splitter.addWidget(take_panel)
        self._main_splitter = splitter
        saved_sizes = get_main_window_splitter_sizes()
        if len(saved_sizes) == 2 and all(s > 0 for s in saved_sizes):
            splitter.setSizes(saved_sizes)
        else:
            splitter.setSizes([500, 400])

        # 下部: 統合コントロールエリア（録音・再生ボタンを近接配置）
        control_frame = QFrame()
        control_frame.setObjectName("controlPanel")
        control_frame.setFrameShape(QFrame.Shape.StyledPanel)
        control_frame.setFixedHeight(180)
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(16, 12, 16, 12)
        control_layout.setSpacing(20)

        # 左側: 録音コントロール
        rec_group = QVBoxLayout()
        rec_group.setSpacing(8)
        rec_header = QHBoxLayout()
        rec_header.addWidget(QLabel("録音"))
        rec_header.addStretch()
        rec_group.addLayout(rec_header)
        
        rec_controls_row = QHBoxLayout()
        rec_controls_row.setSpacing(8)
        self._record_mode_combo = QComboBox()
        self._record_mode_combo.addItem("台本一括", "bulk")
        self._record_mode_combo.addItem("セリフ個別", "individual")
        self._record_mode_combo.setToolTip("録音モード切り替え\n一括: シーンごとに連番\n個別: カーソル行のセリフをメモとファイル名に反映")
        saved_mode = get_recording_mode()
        idx = self._record_mode_combo.findData(saved_mode)
        if idx >= 0:
            self._record_mode_combo.setCurrentIndex(idx)
        self._record_mode_combo.currentIndexChanged.connect(self._on_recording_mode_changed)
        rec_controls_row.addWidget(self._record_mode_combo)
        rec_controls_row.addSpacing(8)
        
        self._record_toggle_btn = QPushButton("●")
        self._record_toggle_btn.setObjectName("recordToggleBtn")
        self._record_toggle_btn.setFixedSize(50, 50)
        self._record_toggle_btn.setToolTip("録音開始 … 録音を開始（F9）")
        self._record_toggle_btn.setAccessibleName("録音開始")
        self._record_toggle_btn.clicked.connect(self._on_record_toggle)
        rec_controls_row.addWidget(self._record_toggle_btn)
        
        self._record_stop_btn = QPushButton("■")
        self._record_stop_btn.setObjectName("recordStopBtn")
        self._record_stop_btn.setFixedSize(50, 50)
        self._record_stop_btn.setToolTip("録音停止 … 録音を止めてテイクとして保存（F10）")
        self._record_stop_btn.setAccessibleName("録音停止")
        self._record_stop_btn.clicked.connect(self._on_record_stop)
        self._record_stop_btn.setEnabled(False)
        rec_controls_row.addWidget(self._record_stop_btn)
        
        self._recording_label = QLabel("")
        self._recording_label.setObjectName("recordingLabel")
        self._recording_label.setMinimumWidth(80)
        rec_controls_row.addWidget(self._recording_label)
        
        # クイックアクションボタン: 録音→再生
        self._record_and_play_btn = QPushButton("録音→再生")
        self._record_and_play_btn.setToolTip("録音停止後、自動的に再生を開始")
        self._record_and_play_btn.setEnabled(False)
        self._record_and_play_btn.clicked.connect(self._on_record_and_play)
        rec_controls_row.addWidget(self._record_and_play_btn)
        
        rec_controls_row.addStretch()
        rec_group.addLayout(rec_controls_row)
        control_layout.addLayout(rec_group)

        # 中央: 波形表示（録音・再生を切り替え表示）
        waveform_group = QVBoxLayout()
        waveform_group.setSpacing(4)
        waveform_header = QHBoxLayout()
        waveform_label = QLabel("波形")
        waveform_label.setObjectName("heading")
        waveform_header.addWidget(waveform_label)
        self._waveform_zoom_out_btn = QPushButton("−")
        self._waveform_zoom_out_btn.setToolTip("ズームアウト（時間軸を広く）")
        self._waveform_zoom_out_btn.setFixedWidth(28)
        self._waveform_zoom_out_btn.clicked.connect(self._on_waveform_zoom_out)
        waveform_header.addWidget(self._waveform_zoom_out_btn)
        self._waveform_zoom_in_btn = QPushButton("＋")
        self._waveform_zoom_in_btn.setToolTip("ズームイン（時間軸を拡大）")
        self._waveform_zoom_in_btn.setFixedWidth(28)
        self._waveform_zoom_in_btn.clicked.connect(self._on_waveform_zoom_in)
        waveform_header.addWidget(self._waveform_zoom_in_btn)
        waveform_header.addStretch()
        waveform_group.addLayout(waveform_header)
        
        # 録音波形と再生波形を統合表示（StackedWidgetで切り替え）
        self._waveform_stack = QStackedWidget()
        self._record_waveform = WaveformWidget()
        self._record_waveform.set_design_id(get_waveform_design())
        self._playback_waveform = WaveformWidget()
        self._playback_waveform.set_design_id(get_waveform_design())
        self._playback_waveform.set_seekable(True)
        self._playback_waveform.seekRequested.connect(self._on_playback_seek_requested)
        self._waveform_stack.addWidget(self._record_waveform)
        self._waveform_stack.addWidget(self._playback_waveform)
        self._waveform_stack.setCurrentIndex(0)  # 初期は録音波形
        waveform_group.addWidget(self._waveform_stack)
        control_layout.addLayout(waveform_group, 2)  # 中央を広めに

        # 右側: 再生コントロール
        play_group = QVBoxLayout()
        play_group.setSpacing(8)
        play_header = QHBoxLayout()
        play_header.addWidget(QLabel("再生"))
        play_header.addStretch()
        play_group.addLayout(play_header)
        
        play_controls_row = QHBoxLayout()
        play_controls_row.setSpacing(8)
        self._play_pause_btn = QPushButton("▶")
        self._play_pause_btn.setObjectName("playPauseBtn")
        self._play_pause_btn.setFixedSize(50, 50)
        self._play_pause_btn.setToolTip("再生 … 選択したテイクを再生（Space）")
        self._play_pause_btn.clicked.connect(self._on_play_pause_toggle)
        play_controls_row.addWidget(self._play_pause_btn)
        
        self._play_stop_btn = QPushButton("■")
        self._play_stop_btn.setObjectName("playStopBtn")
        self._play_stop_btn.setFixedSize(50, 50)
        self._play_stop_btn.setToolTip("停止 … 再生を停止")
        self._play_stop_btn.clicked.connect(self._on_playback_stop)
        self._play_stop_btn.setEnabled(False)
        play_controls_row.addWidget(self._play_stop_btn)
        
        play_controls_row.addWidget(QLabel("速度:"))
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.5x", "1.0x", "1.25x", "1.5x"])
        self._speed_combo.setCurrentIndex(1)
        self._speed_combo.setToolTip("再生速度 … 0.5x〜1.5x")
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        play_controls_row.addWidget(self._speed_combo)
        
        self._playback_time_label = QLabel("0:00 / 0:00")
        self._playback_time_label.setToolTip("現在時刻 / 総時間")
        self._playback_time_label.setMinimumWidth(100)
        play_controls_row.addWidget(self._playback_time_label)
        play_controls_row.addStretch()
        play_group.addLayout(play_controls_row)
        control_layout.addLayout(play_group)

        # メインコンテナ: スプリッター + 統合コントロール
        main_container = QWidget()
        main_container_layout = QVBoxLayout(main_container)
        main_container_layout.setContentsMargins(0, 0, 0, 0)
        main_container_layout.setSpacing(0)
        main_container_layout.addWidget(self._main_splitter, 1)
        main_container_layout.addWidget(control_frame)

        self._stacked.addWidget(main_container)

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

        # ステータスバー（左: メッセージ、右: 録音時間・再生時間・ショートカット常時表示）
        self.statusBar().showMessage("新規プロジェクトまたはプロジェクトを開いてから、台本を入力・録音できます。")
        
        # 台本位置表示（行・シーン）
        self._status_script_position = QLabel("")
        self._status_script_position.setObjectName("statusScriptPosition")
        self._status_script_position.setMinimumWidth(120)
        self.statusBar().addPermanentWidget(self._status_script_position)
        
        # 録音時間表示
        self._status_recording_time = QLabel("")
        self._status_recording_time.setObjectName("statusRecordingTime")
        self._status_recording_time.setMinimumWidth(80)
        self.statusBar().addPermanentWidget(self._status_recording_time)
        
        # 再生時間表示
        self._status_playback_time = QLabel("")
        self._status_playback_time.setObjectName("statusPlaybackTime")
        self._status_playback_time.setMinimumWidth(100)
        self.statusBar().addPermanentWidget(self._status_playback_time)
        
        # ショートカット表示
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
        
        # 初期モードに応じてプレビューエリアの表示状態を設定
        initial_mode = get_recording_mode()
        self._current_line_preview_frame.setVisible(initial_mode == "individual")
        if initial_mode == "individual":
            self._update_current_line_preview()
        
        # 初期表示時に現在行をハイライト・ステータス行/シーンを更新
        QTimer.singleShot(100, lambda: (self._highlight_current_line(), self._update_status_script_position()))

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
                    if isinstance(d, dict):
                        name = d.get("name", str(d))
                    else:
                        name = getattr(d, "name", str(d))
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

    def _on_recording_mode_changed(self, index: int) -> None:
        mode = self._record_mode_combo.itemData(index)
        set_recording_mode(mode)
        
        # 個別モード時は現在行プレビューを表示、一括モード時は非表示
        is_individual = mode == "individual"
        self._current_line_preview_frame.setVisible(is_individual)
        if is_individual:
            self._update_current_line_preview()
        
        if self.statusBar():
            mode_name = self._record_mode_combo.currentText()
            self.statusBar().showMessage(f"録音モードを「{mode_name}」に変更しました。", 3000)

    def _on_output_device_changed(self, index: int) -> None:
        device = self._output_device_combo.itemData(index)
        if device is not None:
            id_str = self._audio_device_id_string(device)
            set_output_device_id(id_str if id_str else None)
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
        editor_text = self._script_edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        project_text = (self._project.script_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if self._project.has_project_dir() and editor_text != project_text:
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
                self._project.script_text = self._script_edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        set_main_window_geometry(bytes(self.saveGeometry()))
        if self._project.has_project_dir():
            set_last_session_project_path(self._project.project_dir)
        else:
            set_last_session_project_path(None)
        sizes = self._main_splitter.sizes()
        if len(sizes) == 2:
            set_main_window_splitter_sizes(sizes)
        super().closeEvent(event)

    def _setup_shortcuts(self) -> None:
        """録音 F9/Ctrl+R/R・停止 F10。再生 Space/P・左右シーク。テイク一覧でDelete削除・Enter再生。Ctrl+矢印でテイク移動。"""
        QShortcut(QKeySequence("F9"), self, self._on_record_toggle)
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_record_toggle)
        QShortcut(QKeySequence(Qt.Key.Key_R), self, self._on_record_toggle)  # Rキーで録音開始/停止
        QShortcut(QKeySequence("F10"), self, self._on_record_stop)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, self._on_record_stop)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._on_play_pause_toggle)
        QShortcut(QKeySequence(Qt.Key.Key_P), self, self._on_play_pause_toggle)  # Pキーで再生/一時停止
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._on_seek_backward)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._on_seek_forward)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self._take_list, self._on_take_list_delete_key)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self._take_list, self._on_take_list_enter_play)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self._take_list, self._on_take_list_enter_play)
        # Ctrl+矢印でテイク一覧の移動
        QShortcut(QKeySequence("Ctrl+Right"), self, self._on_take_list_next)
        QShortcut(QKeySequence("Ctrl+Left"), self, self._on_take_list_prev)
        # 検索・置換はメニュー経由で _on_find / _on_replace_dialog が呼ばれる（Ctrl+F / Ctrl+H）

    def _format_duration(self, seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def _on_recording_tick(self) -> None:
        """録音中タイマー: 経過時間表示と波形更新。"""
        sec = self._recorder.get_buffer_duration_seconds()
        duration_str = self._format_duration(sec)
        self._recording_label.setText(duration_str)
        # ステータスバーに REC ● 経過時間 を常時表示（視覚的フィードバック）
        if hasattr(self, '_status_recording_time'):
            self._status_recording_time.setText(f"REC ● {duration_str}")
        if self.statusBar():
            self.statusBar().showMessage(f"録音中 {duration_str}")
        samples = self._recorder.get_visualization_samples(max_seconds=10.0)
        self._record_waveform.set_samples(samples)
        self._record_waveform.set_position_seconds(None)
        self._record_waveform.set_duration_seconds(0.0)
        # 録音中は録音波形を表示
        if hasattr(self, '_waveform_stack'):
            self._waveform_stack.setCurrentIndex(0)

    def _update_ui_state(self) -> None:
        has_project = self._project.has_project_dir()
        rec = self._recorder.is_recording
        paused = self._recorder.is_paused
        # 録音トグル: 未録音＝赤丸(開始)、録音中＝一時停止、一時停止中＝赤丸(再開)
        self._record_toggle_btn.setEnabled(has_project)
        if not rec:
            self._record_toggle_btn.setText("●")
            self._record_toggle_btn.setToolTip("録音開始 … 録音を開始（F9）")
            # 録音停止時は点滅を停止
            self._recording_blink_timer.stop()
            self._record_toggle_btn.setStyleSheet("")  # スタイルをリセット
        elif paused:
            self._record_toggle_btn.setText("●")
            self._record_toggle_btn.setToolTip("録音再開 … 一時停止から再開")
            self._recording_blink_timer.stop()
            self._record_toggle_btn.setStyleSheet("")  # スタイルをリセット
        else:
            self._record_toggle_btn.setText("‖")
            self._record_toggle_btn.setToolTip("一時停止 … 録音を一時停止")
            # 録音中は点滅を開始
            if not self._recording_blink_timer.isActive():
                self._recording_blink_state = True
                self._recording_blink_timer.start(500)  # 500ms間隔で点滅
                self._on_recording_blink_tick()  # 即座に実行
        self._record_stop_btn.setEnabled(rec)
        # 録音→再生ボタンの有効/無効を更新
        if hasattr(self, '_record_and_play_btn'):
            self._record_and_play_btn.setEnabled(rec)
        if rec:
            if not self._recording_timer.isActive():
                self._recording_timer.start(100)
            # 録音中は録音波形を表示
            if hasattr(self, '_waveform_stack'):
                self._waveform_stack.setCurrentIndex(0)
        else:
            self._recording_timer.stop()
            self._recording_label.setText("")
            # 録音停止時はステータスバーの録音時間をクリア
            if hasattr(self, '_status_recording_time'):
                self._status_recording_time.setText("")
        # 再生トグル: 停止中＝▶、再生中＝‖、一時停止中＝▶
        has_takes = len(self._project.takes) > 0
        if self._playback.is_playing:
            self._play_pause_btn.setText("‖")
            self._play_pause_btn.setToolTip("一時停止 … 再生を一時停止")
            self._play_pause_btn.setEnabled(True)
            # 再生中はハイライト表示
            self._play_pause_btn.setStyleSheet("""
                QPushButton#playPauseBtn {
                    background-color: rgba(0, 150, 255, 0.3);
                    border: 2px solid rgba(0, 150, 255, 0.8);
                }
            """)
            # 再生中は再生波形を表示
            if hasattr(self, '_waveform_stack'):
                self._waveform_stack.setCurrentIndex(1)
        else:
            self._play_pause_btn.setText("▶")
            self._play_pause_btn.setToolTip("再生 … 選択したテイクを再生")
            self._play_pause_btn.setEnabled(has_project and has_takes)
            # 再生停止時はハイライトを解除
            self._play_pause_btn.setStyleSheet("")
            # 再生停止時、録音中でなければ録音波形を表示
            if hasattr(self, '_waveform_stack') and not rec:
                self._waveform_stack.setCurrentIndex(0)
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

    def _on_recording_blink_tick(self) -> None:
        """録音ボタンの点滅アニメーション。"""
        if not self._recorder.is_recording or self._recorder.is_paused:
            return
        self._recording_blink_state = not self._recording_blink_state
        if self._recording_blink_state:
            # 点滅ON: 赤色のハイライト
            self._record_toggle_btn.setStyleSheet("""
                QPushButton#recordToggleBtn {
                    background-color: rgba(255, 0, 0, 0.4);
                    border: 2px solid rgba(255, 0, 0, 0.9);
                }
            """)
        else:
            # 点滅OFF: 通常表示
            self._record_toggle_btn.setStyleSheet("""
                QPushButton#recordToggleBtn {
                    background-color: rgba(255, 0, 0, 0.2);
                    border: 2px solid rgba(255, 0, 0, 0.6);
                }
            """)

    def _on_take_filter_sort_changed(self) -> None:
        """テイク一覧のフィルタ・ソート変更時に設定を保存して一覧を再描画。"""
        filter_val = self._take_filter_combo.currentData()
        sort_val = self._take_sort_combo.currentData()
        if filter_val:
            set_take_list_filter(filter_val)
        if sort_val:
            set_take_list_sort(sort_val)
        self._refresh_take_list()

    def _get_filtered_sorted_takes(self) -> list[TakeInfo]:
        """現在のフィルタ・ソート設定に従ってテイクのリストを返す。"""
        from datetime import datetime
        takes = list(self._project.takes)
        filter_val = get_take_list_filter()
        if filter_val == "favorite":
            takes = [t for t in takes if t.favorite]
        elif filter_val == "adopted":
            takes = [t for t in takes if t.adopted]
        sort_val = get_take_list_sort()
        def sort_key(t: TakeInfo):
            try:
                dt = datetime.fromisoformat(t.created_at.replace("Z", "+00:00"))
                ts = dt.timestamp()
            except (ValueError, TypeError):
                ts = 0.0
            if sort_val == "date_desc":
                return (-ts, 0)
            if sort_val == "date_asc":
                return (ts, 0)
            if sort_val == "favorite_first":
                return (0 if t.favorite else 1, -ts)
            if sort_val == "adopted_first":
                return (0 if t.adopted else 1, -ts)
            return (-ts, 0)
        takes.sort(key=sort_key)
        return takes

    def _refresh_take_list(self) -> None:
        prev_current_id = None
        prev_selected_ids: set[str] = set()
        cur = self._take_list.currentItem()
        if cur:
            prev_current_id = cur.data(Qt.ItemDataRole.UserRole)
        for i in range(self._take_list.count()):
            it = self._take_list.item(i)
            if it and it.isSelected():
                tid = it.data(Qt.ItemDataRole.UserRole)
                if tid:
                    prev_selected_ids.add(tid)

        self._take_list.clear()
        takes_to_show = self._get_filtered_sorted_takes()
        for i, t in enumerate(takes_to_show):
            fav = "★ " if t.favorite else ""
            new_badge = "🆕 " if t.id in self._new_take_ids else ""
            adopted = "  [採用]" if t.adopted else ""
            dur_sec = storage.get_wav_duration_seconds(self._project.project_dir, t.wav_filename)
            dur_str = f"  {self._format_duration(dur_sec)}" if dur_sec > 0 else ""
            line = f"{new_badge}{fav}{t.display_name(i)}{dur_str}  {t.memo}{adopted}"
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            tooltip_parts = []
            if t.memo:
                tooltip_parts.append(f"メモ: {t.memo}")
            tooltip_parts.append(f"ファイル: {t.wav_filename}")
            if dur_sec > 0:
                tooltip_parts.append(f"長さ: {self._format_duration(dur_sec)}")
            if t.favorite:
                tooltip_parts.append("★ お気に入り")
            if t.adopted:
                tooltip_parts.append("✓ 採用済み")
            item.setToolTip("\n".join(tooltip_parts))
            self._take_list.addItem(item)

        # 以前の選択状態を復元
        restored_current = False
        for i in range(self._take_list.count()):
            it = self._take_list.item(i)
            tid = it.data(Qt.ItemDataRole.UserRole) if it else None
            if tid and tid in prev_selected_ids:
                it.setSelected(True)
            if tid and tid == prev_current_id and not restored_current:
                self._take_list.setCurrentItem(it)
                restored_current = True

        if self._project.takes:
            total = len(self._project.takes)
            shown = len(takes_to_show)
            if shown < total:
                self._take_list_hint.setText(f"{shown}件表示（全{total}件）／ダブルクリックで再生")
            else:
                self._take_list_hint.setText("ダブルクリックで再生／右クリックでメモ・採用・削除")
        else:
            self._take_list_hint.setText("録音開始でテイクが追加されます")
        self._refresh_take_list_highlight()

    def _clear_new_badges(self) -> None:
        """NEWバッジをクリアしてテイク一覧を再描画。"""
        self._new_take_ids.clear()
        self._refresh_take_list()

    def _refresh_take_list_highlight(self) -> None:
        """再生中・選択中のテイク行をハイライト。再生中 > 選択中 > 通常 の優先度。"""
        dark = get_theme() == "dark"
        base = QColor(CARD_BG_DARK) if dark else self._take_list.palette().base()
        playing_color = QColor(TAKE_LIST_HIGHLIGHT_DARK) if dark else QColor(TAKE_LIST_HIGHLIGHT_LIGHT)
        selected_color = QColor(TAKE_LIST_SELECTED_DARK) if dark else QColor(TAKE_LIST_SELECTED_LIGHT)
        for i in range(self._take_list.count()):
            item = self._take_list.item(i)
            take_id = item.data(Qt.ItemDataRole.UserRole)
            if take_id == self._playing_take_id:
                item.setBackground(playing_color)
            elif item.isSelected():
                item.setBackground(selected_color)
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
        self._script_container.line_number_area().setFont(f)

    def _on_script_font_size_changed(self, value: int) -> None:
        set_script_font_size(value)
        self._apply_script_font_size(value)

    def _highlight_current_line(self) -> None:
        """
        現在のカーソル行と、選択中テイクに対応する台本行をハイライト表示する。
        """
        try:
            from PyQt6.QtGui import QColor
            from PyQt6.QtWidgets import QPlainTextEdit
            dark = get_theme() == "dark"
            selections: list[QPlainTextEdit.ExtraSelection] = []

            # 1. 現在のカーソル行をハイライト
            cursor = self._script_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.StartOfLine)
            cursor.movePosition(cursor.MoveOperation.EndOfLine, cursor.MoveMode.KeepAnchor)
            extra = QPlainTextEdit.ExtraSelection()
            extra.cursor = cursor
            if dark:
                extra.format.setBackground(QColor(30, 144, 255))
                extra.format.setForeground(QColor(255, 255, 255))
            else:
                extra.format.setBackground(QColor(173, 216, 230))
                extra.format.setForeground(QColor(0, 0, 0))
            extra.format.setFontWeight(600)
            selections.append(extra)

            # 2. 選択中テイクの script_line_number に対応する行を別色で強調（紐付けがある場合）
            cur_item = self._take_list.currentItem()
            if cur_item:
                take_id = cur_item.data(Qt.ItemDataRole.UserRole)
                t = self._project.get_take(take_id) if take_id else None
                if t and t.script_line_number is not None and t.script_line_number >= 1:
                    doc = self._script_edit.document()
                    block = doc.findBlockByLineNumber(t.script_line_number - 1)
                    if block.isValid():
                        tc = self._script_edit.textCursor()
                        tc.setPosition(block.position())
                        tc.movePosition(tc.MoveOperation.EndOfLine, tc.MoveMode.KeepAnchor)
                        extra_take = QPlainTextEdit.ExtraSelection()
                        extra_take.cursor = tc
                        if dark:
                            extra_take.format.setBackground(QColor(70, 130, 70))  # 暗めの緑
                            extra_take.format.setForeground(QColor(220, 220, 220))
                        else:
                            extra_take.format.setBackground(QColor(200, 230, 200))  # 薄い緑
                            extra_take.format.setForeground(QColor(0, 0, 0))
                        selections.append(extra_take)

            self._script_edit.setExtraSelections(selections)
        except Exception:
            try:
                self._script_edit.setExtraSelections([])
            except Exception:
                pass

    def _update_status_script_position(self) -> None:
        """ステータスバーに現在行とシーンを表示する。"""
        script_text = self._script_edit.toPlainText()
        cursor_pos = self._script_edit.textCursor().position()
        line_no = get_current_line_number(script_text, cursor_pos)
        section = get_current_section(script_text, cursor_pos)
        line_str = str(line_no) if line_no else "—"
        section_str = section if section else "—"
        self._status_script_position.setText(f"行 {line_str} | シーン: {section_str}")

    def _update_current_line_preview(self) -> None:
        """
        個別モード時: 現在のカーソル行のセリフをプレビューエリアに表示する。
        """
        if get_recording_mode() != "individual":
            return
        
        script_text = self._script_edit.toPlainText()
        cursor_pos = self._script_edit.textCursor().position()
        line_text = get_current_line_text(script_text, cursor_pos)
        
        if line_text:
            self._current_line_preview.setPlainText(line_text)
        else:
            self._current_line_preview.setPlainText("")

    def _move_to_next_line(self) -> None:
        """
        VoiceActorStudioのロジックを参考: 次の行へカーソルを移動する。
        個別モード時の自動次行遷移に使用。
        """
        cursor = self._script_edit.textCursor()
        script_text = self._script_edit.toPlainText()
        current_pos = cursor.position()
        current_line_no = get_current_line_number(script_text, current_pos)
        lines = script_text.splitlines()
        
        # 次の行へ移動（見出し行はスキップ）
        next_line_no = current_line_no
        while next_line_no < len(lines):
            next_line_no += 1
            if next_line_no > len(lines):
                break
            line_text = lines[next_line_no - 1].strip()
            # 見出し行でなければ移動
            if line_text and not line_text.startswith("#"):
                # 次の行の先頭に移動
                pos = 0
                for i in range(next_line_no - 1):
                    pos += len(lines[i]) + 1
                cursor.setPosition(pos)
                self._script_edit.setTextCursor(cursor)
                self._script_edit.ensureCursorVisible()
                break

    def _select_and_scroll_to_take(self, take_id: str) -> None:
        """
        指定されたテイクIDのテイクを選択してスクロール表示する。
        録音終了後の自動選択に使用。
        """
        for i in range(self._take_list.count()):
            item = self._take_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == take_id:
                self._take_list.setCurrentRow(i)
                self._take_list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
                # 一時的にハイライト表示（NEWバッジの代わり）
                item.setSelected(True)
                break

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

    def _restore_last_session(self) -> None:
        """起動時に前回開いていたプロジェクト・台本を復元する。"""
        path = get_last_session_project_path()
        if not path or not Path(path).is_dir():
            return
        proj = storage.load_project(path)
        if proj is None:
            QMessageBox.warning(self, "プロジェクトを開けませんでした", "前回開いていたプロジェクトを読み込めませんでした。")
            return
        self._project = proj
        self._reset_playback_ui()
        self._script_edit.setPlainText(self._project.script_text)
        self._refresh_take_list()
        self._update_ui_state()
        self._switch_to_main_view()
        self.statusBar().showMessage(f"前回のセッションを復元: {self._project.project_dir}")
        add_recent_project(path)
        self._update_recent_menu()

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
        self._update_window_title()

    def _update_window_title(self) -> None:
        """ウィンドウタイトルにプロジェクト名と未保存表示を反映する。"""
        base = "Voice Actor Laboratory"
        if self._project.has_project_dir():
            base += " - " + Path(self._project.project_dir).name
            editor_text = self._script_edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
            project_text = (self._project.script_text or "").replace("\r\n", "\n").replace("\r", "\n")
            if editor_text != project_text:
                base += " *"
        self.setWindowTitle(base)

    def _on_restart_app(self) -> None:
        """ヘルプ「アプリを再起動」: 新しいプロセスを起動してから終了する。"""
        if QMessageBox.question(
            self,
            "アプリを再起動",
            "アプリケーションを再起動しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        argv = [sys.executable] + sys.argv
        try:
            cwd = Path(__file__).resolve().parent.parent.parent
            subprocess.Popen(argv, cwd=cwd)
        except Exception as e:
            QMessageBox.warning(self, "再起動エラー", f"再起動に失敗しました: {e}")
            return
        QApplication.quit()

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
            "※ 録音モード「台本一括」は見出しごとに連番、「セリフ個別」はカーソル行のセリフをファイル名に使います。\n"
            "※ 既存のプロジェクトは「開く」または「最近開いたプロジェクト」から。"
        )
        QMessageBox.information(self, "使い方", text)

    def _on_show_shortcuts(self) -> None:
        """ヘルプ「キーボードショートカット」ダイアログを表示する。"""
        text = (
            "【録音】\n"
            "F9 / Ctrl+R / R … 録音開始・一時停止の切り替え\n"
            "F10 / Ctrl+Shift+R … 録音停止（テイクとして保存）\n\n"
            "【再生】\n"
            "Space / P … 再生・一時停止の切り替え\n"
            "← / → … 5秒戻る・進む（シーク）\n\n"
            "【テイク一覧】（フォーカスがあるとき）\n"
            "ダブルクリック / Enter … 選択テイクを再生\n"
            "Delete … 選択テイクを削除\n"
            "Ctrl+→ … 次のテイクに移動\n"
            "Ctrl+← … 前のテイクに移動\n\n"
            "【編集】\n"
            "Ctrl+F … 検索\n"
            "Ctrl+H … 置換\n\n"
            "【その他】\n"
            "Esc … ダイアログを閉じる"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("キーボードショートカット")
        layout = QVBoxLayout(dlg)
        te = QPlainTextEdit()
        te.setPlainText(text)
        te.setReadOnly(True)
        te.setMinimumSize(400, 320)
        layout.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(dlg.accept)
        layout.addWidget(bb)
        dlg.exec()

    def _on_new_project(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "新規プロジェクトの保存先を選択", directory=get_last_project_dialog_dir() or ""
        )
        if not path:
            return
        set_last_project_dialog_dir(path)
        try:
            self._project = storage.create_project(path)
            storage.save_script(path, DEFAULT_SCRIPT_TEMPLATE)
        except OSError as e:
            QMessageBox.warning(self, "エラー", f"プロジェクトフォルダを作成できませんでした: {e}")
            return
        self._reset_playback_ui()
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
        path = QFileDialog.getExistingDirectory(
            self, "プロジェクトフォルダを選択", directory=get_last_project_dialog_dir() or ""
        )
        if not path:
            return
        set_last_project_dialog_dir(path)
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
        """指定パスのテキストを台本として読み込む。ドロップ・メニュー「台本を開く」の共通処理。UTF-8/CP932等にフォールバック。"""
        try:
            text = storage.decode_script_bytes(Path(path).read_bytes())
        except UnicodeDecodeError as e:
            QMessageBox.warning(self, "エラー", "台本ファイルの文字コードを認識できませんでした。UTF-8 または CP932 で保存し直してください。")
            return
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"台本を読み込めませんでした: {e}")
            return
        self._project.set_script(path, text)
        self._script_edit.setPlainText(text)
        if self._project.has_project_dir():
            storage.save_script(self._project.project_dir, text)
        # 台本読み込み後にハイライト・ステータスを更新
        QTimer.singleShot(100, lambda: (self._highlight_current_line(), self._update_status_script_position()))
        if self.statusBar():
            self.statusBar().showMessage(f"台本を読み込みました: {path}")

    def _on_open_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "台本を開く", get_last_script_dialog_dir() or "", "台本ファイル (*.txt *.md);;テキスト (*.txt);;マークダウン (*.md);;すべて (*)"
        )
        if path:
            set_last_script_dialog_dir(str(Path(path).parent))
            self._load_script_from_path(path)

    def _on_new_script(self) -> None:
        """台本エリアに入力例（テンプレート）を表示する。プロジェクト打開時は保存も行う。"""
        self._script_edit.setPlainText(DEFAULT_SCRIPT_TEMPLATE)
        self._project.script_text = DEFAULT_SCRIPT_TEMPLATE
        # 台本設定後にハイライト・ステータスを更新
        QTimer.singleShot(100, lambda: (self._highlight_current_line(), self._update_status_script_position()))
        if self._project.has_project_dir():
            storage.save_script(self._project.project_dir, DEFAULT_SCRIPT_TEMPLATE)
            self.statusBar().showMessage("台本を入力例で置き換え、保存しました。")
        else:
            self.statusBar().showMessage("入力例を表示しました。プロジェクトを開いた状態で「台本を保存」で保存できます。")

    def _on_find(self) -> None:
        """検索ダイアログを表示する（Ctrl+F）。"""
        d = FindReplaceDialog(self, self._script_edit, replace_mode=False)
        d.show()

    def _on_replace_dialog(self) -> None:
        """置換ダイアログを表示する（Ctrl+H）。"""
        d = FindReplaceDialog(self, self._script_edit, replace_mode=True)
        d.show()

    def _on_save_script(self) -> None:
        """UIで編集中の台本をプロジェクトに保存する。プロジェクト未打開の場合は新規作成を促す。"""
        text = self._script_edit.toPlainText()
        if self._project.has_project_dir():
            storage.save_script(self._project.project_dir, text)
            self._project.script_text = text
            self._update_window_title()
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
        editor_text = self._script_edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        project_text = (self._project.script_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if editor_text != project_text and self.statusBar():
            self.statusBar().showMessage("台本に未保存の変更があります。必要に応じて保存してから録音してください。", 5000)
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
                
                mode = get_recording_mode()
                preferred_basename = suggest_take_basename(script_text, cursor_pos, existing, mode=mode)
                
                memo = ""
                script_line_number = None
                if mode == "individual":
                    line_text = get_current_line_text(script_text, cursor_pos)
                    if line_text:
                        memo = line_text
                    script_line_number = get_current_line_number(script_text, cursor_pos)

                try:
                    take = storage.add_take_from_file(
                        self._project.project_dir,
                        tmp,
                        memo=memo,
                        favorite=False,
                        preferred_basename=preferred_basename,
                        script_line_number=script_line_number,
                    )
                except OSError as e:
                    QMessageBox.warning(self, "録音", f"テイクの保存に失敗しました: {e}")
                    return
                self._project.add_take(take)
                self._refresh_take_list()
                take_added = True
                self._last_added_take_id = take.id  # 追加されたテイクIDを保存
                
                # 録音終了時は台本のカーソル位置をそのまま維持（自動進めない）
        finally:
            Path(tmp).unlink(missing_ok=True)
        self._recording_timer.stop()
        self._record_waveform.set_samples(np.array([], dtype=np.float32))
        self._update_ui_state()
        
        # 録音終了後、追加されたテイクを自動選択・スクロール表示
        if take_added and hasattr(self, '_last_added_take_id') and self._last_added_take_id:
            # NEWバッジを追加（5秒間表示）
            self._new_take_ids.add(self._last_added_take_id)
            self._refresh_take_list()
            # 5秒後にNEWバッジを自動削除
            self._new_take_timer.stop()
            self._new_take_timer.start(5000)
            QTimer.singleShot(50, lambda: self._select_and_scroll_to_take(self._last_added_take_id))
            
            # 自動再生オプションが有効な場合、録音終了後に自動再生
            if get_auto_play_after_record():
                QTimer.singleShot(200, self._auto_play_last_take)
        
        if self.statusBar():
            if take_added:
                self.statusBar().showMessage("1テイクを追加しました")
            else:
                self.statusBar().showMessage(self._project.project_dir or "準備完了")

    def _auto_play_last_take(self) -> None:
        """最後に追加されたテイクを自動再生する。"""
        if self._last_added_take_id:
            for i in range(self._take_list.count()):
                item = self._take_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == self._last_added_take_id:
                    self._on_take_double_clicked(item)
                    break

    def _on_record_and_play(self) -> None:
        """録音→再生ボタン: 録音停止後、自動的に再生を開始。"""
        if not self._recorder.is_recording:
            return
        # 録音停止を実行し、自動再生フラグを一時的に有効化
        was_auto_play = get_auto_play_after_record()
        set_auto_play_after_record(True)
        self._on_record_stop()
        # 元の設定に戻す
        set_auto_play_after_record(was_auto_play)

    def _on_take_list_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        """テイク一覧の選択変更時、紐付いた台本行へスクロールし、ハイライトを更新する。"""
        if current is None:
            return
        take_id = current.data(Qt.ItemDataRole.UserRole)
        t = self._project.get_take(take_id) if take_id else None
        if t and t.script_line_number is not None:
            self._scroll_script_to_line(t.script_line_number)
        self._highlight_current_line()

    def _scroll_script_to_line(self, line_number: int | None) -> None:
        """台本エリアを指定行（1-based）にスクロールし、カーソルを移動する。"""
        if line_number is None or line_number < 1:
            return
        doc = self._script_edit.document()
        block = doc.findBlockByLineNumber(line_number - 1)  # 0-based
        if block.isValid():
            cursor = self._script_edit.textCursor()
            cursor.setPosition(block.position())
            self._script_edit.setTextCursor(cursor)
            self._script_edit.ensureCursorVisible()

    def _play_take_by_id(self, take_id: str) -> None:
        """テイクIDを指定して再生を開始する（A/B比較などで使用）。"""
        t = self._project.get_take(take_id)
        if t is None:
            return
        wav_path = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
        self._playing_take_id = take_id
        self._loaded_take_id = take_id
        self._load_playback_waveform(wav_path)
        self._playback.play(wav_path)
        self._playback_position_timer.start(80)
        if hasattr(self, '_waveform_stack'):
            self._waveform_stack.setCurrentIndex(1)
        if t.script_line_number is not None:
            self._scroll_script_to_line(t.script_line_number)
        self._update_ui_state()

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
        if hasattr(self, '_waveform_stack'):
            self._waveform_stack.setCurrentIndex(1)
        if t.script_line_number is not None:
            self._scroll_script_to_line(t.script_line_number)
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

    def _on_waveform_zoom_in(self) -> None:
        """波形の時間軸をズームイン。"""
        r = self._playback_waveform.get_zoom_ratio()
        self._playback_waveform.set_zoom_ratio(r * 1.2)

    def _on_waveform_zoom_out(self) -> None:
        """波形の時間軸をズームアウト。"""
        r = self._playback_waveform.get_zoom_ratio()
        self._playback_waveform.set_zoom_ratio(r / 1.2)

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

    def _on_take_list_next(self) -> None:
        """Ctrl+→: テイク一覧で次のテイクに移動。"""
        current_row = self._take_list.currentRow()
        if current_row < self._take_list.count() - 1:
            self._take_list.setCurrentRow(current_row + 1)
            self._take_list.scrollToItem(self._take_list.item(current_row + 1))

    def _on_take_list_prev(self) -> None:
        """Ctrl+←: テイク一覧で前のテイクに移動。"""
        current_row = self._take_list.currentRow()
        if current_row > 0:
            self._take_list.setCurrentRow(current_row - 1)
            self._take_list.scrollToItem(self._take_list.item(current_row - 1))

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
        self._ab_compare_queue.clear()
        self._playback_waveform.set_position_seconds(None)
        if self._playback_duration_seconds > 0:
            total_str = self._format_duration(self._playback_duration_seconds)
            self._playback_time_label.setText(f"0:00 / {total_str}")
            # ステータスバーの再生時間を更新
            if hasattr(self, '_status_playback_time'):
                self._status_playback_time.setText(f"再生: 0:00 / {total_str}")
        else:
            # 再生時間がない場合はクリア
            if hasattr(self, '_status_playback_time'):
                self._status_playback_time.setText("")
        self._update_ui_state()

    def _on_playback_state_changed(self) -> None:
        now_playing = self._playback.is_playing
        now_stopped = not now_playing and not self._playback.is_paused
        if self._last_playback_was_playing and now_stopped:
            # A/B比較キュー: 今再生していたテイクの次があれば再生
            if self._ab_compare_queue and self._playing_take_id == self._ab_compare_queue[0]:
                self._ab_compare_queue.pop(0)
                if self._ab_compare_queue:
                    next_id = self._ab_compare_queue[0]
                    QTimer.singleShot(300, lambda: self._play_take_by_id(next_id))
                else:
                    if self.statusBar():
                        self.statusBar().showMessage("A/B比較の再生が終わりました")
                self._last_playback_was_playing = False
                self._update_ui_state()
                return
            if self.statusBar():
                self.statusBar().showMessage("再生が終わりました")
        self._last_playback_was_playing = now_playing
        if now_stopped:
            self._playback_position_timer.stop()
            self._playing_take_id = None
            self._playback_waveform.set_position_seconds(None)
        self._update_ui_state()

    def _on_playback_error(self, error: object, error_string: str = "") -> None:
        """再生エラー時にステータスバーで通知する。"""
        msg = error_string or str(error) or "再生に失敗しました"
        if self.statusBar():
            self.statusBar().showMessage(f"再生エラー: {msg}", 8000)

    def _on_playback_position_tick(self) -> None:
        """再生位置を波形に反映し、時刻ラベルを更新。"""
        pos_ms = max(0, self._playback.get_player().position())
        pos_sec = pos_ms / 1000.0
        self._playback_waveform.set_position_seconds(pos_sec)
        if self._playback_duration_seconds > 0:
            total_str = self._format_duration(self._playback_duration_seconds)
            pos_str = self._format_duration(pos_sec)
            self._playback_time_label.setText(f"{pos_str} / {total_str}")
            # ステータスバーに再生中テイク名 + 位置を表示
            if hasattr(self, '_status_playback_time'):
                take_label = ""
                if self._playing_take_id:
                    t = self._project.get_take(self._playing_take_id)
                    if t:
                        idx = next((i for i, x in enumerate(self._project.takes) if x.id == self._playing_take_id), 0)
                        take_label = t.display_name(idx) + " — "
                self._status_playback_time.setText(f"再生中: {take_label}{pos_str} / {total_str}")
        else:
            self._playback_time_label.setText("0:00 / 0:00")
            # 再生時間がない場合はクリア
            if hasattr(self, '_status_playback_time'):
                self._status_playback_time.setText("")

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
            self._playback_waveform.set_zoom_ratio(1.0)
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
        """設定ダイアログを表示し、OK ならテーマ・フォント・波形・録音モード等を反映。"""
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._apply_theme(get_theme())
            self._apply_script_font_size(get_script_font_size())
            mode = get_recording_mode()
            idx = self._record_mode_combo.findData(mode)
            if idx >= 0:
                self._record_mode_combo.setCurrentIndex(idx)
            self._current_line_preview_frame.setVisible(mode == "individual")
            if mode == "individual":
                self._update_current_line_preview()
            design = get_waveform_design()
            self._record_waveform.set_design_id(design)
            self._playback_waveform.set_design_id(design)
            self.statusBar().showMessage("設定を反映しました。", 3000)

    def _on_take_context_menu(self, pos: typing.Any) -> None:
        item = self._take_list.itemAt(pos)
        if not item:
            return
        take_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        # A/B比較: 2件選択時のみ表示
        selected = [
            self._take_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._take_list.count())
            if self._take_list.item(i).isSelected()
        ]
        if len(selected) == 2:
            act_ab = QAction("A/B比較で再生（A→Bの順）", self)
            def start_ab_compare():
                self._ab_compare_queue = list(selected)
                self._play_take_by_id(self._ab_compare_queue[0])
                self.statusBar().showMessage("A/B比較: 2本を順に再生します", 3000)
            act_ab.triggered.connect(start_ab_compare)
            menu.addAction(act_ab)
            menu.addSeparator()
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

        menu.addSeparator()

        # 再生
        act_play = QAction("このテイクを再生    Enter", self)
        act_play.triggered.connect(lambda: self._on_take_double_clicked(item))
        menu.addAction(act_play)

        # リテイク（削除して再録音）
        act_retake = QAction("このテイクをリテイク", self)
        def retake_take():
            if get_confirm_before_delete_take():
                box = QMessageBox(self)
                box.setWindowTitle("確認")
                box.setText("このテイクを削除して再録音しますか？")
                box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                box.setDefaultButton(QMessageBox.StandardButton.Yes)
                if box.exec() != QMessageBox.StandardButton.Yes:
                    return
            if self._playing_take_id == take_id or self._loaded_take_id == take_id:
                self._playback.release_file_lock()
                self._playback_position_timer.stop()
                self._playing_take_id = None
                self._loaded_take_id = None
                self._update_ui_state()
                QTimer.singleShot(100, lambda: self._delete_take_and_start_recording(take_id))
            else:
                if storage.delete_take(self._project.project_dir, take_id):
                    self._project = storage.load_project(self._project.project_dir) or self._project
                    self._refresh_take_list()
                    if not self._recorder.is_recording:
                        self._on_record_toggle()
        act_retake.triggered.connect(retake_take)
        menu.addAction(act_retake)

        menu.addSeparator()

        # 削除
        act_del = QAction("テイクを削除    Del", self)
        def delete_take():
            if get_confirm_before_delete_take():
                box = QMessageBox(self)
                box.setWindowTitle("確認")
                box.setText("このテイクを削除しますか？")
                box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                box.setDefaultButton(QMessageBox.StandardButton.No)
                if box.exec() != QMessageBox.StandardButton.Yes:
                    return
            if self._playing_take_id == take_id or self._loaded_take_id == take_id:
                self._playback.release_file_lock()
                self._playback_position_timer.stop()
                self._playing_take_id = None
                self._loaded_take_id = None
                self._update_ui_state()
                QTimer.singleShot(100, lambda: self._delete_take_after_unlock(take_id))
            else:
                if storage.delete_take(self._project.project_dir, take_id):
                    self._project = storage.load_project(self._project.project_dir) or self._project
                    self._refresh_take_list()
                else:
                    QMessageBox.warning(self, "エラー", "削除に失敗しました。ファイルが使用中かもしれません。")
        act_del.triggered.connect(delete_take)
        menu.addAction(act_del)

        menu.exec(self._take_list.mapToGlobal(pos))

    def _delete_take_and_start_recording(self, take_id: str) -> None:
        """テイクを削除して録音を開始する。"""
        if storage.delete_take(self._project.project_dir, take_id):
            self._project = storage.load_project(self._project.project_dir) or self._project
            self._refresh_take_list()
            # 録音開始
            if not self._recorder.is_recording:
                self._on_record_toggle()

    def _delete_take_after_unlock(self, take_id: str) -> None:
        """ファイルロック解除後にテイクを削除する。"""
        if storage.delete_take(self._project.project_dir, take_id):
            self._project = storage.load_project(self._project.project_dir) or self._project
            self._refresh_take_list()
        else:
            QMessageBox.warning(self, "エラー", "削除に失敗しました。ファイルが使用中かもしれません。")

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
        if get_confirm_before_delete_take():
            box = QMessageBox(self)
            box.setWindowTitle("確認")
            box.setText(msg)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
        # 削除前に再生中のファイルなら停止してロック解除
        needs_unlock = False
        for take_id in take_ids:
            if self._playing_take_id == take_id or self._loaded_take_id == take_id:
                self._playback.release_file_lock()
                self._playback_position_timer.stop()
                self._playing_take_id = None
                self._loaded_take_id = None
                self._update_ui_state()
                needs_unlock = True
                break
        
        if needs_unlock:
            # ファイルロックが解放されるまで少し待ってから削除
            QTimer.singleShot(100, lambda: self._delete_takes_after_unlock(take_ids, n))
        else:
            # 再生中でない場合は即座に削除
            self._delete_takes_after_unlock(take_ids, n)

    def _delete_takes_after_unlock(self, take_ids: list[str], total_count: int) -> None:
        """ファイルロック解除後にテイクを削除する。"""
        ok_count = 0
        for take_id in take_ids:
            if storage.delete_take(self._project.project_dir, take_id):
                ok_count += 1
        if ok_count > 0:
            self._project = storage.load_project(self._project.project_dir) or self._project
            self._refresh_take_list()
        if ok_count < total_count:
            QMessageBox.warning(self, "エラー", f"{total_count - ok_count}件の削除に失敗しました。ファイルが使用中かもしれません。")

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
        favorite_ids = [t.id for t in self._project.takes if t.favorite]
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
        r_favorite = QRadioButton("お気に入りのみ")
        if adopted_ids:
            r_adopted.setEnabled(True)
        else:
            r_adopted.setEnabled(False)
            r_adopted.setToolTip("採用テイクがありません")
        if favorite_ids:
            r_favorite.setEnabled(True)
        else:
            r_favorite.setEnabled(False)
            r_favorite.setToolTip("お気に入りテイクがありません")
        if selected_ids:
            r_selected.setChecked(True)
        elif adopted_ids:
            r_adopted.setChecked(True)
        elif favorite_ids:
            r_favorite.setChecked(True)
        else:
            r_all.setChecked(True)
        grp.addButton(r_all)
        grp.addButton(r_selected)
        grp.addButton(r_adopted)
        grp.addButton(r_favorite)
        layout.addWidget(r_all)
        layout.addWidget(r_selected)
        layout.addWidget(r_adopted)
        layout.addWidget(r_favorite)
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
        elif r_favorite.isChecked() and favorite_ids:
            take_ids = favorite_ids
        else:
            take_ids = [t.id for t in self._project.takes]
        set_export_use_friendly_names(friendly.isChecked())
        dest = QFileDialog.getExistingDirectory(
            self, "エクスポート先を選択", directory=get_export_last_dir() or ""
        )
        if not dest:
            return
        set_export_last_dir(dest)
        try:
            paths = storage.export_takes(
                self._project.project_dir,
                take_ids,
                dest,
                use_friendly_names=friendly.isChecked(),
            )
        except OSError as e:
            QMessageBox.warning(self, "エクスポート", str(e))
            return
        dest_path = str(Path(paths[0]).parent) if paths else ""
        msg = f"{len(paths)} 件をエクスポートしました。" + (f"\n保存先: {dest_path}" if dest_path else "")
        QMessageBox.information(self, "エクスポート", msg)