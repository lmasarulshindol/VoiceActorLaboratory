"""sample_loader のテスト。"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stream_soundboard.sample_loader import (
    SampleLoaderError,
    _convert_channels,
    _linear_resample,
    load_audio,
)


def _write_wav(
    path: Path,
    *,
    rate: int = 8000,
    channels: int = 1,
    duration_ms: int = 100,
    amplitude: float = 0.5,
) -> Path:
    """テスト用の正弦波 WAV を書き出す。"""
    n = max(1, int(rate * duration_ms / 1000))
    t = np.arange(n, dtype=np.float64) / rate
    mono = (amplitude * np.sin(2 * np.pi * 440.0 * t) * 32767.0).astype(np.int16)

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        if channels == 1:
            wf.writeframes(mono.tobytes())
        else:
            # L=信号, R=-信号（ステレオ判別しやすい）
            frames = np.empty(n * channels, dtype=np.int16)
            for c in range(channels):
                sign = 1 if c % 2 == 0 else -1
                frames[c::channels] = (mono * sign).astype(np.int16)
            wf.writeframes(frames.tobytes())
    return path


def _wav_to_float32(path: Path) -> tuple[np.ndarray, int]:
    """wave モジュールで float32 に読み込む（soundfile の代替）。"""
    with wave.open(str(path), "r") as wf:
        nch = wf.getnchannels()
        sr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        data = data.reshape(-1, nch)
    return data, sr


@pytest.fixture
def mock_soundfile_read():
    """soundfile.read を wave ベースの実装に差し替える。"""

    def _read(path, dtype="float32", always_2d=False):
        data, sr = _wav_to_float32(Path(path))
        if always_2d and data.ndim == 1:
            data = data.reshape(-1, 1)
        return data.astype(np.float32), sr

    sf = MagicMock()
    sf.read.side_effect = _read
    with patch.dict("sys.modules", {"soundfile": sf}):
        # sample_loader 内の import soundfile がこのモックを使う
        yield sf


class TestLoadAudioBasic:
    def test_存在しないファイルはエラー(self, tmp_path: Path):
        with pytest.raises(SampleLoaderError, match="見つかりません"):
            load_audio(tmp_path / "missing.wav")

    def test_ディレクトリはエラー(self, tmp_path: Path):
        with pytest.raises(SampleLoaderError, match="ファイルではありません"):
            load_audio(tmp_path)

    def test_モノラルWAVを読める(self, tmp_path: Path, mock_soundfile_read):
        path = _write_wav(tmp_path / "mono.wav", rate=8000, channels=1, duration_ms=50)
        data = load_audio(path, target_sr=8000, target_channels=1)
        assert data.dtype == np.float32
        assert data.ndim == 1
        assert data.shape[0] == pytest.approx(8000 * 0.05, abs=2)
        assert np.max(np.abs(data)) > 0.1  # 無音でない

    def test_ステレオをモノラルに変換(self, tmp_path: Path, mock_soundfile_read):
        path = _write_wav(tmp_path / "stereo.wav", rate=8000, channels=2, duration_ms=50)
        data = load_audio(path, target_sr=8000, target_channels=1)
        assert data.ndim == 1
        # L と R が逆位相なので平均はほぼ 0
        assert np.max(np.abs(data)) < 1e-3

    def test_モノラルをステレオに変換(self, tmp_path: Path, mock_soundfile_read):
        path = _write_wav(tmp_path / "mono.wav", rate=8000, channels=1, duration_ms=50)
        data = load_audio(path, target_sr=8000, target_channels=2)
        assert data.ndim == 2
        assert data.shape[1] == 2
        np.testing.assert_allclose(data[:, 0], data[:, 1])

    def test_リサンプルで長さが変わる(self, tmp_path: Path, mock_soundfile_read):
        path = _write_wav(tmp_path / "mono.wav", rate=8000, channels=1, duration_ms=100)
        data = load_audio(path, target_sr=16000, target_channels=1)
        # 100ms @ 16kHz ≈ 1600 samples
        assert data.shape[0] == pytest.approx(1600, abs=2)

    def test_ピーク正規化はしない(self, tmp_path: Path, mock_soundfile_read):
        path = _write_wav(
            tmp_path / "quiet.wav",
            rate=8000,
            channels=1,
            duration_ms=50,
            amplitude=0.1,
        )
        data = load_audio(path, target_sr=8000, target_channels=1)
        peak = float(np.max(np.abs(data)))
        assert peak < 0.2  # 正規化されて 1.0 近くになっていない


class TestConvertChannels:
    def test_モノラル配列はそのまま(self):
        x = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        out = _convert_channels(x, 1)
        np.testing.assert_array_equal(out, x)

    def test_ステレオからモノラルは平均(self):
        x = np.array([[1.0, 3.0], [2.0, 4.0]], dtype=np.float32)
        out = _convert_channels(x, 1)
        np.testing.assert_allclose(out, [2.0, 3.0])

    def test_不正なチャンネル数はエラー(self):
        with pytest.raises(SampleLoaderError, match="target_channels"):
            _convert_channels(np.zeros(4, dtype=np.float32), 0)


class TestLinearResample:
    def test_同じレートなら長さ不変(self):
        x = np.linspace(-1, 1, 100, dtype=np.float32)
        out = _linear_resample(x, 48000, 48000)
        assert out.shape == x.shape
        np.testing.assert_array_equal(out, x)

    def test_アップサンプルで長さが増える(self):
        x = np.linspace(0, 1, 10, dtype=np.float32)
        out = _linear_resample(x, 1000, 2000)
        assert out.shape[0] == 20

    def test_ダウンサンプルで長さが減る(self):
        x = np.linspace(0, 1, 20, dtype=np.float32)
        out = _linear_resample(x, 2000, 1000)
        assert out.shape[0] == 10


class TestFfmpegFallback:
    def test_soundfile失敗かつffmpeg無しなら分かりやすいエラー(
        self, tmp_path: Path
    ):
        path = tmp_path / "fake.mp3"
        path.write_bytes(b"not a real mp3")

        sf = MagicMock()
        sf.read.side_effect = RuntimeError("unsupported")

        with patch.dict("sys.modules", {"soundfile": sf}):
            with patch(
                "stream_soundboard.sample_loader.shutil.which",
                return_value=None,
            ):
                with pytest.raises(SampleLoaderError, match="ffmpeg"):
                    load_audio(path)
