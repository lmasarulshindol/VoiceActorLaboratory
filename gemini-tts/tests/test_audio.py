"""audio モジュールのテスト."""

from __future__ import annotations

import base64
import wave
from pathlib import Path

import pytest

from gemini_tts.audio import (
    decode_audio_payload,
    is_wav_bytes,
    normalize_to_wav,
    save_wav,
    wrap_pcm_as_wav,
)


def _make_pcm(frames: int = 100) -> bytes:
    # 無音 16-bit mono
    return b"\x00\x00" * frames


def test_wrap_pcm_as_wav_has_riff_header():
    pcm = _make_pcm()
    wav = wrap_pcm_as_wav(pcm, sample_rate=24000)
    assert is_wav_bytes(wav)
    assert len(wav) > len(pcm)


def test_normalize_wav_passthrough():
    pcm = _make_pcm()
    wav = wrap_pcm_as_wav(pcm)
    assert normalize_to_wav(wav) == wav


def test_normalize_pcm_wraps():
    pcm = _make_pcm(50)
    out = normalize_to_wav(pcm, sample_rate=24000)
    assert is_wav_bytes(out)


def test_decode_base64_string():
    raw = b"hello-audio"
    encoded = base64.b64encode(raw).decode("ascii")
    assert decode_audio_payload(encoded) == raw


def test_decode_wav_bytes_passthrough():
    wav = wrap_pcm_as_wav(_make_pcm())
    assert decode_audio_payload(wav) == wav


def test_save_wav_creates_file(tmp_path: Path):
    path = tmp_path / "out" / "a.wav"
    saved = save_wav(path, _make_pcm(80), sample_rate=16000)
    assert saved.exists()
    with wave.open(str(saved), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000
        assert wf.getsampwidth() == 2


@pytest.mark.parametrize(
    "header",
    [b"RIFF....WAVE", b"ID3....", b"fLaC", b"OggS"],
)
def test_is_wav_bytes_only_riff_wave(header: bytes):
    data = header + b"\x00" * 20
    if header.startswith(b"RIFF") and b"WAVE" in header:
        # 不完全でも先頭チェック用に十分な長さへ
        data = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 8
        assert is_wav_bytes(data)
    else:
        assert not is_wav_bytes(data)
