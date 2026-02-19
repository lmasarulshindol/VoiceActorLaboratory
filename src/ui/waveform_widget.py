"""
録音・再生時の音声波形を描画するウィジェット。
複数デザインから選択可能。
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QRect, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath, QMouseEvent
from PyQt6.QtWidgets import QWidget, QSizePolicy


# デザイン名（設定画面のコンボ用）
WAVEFORM_DESIGN_NAMES = [
    "クラシック（線）",
    "塗りつぶし",
    "縦棒",
    "ドット",
    "グラデーション",
    "ミラー（対称）",
    "ミニマル（細線）",
    "角丸棒",
    "ステップ",
    "グロー",
]
NUM_DESIGNS = len(WAVEFORM_DESIGN_NAMES)


def _downsample(samples: np.ndarray, width: int) -> np.ndarray:
    """幅 width 用にダウンサンプル（ブロック最大絶対値）。"""
    if len(samples) == 0 or width <= 0:
        return np.array([], dtype=np.float32)
    n = len(samples)
    block = max(1, n // width)
    out = []
    for i in range(width):
        start = int(i * n / width)
        end = min(int((i + 1) * n / width), n)
        if end > start:
            chunk = samples[start:end]
            out.append(np.max(np.abs(chunk)))
        else:
            out.append(0.0)
    return np.array(out, dtype=np.float32)


class WaveformWidget(QWidget):
    """音声サンプルを波形で表示する。録音・再生どちらにも使用。"""

    seekRequested = pyqtSignal(float)  # 0.0〜1.0 のシーク比率

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(72)
        self.setMinimumWidth(120)
        self._samples: np.ndarray = np.array([], dtype=np.float32)
        self._position_seconds: float | None = None  # 再生時は再生位置（秒）
        self._duration_seconds: float = 0.0
        self._design_id: int = 0
        self._is_dark: bool = False
        self._seekable: bool = False

    def set_samples(self, samples: np.ndarray) -> None:
        """表示するサンプル（float32, -1〜1）を設定。"""
        self._samples = np.asarray(samples, dtype=np.float32).flatten()
        self.update()

    def set_position_seconds(self, sec: float | None) -> None:
        """再生位置（秒）。None で再生ヘッド非表示。"""
        self._position_seconds = sec
        self.update()

    def get_position_seconds(self) -> float:
        """現在の再生位置（秒）。未設定時は 0.0。"""
        if self._position_seconds is None:
            return 0.0
        return self._position_seconds

    def set_duration_seconds(self, sec: float) -> None:
        """再生時の総時間（秒）。"""
        self._duration_seconds = max(0.0, sec)
        self.update()

    def set_design_id(self, design_id: int) -> None:
        """波形デザイン ID（0 〜 NUM_DESIGNS-1）。"""
        self._design_id = max(0, min(design_id, NUM_DESIGNS - 1))
        self.update()

    def set_dark_theme(self, dark: bool) -> None:
        """ダークテーマ時は True。"""
        self._is_dark = dark
        self.update()

    def set_seekable(self, enabled: bool) -> None:
        """クリック・ドラッグでシーク可能にする。再生用のみ True にすること。"""
        self._seekable = enabled
        self.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)

    def _emit_seek_from_x(self, x: int) -> None:
        if not self._seekable or self._duration_seconds <= 0:
            return
        w = self.width()
        if w <= 0:
            return
        ratio = max(0.0, min(1.0, x / w))
        self.seekRequested.emit(ratio)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_seek_from_x(int(event.position().x()))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit_seek_from_x(int(event.position().x()))

    def paintEvent(self, event: object) -> None:
        from PyQt6.QtGui import QPaintEvent
        super().paintEvent(event)
        if not isinstance(event, QPaintEvent):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        samples = self._samples
        if len(samples) == 0:
            _draw_empty(painter, w, h, self._is_dark)
            return
        # 表示用にダウンサンプル（再生時は全体、録音時は直近）
        n_show = int(self._duration_seconds * 44100) if self._duration_seconds > 0 else len(samples)
        if n_show < len(samples) and self._duration_seconds > 0:
            # 再生: 全体のうち position に合わせて表示範囲をずらすこともできるが、ここでは常に全体
            start = max(0, len(samples) - n_show)
            samples = samples[start:]
        y_vals = _downsample(samples, w)
        if len(y_vals) == 0:
            return
        center = h / 2.0
        half = (h - 4) / 2.0
        # 再生ヘッド位置（0.0〜1.0）
        head = None
        if self._position_seconds is not None and self._duration_seconds > 0:
            head = self._position_seconds / self._duration_seconds
        design = self._design_id
        if design == 0:
            _paint_classic_line(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 1:
            _paint_filled(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 2:
            _paint_bars(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 3:
            _paint_dots(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 4:
            _paint_gradient(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 5:
            _paint_mirror(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 6:
            _paint_minimal(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 7:
            _paint_rounded_bars(painter, w, h, y_vals, center, half, head, self._is_dark)
        elif design == 8:
            _paint_step(painter, w, h, y_vals, center, half, head, self._is_dark)
        else:
            _paint_glow(painter, w, h, y_vals, center, half, head, self._is_dark)
        painter.end()


def _color(dark: bool, base: str = "wave") -> QColor:
    if dark:
        if base == "wave":
            return QColor(100, 180, 255)
        if base == "fill":
            return QColor(80, 140, 220, 80)
        return QColor(220, 220, 220)
    if base == "wave":
        return QColor(50, 120, 200)
    if base == "fill":
        return QColor(100, 160, 220, 90)
    return QColor(60, 60, 60)


def _draw_empty(painter: QPainter, w: int, h: int, dark: bool) -> None:
    c = _color(dark, "bg") if dark else QColor(240, 240, 240)
    painter.fillRect(0, 0, w, h, c)
    pen = QPen(QColor(180, 180, 180) if not dark else QColor(80, 80, 80))
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.drawLine(0, h // 2, w, h // 2)


def _paint_classic_line(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(30, 30, 30) if dark else QColor(250, 250, 250))
    path = QPainterPath()
    path.moveTo(0, center)
    for i in range(len(y_vals)):
        x = i + 0.5
        y = center - y_vals[i] * half
        path.lineTo(x, y)
    path.lineTo(w, center)
    painter.setPen(QPen(_color(dark), 1.5))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.drawLine(px, 0, px, h)


def _paint_filled(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(28, 28, 28) if dark else QColor(252, 252, 252))
    path = QPainterPath()
    path.moveTo(0, center)
    for i in range(len(y_vals)):
        path.lineTo(i + 0.5, center - y_vals[i] * half)
    path.lineTo(w, center)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_color(dark, "fill")))
    painter.drawPath(path)
    painter.setPen(QPen(_color(dark), 1.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path2 = QPainterPath()
    path2.moveTo(0, center)
    for i in range(len(y_vals)):
        path2.lineTo(i + 0.5, center - y_vals[i] * half)
    painter.drawPath(path2)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.drawLine(px, 0, px, h)


def _paint_bars(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(26, 26, 26) if dark else QColor(248, 248, 248))
    bar_w = max(1, w // len(y_vals) - 1)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_color(dark)))
    for i, v in enumerate(y_vals):
        x = int(i * w / len(y_vals)) + 1
        dh = v * half
        if dh >= 0:
            painter.drawRect(x, int(center - dh), bar_w, int(dh) + 1)
        else:
            painter.drawRect(x, int(center), bar_w, int(-dh) + 1)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(px, 0, px, h)


def _paint_dots(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(28, 28, 28) if dark else QColor(250, 250, 250))
    r = 1.5
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_color(dark)))
    for i, v in enumerate(y_vals):
        x = i * w / len(y_vals) + (w / len(y_vals)) / 2
        y = center - v * half
        painter.drawEllipse(QPointF(x, y), r, r)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(px, 0, px, h)


def _paint_gradient(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(20, 20, 20) if dark else QColor(255, 255, 255))
    grad = QLinearGradient(0, 0, 0, h)
    if dark:
        grad.setColorAt(0, QColor(80, 160, 255))
        grad.setColorAt(1, QColor(40, 80, 140))
    else:
        grad.setColorAt(0, QColor(80, 140, 220))
        grad.setColorAt(1, QColor(120, 180, 255))
    path = QPainterPath()
    path.moveTo(0, center)
    for i in range(len(y_vals)):
        path.lineTo(i + 0.5, center - y_vals[i] * half)
    path.lineTo(w, center)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawPath(path)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(255, 100, 100), 2))
        painter.drawLine(px, 0, px, h)


def _paint_mirror(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(15, 15, 15) if dark else QColor(245, 245, 245))
    path = QPainterPath()
    path.moveTo(0, center)
    for i in range(len(y_vals)):
        path.lineTo(i + 0.5, center - y_vals[i] * half)
    path.lineTo(w, center)
    for i in range(len(y_vals) - 1, -1, -1):
        path.lineTo(i + 0.5, center + y_vals[i] * half)
    path.closeSubpath()
    painter.setPen(QPen(_color(dark), 1))
    painter.setBrush(QBrush(_color(dark, "fill")))
    painter.drawPath(path)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(px, 0, px, h)


def _paint_minimal(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(30, 30, 30) if dark else QColor(253, 253, 253))
    path = QPainterPath()
    path.moveTo(0, center - y_vals[0] * half)
    for i in range(1, len(y_vals)):
        path.lineTo(i * w / len(y_vals), center - y_vals[i] * half)
    painter.setPen(QPen(_color(dark), 0.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 1.5))
        painter.drawLine(px, 0, px, h)


def _paint_rounded_bars(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(27, 27, 27) if dark else QColor(249, 249, 249))
    step = w / len(y_vals)
    bar_w = max(2, int(step * 0.7))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(_color(dark)))
    for i, v in enumerate(y_vals):
        x = int(i * step + (step - bar_w) / 2)
        dh = v * half
        if abs(dh) < 1:
            continue
        r = min(bar_w / 2, abs(dh) / 2)
        if dh >= 0:
            painter.drawRoundedRect(QRect(x, int(center - dh), bar_w, int(dh) + 1), r, r)
        else:
            painter.drawRoundedRect(QRect(x, int(center), bar_w, int(-dh) + 1), r, r)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(px, 0, px, h)


def _paint_step(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(29, 29, 29) if dark else QColor(251, 251, 251))
    path = QPainterPath()
    step_x = w / len(y_vals)
    path.moveTo(0, center - y_vals[0] * half)
    for i in range(len(y_vals)):
        x = i * step_x
        y = center - y_vals[i] * half
        path.lineTo(x, y)
        if i + 1 < len(y_vals):
            path.lineTo(x + step_x, y)
    path.lineTo(w, center)
    path.lineTo(0, center)
    path.closeSubpath()
    painter.setPen(QPen(_color(dark), 1))
    painter.setBrush(QBrush(_color(dark, "fill")))
    painter.drawPath(path)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(px, 0, px, h)


def _paint_glow(
    painter: QPainter, w: int, h: int, y_vals: np.ndarray,
    center: float, half: float, head: float | None, dark: bool,
) -> None:
    painter.fillRect(0, 0, w, h, QColor(18, 18, 28) if dark else QColor(248, 250, 255))
    path = QPainterPath()
    path.moveTo(0, center - y_vals[0] * half)
    for i in range(1, len(y_vals)):
        path.lineTo(i * w / len(y_vals), center - y_vals[i] * half)
    col = _color(dark)
    for thickness in [6, 4, 2]:
        alpha = 40 - thickness * 8
        pen = QPen(QColor(col.red(), col.green(), col.blue(), alpha))
        pen.setWidth(thickness)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    painter.setPen(QPen(_color(dark), 1.5))
    painter.drawPath(path)
    if head is not None:
        px = int(head * w)
        painter.setPen(QPen(QColor(220, 80, 80), 2))
        painter.drawLine(px, 0, px, h)
