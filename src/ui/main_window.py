"""
メインウィンドウ。台本エリア・録音ボタン・テイク一覧を表示する。
"""
import math
import shutil
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
    QTextBrowser,
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
    get_preroll_seconds,
    set_preroll_seconds,
    get_level_meter_enabled,
    set_level_meter_enabled,
    get_export_name_template,
    set_export_name_template,
    get_lufs_target,
    set_lufs_target,
    get_auto_analyze_lufs,
    set_auto_analyze_lufs,
    get_mp3_bitrate,
    set_mp3_bitrate,
    get_export_format,
    set_export_format,
    get_export_apply_lufs,
    set_export_apply_lufs,
    get_export_apply_trim_silence,
    set_export_apply_trim_silence,
    get_export_apply_noise_reduce,
    set_export_apply_noise_reduce,
)
from src.ui.waveform_widget import WaveformWidget
from src.ui.settings_dialog import SettingsDialog
from src.ui.find_replace_dialog import FindReplaceDialog
from src.ui.script_edit_with_line_numbers import ScriptEditWithLineNumbers
from src.ui.level_meter import LevelMeterWidget
from src.ui.preroll_overlay import PrerollOverlay
from src.ui.record_button import RecordButton
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


def _amp_to_dbfs_value(amp: float) -> float | None:
    """振幅比（0〜1）を dBFS に変換。無音なら None。

    リアルタイム Peak 数値表示に使用する。下限は -90 dBFS まで。
    """
    try:
        a = float(amp)
    except (TypeError, ValueError):
        return None
    if a <= 1e-5:
        return None
    return 20.0 * math.log10(max(a, 1e-5))


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
        self._syncing_script_cursor: bool = False  # 台本⇄テイク一覧の同期ループガード
        self._last_synced_script_line: int | None = None  # 直近に同期済みのカーソル行
        self._new_take_timer = QTimer(self)  # NEWバッジの自動削除用タイマー
        self._new_take_timer.setSingleShot(True)
        self._new_take_timer.timeout.connect(self._clear_new_badges)
        self._recording_blink_timer = QTimer(self)  # 録音ボタンの点滅用タイマー
        self._recording_blink_state = False  # 録音ボタンの点滅状態
        self._recording_blink_timer.timeout.connect(self._on_recording_blink_tick)
        self._ab_compare_queue: list[str] = []  # A/B比較で連続再生するテイクIDのキュー
        self._level_meter_timer = QTimer(self)  # A1: マイクレベルメーターの更新タイマー
        self._level_meter_timer.timeout.connect(self._on_level_meter_tick)
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
        # A1: レベルメーター開始（初回表示時のみ、設定が ON の場合）
        if get_level_meter_enabled() and not self._level_meter_timer.isActive():
            if self._recorder.start_monitoring():
                self._level_meter_timer.start(50)
            # 録音中は録音ストリーム側が更新するのでタイマのみでもOK
            else:
                self._level_meter_timer.start(50)

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
        # G1: 採用テイクをワンクリックで納品
        act_export_adopted = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton),
            "採用テイクを一括納品",
            self,
        )
        act_export_adopted.setToolTip("採用テイクのみを前回の保存先にワンクリックで書き出します")
        act_export_adopted.triggered.connect(self._on_export_adopted_oneclick)
        toolbar.addAction(act_export_adopted)
        self._act_export_adopted = act_export_adopted
        # 保存フォルダをエクスプローラーで開く
        act_reveal_takes = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DirIcon),
            "保存フォルダを開く",
            self,
        )
        act_reveal_takes.setToolTip("録音したWAVが保存されている takes フォルダをOSのファイルマネージャで開きます")
        act_reveal_takes.triggered.connect(self._on_reveal_takes_folder)
        toolbar.addAction(act_reveal_takes)
        self._act_reveal_takes = act_reveal_takes

        # メニュー
        menubar = self.menuBar()
        file_menu = menubar.addMenu("ファイル")
        file_menu.addAction(act_new)
        file_menu.addAction(act_open)
        file_menu.addAction(act_open_script)
        file_menu.addAction(act_new_script)
        file_menu.addAction(act_save_script)
        file_menu.addAction(act_export)
        file_menu.addAction(act_export_adopted)
        file_menu.addSeparator()
        file_menu.addAction(act_reveal_takes)
        file_menu.addSeparator()
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
        act_glossary = QAction("用語解説（LUFS・dBFSなど）", self)
        act_glossary.setToolTip("アプリ内で使われている音響用語の意味を一覧で表示")
        act_glossary.triggered.connect(self._on_show_glossary)
        help_menu.addAction(act_glossary)
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
        self._font_spin.setRange(8, 24)
        self._font_spin.setValue(get_script_font_size())
        self._font_spin.setToolTip("台本フォントサイズ（8〜24pt）")
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
        self._script_edit.cursorPositionChanged.connect(self._on_script_cursor_line_changed)
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
        # レベルメーター行を足したため固定高は廃止し、最小高のみ指定
        control_frame.setMinimumHeight(200)
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
        
        self._record_toggle_btn = RecordButton()
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
        # A1: マイク入力レベルメーター
        meter_row = QHBoxLayout()
        meter_row.setSpacing(6)
        meter_label = QLabel("入力:")
        meter_label.setObjectName("caption")
        meter_row.addWidget(meter_label)
        self._level_meter = LevelMeterWidget()
        self._level_meter.setVisible(get_level_meter_enabled())
        self._level_meter.setMinimumWidth(160)
        meter_row.addWidget(self._level_meter, 1)
        # リアルタイム数値表示: Peak dBFS / 直近3秒の LUFS
        self._live_lufs_label = QLabel("Peak —.— dBFS   ST —.— LUFS")
        self._live_lufs_label.setObjectName("liveLufsLabel")
        self._live_lufs_label.setToolTip(
            "Peak: 直近ブロックの最大値（0 dBFS 超で歪み）\n"
            "ST: 直近 3 秒の BS.1770 ラウドネス。目標値の目安 -16 LUFS"
        )
        self._live_lufs_label.setMinimumWidth(220)
        self._live_lufs_label.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        self._live_lufs_label.setVisible(get_level_meter_enabled())
        meter_row.addWidget(self._live_lufs_label, 0)
        # LUFS は負荷軽減のため、レベルメーターの毎回tickではなく4tickに1回だけ更新する
        self._live_lufs_tick_counter = 0
        rec_group.addLayout(meter_row)
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
        # A2: プリロールカウントダウンオーバーレイ（Central Widget の上に被せる）
        self._preroll_overlay = PrerollOverlay(root)

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
        # A1: モニターが走っていればデバイス変更後に再起動
        if get_level_meter_enabled() and not self._recorder.is_recording:
            self._recorder.stop_monitoring()
            self._recorder.start_monitoring()

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
            box.button(QMessageBox.StandardButton.Save).setText("保存する")
            box.button(QMessageBox.StandardButton.Discard).setText("破棄して終了")
            box.button(QMessageBox.StandardButton.Cancel).setText("キャンセル")
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
        # A1: 終了時にレベルメーターとモニターストリームを停止
        try:
            self._level_meter_timer.stop()
            self._recorder.stop_monitoring()
        except Exception:
            pass
        super().closeEvent(event)

    def _setup_shortcuts(self) -> None:
        """録音 F9/Ctrl+R・停止 F10。再生 Space/P・左右シーク。テイク一覧で Delete 削除・Enter 再生。

        F1 修正: 単一キー（R/P/Space/矢印）は台本エディタにフォーカスがある時は発火させない
        （``_should_handle_single_key_shortcut`` のガードで弾く）。F9/F10/Ctrl+R 等は常時有効。
        """
        # 常時有効（ファンクションキー・Ctrl 修飾あり）
        QShortcut(QKeySequence("F9"), self, self._on_record_toggle)
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_record_toggle)
        QShortcut(QKeySequence("F10"), self, self._on_record_stop)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, self._on_record_stop)
        # Ctrl+矢印でテイク一覧の移動（常時）
        QShortcut(QKeySequence("Ctrl+Right"), self, self._on_take_list_next)
        QShortcut(QKeySequence("Ctrl+Left"), self, self._on_take_list_prev)
        # 単一キー系は台本編集中は無効化するためのガード付きで登録
        QShortcut(QKeySequence(Qt.Key.Key_R), self, self._sk_record_toggle)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._sk_play_pause_toggle)
        QShortcut(QKeySequence(Qt.Key.Key_P), self, self._sk_play_pause_toggle)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, self._sk_seek_backward)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, self._sk_seek_forward)
        # テイク一覧専用（WidgetShortcut: リストにフォーカスがあるときのみ発火）
        sh_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._take_list, self._on_take_list_delete_key)
        sh_del.setContext(Qt.ShortcutContext.WidgetShortcut)
        sh_ret = QShortcut(QKeySequence(Qt.Key.Key_Return), self._take_list, self._on_take_list_enter_play)
        sh_ret.setContext(Qt.ShortcutContext.WidgetShortcut)
        sh_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), self._take_list, self._on_take_list_enter_play)
        sh_enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        # 検索・置換はメニュー経由で _on_find / _on_replace_dialog が呼ばれる（Ctrl+F / Ctrl+H）

    def _should_handle_single_key_shortcut(self) -> bool:
        """単一キーのグローバルショートカットを処理してよいか。

        台本エディタや現在行プレビュー、メモ入力ダイアログなどのテキスト入力にフォーカスがある
        ときは単一キーの動作を奪わない（F1）。
        """
        app = QApplication.instance()
        focus = app.focusWidget() if app else None
        if focus is None:
            return True
        # 台本本文は QPlainTextEdit。テキスト入力全般を除外。
        if isinstance(focus, (QPlainTextEdit,)):
            return False
        try:
            from PyQt6.QtWidgets import QLineEdit, QTextEdit
            if isinstance(focus, (QLineEdit, QTextEdit)):
                return False
        except Exception:
            pass
        return True

    def _sk_record_toggle(self) -> None:
        if self._should_handle_single_key_shortcut():
            self._on_record_toggle()

    def _sk_play_pause_toggle(self) -> None:
        if self._should_handle_single_key_shortcut():
            self._on_play_pause_toggle()

    def _sk_seek_backward(self) -> None:
        if self._should_handle_single_key_shortcut():
            self._on_seek_backward()

    def _sk_seek_forward(self) -> None:
        if self._should_handle_single_key_shortcut():
            self._on_seek_forward()

    def _on_level_meter_tick(self) -> None:
        """A1: レベルメーターを定期更新する。合わせて数値表示（Peak / ST LUFS）も更新。"""
        if not hasattr(self, "_level_meter") or not self._level_meter.isVisible():
            return
        try:
            peak, rms = self._recorder.get_monitor_levels()
        except Exception:
            peak, rms = 0.0, 0.0
        self._level_meter.set_levels(peak, rms)

        # リアルタイム数値（Peak / ST LUFS）は 200ms 間隔（tick は 50ms なので 4 回に 1 回）
        if not hasattr(self, "_live_lufs_label") or not self._live_lufs_label.isVisible():
            return
        self._live_lufs_tick_counter = (getattr(self, "_live_lufs_tick_counter", 0) + 1) % 4
        if self._live_lufs_tick_counter != 0:
            return
        # Peak dBFS（数値）
        peak_dbfs = _amp_to_dbfs_value(peak)
        peak_str = "—.—" if peak_dbfs is None else f"{peak_dbfs:+5.1f}"
        # Short-term LUFS: 直近 3 秒のモノラルサンプルから pyloudnorm で計算
        lufs_str = "—.—"
        try:
            from src.recorder import SAMPLE_RATE as _SR
            samples = self._recorder.get_monitor_samples_mono(seconds=3.0)
            if samples.size >= int(_SR * 0.5):
                from src.audio_processing import analyze_loudness_samples
                info = analyze_loudness_samples(samples, _SR)
                lufs = info.get("integrated_lufs")
                if isinstance(lufs, float) and math.isfinite(lufs):
                    lufs_str = f"{lufs:+6.1f}"
        except Exception:  # noqa: BLE001
            pass
        self._live_lufs_label.setText(f"Peak {peak_str} dBFS   ST {lufs_str} LUFS")

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
        if isinstance(self._record_toggle_btn, RecordButton):
            # E4: 新しい RecordButton は内部で脈動アニメを制御
            self._record_toggle_btn.set_recording(rec, paused=paused)
            if not rec:
                self._record_toggle_btn.setToolTip("録音開始 … 録音を開始（F9）")
            elif paused:
                self._record_toggle_btn.setToolTip("録音再開 … 一時停止から再開")
            else:
                self._record_toggle_btn.setToolTip("一時停止 … 録音を一時停止")
            # 旧 blink タイマーは使わない
            self._recording_blink_timer.stop()
        else:
            # フォールバック（RecordButton 化されていない場合の後方互換）
            if not rec:
                self._record_toggle_btn.setText("●")
                self._record_toggle_btn.setToolTip("録音開始 … 録音を開始（F9）")
                self._recording_blink_timer.stop()
                self._record_toggle_btn.setStyleSheet("")
            elif paused:
                self._record_toggle_btn.setText("●")
                self._record_toggle_btn.setToolTip("録音再開 … 一時停止から再開")
                self._recording_blink_timer.stop()
                self._record_toggle_btn.setStyleSheet("")
            else:
                self._record_toggle_btn.setText("‖")
                self._record_toggle_btn.setToolTip("一時停止 … 録音を一時停止")
                if not self._recording_blink_timer.isActive():
                    self._recording_blink_state = True
                    self._recording_blink_timer.start(500)
                    self._on_recording_blink_tick()
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
            # B1: 星評価の表示（1〜5）
            rating_str = f"  {'★' * t.rating}{'☆' * (5 - t.rating)}" if getattr(t, "rating", 0) else ""
            # B1: タグ（最大 3 件まで表示）
            tag_preview = ""
            if getattr(t, "tags", None):
                tag_preview = "  " + " ".join(f"#{g}" for g in list(t.tags)[:3])
            # D2: クリッピング警告バッジ
            clip_badge = " ⚠" if getattr(t, "has_clipping", False) else ""
            # A: LUFS バッジ（解析済みのテイクのみ）
            lufs_val = getattr(t, "integrated_lufs", None)
            lufs_badge = f"  {lufs_val:.1f}LUFS" if isinstance(lufs_val, float) and math.isfinite(lufs_val) else ""
            dur_sec = storage.get_wav_duration_seconds(self._project.project_dir, t.wav_filename)
            dur_str = f"  {self._format_duration(dur_sec)}" if dur_sec > 0 else ""
            memo_str = f"  {t.memo}" if t.memo else ""
            line = f"{new_badge}{fav}{t.display_name(i)}{dur_str}{rating_str}{lufs_badge}{tag_preview}{memo_str}{adopted}{clip_badge}"
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            tooltip_parts = []
            if t.script_line_text:
                tooltip_parts.append(f"セリフ: {t.script_line_text}")
            if t.memo:
                tooltip_parts.append(f"メモ: {t.memo}")
            tooltip_parts.append(f"ファイル: {t.wav_filename}")
            if dur_sec > 0:
                tooltip_parts.append(f"長さ: {self._format_duration(dur_sec)}")
            if t.favorite:
                tooltip_parts.append("★ お気に入り")
            if t.adopted:
                tooltip_parts.append("✓ 採用済み")
            if getattr(t, "rating", 0):
                tooltip_parts.append(f"★ 評価: {t.rating} / 5")
            if getattr(t, "tags", None):
                tooltip_parts.append("タグ: " + ", ".join(t.tags))
            if getattr(t, "has_clipping", False):
                peak_db = getattr(t, "peak_dbfs", None)
                if isinstance(peak_db, float):
                    tooltip_parts.append(f"⚠ クリップ検出（ピーク {peak_db:.1f} dBFS）")
                else:
                    tooltip_parts.append("⚠ クリップ検出")
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
        # C1: 台本ガターのテイク数・採用マーカーを更新
        self._refresh_script_line_indicators()

    def _refresh_script_line_indicators(self) -> None:
        """C1: 台本の行番号ガターにテイク数・採用マーカーを描画するための集計。"""
        counts: dict[int, int] = {}
        adopted_lines: set[int] = set()
        for t in self._project.takes:
            line = getattr(t, "script_line_number", None)
            if isinstance(line, int) and line > 0:
                counts[line] = counts.get(line, 0) + 1
                if t.adopted:
                    adopted_lines.add(line)
        try:
            self._script_container.set_line_take_info(counts, adopted_lines)
        except Exception:
            pass

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
        if hasattr(self, "_level_meter"):
            self._level_meter.set_dark_theme(dark)
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
        """台本エディタと行番号ガターに指定 pt のフォントを適用する。

        QApplication.setFont(...) 後にも値が維持されるよう、明示的に
        新しい QFont を生成し、ガター幅も再計算する。
        """
        from PyQt6.QtGui import QFont
        # 現在の有効フォントをベースにしつつ、全属性を明示にするため QFont() で複製する
        base = QFont(self._script_edit.font())
        base.setPointSize(int(size))
        self._script_edit.setFont(base)
        self._script_container.line_number_area().setFont(base)
        # フォント変更後は行番号エリアの幅を再計算する
        try:
            self._script_container.refresh_line_number_area_width()
        except Exception:
            pass
        # View メニューのスピンボックスと値を同期（ループ回避のため signals ブロック）
        try:
            if hasattr(self, "_font_spin") and self._font_spin.value() != int(size):
                self._font_spin.blockSignals(True)
                try:
                    self._font_spin.setValue(int(size))
                finally:
                    self._font_spin.blockSignals(False)
        except Exception:
            pass

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
            "※ 既存のプロジェクトは「開く」または「最近開いたプロジェクト」から。\n"
            "※ LUFS / dBFS など音まわりの用語は「ヘルプ → 用語解説」で確認できます。"
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

    def _on_show_glossary(self) -> None:
        """ヘルプ「用語解説」: アプリ内の音響用語をまとめて表示する。"""
        html = """
<h2 style="margin-top:0">用語解説（音まわりの言葉）</h2>
<p>本アプリで登場する用語を、ざっくりした意味から順に説明します。</p>

<h3>🔊 LUFS（ラウドネス）</h3>
<p><b>LUFS</b> = <i>Loudness Units relative to Full Scale</i>。人の耳で感じる音の「大きさ」を数値化した国際基準（ITU-R BS.1770 / EBU R128）です。
値はマイナスで、<b>0 に近いほど大きい音</b>。</p>
<ul>
  <li><b>-14 LUFS</b> … Apple Music の目安</li>
  <li><b>-16 LUFS</b> … YouTube / Spotify / Podcast の一般的な目安 <b>（本アプリの既定値）</b></li>
  <li><b>-23 LUFS</b> … テレビ放送（EBU R128）の基準</li>
  <li><b>-24 LUFS</b> … 米国テレビ放送（ATSC A/85）の基準</li>
</ul>
<p>ピーク（最大瞬間音量）ではなく、曲全体の<b>平均的な聴感音量</b>を測るのがポイント。
「-16 LUFS に揃える」とは、ほかの音声と音の大きさをそろえて、<b>提出先で勝手に音量を下げられないようにする</b>作業です。</p>

<h3>📏 dBFS（デシベル・フルスケール）</h3>
<p>デジタル音声の<b>瞬間的な大きさ</b>の単位。上限が 0 dBFS（=フルスケール）で、普通はマイナス方向で表記します。</p>
<ul>
  <li><b>0 dBFS</b> … これ以上大きくできない天井。超えると「クリップ」して音が割れる</li>
  <li><b>-1 dBFS</b>（True Peak 天井）… 配信プラットフォームで推奨される安全マージン</li>
  <li><b>-6 〜 -12 dBFS</b> … 収録時のピーク目安（赤ゾーン手前）</li>
</ul>
<p>本アプリのテイク一覧にある「⚠」は、録音時に <b>0 dBFS</b> にぶつかった（クリップした）サインです。</p>

<h3>🎚️ ピーク / RMS</h3>
<ul>
  <li><b>ピーク（Peak）</b> … その瞬間の最大値。クリップ検出はピーク基準</li>
  <li><b>RMS</b> … 一定時間の<b>平均的な</b>エネルギー。聴感の大きさに近い</li>
</ul>
<p>録音画面上部のレベルメーターは、上段がピーク、下段が RMS を表示しています。</p>

<h3>🎛️ ラウドネス正規化（Normalize）</h3>
<p>録音したテイクの LUFS を測り、<b>目標値（例: -16 LUFS）に合うように全体を均一に音量調整</b>すること。
エクスポートダイアログで ON にすると、書き出し時に自動で適用されます。
ピークが天井（既定 -1 dBFS）を超えそうな場合は、その分だけ控えめに調整されます。</p>

<h3>🌬️ ノイズ除去（Noise Reduction）</h3>
<p>エアコン音・PC のファン音・ヒスノイズなど、声以外の「定常的な雑音」を減らす処理。
本アプリでは、音声の<b>先頭 0.5 秒をノイズの見本</b>とみなし、スペクトルサブトラクションで削ります。
強く掛けすぎると声が痩せるので、軽めの設定（prop_decrease=0.85）で動かしています。</p>

<h3>🤫 無音トリム（Silence Trim）</h3>
<p>テイクの<b>先頭と末尾の無音</b>をカットする処理。しきい値は <b>-45 dBFS</b>（ほぼ聞こえないくらい静か）。
前後に 80 ms の余白を残すので、自然な立ち上がり・終わりを保てます。</p>

<h3>🎼 サンプルレート / ビット深度</h3>
<ul>
  <li><b>サンプルレート</b> … 1 秒間に音を何回サンプリングするか。本アプリは <b>44.1 kHz</b>（CD 相当）</li>
  <li><b>ビット深度</b> … 1 サンプルの階調。本アプリは <b>16 bit PCM</b>（WAV/FLAC 書き出し）</li>
</ul>

<h3>📦 ファイル形式</h3>
<ul>
  <li><b>WAV</b> … 非圧縮。音質劣化なし。ファイル大きめ。スタジオ提出の標準</li>
  <li><b>FLAC</b> … 可逆圧縮。音質劣化なし＆ WAV の約半分サイズ</li>
  <li><b>MP3</b> … 非可逆圧縮。ファイル小。SNS や Web 配布向け。本アプリは 128〜320 kbps CBR</li>
</ul>

<h3>⏱️ プリロール / レベルメーター</h3>
<ul>
  <li><b>プリロール</b> … 録音ボタンを押してから実際の録音が始まるまでのカウントダウン（3 or 5 秒）</li>
  <li><b>レベルメーター</b> … マイクからの入力音量をリアルタイムで表示する棒グラフ</li>
</ul>

<p style="color:#888; margin-top:16px;">※ 用語の目安値は 2026 年時点の主要配信プラットフォームの推奨値に基づきます。最新の基準は各サービスの仕様をご確認ください。</p>
"""
        dlg = QDialog(self)
        dlg.setWindowTitle("用語解説")
        layout = QVBoxLayout(dlg)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml(html)
        tb.setMinimumSize(560, 520)
        layout.addWidget(tb)
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
        """録音開始 / 一時停止 / 再開の切り替え。

        録音開始時のみ、設定の ``preroll_seconds`` が 3 or 5 ならカウントダウンを挟む（A2）。
        プリロール表示中に再度押下するとキャンセルされる。
        """
        if not self._project.has_project_dir():
            QMessageBox.warning(self, "録音", "先にプロジェクトを新規作成するか開いてください。")
            return
        # プリロール中にもう一度押したらキャンセル扱い
        if getattr(self, "_preroll_overlay", None) and self._preroll_overlay.active:
            self._preroll_overlay.cancel()
            return
        editor_text = self._script_edit.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        project_text = (self._project.script_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if editor_text != project_text and self.statusBar():
            self.statusBar().showMessage("台本に未保存の変更があります。必要に応じて保存してから録音してください。", 5000)
        try:
            if not self._recorder.is_recording:
                preroll = get_preroll_seconds()
                if preroll > 0:
                    self._start_recording_with_preroll(preroll)
                    return
                self._start_recording_now()
            elif self._recorder.is_paused:
                self._recorder.resume()
                self._recording_timer.start(100)
                self._on_recording_tick()
                self._update_ui_state()
            else:
                self._recorder.pause()
                self._update_ui_state()
        except Exception as e:
            QMessageBox.warning(self, "録音エラー", str(e))

    def _start_recording_now(self) -> None:
        """プリロール無しで録音を即座に開始する。"""
        # モニター用ストリームが動いていれば録音のため一旦止める（デバイスを譲る）
        try:
            self._recorder.stop_monitoring()
        except Exception:
            pass
        self._recorder.start()
        self._recording_timer.start(100)
        self._on_recording_tick()
        self._update_ui_state()

    def _start_recording_with_preroll(self, seconds: int) -> None:
        """A2: 指定秒数カウントダウン後に録音を開始する。"""
        overlay = getattr(self, "_preroll_overlay", None)
        if overlay is None:
            self._start_recording_now()
            return
        if self.statusBar():
            self.statusBar().showMessage(f"録音まで {seconds} 秒… （キャンセルは Esc / 画面クリック）")

        def on_finished() -> None:
            try:
                self._start_recording_now()
            except Exception as e:
                QMessageBox.warning(self, "録音エラー", str(e))

        def on_cancelled() -> None:
            if self.statusBar():
                self.statusBar().showMessage("録音開始をキャンセルしました", 2000)

        overlay.start(seconds, on_finished=on_finished, on_cancelled=on_cancelled)

    def _on_record_stop(self) -> None:
        if not self._recorder.is_recording:
            return
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        import os
        os.close(fd)
        take_added = False
        clip_info: dict = {}
        try:
            if self._recorder.stop_and_save(tmp):
                script_text = self._script_edit.toPlainText()
                cursor_pos = self._script_edit.textCursor().position()
                existing = [t.wav_filename for t in self._project.takes]
                
                mode = get_recording_mode()
                line_text = get_current_line_text(script_text, cursor_pos)
                script_line_number = get_current_line_number(script_text, cursor_pos) if line_text else None
                preferred_basename = suggest_take_basename(script_text, cursor_pos, existing, mode=mode, line_text=line_text)

                try:
                    take = storage.add_take_from_file(
                        self._project.project_dir,
                        tmp,
                        memo="",
                        favorite=False,
                        preferred_basename=preferred_basename,
                        script_line_number=script_line_number,
                        script_line_text=line_text,
                    )
                except OSError as e:
                    QMessageBox.warning(self, "録音", f"テイクの保存に失敗しました: {e}")
                    return
                # D2: 保存直後にクリッピング解析してメタに書き込む
                try:
                    saved_wav = storage.get_take_wav_path(self._project.project_dir, take.wav_filename)
                    clip_info = storage.analyze_wav_clipping(saved_wav)
                    lufs_value: float | None = None
                    if get_auto_analyze_lufs():
                        try:
                            from src.audio_processing import analyze_loudness
                            lufs_info = analyze_loudness(saved_wav)
                            lufs_value = lufs_info.get("integrated_lufs")
                        except Exception:  # noqa: BLE001
                            lufs_value = None
                    storage.update_take_meta(
                        self._project.project_dir,
                        take.id,
                        has_clipping=bool(clip_info.get("has_clipping", False)),
                        peak_dbfs=clip_info.get("peak_dbfs"),
                        integrated_lufs=lufs_value,
                    )
                    take.has_clipping = bool(clip_info.get("has_clipping", False))
                    take.peak_dbfs = clip_info.get("peak_dbfs")
                    take.integrated_lufs = lufs_value
                except Exception:
                    clip_info = {}
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
        # 録音終了後は引き続きレベルメーターを動かすためモニターを再開
        if get_level_meter_enabled():
            self._recorder.start_monitoring()
        
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
                if clip_info.get("has_clipping"):
                    peak_db = clip_info.get("peak_dbfs")
                    peak_text = f"（ピーク {peak_db:.1f} dBFS）" if isinstance(peak_db, float) else ""
                    self.statusBar().showMessage(
                        f"⚠ テイクを追加しました: クリップを検出しました{peak_text}",
                        6000,
                    )
                else:
                    self.statusBar().showMessage("1テイクを追加しました", 3000)
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
        # 台本カーソル移動起因で選択された場合は、逆方向のスクロールを抑止する。
        if self._syncing_script_cursor:
            self._highlight_current_line()
            return
        take_id = current.data(Qt.ItemDataRole.UserRole)
        t = self._project.get_take(take_id) if take_id else None
        if t and t.script_line_number is not None:
            self._scroll_script_to_line(t.script_line_number)
        self._highlight_current_line()

    def _on_script_cursor_line_changed(self) -> None:
        """台本のカーソル行が変わったら、ガターマーカー更新＋テイク一覧を同期選択する。"""
        try:
            script_text = self._script_edit.toPlainText()
            cursor_pos = self._script_edit.textCursor().position()
            line_no = get_current_line_number(script_text, cursor_pos)
        except Exception:
            line_no = None

        # ガターの●マーカー更新（常に）
        try:
            self._script_container.set_current_script_line(line_no if line_no and line_no >= 1 else None)
        except Exception:
            pass

        # 自分自身が同期中、または行番号が変わっていないなら以降スキップ
        if self._syncing_script_cursor:
            return
        if line_no == self._last_synced_script_line:
            return
        self._last_synced_script_line = line_no
        if not line_no or line_no < 1:
            return

        # 現在の行に対応するテイクを抽出（表示中テイクの中から選ぶ）
        try:
            visible_ids = set()
            for i in range(self._take_list.count()):
                it = self._take_list.item(i)
                if it is not None:
                    tid = it.data(Qt.ItemDataRole.UserRole)
                    if tid:
                        visible_ids.add(tid)
            if not visible_ids:
                return
            matching = [
                t for t in self._project.takes
                if getattr(t, "script_line_number", None) == line_no and t.id in visible_ids
            ]
            if not matching:
                return
            # 採用 > お気に入り > 作成日時新しい順
            def _ts(iso: str) -> float:
                try:
                    from datetime import datetime
                    return datetime.fromisoformat((iso or "").replace("Z", "+00:00")).timestamp()
                except Exception:
                    return 0.0
            matching.sort(key=lambda t: (0 if t.adopted else 1, 0 if t.favorite else 1, -_ts(t.created_at)))
            target_id = matching[0].id

            cur = self._take_list.currentItem()
            already_exact = (
                cur is not None
                and cur.data(Qt.ItemDataRole.UserRole) == target_id
                and cur.isSelected()
                and len(self._take_list.selectedItems()) == 1
            )
            if already_exact:
                return

            self._syncing_script_cursor = True
            try:
                for i in range(self._take_list.count()):
                    item = self._take_list.item(i)
                    if item and item.data(Qt.ItemDataRole.UserRole) == target_id:
                        # ExtendedSelection モードでは既存選択が残るので明示的にクリアしてから選び直す
                        self._take_list.clearSelection()
                        self._take_list.setCurrentItem(item)
                        item.setSelected(True)
                        self._take_list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
                        break
            finally:
                self._syncing_script_cursor = False
            # 同期後、台本側のハイライトも更新（選択テイクに基づく2色目）
            self._highlight_current_line()
        except Exception:
            self._syncing_script_cursor = False

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
            # 先にアプリ全体フォントを反映し、その後に台本フォントを明示的に上書きする。
            # （順序を逆にすると QApplication.setFont() 後のカスケードで台本フォントが
            # 意図しないサイズに戻ってしまうケースがあるため）
            try:
                from src.ui.app_font import apply_from_settings as _apply_app_font
                _apply_app_font()
            except Exception:
                pass
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
            # A1: レベルメーターの表示切替
            meter_enabled = get_level_meter_enabled()
            self._level_meter.setVisible(meter_enabled)
            if hasattr(self, "_live_lufs_label"):
                self._live_lufs_label.setVisible(meter_enabled)
            if meter_enabled:
                if not self._recorder.is_recording:
                    self._recorder.start_monitoring()
                if not self._level_meter_timer.isActive():
                    self._level_meter_timer.start(50)
            else:
                self._level_meter_timer.stop()
                self._recorder.stop_monitoring()
            self.statusBar().showMessage("設定を反映しました。", 3000)

    def _set_rating_for_take(self, take_id: str, rating: int) -> None:
        """B1: 単一テイクの星評価を設定する。"""
        storage.update_take_meta(self._project.project_dir, take_id, rating=rating)
        self._project = storage.load_project(self._project.project_dir) or self._project
        self._refresh_take_list()

    def _edit_tags_for_take(self, take_id: str) -> None:
        """B1: タグ編集ダイアログ（カンマ区切り）。"""
        from PyQt6.QtWidgets import QInputDialog
        ti = self._project.get_take(take_id)
        if ti is None:
            return
        current = ", ".join(ti.tags)
        text, ok = QInputDialog.getText(
            self,
            "タグを編集",
            "タグをカンマ区切りで入力（例: OK, 要リテイク, キャラA）:",
            text=current,
        )
        if not ok:
            return
        tags = [s.strip() for s in text.split(",") if s.strip()]
        storage.update_take_meta(self._project.project_dir, take_id, tags=tags)
        self._project = storage.load_project(self._project.project_dir) or self._project
        self._refresh_take_list()

    def _build_bulk_submenu(self, parent_menu: QMenu, take_ids: list[str]) -> None:
        """B3: 複数選択時の一括操作メニュー。"""
        n = len(take_ids)
        bulk_menu = parent_menu.addMenu(f"選択中 {n} 件に一括適用")
        # お気に入り付与／解除
        act_fav_on = QAction("★ お気に入りに追加", self)
        act_fav_on.triggered.connect(lambda: self._bulk_apply(take_ids, favorite=True))
        bulk_menu.addAction(act_fav_on)
        act_fav_off = QAction("お気に入りを解除", self)
        act_fav_off.triggered.connect(lambda: self._bulk_apply(take_ids, favorite=False))
        bulk_menu.addAction(act_fav_off)
        bulk_menu.addSeparator()
        # 評価の一括変更
        rating_menu = bulk_menu.addMenu("評価 (★) を一括設定")
        for r in (0, 1, 2, 3, 4, 5):
            label = "評価なし" if r == 0 else ("★" * r)
            act_r = QAction(label, self)
            act_r.triggered.connect(lambda _c=False, rr=r: self._bulk_apply(take_ids, rating=rr))
            rating_menu.addAction(act_r)
        bulk_menu.addSeparator()
        # タグ一括追加・削除
        act_add_tag = QAction("タグを追加…", self)
        act_add_tag.triggered.connect(lambda: self._bulk_edit_tags(take_ids, add=True))
        bulk_menu.addAction(act_add_tag)
        act_rm_tag = QAction("タグを削除…", self)
        act_rm_tag.triggered.connect(lambda: self._bulk_edit_tags(take_ids, add=False))
        bulk_menu.addAction(act_rm_tag)
        bulk_menu.addSeparator()
        # 採用解除（採用付与は 1 本のみなので一括では提供しない）
        act_clear_adopt = QAction("採用を解除（選択全て）", self)
        act_clear_adopt.triggered.connect(lambda: self._bulk_apply(take_ids, clear_adopted=True))
        bulk_menu.addAction(act_clear_adopt)
        bulk_menu.addSeparator()
        # 選択したテイクだけエクスポート
        act_export_selected = QAction("選択したテイクだけエクスポート…", self)
        act_export_selected.triggered.connect(lambda: self._export_specific_takes(take_ids))
        bulk_menu.addAction(act_export_selected)

    def _bulk_apply(
        self,
        take_ids: list[str],
        *,
        favorite: bool | None = None,
        rating: int | None = None,
        clear_adopted: bool = False,
    ) -> None:
        """B3: 一括メタ更新（お気に入り・評価・採用解除）。"""
        storage.update_takes_meta_bulk(
            self._project.project_dir,
            take_ids,
            favorite=favorite,
            rating=rating,
            clear_adopted=clear_adopted,
        )
        self._project = storage.load_project(self._project.project_dir) or self._project
        self._refresh_take_list()
        if self.statusBar():
            self.statusBar().showMessage(f"{len(take_ids)} 件に変更を適用しました", 3000)

    def _bulk_edit_tags(self, take_ids: list[str], *, add: bool) -> None:
        """B3: 選択テイクにタグを一括追加／削除。"""
        from PyQt6.QtWidgets import QInputDialog
        verb = "追加" if add else "削除"
        text, ok = QInputDialog.getText(
            self,
            f"タグを一括{verb}",
            f"カンマ区切りで{verb}するタグを入力:",
        )
        if not ok:
            return
        tags = [s.strip() for s in text.split(",") if s.strip()]
        if not tags:
            return
        storage.update_takes_meta_bulk(
            self._project.project_dir,
            take_ids,
            add_tags=tags if add else None,
            remove_tags=None if add else tags,
        )
        self._project = storage.load_project(self._project.project_dir) or self._project
        self._refresh_take_list()

    def _export_specific_takes(self, take_ids: list[str]) -> None:
        """選択したテイクのみエクスポートする簡易ダイアログ。"""
        if not take_ids:
            return
        dest = QFileDialog.getExistingDirectory(
            self,
            "エクスポート先を選択",
            directory=get_export_last_dir() or "",
        )
        if not dest:
            return
        set_export_last_dir(dest)
        try:
            paths = storage.export_takes(
                self._project.project_dir,
                take_ids,
                dest,
                use_friendly_names=get_export_use_friendly_names(),
                name_template=get_export_name_template() or None,
            )
        except OSError as e:
            QMessageBox.warning(self, "エクスポート", str(e))
            return
        QMessageBox.information(self, "エクスポート", f"{len(paths)} 件をエクスポートしました。\n{dest}")

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
        # B3: 複数選択時は一括操作メニューを先頭に
        if len(selected) >= 2:
            self._build_bulk_submenu(menu, selected)
            menu.addSeparator()
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
        # 選択中の複数テイクが対象になる場合のIDリストを算出。
        # （右クリック対象が選択群に含まれていれば全選択を、含まれていなければ当該テイクのみ）
        if len(selected) >= 2 and take_id in selected:
            sel_targets = list(selected)
        else:
            sel_targets = [take_id]
        multi = len(sel_targets) >= 2

        # B1: 星評価サブメニュー（複数選択時は一括適用）
        rating_label = f"評価 (★) （{len(sel_targets)}件に適用）" if multi else "評価 (★)"
        rating_menu = menu.addMenu(rating_label)
        # 複数選択時は「全員が同じ評価のときだけ ● を付ける」
        if multi:
            ratings_set = {
                (self._project.get_take(i).rating if self._project.get_take(i) else 0)
                for i in sel_targets
            }
            current_rating = next(iter(ratings_set)) if len(ratings_set) == 1 else None
        else:
            current_rating = t.rating if t else 0
        for r in (0, 1, 2, 3, 4, 5):
            label = "評価なし" if r == 0 else ("★" * r)
            if current_rating is not None and r == current_rating:
                label = "● " + label
            act_r = QAction(label, self)
            if multi:
                act_r.triggered.connect(
                    lambda _c=False, rating=r, ids=sel_targets: self._bulk_apply(ids, rating=rating)
                )
            else:
                act_r.triggered.connect(
                    lambda _c=False, rating=r: self._set_rating_for_take(take_id, rating)
                )
            rating_menu.addAction(act_r)
        # B1: タグ編集
        act_tags = QAction("タグを編集…", self)
        act_tags.triggered.connect(lambda: self._edit_tags_for_take(take_id))
        menu.addAction(act_tags)
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

        # ファイルの場所を開く
        act_reveal = QAction("このファイルの場所を開く", self)
        act_reveal.triggered.connect(lambda: self._on_reveal_take_in_folder(take_id))
        menu.addAction(act_reveal)

        menu.addSeparator()

        # 後処理サブメニュー（A/B）- 複数選択時は全件に適用
        proc_label = f"後処理（{len(sel_targets)}件に適用）" if multi else "後処理"
        proc_menu = menu.addMenu(proc_label)
        act_analyze = QAction("ラウドネス(LUFS) 解析", self)
        act_analyze.triggered.connect(
            lambda _c=False, ids=sel_targets: self._apply_post_op_to_takes(
                ids, "LUFS 解析", self._on_analyze_loudness_take, confirm_overwrite=False
            )
        )
        proc_menu.addAction(act_analyze)
        act_trim = QAction("前後の無音をトリム（上書き）", self)
        act_trim.triggered.connect(
            lambda _c=False, ids=sel_targets: self._apply_post_op_to_takes(
                ids, "無音トリム", self._on_trim_silence_take
            )
        )
        proc_menu.addAction(act_trim)
        act_nr = QAction("ノイズ除去（上書き）", self)
        act_nr.triggered.connect(
            lambda _c=False, ids=sel_targets: self._apply_post_op_to_takes(
                ids, "ノイズ除去", self._on_noise_reduce_take
            )
        )
        proc_menu.addAction(act_nr)
        act_norm = QAction("LUFS 正規化（上書き）", self)
        act_norm.triggered.connect(
            lambda _c=False, ids=sel_targets: self._apply_post_op_to_takes(
                ids, "LUFS 正規化", self._on_normalize_loudness_take
            )
        )
        proc_menu.addAction(act_norm)

        # 書き出し（C）- 複数選択時はフォルダに一括書き出し
        exp_label = f"選択 {len(sel_targets)} 件を書き出し" if multi else "このテイクを書き出し"
        exp_menu = menu.addMenu(exp_label)
        act_exp_wav = QAction("WAV で書き出し", self)
        act_exp_wav.triggered.connect(
            lambda _c=False, ids=sel_targets: self._on_export_takes_as(ids, "wav")
        )
        exp_menu.addAction(act_exp_wav)
        act_exp_flac = QAction("FLAC で書き出し", self)
        act_exp_flac.triggered.connect(
            lambda _c=False, ids=sel_targets: self._on_export_takes_as(ids, "flac")
        )
        exp_menu.addAction(act_exp_flac)
        act_exp_mp3 = QAction("MP3 で書き出し", self)
        act_exp_mp3.triggered.connect(
            lambda _c=False, ids=sel_targets: self._on_export_takes_as(ids, "mp3")
        )
        exp_menu.addAction(act_exp_mp3)

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

        # 削除（Deleteキーと同じ挙動: 右クリックしたテイクが複数選択に含まれていれば全件削除）
        if len(selected) >= 2 and take_id in selected:
            del_label = f"選択した{len(selected)}件のテイクを削除    Del"
            del_targets = [tid for tid in selected if tid]
        else:
            del_label = "テイクを削除    Del"
            del_targets = [take_id]
        act_del = QAction(del_label, self)
        def delete_take():
            self._delete_takes_with_confirm(list(del_targets))
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

    def _delete_takes_with_confirm(self, take_ids: list[str]) -> None:
        """確認ダイアログ・再生ロック解除・一括削除までを共通化した削除処理。

        Deleteキーと右クリック「テイクを削除」の両方から呼ばれ、
        複数テイクを安全にまとめて削除する。
        """
        if not take_ids:
            return
        if not self._project.has_project_dir():
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
            self._delete_takes_after_unlock(take_ids, n)

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
        self._delete_takes_with_confirm(take_ids)

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

    def _on_export_adopted_oneclick(self) -> None:
        """G1: 採用テイクをワンクリックで前回の保存先にエクスポートする。

        採用テイクが無い場合は、お気に入りテイクにフォールバックし、それも無ければ通知のみ。
        前回の保存先が未設定の場合はフォルダ選択ダイアログを出す。
        """
        if not self._project.has_project_dir():
            QMessageBox.warning(self, "エクスポート", "プロジェクトを開いてください。")
            return
        adopted_ids = [t.id for t in self._project.takes if t.adopted]
        fallback_used = False
        if not adopted_ids:
            fav_ids = [t.id for t in self._project.takes if t.favorite]
            if not fav_ids:
                QMessageBox.information(
                    self,
                    "エクスポート",
                    "採用テイクもお気に入りテイクもありません。右クリックから★または採用を設定してください。",
                )
                return
            adopted_ids = fav_ids
            fallback_used = True
        last_dir = get_export_last_dir() or ""
        dest = last_dir
        if not dest or not Path(dest).is_dir():
            dest = QFileDialog.getExistingDirectory(self, "エクスポート先を選択", directory=last_dir)
            if not dest:
                return
            set_export_last_dir(dest)
        try:
            paths = storage.export_takes(
                self._project.project_dir,
                adopted_ids,
                dest,
                use_friendly_names=True,
                name_template=get_export_name_template() or None,
            )
        except OSError as e:
            QMessageBox.warning(self, "エクスポート", str(e))
            return
        note = "（採用が無かったためお気に入りを書き出しました）" if fallback_used else ""
        msg = f"{len(paths)} 件をエクスポートしました{note}。\n保存先: {dest}"
        QMessageBox.information(self, "一括納品", msg)

    def _on_reveal_takes_folder(self) -> None:
        """録音WAVが保存されている takes フォルダをOSのファイルマネージャで開く。"""
        if not self._project.has_project_dir():
            QMessageBox.warning(self, "保存フォルダを開く", "プロジェクトを開いてください。")
            return
        takes_dir = storage.get_takes_dir(self._project.project_dir)
        try:
            from pathlib import Path as _Path
            _Path(takes_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if storage.reveal_in_file_manager(takes_dir):
            self.statusBar().showMessage(f"保存フォルダを開きました: {takes_dir}", 4000)
        else:
            QMessageBox.warning(
                self,
                "保存フォルダを開く",
                f"フォルダを開けませんでした:\n{takes_dir}",
            )

    def _on_reveal_take_in_folder(self, take_id: str) -> None:
        """指定テイクのWAVファイルを、ファイルマネージャで選択状態で開く。"""
        if not self._project.has_project_dir():
            return
        t = self._project.get_take(take_id)
        if t is None:
            return
        wav_path = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
        if storage.reveal_in_file_manager(wav_path):
            self.statusBar().showMessage(f"ファイルの場所を開きました: {wav_path}", 4000)
        else:
            QMessageBox.warning(
                self,
                "ファイルの場所を開く",
                f"ファイルを見つけられませんでした:\n{wav_path}",
            )

    # ----- A/B: 単発後処理 -----

    def _stop_playback_if_using(self, take_id: str) -> None:
        """編集対象が再生中/ロード中なら停止してファイルロックを解放する。"""
        if self._playing_take_id == take_id or self._loaded_take_id == take_id:
            try:
                self._playback.release_file_lock()
            except Exception:  # noqa: BLE001
                pass
            self._playback_position_timer.stop()
            self._playing_take_id = None
            self._loaded_take_id = None
            self._update_ui_state()

    def _on_analyze_loudness_take(self, take_id: str) -> None:
        """単一テイクの LUFS を解析してメタに書き込む。"""
        if not self._project.has_project_dir():
            return
        t = self._project.get_take(take_id)
        if t is None:
            return
        wav_path = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
        from PyQt6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            try:
                from src.audio_processing import analyze_loudness
                info = analyze_loudness(wav_path)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "LUFS 解析", f"解析に失敗しました: {e}")
                return
        finally:
            QApplication.restoreOverrideCursor()
        lufs = info.get("integrated_lufs")
        peak = info.get("peak_dbfs")
        storage.update_take_meta(
            self._project.project_dir,
            take_id,
            integrated_lufs=lufs if isinstance(lufs, float) else None,
            peak_dbfs=peak if isinstance(peak, float) else None,
        )
        self._project = storage.load_project(self._project.project_dir) or self._project
        self._refresh_take_list()
        if isinstance(lufs, float) and math.isfinite(lufs):
            self.statusBar().showMessage(f"LUFS 解析: {lufs:.1f} LUFS", 5000)
        else:
            self.statusBar().showMessage("LUFS 解析: 短すぎる/無音のため測定不能", 5000)

    def _process_take_in_place(
        self,
        take_id: str,
        operation_label: str,
        processor,  # (in_path, out_path) -> dict
    ) -> None:
        """共通: テイクの WAV を一時ファイルで処理してから置き換える。

        ``processor`` は入力パス・出力パスを受け取り任意の dict を返す関数。
        """
        if not self._project.has_project_dir():
            return
        t = self._project.get_take(take_id)
        if t is None:
            return
        self._stop_playback_if_using(take_id)
        wav_path = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
        if not Path(wav_path).exists():
            QMessageBox.warning(self, operation_label, "WAV ファイルが見つかりません。")
            return
        from PyQt6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    processor(wav_path, tmp_path)
                    # 元ファイルを置き換え（Windows のロック対策で少しリトライ）
                    import time as _time
                    for i in range(3):
                        try:
                            shutil.copy2(tmp_path, wav_path)
                            break
                        except PermissionError:
                            if i == 2:
                                raise
                            _time.sleep(0.1)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, operation_label, f"処理に失敗しました: {e}")
                return
        finally:
            QApplication.restoreOverrideCursor()
        # 処理後にクリッピング・LUFS を再解析して反映
        try:
            clip_info = storage.analyze_wav_clipping(wav_path)
            from src.audio_processing import analyze_loudness
            lufs_info = analyze_loudness(wav_path)
            storage.update_take_meta(
                self._project.project_dir,
                take_id,
                has_clipping=bool(clip_info.get("has_clipping", False)),
                peak_dbfs=clip_info.get("peak_dbfs"),
                integrated_lufs=lufs_info.get("integrated_lufs"),
            )
        except Exception:  # noqa: BLE001
            pass
        self._project = storage.load_project(self._project.project_dir) or self._project
        self._refresh_take_list()
        self.statusBar().showMessage(f"{operation_label} を適用しました", 4000)

    def _on_trim_silence_take(self, take_id: str) -> None:
        """前後の無音をトリムして上書き。"""
        def _proc(in_path: str, out_path: str) -> dict:
            from src.audio_processing import trim_silence
            return trim_silence(in_path, out_path)
        self._process_take_in_place(take_id, "無音トリム", _proc)

    def _on_noise_reduce_take(self, take_id: str) -> None:
        """ノイズ除去をかけて上書き。"""
        def _proc(in_path: str, out_path: str) -> dict:
            from src.audio_processing import reduce_noise
            return reduce_noise(in_path, out_path)
        self._process_take_in_place(take_id, "ノイズ除去", _proc)

    def _on_normalize_loudness_take(self, take_id: str) -> None:
        """LUFS 正規化をかけて上書き。目標値は設定に従う。"""
        target = get_lufs_target()
        def _proc(in_path: str, out_path: str) -> dict:
            from src.audio_processing import normalize_to_lufs
            return normalize_to_lufs(in_path, out_path, target_lufs=target)
        self._process_take_in_place(take_id, f"LUFS 正規化({target:.0f})", _proc)

    def _apply_post_op_to_takes(
        self,
        take_ids: list[str],
        label: str,
        single_op,
        *,
        confirm_overwrite: bool = True,
    ) -> None:
        """複数テイクに後処理を順次適用するヘルパー。

        単一テイク用の処理関数 ``single_op(take_id)`` を反復呼び出しする。
        ``confirm_overwrite=True`` の場合、2件以上なら上書き確認ダイアログを出す。
        """
        if not take_ids:
            return
        n = len(take_ids)
        if confirm_overwrite and n >= 2:
            box = QMessageBox(self)
            box.setWindowTitle(label)
            box.setText(f"選択中の {n} 件に「{label}」を適用します。\n元の WAV を上書きします。よろしいですか？")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.Yes)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for i, tid in enumerate(take_ids, start=1):
                if n >= 2:
                    self.statusBar().showMessage(f"{label}: {i}/{n} …", 0)
                    QApplication.processEvents()
                single_op(tid)
        finally:
            QApplication.restoreOverrideCursor()
        if n >= 2:
            self.statusBar().showMessage(f"{label}: {n} 件に適用しました", 5000)

    def _on_export_takes_as(self, take_ids: list[str], fmt: str) -> None:
        """右クリック書き出し。1件なら単発ダイアログ、複数ならフォルダ選択＋自動命名。"""
        if not take_ids:
            return
        if len(take_ids) == 1:
            self._on_export_single_take(take_ids[0], fmt)
            return
        if not self._project.has_project_dir():
            return
        try:
            from src.audio_processing import output_extension_for
            ext = output_extension_for(fmt)
        except ImportError:
            QMessageBox.warning(self, "書き出し", "音声処理モジュールを読み込めませんでした。")
            return
        dest = QFileDialog.getExistingDirectory(
            self,
            f"{fmt.upper()} 書き出し先フォルダを選択（{len(take_ids)} 件）",
            directory=get_export_last_dir() or "",
        )
        if not dest:
            return
        set_export_last_dir(dest)
        project_name = Path(self._project.project_dir).name or "project"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok_count = 0
        failed: list[str] = []
        try:
            from src.audio_processing import convert_format
            bitrate = get_mp3_bitrate()
            for i, tid in enumerate(take_ids, start=1):
                t = self._project.get_take(tid)
                if t is None:
                    continue
                out_name = f"{project_name}_{Path(t.wav_filename).stem}{ext}"
                out_path = str(Path(dest) / out_name)
                self.statusBar().showMessage(f"{fmt.upper()} 書き出し: {i}/{len(take_ids)} …", 0)
                QApplication.processEvents()
                try:
                    src_wav = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
                    convert_format(src_wav, out_path, fmt=fmt, mp3_bitrate_kbps=bitrate)
                    ok_count += 1
                except Exception as e:  # noqa: BLE001
                    failed.append(f"{t.wav_filename}: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        if failed:
            QMessageBox.warning(
                self,
                "書き出し",
                f"{ok_count} 件成功 / {len(failed)} 件失敗\n\n失敗:\n" + "\n".join(failed[:10]),
            )
        else:
            self.statusBar().showMessage(f"{fmt.upper()} 書き出し完了: {ok_count} 件 → {dest}", 6000)

    def _on_export_single_take(self, take_id: str, fmt: str) -> None:
        """右クリックからの単発書き出し（フォーマット指定）。"""
        if not self._project.has_project_dir():
            return
        t = self._project.get_take(take_id)
        if t is None:
            return
        try:
            from src.audio_processing import output_extension_for
        except ImportError:
            QMessageBox.warning(self, "書き出し", "音声処理モジュールを読み込めませんでした。")
            return
        ext = output_extension_for(fmt)
        project_name = Path(self._project.project_dir).name or "project"
        default_name = f"{project_name}_{Path(t.wav_filename).stem}{ext}"
        initial = str(Path(get_export_last_dir() or "") / default_name) if get_export_last_dir() else default_name
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "テイクを書き出し",
            initial,
            f"{fmt.upper()} files (*{ext})",
        )
        if not out_path:
            return
        if not out_path.lower().endswith(ext):
            out_path += ext
        set_export_last_dir(str(Path(out_path).parent))
        src_wav = storage.get_take_wav_path(self._project.project_dir, t.wav_filename)
        from PyQt6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            try:
                from src.audio_processing import convert_format
                convert_format(src_wav, out_path, fmt=fmt, mp3_bitrate_kbps=get_mp3_bitrate())
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "書き出し", f"書き出しに失敗しました: {e}")
                return
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"書き出し完了: {out_path}", 5000)

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
        friendly = QCheckBox("ファイル名を「プロジェクト名_Take1」形式にする")
        friendly.setChecked(get_export_use_friendly_names())
        layout.addWidget(friendly)

        # --- フォーマット選択（C） ---
        from PyQt6.QtWidgets import QComboBox, QGroupBox, QFormLayout, QDoubleSpinBox
        fmt_group = QGroupBox("フォーマット")
        fmt_form = QFormLayout(fmt_group)
        fmt_combo = QComboBox()
        fmt_combo.addItem("WAV (16bit PCM)", "wav")
        fmt_combo.addItem("FLAC (可逆圧縮)", "flac")
        fmt_combo.addItem("MP3 (CBR)", "mp3")
        default_fmt = get_export_format()
        fmt_idx = {"wav": 0, "flac": 1, "mp3": 2}.get(default_fmt, 0)
        fmt_combo.setCurrentIndex(fmt_idx)
        fmt_form.addRow("出力形式:", fmt_combo)

        mp3_combo = QComboBox()
        for br in (128, 192, 256, 320):
            mp3_combo.addItem(f"{br} kbps", br)
        current_br = get_mp3_bitrate()
        for i in range(mp3_combo.count()):
            if mp3_combo.itemData(i) == current_br:
                mp3_combo.setCurrentIndex(i)
                break
        mp3_combo.setEnabled(default_fmt == "mp3")
        fmt_form.addRow("MP3 ビットレート:", mp3_combo)
        fmt_combo.currentIndexChanged.connect(
            lambda _i: mp3_combo.setEnabled(fmt_combo.currentData() == "mp3")
        )
        layout.addWidget(fmt_group)

        # --- 後処理オプション（A/B） ---
        post_group = QGroupBox("書き出し前処理")
        post_form = QFormLayout(post_group)
        chk_noise = QCheckBox("ノイズ除去を適用する")
        chk_noise.setChecked(get_export_apply_noise_reduce())
        chk_noise.setToolTip("先頭 0.5 秒をノイズプロファイルとしてスペクトルサブトラクションを適用")
        post_form.addRow(chk_noise)
        chk_trim = QCheckBox("前後の無音をトリムする")
        chk_trim.setChecked(get_export_apply_trim_silence())
        chk_trim.setToolTip("閾値 -45 dBFS を下回る区間を先頭/末尾からカット（前後 80ms の余白あり）")
        post_form.addRow(chk_trim)
        chk_lufs = QCheckBox("LUFS ラウドネス正規化を適用する")
        chk_lufs.setChecked(get_export_apply_lufs())
        post_form.addRow(chk_lufs)
        lufs_spin = QDoubleSpinBox()
        lufs_spin.setRange(-30.0, -6.0)
        lufs_spin.setDecimals(1)
        lufs_spin.setSingleStep(1.0)
        lufs_spin.setValue(float(get_lufs_target()))
        lufs_spin.setSuffix(" LUFS")
        lufs_spin.setToolTip("目標ラウドネス。-16: YouTube/Spotify, -14: Apple Music, -23: 放送基準")
        lufs_spin.setEnabled(chk_lufs.isChecked())
        chk_lufs.toggled.connect(lufs_spin.setEnabled)
        post_form.addRow("目標ラウドネス:", lufs_spin)
        layout.addWidget(post_group)

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

        chosen_fmt = fmt_combo.currentData() or "wav"
        chosen_bitrate = int(mp3_combo.currentData() or 192)
        chosen_lufs = float(lufs_spin.value())
        do_nr = chk_noise.isChecked()
        do_trim = chk_trim.isChecked()
        do_lufs = chk_lufs.isChecked()
        set_export_format(chosen_fmt)
        set_mp3_bitrate(chosen_bitrate)
        set_lufs_target(chosen_lufs)
        set_export_apply_noise_reduce(do_nr)
        set_export_apply_trim_silence(do_trim)
        set_export_apply_lufs(do_lufs)

        dest = QFileDialog.getExistingDirectory(
            self, "エクスポート先を選択", directory=get_export_last_dir() or ""
        )
        if not dest:
            return
        set_export_last_dir(dest)

        # 重い処理はウェイトカーソルにして体感フリーズを減らす
        from PyQt6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            try:
                paths = storage.export_takes(
                    self._project.project_dir,
                    take_ids,
                    dest,
                    use_friendly_names=friendly.isChecked(),
                    name_template=get_export_name_template() or None,
                    fmt=chosen_fmt,
                    mp3_bitrate_kbps=chosen_bitrate,
                    do_noise_reduce=do_nr,
                    do_trim_silence=do_trim,
                    do_lufs_normalize=do_lufs,
                    target_lufs=chosen_lufs,
                )
            except OSError as e:
                QMessageBox.warning(self, "エクスポート", str(e))
                return
        finally:
            QApplication.restoreOverrideCursor()
        dest_path = str(Path(paths[0]).parent) if paths else ""
        summary = []
        summary.append(f"形式: {chosen_fmt.upper()}")
        if do_nr:
            summary.append("ノイズ除去")
        if do_trim:
            summary.append("無音トリム")
        if do_lufs:
            summary.append(f"{chosen_lufs:.1f} LUFS 正規化")
        detail = f"（{' / '.join(summary)}）" if summary else ""
        msg = f"{len(paths)} 件をエクスポートしました{detail}。" + (f"\n保存先: {dest_path}" if dest_path else "")
        QMessageBox.information(self, "エクスポート", msg)