"""
録音開始/停止/一時停止、バッファ→WAV 保存。
sounddevice でマイク入力、soundfile で 16bit 44.1kHz WAV 保存。
"""
import threading
from pathlib import Path
import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = "int16"


class Recorder:
    """マイク録音を開始/停止/一時停止し、WAV ファイルに保存する。"""

    def __init__(self) -> None:
        self._is_recording = False
        self._is_paused = False
        self._buffer: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._input_device: int | None = None  # sounddevice のデバイス番号。None はデフォルト。

    def set_input_device(self, device_id: int | None) -> None:
        """録音に使う入力デバイスを指定する。None でデフォルト。"""
        self._input_device = device_id

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
                self._buffer.append(indata.copy())

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
        sf.write(wav_path, data, SAMPLE_RATE, subtype="PCM_16")
        return True

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
