"""Google Gemini TTS クライアントパッケージ."""

from .client import GeminiTTSClient, SpeakerVoice, TTSResult
from .voices import PREBUILT_VOICES, get_voice, list_voices

__all__ = [
    "GeminiTTSClient",
    "SpeakerVoice",
    "TTSResult",
    "PREBUILT_VOICES",
    "get_voice",
    "list_voices",
]

__version__ = "0.1.0"
