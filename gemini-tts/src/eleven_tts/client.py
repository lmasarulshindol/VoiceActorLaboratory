"""Eleven v4 を Text to Dialogue API で1行ずつ合成する."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://api.elevenlabs.io/v1/text-to-dialogue"
DEFAULT_MODEL = "eleven_v4"
DEFAULT_FORMAT = "mp3_44100_128"

Opener = Callable[..., object]


class ElevenV4Client:
    """Eleven v4 の音声をバイト列で返す."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        output_format: str = DEFAULT_FORMAT,
        opener: Opener | None = None,
        timeout: float = 120,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.output_format = output_format
        self.opener = opener or urlopen
        self.timeout = timeout

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        language_code: str = "ja",
        stability: float = 0.4,
        similarity: float = 0.75,
        seed: int | None = None,
    ) -> bytes:
        """1人分のセリフを合成する. 空の応答や HTTP エラーは例外にする."""
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY が未設定です。.env に記入してください。")
        spoken = text.strip()
        if not spoken:
            raise ValueError("合成するテキストが空です")
        if not voice_id.strip():
            raise ValueError("voice_id が空です")
        payload: dict[str, object] = {
            "model_id": self.model,
            "language_code": language_code,
            "inputs": [{"text": spoken, "voice_id": voice_id}],
            "settings": {"stability": stability, "similarity": similarity},
        }
        if seed is not None:
            payload["seed"] = seed
        request = Request(
            f"{API_URL}?output_format={self.output_format}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"ElevenLabs API {exc.code}: {detail}") from None
        except URLError as exc:
            raise RuntimeError(f"ElevenLabs API に接続できません: {exc.reason}") from None
        if status != 200:
            raise RuntimeError(f"ElevenLabs API {status}")
        if not body or len(body) < 100:
            raise RuntimeError("ElevenLabs API の音声が空です")
        return body
