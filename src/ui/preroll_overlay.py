"""
録音開始前のカウントダウンを表示するオーバーレイウィジェット。

メインウィンドウの上に乗せ、3-2-1 のカウントを大きな数字で描画する。
カウント終了時に ``finished`` シグナル風の callback（``on_finished``）を呼ぶ。
キャンセル（Esc や中断）時は ``on_cancelled`` を呼ぶ。
"""
from __future__ import annotations

import typing

from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter
from PyQt6.QtWidgets import QWidget


class PrerollOverlay(QWidget):
    """親ウィジェットに重なるフルサイズの半透明オーバーレイ。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._remaining = 0
        self._total = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._on_finished: typing.Callable[[], None] | None = None
        self._on_cancelled: typing.Callable[[], None] | None = None
        self._active = False
        self.hide()
        # 親ウィジェットの resize を追従するため eventFilter を仕掛ける
        parent.installEventFilter(self)
        self._fit_to_parent()

    @property
    def active(self) -> bool:
        return self._active

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._fit_to_parent()
        return super().eventFilter(obj, event)

    def _fit_to_parent(self) -> None:
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(0, 0, p.width(), p.height())

    def start(
        self,
        seconds: int,
        on_finished: typing.Callable[[], None],
        on_cancelled: typing.Callable[[], None] | None = None,
    ) -> None:
        """カウントダウンを開始する。``seconds`` が 0 以下なら即 on_finished を呼ぶ。"""
        self._on_finished = on_finished
        self._on_cancelled = on_cancelled
        if seconds <= 0:
            cb = on_finished
            cb()
            return
        self._total = seconds
        self._remaining = seconds
        self._active = True
        self._fit_to_parent()
        self.raise_()
        self.show()
        self.setFocus()
        self.update()
        self._timer.start(1000)

    def cancel(self) -> None:
        """カウントダウンを中止する。"""
        if not self._active:
            return
        self._stop()
        if self._on_cancelled:
            cb = self._on_cancelled
            self._on_cancelled = None
            cb()

    def _stop(self) -> None:
        self._timer.stop()
        self._active = False
        self.hide()

    def _on_tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            cb = self._on_finished
            self._stop()
            self._on_finished = None
            self._on_cancelled = None
            if cb is not None:
                cb()
            return
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # オーバーレイ表示中はクリックでキャンセル
        self.cancel()
        event.accept()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 半透明の暗幕
        painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
        # 中央に大きな数字
        text = str(self._remaining)
        font = QFont(self.font())
        base_size = min(self.width(), self.height())
        font.setPointSizeF(max(40.0, base_size * 0.25))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
        # サブ文言
        sub_font = QFont(self.font())
        sub_font.setPointSizeF(max(12.0, base_size * 0.025))
        sub_font.setBold(False)
        painter.setFont(sub_font)
        painter.setPen(QColor(255, 255, 255, 200))
        sub_rect = self.rect().adjusted(0, int(base_size * 0.18), 0, 0)
        painter.drawText(
            sub_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "録音開始まで…（クリックまたは Esc でキャンセル）",
        )
        painter.end()
