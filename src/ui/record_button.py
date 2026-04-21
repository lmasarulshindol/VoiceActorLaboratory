"""
録音ボタン。録音中は脈動する赤いリングを描画する（E4）。

- クリックで ``clicked`` を発火（``QPushButton`` と同じ）。
- ``set_recording(True)`` で脈動アニメーション開始。
- ``set_paused(True)`` で脈動は止めるが赤いままにする（一時停止中）。
"""
from __future__ import annotations

from PyQt6.QtCore import (
    Qt,
    QEasingCurve,
    QPropertyAnimation,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton


class RecordButton(QAbstractButton):
    """カスタム描画の録音トグルボタン。"""

    # 互換: 既存コードで ``clicked`` にスロット接続している場合にそのまま使える。

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("recordToggleBtn")
        self.setCheckable(False)
        self.setFixedSize(56, 56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recording = False
        self._paused = False
        self._pulse = 0.0  # 0.0〜1.0
        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(900)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)

    def set_recording(self, recording: bool, paused: bool = False) -> None:
        self._recording = bool(recording)
        self._paused = bool(paused)
        if self._recording and not self._paused:
            if self._anim.state() != QPropertyAnimation.State.Running:
                self._anim.start()
        else:
            self._anim.stop()
            self._pulse = 0.0
        self.update()

    def _get_pulse(self) -> float:
        return self._pulse

    def _set_pulse(self, value: float) -> None:
        self._pulse = max(0.0, min(1.0, float(value)))
        self.update()

    pulse = pyqtProperty(float, fget=_get_pulse, fset=_set_pulse)

    def sizeHint(self):  # noqa: D401
        return super().sizeHint()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        side = min(rect.width(), rect.height())
        cx = rect.center().x()
        cy = rect.center().y()
        base_radius = side * 0.36
        # 脈動リング（録音中のみ描画）
        if self._recording and not self._paused:
            ring_radius = base_radius + (side * 0.18 * self._pulse)
            alpha = int(220 * (1.0 - self._pulse))
            pen = QPen(QColor(232, 84, 60, alpha))
            pen.setWidthF(max(1.5, 4.0 * (1.0 - self._pulse * 0.5)))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(cx - ring_radius),
                int(cy - ring_radius),
                int(ring_radius * 2),
                int(ring_radius * 2),
            )
        # メインの円
        if self._recording and self._paused:
            fill = QColor("#b0b0b0")  # 一時停止中はグレー
        elif self._recording:
            fill = QColor("#e8543c")
        elif self.isEnabled():
            fill = QColor("#c0392b")
        else:
            fill = QColor("#8a8a8a")
        painter.setBrush(fill)
        painter.setPen(QPen(QColor(0, 0, 0, 40), 1))
        painter.drawEllipse(
            int(cx - base_radius),
            int(cy - base_radius),
            int(base_radius * 2),
            int(base_radius * 2),
        )
        # 内部のアイコン（録音中は 2 本縦線＝一時停止可能、それ以外は赤丸）
        icon_color = QColor("#ffffff")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_color)
        if self._recording and not self._paused:
            # 一時停止記号
            bar_w = side * 0.06
            bar_h = side * 0.24
            gap = side * 0.05
            painter.drawRoundedRect(
                int(cx - gap - bar_w),
                int(cy - bar_h / 2),
                int(bar_w),
                int(bar_h),
                2.0,
                2.0,
            )
            painter.drawRoundedRect(
                int(cx + gap),
                int(cy - bar_h / 2),
                int(bar_w),
                int(bar_h),
                2.0,
                2.0,
            )
        else:
            # 赤丸（録音開始 or 再開）
            dot_r = side * 0.12
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(
                int(cx - dot_r),
                int(cy - dot_r),
                int(dot_r * 2),
                int(dot_r * 2),
            )
        painter.end()
