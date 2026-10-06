"""Eleven v4 クライアントのリクエスト組み立て."""

from __future__ import annotations

import json

import pytest

from eleven_tts import ElevenV4Client


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_v4の対話APIへ日本語で送る() -> None:
    seen: dict[str, object] = {}

    def opener(request, timeout=0):  # noqa: ANN001
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["key"] = request.get_header("Xi-api-key")
        seen["timeout"] = timeout
        return _Response(200, b"ID3" + b"\x00" * 120)

    audio = ElevenV4Client("secret-key", opener=opener).synthesize("こんにちは", "voice123", seed=7)
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model_id"] == "eleven_v4"
    assert body["language_code"] == "ja"
    assert body["inputs"] == [{"text": "こんにちは", "voice_id": "voice123"}]
    assert body["seed"] == 7
    assert "output_format=mp3_44100_128" in str(seen["url"])
    assert seen["key"] == "secret-key"
    assert audio.startswith(b"ID3")


def test_キーが無いと送らない() -> None:
    def opener(request, timeout=0):  # noqa: ANN001
        raise AssertionError("request should not be sent")

    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        ElevenV4Client("  ", opener=opener).synthesize("こんにちは", "voice123")
