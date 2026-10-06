"""GeminiTTSClient のテスト（API はモック）."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gemini_tts.audio import wrap_pcm_as_wav
from gemini_tts.client import GeminiTTSClient, SpeakerVoice


class _FakeModels:
    def __init__(self, response):
        self.response = response
        self.last_kwargs = None

    def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


def _audio_response(data: bytes, mime: str = "audio/wav"):
    inline = SimpleNamespace(data=data, mime_type=mime)
    part = SimpleNamespace(inline_data=inline)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[candidate], data=None)


def test_synthesize_single_speaker_returns_wav():
    pcm = b"\x00\x00" * 40
    wav = wrap_pcm_as_wav(pcm)
    fake = _FakeClient(_audio_response(wav))
    client = GeminiTTSClient("test-key", client=fake, model="gemini-3.8-flash-tts")

    result = client.synthesize("こんにちは", voice="Kore")

    assert result.audio_wav[:4] == b"RIFF"
    assert result.model == "gemini-3.8-flash-tts"
    assert fake.models.last_kwargs["model"] == "gemini-3.8-flash-tts"
    assert fake.models.last_kwargs["config"].response_modalities == ["AUDIO"]


def test_synthesize_empty_text():
    client = GeminiTTSClient("test-key", client=_FakeClient(_audio_response(b"RIFF")))
    with pytest.raises(ValueError, match="空"):
        client.synthesize("   ")


def test_synthesize_unknown_voice():
    client = GeminiTTSClient("test-key", client=_FakeClient(_audio_response(b"RIFF")))
    with pytest.raises(ValueError, match="未知のボイス名"):
        client.synthesize("hi", voice="Nope")


def test_synthesize_multi_speaker():
    wav = wrap_pcm_as_wav(b"\x00\x00" * 20)
    fake = _FakeClient(_audio_response(wav))
    client = GeminiTTSClient("test-key", client=fake)

    result = client.synthesize(
        "Alice: こんにちは\nBob: やあ",
        speakers=[
            SpeakerVoice("Alice", "Kore"),
            SpeakerVoice("Bob", "Puck"),
        ],
    )
    assert result.audio_wav[:4] == b"RIFF"
    speech = fake.models.last_kwargs["config"].speech_config
    assert speech.multi_speaker_voice_config is not None


def test_missing_api_key():
    with pytest.raises(ValueError, match="api_key"):
        GeminiTTSClient("")


def test_extract_audio_missing_candidates():
    client = GeminiTTSClient("k", client=_FakeClient(SimpleNamespace(candidates=[], data=None)))
    with pytest.raises(RuntimeError, match="candidates"):
        client.synthesize("hello", voice="Kore")
