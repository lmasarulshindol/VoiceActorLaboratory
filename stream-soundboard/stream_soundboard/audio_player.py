"""音声再生モジュール。

ミキサー (AudioMixer) が起動中なら load_audio → mixer.play を主経路とする。
ミキサー無し／未起動時は従来どおり winsound / 外部プレイヤーにフォールバックする。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from stream_soundboard.audio_mixer import AudioMixer


class AudioPlayerError(Exception):
    """再生に失敗したとき。"""


class AudioPlayer:
    """非同期で音声ファイルを再生する。

    Attributes:
        mixer: 接続中の AudioMixer（None ならフォールバック再生）
        volume: 0.0〜1.0
        sample_rate: ミキサー経路での読込目標サンプルレート
        channels: ミキサー経路での読込目標チャンネル数
    """

    SUPPORTED_SUFFIXES = {
        ".wav",
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".flac",
        ".wma",
    }

    def __init__(
        self,
        mixer: "AudioMixer | None" = None,
        volume: float = 1.0,
        sample_rate: int = 48000,
        channels: int = 1,
    ) -> None:
        self.mixer = mixer
        self.volume = max(0.0, min(1.0, float(volume)))
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._winsound_active = False
        self._on_finished: Optional[Callable[[], None]] = None
        self._mixer_play_id: Optional[int] = None
        self._poll_stop = threading.Event()
        if self.mixer is not None:
            self.mixer.set_playback_volume(self.volume)

    def set_mixer(self, mixer: "AudioMixer | None") -> None:
        """再生に使うミキサーを差し替える。"""
        self.mixer = mixer
        if self.mixer is not None:
            self.mixer.set_playback_volume(self.volume)

    def set_volume(self, volume: float) -> float:
        """音量を設定（0.0〜1.0）。ミキサーがあれば set_playback_volume も呼ぶ。"""
        self.volume = max(0.0, min(1.0, float(volume)))
        if self.mixer is not None:
            self.mixer.set_playback_volume(self.volume)
        return self.volume

    def is_playing(self) -> bool:
        """再生中かどうか。"""
        if self.mixer is not None and self.mixer.active_playback_count() > 0:
            return True
        with self._lock:
            if self._winsound_active:
                return True
            if self._process is not None and self._process.poll() is None:
                return True
            return False

    def stop(self) -> None:
        """再生中の音声を停止。"""
        self._poll_stop.set()
        with self._lock:
            self._mixer_play_id = None
        if self.mixer is not None:
            self.mixer.stop_all_playback()
        with self._lock:
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=1.5)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                self._process = None
            if self._winsound_active and sys.platform == "win32":
                try:
                    import winsound

                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass
                self._winsound_active = False

    def play(
        self,
        path: str | Path,
        on_finished: Optional[Callable[[], None]] = None,
        stop_previous: bool = True,
        loop: bool = False,
    ) -> None:
        """音声を再生開始。存在しない/非対応なら例外。

        ミキサーがあり running なら load_audio → mixer.play。
        on_finished は別スレッドで再生終了をポーリングして呼ぶ（loop 時は呼ばない）。
        ミキサー無し／未起動なら既存の winsound/外部プレイヤー経路。
        """
        file_path = Path(path)
        if not file_path.exists():
            raise AudioPlayerError(f"ファイルが見つかりません: {file_path}")
        if not file_path.is_file():
            raise AudioPlayerError(f"ファイルではありません: {file_path}")
        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_SUFFIXES:
            raise AudioPlayerError(f"非対応形式です: {suffix or '(拡張子なし)'}")

        if self._can_use_mixer():
            self._play_via_mixer(
                file_path,
                on_finished=on_finished,
                stop_previous=stop_previous,
                loop=loop,
            )
            return

        if stop_previous:
            self.stop()

        self._on_finished = on_finished
        thread = threading.Thread(
            target=self._play_worker,
            args=(file_path,),
            daemon=True,
        )
        thread.start()

    def _can_use_mixer(self) -> bool:
        return self.mixer is not None and self.mixer.is_running()

    def _play_via_mixer(
        self,
        file_path: Path,
        *,
        on_finished: Optional[Callable[[], None]],
        stop_previous: bool,
        loop: bool,
    ) -> None:
        from stream_soundboard.sample_loader import SampleLoaderError, load_audio

        assert self.mixer is not None

        if stop_previous:
            self._poll_stop.set()
            self.mixer.stop_all_playback()
            with self._lock:
                self._mixer_play_id = None
                if self._process is not None:
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=1.5)
                    except Exception:
                        try:
                            self._process.kill()
                        except Exception:
                            pass
                    self._process = None
                if self._winsound_active and sys.platform == "win32":
                    try:
                        import winsound

                        winsound.PlaySound(None, winsound.SND_PURGE)
                    except Exception:
                        pass
                    self._winsound_active = False

        try:
            samples = load_audio(
                file_path,
                target_sr=self.sample_rate,
                target_channels=self.channels,
            )
        except SampleLoaderError as exc:
            raise AudioPlayerError(str(exc)) from exc

        play_id = self.mixer.play(samples, loop=loop, gain=1.0)
        with self._lock:
            self._mixer_play_id = play_id
        self._poll_stop.clear()

        if on_finished is not None and not loop:
            thread = threading.Thread(
                target=self._poll_mixer_finished,
                args=(play_id, on_finished),
                daemon=True,
            )
            thread.start()

    def _poll_mixer_finished(
        self,
        play_id: int,
        on_finished: Callable[[], None],
    ) -> None:
        """ミキサー上の再生終了をポーリングしてコールバックを呼ぶ。"""
        while not self._poll_stop.is_set():
            with self._lock:
                if self._mixer_play_id != play_id:
                    return
            if not self._is_mixer_play_active(play_id):
                break
            time.sleep(0.03)
        else:
            return

        with self._lock:
            if self._mixer_play_id != play_id:
                return
            self._mixer_play_id = None

        try:
            on_finished()
        except Exception:
            pass

    def _is_mixer_play_active(self, play_id: int) -> bool:
        mixer = self.mixer
        if mixer is None:
            return False
        playbacks = getattr(mixer, "_playbacks", None)
        if isinstance(playbacks, dict):
            return play_id in playbacks
        return mixer.active_playback_count() > 0

    def _play_worker(self, file_path: Path) -> None:
        try:
            if sys.platform == "win32" and file_path.suffix.lower() == ".wav":
                self._play_winsound(file_path)
            else:
                self._play_external(file_path)
        finally:
            cb = self._on_finished
            self._on_finished = None
            if cb:
                try:
                    cb()
                except Exception:
                    pass

    def _play_winsound(self, file_path: Path) -> None:
        import winsound

        with self._lock:
            self._winsound_active = True
        try:
            winsound.PlaySound(
                str(file_path),
                winsound.SND_FILENAME,
            )
        except Exception as exc:
            raise AudioPlayerError(f"WAV再生に失敗: {exc}") from exc
        finally:
            with self._lock:
                self._winsound_active = False

    def _play_external(self, file_path: Path) -> None:
        cmd = self._build_play_command(file_path)
        if not cmd:
            raise AudioPlayerError(
                "再生コマンドが見つかりません。"
                " Windowsでは .wav 推奨、または ffplay を入れてください。"
            )
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise AudioPlayerError(f"再生プロセス起動に失敗: {exc}") from exc

        with self._lock:
            self._process = proc
        proc.wait()
        with self._lock:
            if self._process is proc:
                self._process = None

    def _build_play_command(self, file_path: Path) -> Optional[list[str]]:
        """利用可能な外部再生コマンドを組み立てる。"""
        path_str = str(file_path)

        if shutil.which("ffplay"):
            return [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                path_str,
            ]

        if sys.platform == "darwin" and shutil.which("afplay"):
            return ["afplay", path_str]

        if sys.platform == "win32":
            vol = max(0.0, min(1.0, self.volume))
            escaped = path_str.replace("'", "''")
            ps = (
                "Add-Type -AssemblyName presentationCore; "
                "$p = New-Object System.Windows.Media.MediaPlayer; "
                f"$p.Volume = {vol}; "
                f"$p.Open([uri]'{escaped}'); "
                "$p.Play(); "
                "while (-not $p.NaturalDuration.HasTimeSpan) { Start-Sleep -Milliseconds 50 }; "
                "$dur = $p.NaturalDuration.TimeSpan.TotalMilliseconds; "
                "Start-Sleep -Milliseconds ([int]$dur + 200); "
                "$p.Stop(); $p.Close()"
            )
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ]

        if shutil.which("mpg123"):
            return ["mpg123", "-q", path_str]
        if shutil.which("aplay") and file_path.suffix.lower() == ".wav":
            return ["aplay", "-q", path_str]

        return None
