"""
台本エリアを行番号ガター付きで表示するウィジェット。
"""
import typing
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPlainTextEdit


class LineNumberArea(QWidget):
    """QPlainTextEdit の左側に行番号を描画するガター。"""

    def __init__(self, script_edit: QPlainTextEdit, parent: QWidget | None = None):
        super().__init__(parent)
        self._script_edit = script_edit
        self.setObjectName("lineNumberArea")

    def sizeHint(self) -> QSize:
        digits = 1
        count = min(max(1, self._script_edit.document().blockCount()), 99999)
        while count >= 10:
            digits += 1
            count //= 10
        char_width = self.fontMetrics().horizontalAdvance("9")
        return QSize(char_width * digits + 8, 0)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.palette().color(self.backgroundRole()))
        painter.setPen(self.palette().color(self.foregroundRole()))
        block = self._script_edit.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self._script_edit.blockBoundingGeometry(block).translated(self._script_edit.contentOffset()).top())
        bottom = top + round(self._script_edit.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(0, top, self.width() - 4, self._script_edit.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self._script_edit.blockBoundingRect(block).height())
            block_number += 1


class ScriptEditWithLineNumbers(QWidget):
    """
    左に行番号ガター、右に台本テキストを持つコンテナ。
    script_edit() で内部の QPlainTextEdit を取得して接続・設定する。
    """

    def __init__(self, parent: QWidget | None = None, script_edit_factory: typing.Callable[[QWidget], QPlainTextEdit] | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._script_edit = script_edit_factory(self) if script_edit_factory else QPlainTextEdit(self)
        self._line_number_area = LineNumberArea(self._script_edit, self)
        layout.addWidget(self._line_number_area)
        layout.addWidget(self._script_edit)

        self._script_edit.blockCountChanged.connect(self._update_line_number_area_width)
        self._script_edit.updateRequest.connect(self._update_line_number_area)
        self._script_edit.verticalScrollBar().valueChanged.connect(lambda: self._line_number_area.update())

        self._update_line_number_area_width(0)

    def _update_line_number_area_width(self, _count: int) -> None:
        w = self._line_number_area.sizeHint().width()
        self._line_number_area.setFixedWidth(w)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self._script_edit.viewport().rect()):
            self._update_line_number_area_width(0)

    def script_edit(self) -> QPlainTextEdit:
        return self._script_edit

    def line_number_area(self) -> QWidget:
        return self._line_number_area