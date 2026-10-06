"""voices / config のテスト."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gemini_tts.config import load_config
from gemini_tts.voices import get_voice, is_known_voice, list_voices


def test_list_voices_has_30():
    voices = list_voices()
    assert len(voices) == 30
    names = {v.name for v in voices}
    assert "Kore" in names
    assert "Aoede" in names


def test_get_voice_case_insensitive():
    assert get_voice("kore").name == "Kore"
    assert get_voice("AOEDE").description == "Breezy"


def test_get_voice_unknown():
    with pytest.raises(ValueError, match="未知のボイス名"):
        get_voice("NotAVoice")


def test_is_known_voice():
    assert is_known_voice("Puck")
    assert not is_known_voice("zzz")


def test_load_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_TTS_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_TTS_VOICE", raising=False)
    cfg = load_config(env_path=tmp_path / "missing.env")
    assert cfg.model == "gemini-3.8-flash-tts"
    assert cfg.voice == "Kore"
    assert cfg.sample_rate == 24000


def test_load_config_env_and_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=env-key\nGEMINI_TTS_VOICE=Puck\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_TTS_VOICE", raising=False)
    # dotenv が OS 環境に載るので、読み込み後の状態を確認
    cfg = load_config(
        env_path=env,
        overrides={"voice": "Aoede", "model": "gemini-3.8-flash-lite-tts"},
    )
    assert cfg.api_key == "env-key"
    assert cfg.voice == "Aoede"
    assert cfg.model == "gemini-3.8-flash-lite-tts"


def test_load_config_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_TTS_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_TTS_VOICE", raising=False)
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "model: gemini-2.5-flash-preview-tts\nvoice: Fenrir\nsample_rate: 16000\n",
        encoding="utf-8",
    )
    cfg = load_config(config_path=yaml_path, env_path=tmp_path / "no.env")
    assert cfg.model == "gemini-2.5-flash-preview-tts"
    assert cfg.voice == "Fenrir"
    assert cfg.sample_rate == 16000


def test_require_api_key_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = load_config(env_path=tmp_path / "no.env")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        cfg.require_api_key()


def test_sample_rate_invalid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    with pytest.raises(ValueError, match="sample_rate"):
        load_config(env_path=tmp_path / "no.env", overrides={"sample_rate": "abc"})
