"""
台本エリアを行番号ガター付きで表示するウィジェット。

行番号の右側にテイク数／採用マークのミニインジケーターを描画できる（C1）。
"""
import typing
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPlainTextEdit


class LineNumberArea(QWidget):
    """QPlainTextEdit の左側に行番号＋テイク数インジケーターを描画するガター。

    左端にカーソル行を示す色付き「●」マーカーを描画する（選択行の視認性向上）。
    """

    # 行番号 + [ ●3 ][ ✓ ] 分の余白を取るための定数
    _INDICATOR_WIDTH = 34
    # カーソル行●マーカー用にガター左端で確保する幅
    _CURSOR_DOT_AREA = 12

    def __init__(self, script_edit: QPlainTextEdit, parent: QWidget | None = None):
        super().__init__(parent)
        self._script_edit = script_edit
        self.setObjectName("lineNumberArea")
        # 行ごとのテイク数・採用フラグ（1-based の行番号をキー）
        self._line_take_counts: dict[int, int] = {}
        self._line_adopted: set[int] = set()
        # カーソル行（1-based）。None でマーカーなし。
        self._current_line: int | None = None
        self.setMouseTracking(True)

    def set_line_take_info(self, take_counts: dict[int, int], adopted_lines: set[int]) -> None:
        """行ごとのテイク件数と採用済み行を設定してガターを再描画する。"""
        self._line_take_counts = dict(take_counts or {})
        self._line_adopted = set(adopted_lines or set())
        self.update()

    def set_current_line(self, line_number: int | None) -> None:
        """カーソル行（1-based）を設定してマーカーを再描画する。None で非表示。"""
        if self._current_line == line_number:
            return
        self._current_line = line_number
        self.update()

    def sizeHint(self) -> QSize:
        digits = 1
        count = min(max(1, self._script_edit.document().blockCount()), 99999)
        while count >= 10:
            digits += 1
            count //= 10
        char_width = self.fontMetrics().horizontalAdvance("9")
        indicator = self._INDICATOR_WIDTH if (self._line_take_counts or self._line_adopted) else 0
        return QSize(self._CURSOR_DOT_AREA + char_width * digits + 8 + indicator, 0)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(event.rect(), self.palette().color(self.backgroundRole()))
        painter.setPen(self.palette().color(self.foregroundRole()))
        block = self._script_edit.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self._script_edit.blockBoundingGeometry(block).translated(self._script_edit.contentOffset()).top())
        bottom = top + round(self._script_edit.blockBoundingRect(block).height())
        fm = self._script_edit.fontMetrics()
        line_h = fm.height()
        indicator_w = self._INDICATOR_WIDTH if (self._line_take_counts or self._line_adopted) else 0
        dot_area = self._CURSOR_DOT_AREA
        number_left = dot_area
        number_right = self.width() - indicator_w - 4
        # 色準備（パレット依存）
        fg = self.palette().color(self.foregroundRole())
        dim = QColor(fg)
        dim.setAlpha(150)
        accent = QColor("#2f7cff")
        adopted_color = QColor("#2bbf5b")
        cursor_dot_color = QColor("#ff7a29")  # カーソル行用: 暖色オレンジ
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_no = block_number + 1
                # カーソル行マーカー（ガター左端の塗り潰し●）
                if self._current_line is not None and line_no == self._current_line:
                    dot_r = max(3, min(line_h // 3, 5))
                    cx = 2 + dot_r
                    cy = top + line_h // 2
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(cursor_dot_color)
                    painter.drawEllipse(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2)
                number = str(line_no)
                painter.setPen(fg)
                painter.drawText(
                    number_left,
                    top,
                    max(0, number_right - number_left),
                    line_h,
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
                if indicator_w > 0:
                    icon_x = number_right + 4
                    icon_y = top
                    take_count = self._line_take_counts.get(line_no, 0)
                    if take_count > 0:
                        painter.setPen(accent)
                        badge = f"●{take_count}"
                        painter.drawText(
                            icon_x,
                            icon_y,
                            indicator_w - 12,
                            line_h,
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            badge,
                        )
                    if line_no in self._line_adopted:
                        painter.setPen(adopted_color)
                        painter.drawText(
                            icon_x,
                            icon_y,
                            indicator_w,
                            line_h,
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                            "✓",
                        )
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

    def line_number_area(self) -> LineNumberArea:
        return self._line_number_area

    def set_line_take_info(self, take_counts: dict[int, int], adopted_lines: set[int]) -> None:
        """行ごとのテイク数・採用マーカーを更新。行番号エリアの幅も再計算する。"""
        self._line_number_area.set_line_take_info(take_counts, adopted_lines)
        self._update_line_number_area_width(0)

    def set_current_script_line(self, line_number: int | None) -> None:
        """カーソル行（1-based）のガターマーカーを更新する。None で非表示。"""
        self._line_number_area.set_current_line(line_number)

    def refresh_line_number_area_width(self) -> None:
        """フォントサイズ変更などで行番号エリアの幅を再計算する。"""
        self._update_line_number_area_width(0)