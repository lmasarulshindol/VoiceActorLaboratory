"""
設定ダイアログ。テーマ・フォント・波形デザイン等を変更する。
"""
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QFormLayout,
)
from src.ui.settings import get_waveform_design, set_waveform_design
from src.ui.waveform_widget import WAVEFORM_DESIGN_NAMES


class SettingsDialog(QDialog):
    """設定画面。OK で保存し、キャンセルで破棄。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("設定")
        layout = QVBoxLayout(self)

        # 波形デザイン
        wave_group = QGroupBox("波形表示")
        wave_layout = QFormLayout(wave_group)
        self._waveform_combo = QComboBox()
        self._waveform_combo.addItems(WAVEFORM_DESIGN_NAMES)
        self._waveform_combo.setCurrentIndex(get_waveform_design())
        self._waveform_combo.setToolTip("録音・再生時の波形の見た目を選べます")
        wave_layout.addRow("波形デザイン:", self._waveform_combo)
        layout.addWidget(wave_group)

        # ボタン
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        set_waveform_design(self._waveform_combo.currentIndex())
        self.accept()
