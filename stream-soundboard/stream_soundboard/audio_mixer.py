"""リアルタイム・オーディオミキサー。

マイク入力と再生サンプルをミックスし、出力デバイスへ送る。
sounddevice は遅延 import する。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np


class AudioMixerError(Exception):
    """ミキサーの開始・操作に失敗したとき。"""


@dataclass
class _Playback:
    """1本の再生キュー。"""

    play_id: int
    samples: np.ndarray  # float32, shape (N, channels)
    position: int = 0
    loop: bool = False
    gain: float = 1.0
    finished: bool = False


class AudioMixer:
    """マイクと再生サンプルをリアルタイムでミックスする。

    Attributes:
        sample_rate: サンプリングレート (Hz)
        channels: チャンネル数
        blocksize: コールバックのブロックサイズ
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 1,
        blocksize: int = 1024,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate は正の整数である必要があります")
        if channels <= 0:
            raise ValueError("channels は正の整数である必要があります")
        if blocksize <= 0:
            raise ValueError("blocksize は正の整数である必要があります")

        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)

        self._mic_volume = 1.0
        self._playback_volume = 1.0
        self._mic_muted = False

        self._lock = threading.RLock()
        self._playbacks: dict[int, _Playback] = {}
        self._next_play_id = 1
        self._stream: Any = None
        self._running = False

    def set_mic_volume(self, v: float) -> float:
        """マイク音量を設定（0.0〜1.0）。"""
        with self._lock:
            self._mic_volume = float(np.clip(v, 0.0, 1.0))
            return self._mic_volume

    def set_playback_volume(self, v: float) -> float:
        """再生音量を設定（0.0〜1.0）。"""
        with self._lock:
            self._playback_volume = float(np.clip(v, 0.0, 1.0))
            return self._playback_volume

    def set_mic_muted(self, muted: bool) -> None:
        """マイクのミュート状態を設定。"""
        with self._lock:
            self._mic_muted = bool(muted)

    def is_running(self) -> bool:
        """ストリームが動作中か。"""
        with self._lock:
            return self._running

    def start(
        self,
        input_device: int | None,
        output_device: int | None,
    ) -> None:
        """デュプレックス・ストリームを開始する。

        既に動いていれば一度 stop してから再開する。
        失敗時は AudioMixerError を送出する。
        """
        if self.is_running():
            self.stop()

        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioMixerError(
                "sounddevice がインストールされていません"
            ) from exc

        try:
            stream = sd.Stream(
                device=(input_device, output_device),
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.blocksize,
                dtype="float32",
                callback=self._stream_callback,
            )
            stream.start()
        except AudioMixerError:
            raise
        except Exception as exc:
            raise AudioMixerError(f"ストリームの開始に失敗しました: {exc}") from exc

        with self._lock:
            self._stream = stream
            self._running = True

    def stop(self) -> None:
        """ストリームを停止する。"""
        with self._lock:
            stream = self._stream
            self._stream = None
            self._running = False

        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def play(
        self,
        samples: np.ndarray,
        *,
        loop: bool = False,
        gain: float = 1.0,
    ) -> int:
        """float32 の (N,) または (N, C) を再生キューに追加する。

        Returns:
            再生ID（複数同時再生可能）
        """
        arr = np.asarray(samples, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        elif arr.ndim != 2:
            raise AudioMixerError(
                f"samples は 1D または 2D である必要があります: ndim={arr.ndim}"
            )
        if arr.shape[0] == 0:
            raise AudioMixerError("空のサンプルは再生できません")

        arr = self._match_channels(arr)

        with self._lock:
            play_id = self._next_play_id
            self._next_play_id += 1
            self._playbacks[play_id] = _Playback(
                play_id=play_id,
                samples=arr.copy(),
                position=0,
                loop=bool(loop),
                gain=float(gain),
            )
            return play_id

    def stop_play(self, play_id: int) -> None:
        """指定した再生IDを停止する。"""
        with self._lock:
            self._playbacks.pop(int(play_id), None)

    def stop_all_playback(self) -> None:
        """すべての再生を停止する。"""
        with self._lock:
            self._playbacks.clear()

    def active_playback_count(self) -> int:
        """再生中の本数。"""
        with self._lock:
            return len(self._playbacks)

    def is_play_active(self, play_id: int) -> bool:
        """指定の再生IDがまだキューにあるか。"""
        with self._lock:
            return int(play_id) in self._playbacks

    def _match_channels(self, block: np.ndarray) -> np.ndarray:
        """チャンネル数を self.channels に合わせる。

        モノラル→マルチ: 複製拡張。
        マルチ→少ない: 平均してから必要なら拡張。
        """
        block = np.asarray(block, dtype=np.float32)
        if block.ndim == 1:
            block = block.reshape(-1, 1)

        src_ch = block.shape[1]
        dst_ch = self.channels

        if src_ch == dst_ch:
            return block

        if src_ch == 1:
            return np.repeat(block, dst_ch, axis=1)

        # 複数ch → モノラル平均 → 必要なら拡張
        mono = np.mean(block, axis=1, keepdims=True, dtype=np.float32)
        if dst_ch == 1:
            return mono
        return np.repeat(mono, dst_ch, axis=1)

    def _read_playback_block(self, frames: int) -> np.ndarray:
        """再生中サンプルを合算して frames 分返す（gain 込み、playback_vol 前）。"""
        mixed = np.zeros((frames, self.channels), dtype=np.float32)
        finished_ids: list[int] = []

        for play_id, pb in self._playbacks.items():
            remaining = frames
            write_pos = 0
            while remaining > 0:
                available = pb.samples.shape[0] - pb.position
                if available <= 0:
                    if pb.loop:
                        pb.position = 0
                        available = pb.samples.shape[0]
                    else:
                        finished_ids.append(play_id)
                        break

                n = min(remaining, available)
                chunk = pb.samples[pb.position : pb.position + n]
                mixed[write_pos : write_pos + n] += chunk * np.float32(pb.gain)
                pb.position += n
                write_pos += n
                remaining -= n

                if pb.position >= pb.samples.shape[0] and not pb.loop:
                    finished_ids.append(play_id)
                    break

        for play_id in finished_ids:
            self._playbacks.pop(play_id, None)

        return mixed

    def _mix_block(self, mic_block: np.ndarray) -> np.ndarray:
        """マイクブロックと再生をミックスして返す（テスト用に公開）。

        Args:
            mic_block: float32 の (frames,) または (frames, C)

        Returns:
            float32 (frames, channels)、クリップ済み
        """
        mic = np.asarray(mic_block, dtype=np.float32)
        if mic.ndim == 1:
            mic = mic.reshape(-1, 1)
        elif mic.ndim != 2:
            raise AudioMixerError(f"不正な mic_block: ndim={mic.ndim}")

        frames = mic.shape[0]
        mic = self._match_channels(mic)

        with self._lock:
            mic_vol = 0.0 if self._mic_muted else self._mic_volume
            play_vol = self._playback_volume
            playback = self._read_playback_block(frames)

        out = mic * np.float32(mic_vol) + playback * np.float32(play_vol)
        return np.clip(out, -1.0, 1.0).astype(np.float32)

    def _stream_callback(
        self,
        indata: np.ndarray,
        outdata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """sounddevice コールバック。"""
        del frames, time_info, status  # 未使用
        mixed = self._mix_block(indata)
        outdata[:] = mixed
