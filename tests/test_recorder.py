"""
recorder モジュールの単体テスト。録音はモックで検証する。
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
from src.recorder import Recorder, SAMPLE_RATE


class TestRecorder:
    """Recorder のテスト。"""

    def test_初期状態は録音していない(self) -> None:
        r = Recorder()
        assert r.is_recording is False
        assert r.get_buffer_duration_seconds() == 0.0

    def test_save_to_wav_バッファが空ならFalse(self) -> None:
        r = Recorder()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            assert r.save_to_wav(path) is False
        finally:
            Path(path).unlink(missing_ok=True)

    def test_stop_は録音中でなくても例外を出さない(self) -> None:
        r = Recorder()
        r.stop()

    @patch("src.recorder.sd.InputStream")
    def test_startで録音開始_停止でバッファが空ならsaveはFalse(self, mock_input_stream: MagicMock) -> None:
        mock_input_stream.return_value = MagicMock()
        r = Recorder()
        r.start()
        assert r.is_recording is True
        r.stop()
        assert r.is_recording is False
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            assert r.save_to_wav(path) is False
        finally:
            Path(path).unlink(missing_ok=True)

    @patch("src.recorder.sd.InputStream")
    def test_stop_and_saveで停止と保存(self, mock_input_stream: MagicMock) -> None:
        mock_input_stream.return_value = MagicMock()
        r = Recorder()
        r.start()
        # 手動でバッファにデータを入れる（テスト用）
        r._buffer.append(np.zeros((1024, 1), dtype="int16"))
        r._buffer.append(np.zeros((1024, 1), dtype="int16"))
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            result = r.stop_and_save(path)
            assert result is True
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0
        finally:
            Path(path).unlink(missing_ok=True)
