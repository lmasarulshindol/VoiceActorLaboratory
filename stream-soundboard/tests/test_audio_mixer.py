"""AudioMixer の単体テスト（実デバイス不要）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stream_soundboard.audio_mixer import AudioMixer, AudioMixerError


@pytest.fixture
def mixer() -> AudioMixer:
    return AudioMixer(sample_rate=48000, channels=1, blocksize=4)


class TestAudioMixerInit:
    def test_デフォルトパラメータ(self):
        m = AudioMixer()
        assert m.sample_rate == 48000
        assert m.channels == 1
        assert m.blocksize == 1024
        assert m.is_running() is False
        assert m.active_playback_count() == 0

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"sample_rate": 0},
            {"channels": 0},
            {"blocksize": -1},
        ],
    )
    def test_不正な初期化はValueError(self, kwargs):
        with pytest.raises(ValueError):
            AudioMixer(**kwargs)


class TestVolumeAndMute:
    def test_マイク音量クランプ(self, mixer: AudioMixer):
        assert mixer.set_mic_volume(1.5) == 1.0
        assert mixer.set_mic_volume(-0.5) == 0.0
        assert mixer.set_mic_volume(0.3) == pytest.approx(0.3)

    def test_再生音量クランプ(self, mixer: AudioMixer):
        assert mixer.set_playback_volume(2.0) == 1.0
        assert mixer.set_playback_volume(-1.0) == 0.0

    def test_ミュート時マイクはゼロ(self, mixer: AudioMixer):
        mixer.set_mic_volume(1.0)
        mixer.set_mic_muted(True)
        mic = np.ones(4, dtype=np.float32) * 0.5
        out = mixer._mix_block(mic)
        assert np.allclose(out, 0.0)

    def test_ミュート解除でマイク復帰(self, mixer: AudioMixer):
        mixer.set_mic_volume(0.5)
        mixer.set_mic_muted(True)
        mixer.set_mic_muted(False)
        mic = np.ones(4, dtype=np.float32)
        out = mixer._mix_block(mic)
        assert np.allclose(out.ravel(), 0.5)

    def test_マイク音量反映(self, mixer: AudioMixer):
        mixer.set_mic_volume(0.25)
        mic = np.ones(4, dtype=np.float32)
        out = mixer._mix_block(mic)
        assert np.allclose(out.ravel(), 0.25)

    def test_再生音量反映(self, mixer: AudioMixer):
        mixer.set_mic_volume(0.0)
        mixer.set_playback_volume(0.5)
        samples = np.ones(4, dtype=np.float32)
        mixer.play(samples, gain=1.0)
        out = mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert np.allclose(out.ravel(), 0.5)


class TestMixBlock:
    def test_マイクのみ(self, mixer: AudioMixer):
        mic = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        out = mixer._mix_block(mic)
        assert out.shape == (4, 1)
        assert np.allclose(out.ravel(), mic)

    def test_再生とマイク合算(self, mixer: AudioMixer):
        mixer.set_mic_volume(1.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.full(4, 0.2, dtype=np.float32), gain=1.0)
        mic = np.full(4, 0.3, dtype=np.float32)
        out = mixer._mix_block(mic)
        assert np.allclose(out.ravel(), 0.5)

    def test_gain反映(self, mixer: AudioMixer):
        mixer.set_mic_volume(0.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.full(4, 0.4, dtype=np.float32), gain=0.5)
        out = mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert np.allclose(out.ravel(), 0.2)

    def test_クリップ(self, mixer: AudioMixer):
        mixer.set_mic_volume(1.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.full(4, 0.8, dtype=np.float32), gain=1.0)
        mic = np.full(4, 0.8, dtype=np.float32)
        out = mixer._mix_block(mic)
        assert np.all(out <= 1.0)
        assert np.all(out >= -1.0)
        assert np.allclose(out.ravel(), 1.0)

    def test_負側クリップ(self, mixer: AudioMixer):
        mixer.set_mic_volume(1.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.full(4, -0.8, dtype=np.float32), gain=1.0)
        mic = np.full(4, -0.8, dtype=np.float32)
        out = mixer._mix_block(mic)
        assert np.allclose(out.ravel(), -1.0)

    def test_2Dマイク入力(self, mixer: AudioMixer):
        mic = np.ones((4, 1), dtype=np.float32) * 0.5
        out = mixer._mix_block(mic)
        assert np.allclose(out, 0.5)


class TestPlaybackQueue:
    def test_playはIDを返しカウント増(self, mixer: AudioMixer):
        pid = mixer.play(np.ones(8, dtype=np.float32))
        assert isinstance(pid, int)
        assert mixer.active_playback_count() == 1

    def test_複数同時再生(self, mixer: AudioMixer):
        mixer.set_mic_volume(0.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.full(4, 0.1, dtype=np.float32), gain=1.0)
        mixer.play(np.full(4, 0.2, dtype=np.float32), gain=1.0)
        assert mixer.active_playback_count() == 2
        out = mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert np.allclose(out.ravel(), 0.3)

    def test_再生終了でカウント減(self, mixer: AudioMixer):
        mixer.play(np.ones(4, dtype=np.float32), loop=False)
        mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert mixer.active_playback_count() == 0

    def test_ループ再生(self, mixer: AudioMixer):
        mixer.set_mic_volume(0.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.array([0.5, 0.5], dtype=np.float32), loop=True)
        out1 = mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert np.allclose(out1.ravel(), 0.5)
        assert mixer.active_playback_count() == 1
        out2 = mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert np.allclose(out2.ravel(), 0.5)
        assert mixer.active_playback_count() == 1

    def test_stop_play(self, mixer: AudioMixer):
        pid = mixer.play(np.ones(100, dtype=np.float32), loop=True)
        mixer.stop_play(pid)
        assert mixer.active_playback_count() == 0
        out = mixer._mix_block(np.zeros(4, dtype=np.float32))
        assert np.allclose(out, 0.0)

    def test_stop_all_playback(self, mixer: AudioMixer):
        mixer.play(np.ones(100, dtype=np.float32), loop=True)
        mixer.play(np.ones(100, dtype=np.float32), loop=True)
        mixer.stop_all_playback()
        assert mixer.active_playback_count() == 0

    def test_空サンプルはエラー(self, mixer: AudioMixer):
        with pytest.raises(AudioMixerError, match="空"):
            mixer.play(np.array([], dtype=np.float32))

    def test_ステレオサンプルをモノラルへ(self):
        m = AudioMixer(channels=1, blocksize=4)
        m.set_mic_volume(0.0)
        # L=0.2, R=0.4 → 平均 0.3
        stereo = np.column_stack(
            [np.full(4, 0.2, dtype=np.float32), np.full(4, 0.4, dtype=np.float32)]
        )
        m.play(stereo)
        out = m._mix_block(np.zeros(4, dtype=np.float32))
        assert out.shape == (4, 1)
        assert np.allclose(out.ravel(), 0.3)

    def test_モノラルサンプルをステレオへ(self):
        m = AudioMixer(channels=2, blocksize=4)
        m.set_mic_volume(0.0)
        m.play(np.full(4, 0.5, dtype=np.float32))
        out = m._mix_block(np.zeros((4, 2), dtype=np.float32))
        assert out.shape == (4, 2)
        assert np.allclose(out, 0.5)


class TestStartStop:
    def test_startでStream開始(self, mixer: AudioMixer):
        mock_stream = MagicMock()
        mock_sd = MagicMock()
        mock_sd.Stream.return_value = mock_stream

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            # 遅延import用にモジュールキャッシュを差し替え
            mixer.start(input_device=1, output_device=2)

        mock_sd.Stream.assert_called_once()
        kwargs = mock_sd.Stream.call_args.kwargs
        assert kwargs["device"] == (1, 2)
        assert kwargs["samplerate"] == 48000
        assert kwargs["channels"] == 1
        assert kwargs["blocksize"] == 4
        assert kwargs["dtype"] == "float32"
        mock_stream.start.assert_called_once()
        assert mixer.is_running() is True

    def test_既に動作中なら再起動(self, mixer: AudioMixer):
        mock_stream1 = MagicMock()
        mock_stream2 = MagicMock()
        mock_sd = MagicMock()
        mock_sd.Stream.side_effect = [mock_stream1, mock_stream2]

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mixer.start(0, 1)
            mixer.start(2, 3)

        mock_stream1.stop.assert_called()
        mock_stream1.close.assert_called()
        assert mock_sd.Stream.call_count == 2
        assert mixer.is_running() is True

    def test_stopで停止(self, mixer: AudioMixer):
        mock_stream = MagicMock()
        mock_sd = MagicMock()
        mock_sd.Stream.return_value = mock_stream

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            mixer.start(None, None)
            mixer.stop()

        mock_stream.stop.assert_called()
        mock_stream.close.assert_called()
        assert mixer.is_running() is False

    def test_start失敗はAudioMixerError(self, mixer: AudioMixer):
        mock_sd = MagicMock()
        mock_sd.Stream.side_effect = RuntimeError("no device")

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            with pytest.raises(AudioMixerError, match="開始に失敗"):
                mixer.start(0, 1)

        assert mixer.is_running() is False

    def test_コールバック経由でミックス(self, mixer: AudioMixer):
        mixer.set_mic_volume(1.0)
        mixer.set_playback_volume(1.0)
        mixer.play(np.full(4, 0.2, dtype=np.float32))
        indata = np.full((4, 1), 0.3, dtype=np.float32)
        outdata = np.zeros((4, 1), dtype=np.float32)
        mixer._stream_callback(indata, outdata, 4, None, None)
        assert np.allclose(outdata.ravel(), 0.5)
