"""
マイク入力レベルを横バーで可視化するウィジェット。

デザイン方針:
- 横長に並ぶ dB メーター。値 0.0〜1.0 をそのままバー幅比に反映する。
- 緑 (〜-12dBFS) / 黄 (-12〜-3dBFS) / 赤 (-3dBFS〜0dBFS) のグラデ。
- ピークホールドは 1.5 秒保持し、点線でマークする。
- 入力が来ない/無音でも 0 表示で描画コストを抑える。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtProperty
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget


def _amp_to_dbfs(amp: float) -> float:
    """振幅比（0〜1）を dBFS に変換。0 は -90 に丸める。"""
    import math
    if amp <= 1e-5:
        return -90.0
    return 20.0 * math.log10(max(amp, 1e-5))


class LevelMeterWidget(QWidget):
    """1〜2 色のグラデーション横バー＋ピークホールド付きの入力レベルメーター。"""

    _PEAK_HOLD_MS = 1500
    _DB_MIN = -60.0
    _DB_MAX = 3.0  # 0dBFS 少し上まで

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rms = 0.0
        self._peak = 0.0
        self._peak_hold = 0.0
        self._peak_hold_age = 0
        self._dark = False
        self.setMinimumHeight(14)
        self.setMaximumHeight(18)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._peak_decay_timer = QTimer(self)
        self._peak_decay_timer.timeout.connect(self._on_decay_tick)
        self._peak_decay_timer.start(100)  # 100ms 毎にピーク減衰タイマ

    def set_dark_theme(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.update()

    def set_levels(self, peak: float, rms: float) -> None:
        """peak / rms（いずれも 0.0〜1.0）を更新する。"""
        peak = max(0.0, min(1.0, float(peak)))
        rms = max(0.0, min(1.0, float(rms)))
        self._peak = peak
        self._rms = rms
        if peak >= self._peak_hold:
            self._peak_hold = peak
            self._peak_hold_age = 0
        self.update()

    def _on_decay_tick(self) -> None:
        self._peak_hold_age += 100
        if self._peak_hold_age >= self._PEAK_HOLD_MS:
            # ピーク値を徐々に落とす
            self._peak_hold = max(0.0, self._peak_hold - 0.02)
            if self._peak_hold <= 0.001:
                self._peak_hold = 0.0
                self._peak_hold_age = 0
        self.update()

    def _dbfs_to_x(self, dbfs: float, width: int) -> int:
        if width <= 0:
            return 0
        ratio = (dbfs - self._DB_MIN) / (self._DB_MAX - self._DB_MIN)
        ratio = max(0.0, min(1.0, ratio))
        return int(ratio * width)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect().adjusted(1, 2, -1, -2)
        # 背景
        bg = QColor("#1c1c1c") if self._dark else QColor("#e6e6e6")
        painter.fillRect(rect, bg)
        # グラデーション（緑→黄→赤）
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        grad.setColorAt(0.0, QColor("#2bbf5b"))
        grad.setColorAt(0.55, QColor("#2bbf5b"))
        grad.setColorAt(0.78, QColor("#f4c237"))
        grad.setColorAt(0.92, QColor("#e8543c"))
        grad.setColorAt(1.0, QColor("#e8543c"))
        # RMS バーを描画
        rms_db = _amp_to_dbfs(self._rms)
        peak_db = _amp_to_dbfs(self._peak)
        hold_db = _amp_to_dbfs(self._peak_hold)
        w = rect.width()
        rms_x = self._dbfs_to_x(rms_db, w)
        peak_x = self._dbfs_to_x(peak_db, w)
        # RMS は濃いめ、peak は半透明で上に重ねる
        painter.save()
        painter.setClipRect(rect.left(), rect.top(), rms_x, rect.height())
        painter.fillRect(rect, grad)
        painter.restore()
        # peak（薄く）
        if peak_x > rms_x:
            painter.save()
            painter.setClipRect(rect.left() + rms_x, rect.top(), peak_x - rms_x, rect.height())
            painter.setOpacity(0.45)
            painter.fillRect(rect, grad)
            painter.setOpacity(1.0)
            painter.restore()
        # ピークホールド: 縦線
        if self._peak_hold > 0.001:
            hold_x = self._dbfs_to_x(hold_db, w)
            pen = QPen(QColor("#ffffff") if self._dark else QColor("#222"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(rect.left() + hold_x, rect.top(), rect.left() + hold_x, rect.bottom())
        # 0dBFS / -6 / -18 の目盛線
        pen = QPen(QColor(255, 255, 255, 60) if self._dark else QColor(0, 0, 0, 60))
        pen.setWidth(1)
        painter.setPen(pen)
        for db in (-18.0, -6.0, 0.0):
            x = rect.left() + self._dbfs_to_x(db, w)
            painter.drawLine(x, rect.top(), x, rect.bottom())
        painter.end()
