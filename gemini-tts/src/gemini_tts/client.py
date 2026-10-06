"""Gemini TTS API クライアント."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .audio import normalize_to_wav
from .config import DEFAULT_MODEL, DEFAULT_SAMPLE_RATE, DEFAULT_VOICE
from .voices import get_voice


@dataclass(frozen=True)
class SpeakerVoice:
    """マルチスピーカー用の話者設定."""

    speaker: str
    voice: str


@dataclass(frozen=True)
class TTSResult:
    """TTS 生成結果."""

    audio_wav: bytes
    model: str
    mime_type: str | None = None
    raw_bytes: bytes | None = None


class GeminiTTSClient:
    """google-genai SDK 経由で Gemini TTS を呼び出す."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        client: Any | None = None,
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise ValueError("api_key は必須です")
        self.api_key = str(api_key).strip()
        self.model = model
        self.sample_rate = sample_rate
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from google import genai

        self._client = genai.Client(api_key=self.api_key)
        return self._client

    def synthesize(
        self,
        text: str,
        *,
        voice: str = DEFAULT_VOICE,
        style: str | None = None,
        language_code: str | None = None,
        speakers: Sequence[SpeakerVoice] | None = None,
        model: str | None = None,
    ) -> TTSResult:
        """テキストを音声（WAV）に変換する.

        Args:
            text: 読み上げるテキスト（3.8 系では verbatim として扱われる）
            voice: シングルスピーカー時のプリビルトボイス名
            style: 話し方指示（可能なら speech_metadata、否则プロンプト前置）
            language_code: BCP-47 言語コード（任意）
            speakers: マルチスピーカー設定（最大2名想定）
            model: モデル上書き
        """
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("text が空です")

        use_model = model or self.model
        if speakers:
            if len(speakers) < 1:
                raise ValueError("speakers は1名以上必要です")
            for sp in speakers:
                get_voice(sp.voice)
        else:
            voice_info = get_voice(voice)
            voice = voice_info.name

        from google.genai import types

        speech_config = self._build_speech_config(
            types,
            voice=voice,
            speakers=speakers,
            language_code=language_code,
        )
        contents = self._build_contents(
            types,
            text=cleaned,
            style=style,
            speakers=speakers,
            model=use_model,
        )

        client = self._get_client()
        response = client.models.generate_content(
            model=use_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=speech_config,
            ),
        )

        raw, mime = self._extract_audio(response)
        wav = normalize_to_wav(raw, sample_rate=self.sample_rate)
        return TTSResult(
            audio_wav=wav,
            model=use_model,
            mime_type=mime,
            raw_bytes=raw,
        )

    def _build_speech_config(
        self,
        types: Any,
        *,
        voice: str,
        speakers: Sequence[SpeakerVoice] | None,
        language_code: str | None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if language_code:
            kwargs["language_code"] = language_code

        if speakers:
            speaker_configs = []
            for sp in speakers:
                speaker_configs.append(
                    types.SpeakerVoiceConfig(
                        speaker=sp.speaker,
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=get_voice(sp.voice).name,
                            )
                        ),
                    )
                )
            kwargs["multi_speaker_voice_config"] = types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=speaker_configs,
            )
        else:
            kwargs["voice_config"] = types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        return types.SpeechConfig(**kwargs)

    def _build_contents(
        self,
        types: Any,
        *,
        text: str,
        style: str | None,
        speakers: Sequence[SpeakerVoice] | None,
        model: str,
    ) -> Any:
        """モデル世代に応じて contents / speech_metadata を組み立てる."""
        # Gemini 3.8 系は verbatim transcript + speech_metadata が推奨
        use_metadata = "3.8" in model

        if speakers and use_metadata:
            # 簡易: 全体に style のみ。話者ラベルはテキスト側に任せる
            return self._part_with_optional_metadata(types, text, style=style)

        if use_metadata and style:
            return self._part_with_optional_metadata(types, text, style=style)

        # 旧モデル向け: スタイルをプロンプト前置
        prompt = text
        if style:
            prompt = f"{style.strip()}\n\n{text}"
        return prompt

    def _part_with_optional_metadata(
        self,
        types: Any,
        text: str,
        *,
        style: str | None,
    ) -> Any:
        meta_kwargs: dict[str, Any] = {}
        if style:
            meta_kwargs["style"] = style.strip()

        # SDK に SpeechMetadata / Part.speech_metadata がある場合は使う
        speech_metadata = None
        if meta_kwargs:
            speech_metadata = self._try_speech_metadata(types, meta_kwargs)

        if speech_metadata is not None:
            try:
                return [types.Content(role="user", parts=[types.Part(text=text, speech_metadata=speech_metadata)])]
            except TypeError:
                pass

        # フォールバック: スタイル前置（3.8 では読み上げられる可能性あり）
        if style:
            return f"{style.strip()}\n\n{text}"
        return text

    @staticmethod
    def _try_speech_metadata(types: Any, kwargs: dict[str, Any]) -> Any | None:
        for name in ("SpeechMetadata", "SpeechGenerationMetadata"):
            cls = getattr(types, name, None)
            if cls is None:
                continue
            try:
                return cls(**kwargs)
            except TypeError:
                continue
        return None

    @staticmethod
    def _extract_audio(response: Any) -> tuple[bytes, str | None]:
        """generate_content 応答から audio bytes を取り出す."""
        # 一部 SDK は response.data を提供
        data_attr = getattr(response, "data", None)
        if isinstance(data_attr, (bytes, str)) and data_attr:
            return (
                data_attr if isinstance(data_attr, bytes) else data_attr.encode("utf-8"),
                None,
            )

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise RuntimeError("TTS 応答に candidates がありません")

        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        if not parts:
            raise RuntimeError("TTS 応答に audio parts がありません")

        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is None:
                continue
            data = getattr(inline, "data", None)
            mime = getattr(inline, "mime_type", None)
            if data is None:
                continue
            if isinstance(data, str):
                data = data.encode("utf-8")
            if not isinstance(data, (bytes, bytearray)):
                raise RuntimeError(f"予期しない audio data 型: {type(data)}")
            return bytes(data), mime

        raise RuntimeError("TTS 応答から audio データを抽出できませんでした")
