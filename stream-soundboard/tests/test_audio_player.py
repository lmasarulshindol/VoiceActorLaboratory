"""AudioPlayer のテスト。"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stream_soundboard.audio_player import AudioPlayer, AudioPlayerError


def _write_silent_wav(path: Path, duration_ms: int = 50) -> Path:
    rate = 8000
    n = max(1, int(rate * duration_ms / 1000))
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = struct.pack("<" + "h" * n, *([0] * n))
        wf.writeframes(frames)
    return path


@pytest.fixture
def wav_file(tmp_path: Path) -> Path:
    return _write_silent_wav(tmp_path / "beep.wav")


def _make_mixer(*, running: bool = True, play_id: int = 1) -> MagicMock:
    mixer = MagicMock()
    mixer.is_running.return_value = running
    mixer.active_playback_count.return_value = 0
    mixer.play.return_value = play_id
    mixer.sample_rate = 48000
    mixer.channels = 1
    mixer._playbacks = {}
    return mixer


class TestAudioPlayerBasics:
    def test_音量クランプ(self):
        p = AudioPlayer(volume=2.0)
        assert p.volume == 1.0
        assert p.set_volume(-1) == 0.0

    def test_存在しないファイルはエラー(self, tmp_path: Path):
        p = AudioPlayer()
        with pytest.raises(AudioPlayerError, match="見つかりません"):
            p.play(tmp_path / "missing.wav")

    def test_非対応拡張子はエラー(self, tmp_path: Path):
        f = tmp_path / "a.txt"
        f.write_text("x", encoding="utf-8")
        p = AudioPlayer()
        with pytest.raises(AudioPlayerError, match="非対応"):
            p.play(f)

    def test_ディレクトリはエラー(self, tmp_path: Path):
        p = AudioPlayer()
        with pytest.raises(AudioPlayerError, match="ファイルではありません"):
            p.play(tmp_path)


class TestAudioPlayerMixerPath:
    def test_playがload_audioとmixer_playを呼ぶ(self, wav_file: Path):
        mixer = _make_mixer(play_id=42)
        player = AudioPlayer(mixer=mixer, sample_rate=48000, channels=1)
        fake_samples = np.zeros(100, dtype=np.float32)

        with patch(
            "stream_soundboard.sample_loader.load_audio",
            return_value=fake_samples,
        ) as mock_load:
            player.play(wav_file, stop_previous=False)

        mock_load.assert_called_once_with(
            wav_file,
            target_sr=48000,
            target_channels=1,
        )
        mixer.play.assert_called_once()
        args, kwargs = mixer.play.call_args
        assert np.array_equal(args[0], fake_samples)
        assert kwargs.get("loop") is False

    def test_stop_previousでstop_all_playback(self, wav_file: Path):
        mixer = _make_mixer()
        player = AudioPlayer(mixer=mixer)
        fake_samples = np.zeros(8, dtype=np.float32)

        with patch(
            "stream_soundboard.sample_loader.load_audio",
            return_value=fake_samples,
        ):
            player.play(wav_file, stop_previous=True)

        mixer.stop_all_playback.assert_called()

    def test_set_volumeがmixerのset_playback_volumeを呼ぶ(self):
        mixer = _make_mixer()
        player = AudioPlayer(mixer=mixer, volume=0.5)
        mixer.set_playback_volume.assert_called_with(0.5)

        result = player.set_volume(0.3)
        assert result == pytest.approx(0.3)
        mixer.set_playback_volume.assert_called_with(0.3)

    def test_is_playingはactive_playback_countを見る(self):
        mixer = _make_mixer()
        mixer.active_playback_count.return_value = 2
        player = AudioPlayer(mixer=mixer)
        assert player.is_playing() is True

        mixer.active_playback_count.return_value = 0
        assert player.is_playing() is False

    def test_stopがstop_all_playbackを呼ぶ(self):
        mixer = _make_mixer()
        player = AudioPlayer(mixer=mixer)
        player.stop()
        mixer.stop_all_playback.assert_called()

    def test_mixer未起動ならフォールバック経路(self, wav_file: Path):
        mixer = _make_mixer(running=False)
        player = AudioPlayer(mixer=mixer)
        with patch.object(player, "_play_worker") as mock_worker:
            # play はスレッドで _play_worker を呼ぶので、start を差し替える
            with patch(
                "stream_soundboard.audio_player.threading.Thread"
            ) as mock_thread:
                instance = MagicMock()
                mock_thread.return_value = instance
                player.play(wav_file)
                mock_thread.assert_called_once()
                instance.start.assert_called_once()
        mixer.play.assert_not_called()


class TestAudioPlayerPlay:
    def test_wav再生完了でコールバック(self, wav_file: Path):
        p = AudioPlayer()
        done = MagicMock()
        with patch("stream_soundboard.audio_player.sys") as mock_sys:
            mock_sys.platform = "win32"
            with patch("winsound.PlaySound") as mock_ws:
                p._on_finished = done
                p._play_worker(wav_file)
                mock_ws.assert_called_once()
                done.assert_called_once()

    def test_stopはプロセスを終了(self):
        p = AudioPlayer()
        proc = MagicMock()
        proc.poll.return_value = None
        p._process = proc
        p.stop()
        proc.terminate.assert_called_once()
        assert p._process is None

    def test_is_playing_プロセス生存中(self):
        p = AudioPlayer()
        proc = MagicMock()
        proc.poll.return_value = None
        p._process = proc
        assert p.is_playing() is True
        proc.poll.return_value = 0
        assert p.is_playing() is False

    def test_build_play_command_ffplay優先(self, wav_file: Path):
        p = AudioPlayer()
        with patch("stream_soundboard.audio_player.shutil.which") as which:
            which.side_effect = lambda name: (
                "/usr/bin/ffplay" if name == "ffplay" else None
            )
            cmd = p._build_play_command(wav_file)
        assert cmd is not None
        assert cmd[0] == "ffplay"
        assert str(wav_file) in cmd
