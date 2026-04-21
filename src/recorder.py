"""
録音開始/停止/一時停止、バッファ→WAV 保存。
sounddevice でマイク入力、soundfile で 16bit 44.1kHz WAV 保存。
"""
import logging
import threading

logger = logging.getLogger(__name__)
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = "int16"

# 最大録音時間（秒）。これを超えるとバッファ追加を止めてメモリ枯渇を防ぐ（約3時間）
MAX_RECORDING_SECONDS = 3 * 3600
_MAX_SAMPLES = int(SAMPLE_RATE * MAX_RECORDING_SECONDS)


class Recorder:
    """マイク録音を開始/停止/一時停止し、WAV ファイルに保存する。"""

    def __init__(self) -> None:
        self._is_recording = False
        self._is_paused = False
        self._buffer: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._input_device: int | None = None  # sounddevice のデバイス番号。None はデフォルト。
        # 非録音時にマイク入力レベルを取るためのモニター用ストリーム
        self._monitor_stream: sd.InputStream | None = None
        self._monitor_peak: float = 0.0  # 直近ブロックのピーク（0.0〜1.0、int16 を正規化済み）
        self._monitor_rms: float = 0.0  # 直近ブロックの RMS（同上）
        # リアルタイム LUFS 計算用: 直近数秒のモノラル float32 サンプルを保持するリングバッファ。
        # モニター中も録音中も `_update_levels_from_block` から積むため、どちらでも動作する。
        self._monitor_ring: list[np.ndarray] = []
        self._monitor_ring_samples: int = 0
        self._monitor_ring_max_samples: int = int(SAMPLE_RATE * 3.5)

    def set_input_device(self, device_id: int | None) -> None:
        """録音に使う入力デバイスを指定する。None でデフォルト。"""
        if self._input_device == device_id:
            return
        self._input_device = device_id
        # モニター中ならデバイス切替のため一旦張り直す
        if self._monitor_stream is not None and not self._is_recording:
            self.stop_monitoring()
            self.start_monitoring()

    def get_input_device(self) -> int | None:
        """現在の入力デバイス番号。"""
        return self._input_device

    @property
    def is_recording(self) -> bool:
        """録音中かどうか（一時停止中含む）。"""
        with self._lock:
            return self._is_recording

    @property
    def is_paused(self) -> bool:
        """録音一時停止中かどうか。"""
        with self._lock:
            return self._is_paused

    def _callback(self, indata: np.ndarray, _frames: int, _time: object, _status: sd.CallbackFlags) -> None:
        with self._lock:
            if self._is_recording and not self._is_paused:
                total = sum(c.shape[0] for c in self._buffer) + indata.shape[0]
                if total <= _MAX_SAMPLES:
                    self._buffer.append(indata.copy())
        # 録音中も録音外の「常時モニター」も、同じ関数でレベル情報を更新する
        self._update_levels_from_block(indata)

    def _update_levels_from_block(self, indata: np.ndarray) -> None:
        """ブロックから peak / rms を更新する（int16/float どちらも想定）。"""
        if indata is None or indata.size == 0:
            return
        arr = indata
        if arr.dtype == np.int16:
            denom = 32768.0
            a = arr.astype(np.float32) / denom
        else:
            a = arr.astype(np.float32)
        if a.ndim > 1:
            a = a[:, 0]
        peak = float(np.max(np.abs(a))) if a.size else 0.0
        rms = float(np.sqrt(np.mean(a * a))) if a.size else 0.0
        with self._lock:
            self._monitor_peak = peak
            self._monitor_rms = rms
            # リングバッファに追加し、上限を超えた古いチャンクを捨てる。
            if a.size > 0:
                self._monitor_ring.append(a.copy())
                self._monitor_ring_samples += a.shape[0]
                while (
                    self._monitor_ring_samples > self._monitor_ring_max_samples
                    and self._monitor_ring
                ):
                    old = self._monitor_ring.pop(0)
                    self._monitor_ring_samples -= old.shape[0]

    def _start_stream(self) -> None:
        """マイクストリームを開始する。"""
        kwargs: dict = dict(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._callback,
            blocksize=1024,
        )
        if self._input_device is not None:
            kwargs["device"] = self._input_device
        self._stream = sd.InputStream(**kwargs)
        self._stream.start()

    def start(self) -> bool:
        """
        録音を開始する。既に録音中なら False。
        コールバックでバッファに蓄積する。
        """
        with self._lock:
            if self._is_recording:
                return False
            self._is_recording = True
            self._is_paused = False
            self._buffer = []
        try:
            self._start_stream()
            return True
        except Exception:
            with self._lock:
                self._is_recording = False
            raise

    def pause(self) -> None:
        """録音を一時停止する。バッファは保持する。"""
        with self._lock:
            self._is_paused = True
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def resume(self) -> bool:
        """録音を再開する。一時停止中でなければ False。"""
        with self._lock:
            if not self._is_recording or not self._is_paused:
                return False
            self._is_paused = False
        try:
            self._start_stream()
            return True
        except Exception:
            with self._lock:
                self._is_paused = True
            raise

    def stop(self) -> None:
        """録音を停止する。"""
        with self._lock:
            self._is_recording = False
            self._is_paused = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def save_to_wav(self, wav_path: str) -> bool:
        """
        現在のバッファを WAV ファイルに保存する。
        録音停止後に呼ぶ想定。バッファが空なら何も書かず False。
        """
        with self._lock:
            chunks = list(self._buffer)
        if not chunks:
            return False
        data = np.concatenate(chunks, axis=0)
        path = Path(wav_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # soundfile.write()は自動でファイルを閉じるが、念のため明示的に処理
        try:
            sf.write(wav_path, data, SAMPLE_RATE, subtype="PCM_16")
            return True
        except Exception as e:
            logger.exception("WAV 保存に失敗しました: %s", wav_path)
            return False

    def stop_and_save(self, wav_path: str) -> bool:
        """録音を停止し、バッファを指定パスに WAV 保存する。"""
        self.stop()
        return self.save_to_wav(wav_path)

    def get_buffer_duration_seconds(self) -> float:
        """現在のバッファの長さ（秒）。"""
        with self._lock:
            chunks = list(self._buffer)
        if not chunks:
            return 0.0
        total_samples = sum(c.shape[0] for c in chunks)
        return total_samples / SAMPLE_RATE

    def start_monitoring(self) -> bool:
        """録音していない時間もマイク入力レベルを取るための軽いストリームを開始する。

        録音中は録音ストリーム側で peak/rms を更新するので何もしない。
        開始に失敗しても例外は投げず False を返す（マイクが無い環境でも UI を壊さないため）。
        """
        with self._lock:
            if self._is_recording:
                return False
            if self._monitor_stream is not None:
                return True
        try:
            kwargs: dict = dict(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=lambda indata, frames, time_info, status: self._update_levels_from_block(indata),
                blocksize=1024,
            )
            if self._input_device is not None:
                kwargs["device"] = self._input_device
            stream = sd.InputStream(**kwargs)
            stream.start()
            self._monitor_stream = stream
            return True
        except Exception:
            self._monitor_stream = None
            return False

    def stop_monitoring(self) -> None:
        """レベルモニター用ストリームを停止する。"""
        stream = self._monitor_stream
        self._monitor_stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            self._monitor_peak = 0.0
            self._monitor_rms = 0.0
            self._monitor_ring = []
            self._monitor_ring_samples = 0

    def get_monitor_levels(self) -> tuple[float, float]:
        """直近のピーク / RMS（いずれも 0.0〜1.0）を返す。"""
        with self._lock:
            return self._monitor_peak, self._monitor_rms

    def get_monitor_samples_mono(self, seconds: float = 3.0) -> np.ndarray:
        """直近 ``seconds`` 秒ぶんのモノラル float32 サンプル（[-1, 1]）を返す。

        リアルタイム LUFS 計算などに使う想定。録音中・モニター中のどちらでも動く。
        バッファが足りなければ得られる分だけ返す（呼び出し側で長さをチェックする）。
        """
        with self._lock:
            chunks = list(self._monitor_ring)
        if not chunks:
            return np.array([], dtype=np.float32)
        data = np.concatenate(chunks, axis=0).astype(np.float32, copy=False)
        max_samples = int(SAMPLE_RATE * seconds)
        if data.shape[0] > max_samples:
            data = data[-max_samples:]
        return data

    def get_visualization_samples(self, max_seconds: float = 10.0) -> np.ndarray:
        """
        波形表示用に、直近 max_seconds 秒分のバッファを float32 [-1, 1] で返す。
        録音中でなくても呼べる（空配列または前回までのデータ）。
        """
        with self._lock:
            chunks = list(self._buffer)
        if not chunks:
            return np.array([], dtype=np.float32)
        data = np.concatenate(chunks, axis=0)
        if data.ndim > 1:
            data = data[:, 0]
        max_samples = int(SAMPLE_RATE * max_seconds)
        if len(data) > max_samples:
            data = data[-max_samples:]
        return (data.astype(np.float32) / 32768.0).flatten()
