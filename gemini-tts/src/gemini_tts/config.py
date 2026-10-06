"""設定読み込み（.env / YAML / 環境変数）."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemini-3.8-flash-tts"
DEFAULT_VOICE = "Kore"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_OUTPUT_DIR = "output"


@dataclass
class TTSConfig:
    """TTS 実行設定."""

    api_key: str = ""
    model: str = DEFAULT_MODEL
    voice: str = DEFAULT_VOICE
    language_code: str | None = None
    style: str | None = None
    output_dir: Path = field(default_factory=lambda: Path(DEFAULT_OUTPUT_DIR))
    sample_rate: int = DEFAULT_SAMPLE_RATE

    def require_api_key(self) -> str:
        """APIキーが無ければ例外を投げる."""
        key = (self.api_key or "").strip()
        if not key or key.startswith("your_api_key"):
            raise ValueError(
                "GEMINI_API_KEY が未設定です。"
                " .env.example を .env にコピーしてキーを記入してください。"
            )
        return key


def _load_dotenv(env_path: Path | None) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if env_path and env_path.is_file():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML が必要です: pip install PyYAML") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_config(
    *,
    config_path: Path | None = None,
    env_path: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> TTSConfig:
    """環境変数・YAML・上書きオプションから設定を組み立てる.

    優先度（高い順）: overrides > 環境変数 > YAML > デフォルト
    """
    _load_dotenv(env_path)

    yaml_data: dict[str, Any] = {}
    if config_path is not None:
        yaml_data = _load_yaml(config_path)

    def pick(key: str, env_keys: tuple[str, ...] = (), default: Any = None) -> Any:
        if overrides and key in overrides and overrides[key] is not None:
            return overrides[key]
        for ek in env_keys:
            val = os.environ.get(ek)
            if val is not None and str(val).strip() != "":
                return val
        if key in yaml_data and yaml_data[key] is not None:
            return yaml_data[key]
        return default

    output_dir = pick("output_dir", default=DEFAULT_OUTPUT_DIR)
    sample_rate = pick("sample_rate", default=DEFAULT_SAMPLE_RATE)
    try:
        sample_rate = int(sample_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"sample_rate が不正です: {sample_rate!r}") from exc

    return TTSConfig(
        api_key=str(pick("api_key", ("GEMINI_API_KEY",), default="") or ""),
        model=str(pick("model", ("GEMINI_TTS_MODEL",), default=DEFAULT_MODEL)),
        voice=str(pick("voice", ("GEMINI_TTS_VOICE",), default=DEFAULT_VOICE)),
        language_code=pick("language_code", ("GEMINI_TTS_LANGUAGE",), default=None),
        style=pick("style", default=None),
        output_dir=Path(str(output_dir)),
        sample_rate=sample_rate,
    )
