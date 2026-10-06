"""音声バイトの保存ヘルパー."""

from __future__ import annotations

import base64
import wave
from pathlib import Path


def decode_audio_payload(data: bytes | str) -> bytes:
    """API 応答の audio ペイロードを生バイトに正規化する.

    bytes はそのまま、base64 文字列はデコードする。
    """
    if isinstance(data, bytes):
        # SDK がすでにデコード済みの場合と、base64 バイト列の両方に対応
        if data.startswith(b"RIFF") or _looks_like_pcm(data):
            return data
        try:
            decoded = base64.b64decode(data, validate=True)
            if decoded:
                return decoded
        except Exception:
            pass
        return data

    text = data.strip()
    return base64.b64decode(text)


def _looks_like_pcm(data: bytes) -> bool:
    """生 PCM っぽいか（厳密判定ではない）."""
    return len(data) >= 2 and not data.startswith((b"RIFF", b"ID3", b"fLaC", b"OggS"))


def is_wav_bytes(data: bytes) -> bool:
    """RIFF/WAVE ヘッダを持つか."""
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def wrap_pcm_as_wav(
    pcm: bytes,
    *,
    channels: int = 1,
    sample_rate: int = 24000,
    sample_width: int = 2,
) -> bytes:
    """ヘッダ無し PCM を WAV バイト列に包む."""
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def normalize_to_wav(
    data: bytes | str,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """API 応答を WAV バイト列に正規化する.

    Gemini 3.8 TTS は WAV を返す。旧モデルは raw PCM (L16) のことがある。
    """
    raw = decode_audio_payload(data)
    if is_wav_bytes(raw):
        return raw
    return wrap_pcm_as_wav(
        raw,
        channels=channels,
        sample_rate=sample_rate,
        sample_width=sample_width,
    )


def save_wav(
    path: Path | str,
    data: bytes | str,
    *,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> Path:
    """音声データを WAV ファイルとして保存する."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wav_bytes = normalize_to_wav(
        data,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )
    out.write_bytes(wav_bytes)
    return out
