"""
テイクの再生・停止。
PyQt6 の QMediaPlayer で WAV を再生する。
"""
from pathlib import Path
from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioDevice, QMediaDevices


class Playback:
    """指定 WAV の再生/停止。再生状態は playback_state で取得。"""

    def __init__(self) -> None:
        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._output_device: QAudioDevice | None = None  # None はデフォルト

    def set_output_device(self, device: QAudioDevice | None) -> None:
        """再生に使う出力デバイスを指定する。None でデフォルト。"""
        self._output_device = device
        if device is not None:
            self._audio_output.setDevice(device)
        else:
            default_out = QMediaDevices.audioOutputs()
            if default_out:
                self._audio_output.setDevice(default_out[0])

    def get_output_device(self) -> QAudioDevice | None:
        """現在の出力デバイス。"""
        return self._output_device

    def play(self, wav_path: str) -> bool:
        """
        指定パスの WAV を再生する。ファイルが存在しない場合は False。
        """
        path = Path(wav_path)
        if not path.is_file():
            return False
        self._player.setSource(QUrl.fromLocalFile(str(path.absolute())))
        self._player.play()
        return True

    def pause(self) -> None:
        """再生を一時停止する。"""
        self._player.pause()

    def stop(self) -> None:
        """再生を停止する。"""
        self._player.stop()

    def set_speed(self, rate: float) -> None:
        """再生速度を設定する。0.5, 1.0, 1.25, 1.5 など。"""
        self._player.setPlaybackRate(rate)

    def seek_to_position_ms(self, ms: int) -> None:
        """再生位置を指定ミリ秒にシークする。0 以上 duration_ms 以下にクランプする。"""
        d = self._player.duration()
        if d > 0:
            pos = max(0, min(ms, d))
            self._player.setPosition(pos)

    def duration_ms(self) -> int:
        """現在のソースの長さ（ミリ秒）。未ロードや不明な場合は 0 以下。"""
        return self._player.duration()

    @property
    def is_playing(self) -> bool:
        """再生中かどうか。"""
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def is_paused(self) -> bool:
        """一時停止中かどうか。"""
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    def get_player(self) -> QMediaPlayer:
        """シグナル接続用に QMediaPlayer を返す。"""
        return self._player
