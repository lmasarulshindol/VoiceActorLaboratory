"""
設定ダイアログ。テーマ・フォント・波形デザイン・録音モード・エクスポート等を一括で変更する。
"""
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QSpinBox,
    QLineEdit,
    QWidget,
)
from src.ui.settings import (
    get_waveform_design,
    set_waveform_design,
    get_theme,
    set_theme,
    get_script_font_size,
    set_script_font_size,
    get_recording_mode,
    set_recording_mode,
    get_auto_play_after_record,
    set_auto_play_after_record,
    get_export_use_friendly_names,
    set_export_use_friendly_names,
    get_confirm_before_delete_take,
    set_confirm_before_delete_take,
    get_preroll_seconds,
    set_preroll_seconds,
    get_level_meter_enabled,
    set_level_meter_enabled,
    get_export_name_template,
    set_export_name_template,
    get_app_font_size,
    set_app_font_size,
    get_lufs_target,
    set_lufs_target,
    get_auto_analyze_lufs,
    set_auto_analyze_lufs,
    get_mp3_bitrate,
    set_mp3_bitrate,
)
from src.ui.waveform_widget import WAVEFORM_DESIGN_NAMES


class SettingsDialog(QDialog):
    """設定画面。OK で保存し、キャンセルで破棄。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("設定")
        layout = QVBoxLayout(self)

        # 表示
        appearance_group = QGroupBox("表示")
        appearance_layout = QFormLayout(appearance_group)
        self._theme_combo = QComboBox()
        self._theme_combo.addItem("ライト", "light")
        self._theme_combo.addItem("ダーク", "dark")
        self._theme_combo.setCurrentIndex(
            self._theme_combo.findData(get_theme())
        )
        if self._theme_combo.currentIndex() < 0:
            self._theme_combo.setCurrentIndex(0)
        appearance_layout.addRow("テーマ:", self._theme_combo)
        self._font_spin = QSpinBox()
        self._font_spin.setRange(8, 24)
        self._font_spin.setValue(get_script_font_size())
        self._font_spin.setToolTip("台本エリアのフォントサイズ（8〜24pt）")
        appearance_layout.addRow("台本フォントサイズ:", self._font_spin)

        # アプリ全体のフォントサイズ（チェックボックスで有効化）
        current_app_font_size = get_app_font_size()
        self._app_font_override_check = QCheckBox("アプリ全体のフォントサイズを上書きする")
        self._app_font_override_check.setToolTip("オフにするとOS標準のフォントサイズに戻ります")
        self._app_font_override_check.setChecked(current_app_font_size > 0)
        self._app_font_spin = QSpinBox()
        self._app_font_spin.setRange(8, 24)
        self._app_font_spin.setValue(current_app_font_size if current_app_font_size > 0 else 10)
        self._app_font_spin.setEnabled(current_app_font_size > 0)
        self._app_font_spin.setSuffix(" pt")
        self._app_font_spin.setToolTip("アプリ全体（ボタン・メニュー・一覧）のフォントサイズ（8〜24pt）")
        self._app_font_override_check.toggled.connect(self._app_font_spin.setEnabled)

        app_font_row = QWidget()
        app_font_layout = QHBoxLayout(app_font_row)
        app_font_layout.setContentsMargins(0, 0, 0, 0)
        app_font_layout.addWidget(self._app_font_override_check)
        app_font_layout.addWidget(self._app_font_spin)
        app_font_layout.addStretch(1)
        appearance_layout.addRow("アプリ全体フォント:", app_font_row)
        layout.addWidget(appearance_group)

        # 録音
        record_group = QGroupBox("録音")
        record_layout = QFormLayout(record_group)
        self._record_mode_combo = QComboBox()
        self._record_mode_combo.addItem("台本一括", "bulk")
        self._record_mode_combo.addItem("セリフ個別", "individual")
        self._record_mode_combo.setCurrentIndex(
            self._record_mode_combo.findData(get_recording_mode())
        )
        if self._record_mode_combo.currentIndex() < 0:
            self._record_mode_combo.setCurrentIndex(0)
        record_layout.addRow("録音モード:", self._record_mode_combo)
        self._auto_play_check = QCheckBox("録音終了後に自動再生する")
        self._auto_play_check.setChecked(get_auto_play_after_record())
        record_layout.addRow("", self._auto_play_check)
        # A2: プリロール（カウントダウン）
        self._preroll_combo = QComboBox()
        self._preroll_combo.addItem("使用しない（即開始）", 0)
        self._preroll_combo.addItem("3秒カウントダウン", 3)
        self._preroll_combo.addItem("5秒カウントダウン", 5)
        current_preroll = get_preroll_seconds()
        idx = self._preroll_combo.findData(current_preroll)
        if idx >= 0:
            self._preroll_combo.setCurrentIndex(idx)
        self._preroll_combo.setToolTip("録音開始ボタン押下後にカウントダウンを挟みます（3-2-1）")
        record_layout.addRow("録音前カウントダウン:", self._preroll_combo)
        # A1: レベルメーター表示
        self._level_meter_check = QCheckBox("入力レベルメーターを常時表示する")
        self._level_meter_check.setChecked(get_level_meter_enabled())
        self._level_meter_check.setToolTip("録音していない時間もマイク入力レベルを表示します（マイクを占有します）")
        record_layout.addRow("", self._level_meter_check)
        layout.addWidget(record_group)

        # 波形デザイン
        wave_group = QGroupBox("波形表示")
        wave_layout = QFormLayout(wave_group)
        self._waveform_combo = QComboBox()
        self._waveform_combo.addItems(WAVEFORM_DESIGN_NAMES)
        self._waveform_combo.setCurrentIndex(get_waveform_design())
        self._waveform_combo.setToolTip("録音・再生時の波形の見た目を選べます")
        wave_layout.addRow("波形デザイン:", self._waveform_combo)
        layout.addWidget(wave_group)

        # テイク削除
        delete_group = QGroupBox("テイク削除")
        delete_layout = QFormLayout(delete_group)
        self._confirm_delete_check = QCheckBox("削除前に確認メッセージを表示する")
        self._confirm_delete_check.setChecked(get_confirm_before_delete_take())
        self._confirm_delete_check.setToolTip("オフにすると、テイク削除時に確認ダイアログを表示しません。再度有効にすると確認が表示されます。")
        delete_layout.addRow("", self._confirm_delete_check)
        layout.addWidget(delete_group)

        # エクスポート
        export_group = QGroupBox("エクスポート")
        export_layout = QFormLayout(export_group)
        self._export_friendly_check = QCheckBox(
            "ファイル名を「プロジェクト名_Take1.wav」形式にする（既定）"
        )
        self._export_friendly_check.setChecked(get_export_use_friendly_names())
        export_layout.addRow("", self._export_friendly_check)
        # G1: ファイル名テンプレート
        self._export_template_edit = QLineEdit()
        self._export_template_edit.setText(get_export_name_template())
        self._export_template_edit.setPlaceholderText("例: {project}_{n}_{text}")
        self._export_template_edit.setToolTip(
            "ファイル名テンプレート（空なら上のチェックボックスの設定を使用）\n"
            "使えるプレースホルダ: {project} {index} {n} {line} {text} {rating} {original}"
        )
        export_layout.addRow("命名テンプレート:", self._export_template_edit)

        # A/C: LUFS・MP3 ビットレート設定
        self._lufs_target_spin = QDoubleSpinBox()
        self._lufs_target_spin.setRange(-30.0, -6.0)
        self._lufs_target_spin.setDecimals(1)
        self._lufs_target_spin.setSingleStep(1.0)
        self._lufs_target_spin.setValue(float(get_lufs_target()))
        self._lufs_target_spin.setSuffix(" LUFS")
        self._lufs_target_spin.setToolTip(
            "エクスポート時の既定のラウドネス目標値。\n-16: YouTube/Spotify, -14: Apple Music, -23: 放送 (EBU R128)"
        )
        export_layout.addRow("既定 LUFS 目標:", self._lufs_target_spin)

        self._auto_analyze_lufs_check = QCheckBox("録音直後に LUFS を自動解析する")
        self._auto_analyze_lufs_check.setChecked(get_auto_analyze_lufs())
        self._auto_analyze_lufs_check.setToolTip("オフにすると録音後の解析をスキップし、保存速度を優先します")
        export_layout.addRow("", self._auto_analyze_lufs_check)

        self._mp3_bitrate_combo = QComboBox()
        for br in (128, 192, 256, 320):
            self._mp3_bitrate_combo.addItem(f"{br} kbps", br)
        current_br = get_mp3_bitrate()
        for i in range(self._mp3_bitrate_combo.count()):
            if self._mp3_bitrate_combo.itemData(i) == current_br:
                self._mp3_bitrate_combo.setCurrentIndex(i)
                break
        self._mp3_bitrate_combo.setToolTip("MP3 エクスポートのビットレート（高いほど高音質・ファイル大）")
        export_layout.addRow("MP3 ビットレート:", self._mp3_bitrate_combo)

        layout.addWidget(export_group)

        # ボタン
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        set_theme(self._theme_combo.currentData() or "light")
        set_script_font_size(self._font_spin.value())
        set_recording_mode(self._record_mode_combo.currentData() or "bulk")
        set_auto_play_after_record(self._auto_play_check.isChecked())
        set_waveform_design(self._waveform_combo.currentIndex())
        set_export_use_friendly_names(self._export_friendly_check.isChecked())
        set_confirm_before_delete_take(self._confirm_delete_check.isChecked())
        # 追加項目
        preroll_value = self._preroll_combo.currentData()
        set_preroll_seconds(int(preroll_value) if preroll_value is not None else 0)
        set_level_meter_enabled(self._level_meter_check.isChecked())
        set_export_name_template(self._export_template_edit.text().strip())
        # アプリ全体フォントサイズ
        if self._app_font_override_check.isChecked():
            set_app_font_size(self._app_font_spin.value())
        else:
            set_app_font_size(0)
        # A/C: LUFS・MP3
        set_lufs_target(float(self._lufs_target_spin.value()))
        set_auto_analyze_lufs(self._auto_analyze_lufs_check.isChecked())
        set_mp3_bitrate(int(self._mp3_bitrate_combo.currentData() or 192))
        self.accept()
