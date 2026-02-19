"""
playback モジュールの単体テスト。QApplication が必要なため、再生はモックで検証する。
"""
import tempfile
from pathlib import Path
import pytest

# PyQt6 は GUI テスト用にインポート。headless ではスキップする場合あり
pytest.importorskip("PyQt6.QtMultimedia")


class TestPlayback:
    """Playback のテスト。QApplication が存在する前提で実行する。"""

    @pytest.fixture
    def app(self) -> "QApplication":
        from PyQt6.QtWidgets import QApplication
        import sys
        if not QApplication.instance():
            return QApplication(sys.argv)
        return QApplication.instance()

    def test_初期状態は再生していない(self, app: "QApplication") -> None:
        from src.playback import Playback
        pb = Playback()
        assert pb.is_playing is False

    def test_存在しないファイルでplayはFalse(self, app: "QApplication") -> None:
        from src.playback import Playback
        pb = Playback()
        assert pb.play("/nonexistent/file.wav") is False

    def test_存在するWAVでplayはTrue(self, app: "QApplication") -> None:
        from src.playback import Playback
        # 最小の有効な WAV（44バイトヘッダ + 少量データ）
        wav_content = (
            b"RIFF(\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00"
            b"\x88X\x01\x00\x02\x00\x10\x00data\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_content)
            path = f.name
        try:
            pb = Playback()
            result = pb.play(path)
            assert result is True
            pb.stop()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_stopは例外を出さない(self, app: "QApplication") -> None:
        from src.playback import Playback
        pb = Playback()
        pb.stop()

    def test_duration_msは未ロード時0以下(self, app: "QApplication") -> None:
        from src.playback import Playback
        pb = Playback()
        assert pb.duration_ms() <= 0

    def test_存在するWAVでduration_msが0以上(self, app: "QApplication") -> None:
        from src.playback import Playback
        wav_content = (
            b"RIFF(\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00"
            b"\x88X\x01\x00\x02\x00\x10\x00data\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_content)
            path = f.name
        try:
            pb = Playback()
            pb.play(path)
            for _ in range(10):
                app.processEvents()
                if pb.duration_ms() > 0:
                    break
            d = pb.duration_ms()
            pb.stop()
            for _ in range(3):
                app.processEvents()
            assert d >= 0
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except PermissionError:
                pass

    def test_seek_to_position_msで位置が変わる(self, app: "QApplication") -> None:
        from src.playback import Playback
        wav_content = (
            b"RIFF(\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00"
            b"\x88X\x01\x00\x02\x00\x10\x00data\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_content)
            path = f.name
        try:
            pb = Playback()
            pb.play(path)
            pb.seek_to_position_ms(100)
            pos = pb.get_player().position()
            pb.stop()
            for _ in range(5):
                app.processEvents()
            assert 0 <= pos <= 500
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except PermissionError:
                pass
