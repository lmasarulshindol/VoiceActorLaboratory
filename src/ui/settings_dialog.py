"""
設定ダイアログ。テーマ・フォント・波形デザイン・録音モード・エクスポート等を一括で変更する。
"""
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QSpinBox,
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
        self._font_spin.setRange(12, 24)
        self._font_spin.setValue(get_script_font_size())
        self._font_spin.setToolTip("台本エリアのフォントサイズ")
        appearance_layout.addRow("台本フォントサイズ:", self._font_spin)
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

        # エクスポート
        export_group = QGroupBox("エクスポート")
        export_layout = QFormLayout(export_group)
        self._export_friendly_check = QCheckBox(
            "ファイル名を「プロジェクト名_Take1.wav」形式にする（既定）"
        )
        self._export_friendly_check.setChecked(get_export_use_friendly_names())
        export_layout.addRow("", self._export_friendly_check)
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
        self.accept()
