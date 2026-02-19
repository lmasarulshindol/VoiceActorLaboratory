"""
waveform_widget の単体テスト。seekRequested シグナルを検証する。
"""
import numpy as np
import pytest

pytest.importorskip("PyQt6.QtWidgets")


class TestWaveformWidget:
    """WaveformWidget のテスト。"""

    @pytest.fixture
    def app(self):
        from PyQt6.QtWidgets import QApplication
        import sys
        if not QApplication.instance():
            return QApplication(sys.argv)
        return QApplication.instance()

    @pytest.fixture
    def widget(self, app):
        from src.ui.waveform_widget import WaveformWidget
        w = WaveformWidget()
        w.setFixedSize(200, 72)
        w.set_seekable(True)
        w.set_duration_seconds(1.0)
        w.set_samples(np.zeros(44100, dtype=np.float32))
        return w

    def test_seekableでクリックするとseekRequestedが発火(self, widget, app):
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt, QPoint
        received = []
        widget.seekRequested.connect(received.append)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(100, 36))
        app.processEvents()
        assert len(received) == 1
        assert 0.45 <= received[0] <= 0.55

    def test_seekableで左端クリックで0に近い(self, widget, app):
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt, QPoint
        received = []
        widget.seekRequested.connect(received.append)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(0, 36))
        app.processEvents()
        assert len(received) == 1
        assert received[0] <= 0.1

    def test_seekableで右端クリックで1に近い(self, widget, app):
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt, QPoint
        received = []
        widget.seekRequested.connect(received.append)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(199, 36))
        app.processEvents()
        assert len(received) == 1
        assert received[0] >= 0.9

    def test_seekableでなくてもクリックで発火しない(self, app):
        from src.ui.waveform_widget import WaveformWidget
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt, QPoint
        w = WaveformWidget()
        w.setFixedSize(200, 72)
        w.set_seekable(False)
        w.set_duration_seconds(1.0)
        w.set_samples(np.zeros(44100, dtype=np.float32))
        received = []
        w.seekRequested.connect(received.append)
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(100, 36))
        app.processEvents()
        assert len(received) == 0
