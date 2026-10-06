"""プリビルトボイス定義."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceInfo:
    """Gemini TTS プリビルトボイス."""

    name: str
    description: str


# https://ai.google.dev/gemini-api/docs/speech-generation の Voice options
PREBUILT_VOICES: tuple[VoiceInfo, ...] = (
    VoiceInfo("Zephyr", "Bright"),
    VoiceInfo("Puck", "Upbeat"),
    VoiceInfo("Charon", "Informative"),
    VoiceInfo("Kore", "Firm"),
    VoiceInfo("Fenrir", "Excitable"),
    VoiceInfo("Leda", "Youthful"),
    VoiceInfo("Orus", "Firm"),
    VoiceInfo("Aoede", "Breezy"),
    VoiceInfo("Callirrhoe", "Easy-going"),
    VoiceInfo("Autonoe", "Bright"),
    VoiceInfo("Enceladus", "Breathy"),
    VoiceInfo("Iapetus", "Clear"),
    VoiceInfo("Umbriel", "Easy-going"),
    VoiceInfo("Algieba", "Smooth"),
    VoiceInfo("Despina", "Smooth"),
    VoiceInfo("Erinome", "Clear"),
    VoiceInfo("Algenib", "Gravelly"),
    VoiceInfo("Rasalgethi", "Informative"),
    VoiceInfo("Laomedeia", "Upbeat"),
    VoiceInfo("Achernar", "Soft"),
    VoiceInfo("Alnilam", "Firm"),
    VoiceInfo("Schedar", "Even"),
    VoiceInfo("Gacrux", "Mature"),
    VoiceInfo("Pulcherrima", "Forward"),
    VoiceInfo("Achird", "Friendly"),
    VoiceInfo("Zubenelgenubi", "Casual"),
    VoiceInfo("Vindemiatrix", "Gentle"),
    VoiceInfo("Sadachbia", "Lively"),
    VoiceInfo("Sadaltager", "Knowledgeable"),
    VoiceInfo("Sulafat", "Warm"),
)

_VOICE_MAP = {v.name.lower(): v for v in PREBUILT_VOICES}


def list_voices() -> tuple[VoiceInfo, ...]:
    """利用可能なプリビルトボイス一覧を返す."""
    return PREBUILT_VOICES


def get_voice(name: str) -> VoiceInfo:
    """ボイス名で検索する（大文字小文字無視）."""
    key = name.strip().lower()
    if key not in _VOICE_MAP:
        known = ", ".join(v.name for v in PREBUILT_VOICES)
        raise ValueError(f"未知のボイス名: {name!r}. 利用可能: {known}")
    return _VOICE_MAP[key]


def is_known_voice(name: str) -> bool:
    """プリビルト一覧に存在するボイスか."""
    return name.strip().lower() in _VOICE_MAP
