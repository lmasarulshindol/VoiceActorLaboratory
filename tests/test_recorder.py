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


class TestMonitorRingBuffer:
    """リアルタイム LUFS 計算のためのリングバッファ。"""

    def test_初期状態は空配列(self) -> None:
        r = Recorder()
        data = r.get_monitor_samples_mono(seconds=3.0)
        assert isinstance(data, np.ndarray)
        assert data.size == 0

    def test_update_levels経由でサンプルが積まれる(self) -> None:
        r = Recorder()
        # 0.5 秒分の float32 サンプル（モノラル）を 10 ブロックに分けて追加
        block = np.full(int(SAMPLE_RATE * 0.05), 0.1, dtype=np.float32)
        for _ in range(10):
            r._update_levels_from_block(block)
        data = r.get_monitor_samples_mono(seconds=3.0)
        # 10 ブロック × 0.05 秒 = 0.5 秒相当
        assert 0.4 < data.size / SAMPLE_RATE < 0.6

    def test_上限を超えると古い分から捨てられる(self) -> None:
        r = Recorder()
        # 上限 3.5 秒に対して 5 秒分積む
        block = np.full(int(SAMPLE_RATE * 0.5), 0.1, dtype=np.float32)
        for _ in range(10):  # 5 秒ぶん
            r._update_levels_from_block(block)
        # 上限まで丸められていること
        data = r.get_monitor_samples_mono(seconds=10.0)
        assert data.size / SAMPLE_RATE <= 3.6

    def test_秒数指定で末尾を返す(self) -> None:
        r = Recorder()
        # 最初に 0 を 1 秒、あとで 1.0 を 0.5 秒入れる → 直近 0.5 秒は 1.0 が返るはず
        zero = np.zeros(int(SAMPLE_RATE * 0.1), dtype=np.float32)
        for _ in range(10):
            r._update_levels_from_block(zero)
        one = np.full(int(SAMPLE_RATE * 0.1), 1.0, dtype=np.float32)
        for _ in range(5):
            r._update_levels_from_block(one)
        data = r.get_monitor_samples_mono(seconds=0.5)
        assert data.size > 0
        # 末尾側は 1.0 で埋まっているはず（平均が 1.0 近辺）
        assert float(np.mean(data[-int(SAMPLE_RATE * 0.1):])) > 0.9

    def test_stop_monitoringでリングがクリアされる(self) -> None:
        r = Recorder()
        block = np.full(int(SAMPLE_RATE * 0.1), 0.1, dtype=np.float32)
        for _ in range(10):
            r._update_levels_from_block(block)
        assert r.get_monitor_samples_mono().size > 0
        r.stop_monitoring()
        assert r.get_monitor_samples_mono().size == 0
