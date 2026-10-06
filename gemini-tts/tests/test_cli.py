"""CLI のテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from gemini_tts.audio import wrap_pcm_as_wav
from gemini_tts.cli import main
from gemini_tts.client import TTSResult


def test_list_voices_exit_zero(capsys: pytest.CaptureFixture[str]):
    assert main(["list-voices"]) == 0
    out = capsys.readouterr().out
    assert "Kore" in out
    assert "Aoede" in out


def test_synthesize_requires_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=dummy\n", encoding="utf-8")
    code = main(["--env", str(env), "synthesize"])
    assert code == 1


def test_synthesize_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=dummy-key\n", encoding="utf-8")
    out_wav = tmp_path / "hello.wav"

    wav = wrap_pcm_as_wav(b"\x00\x00" * 30)

    def fake_synthesize(self, text, **kwargs):
        assert "テスト" in text
        return TTSResult(audio_wav=wav, model="gemini-3.8-flash-tts", mime_type="audio/wav")

    monkeypatch.setattr(
        "gemini_tts.cli.GeminiTTSClient.synthesize",
        fake_synthesize,
    )

    code = main(
        [
            "--env",
            str(env),
            "synthesize",
            "テストです",
            "-o",
            str(out_wav),
            "--voice",
            "Aoede",
        ]
    )
    assert code == 0
    assert out_wav.exists()
    assert out_wav.read_bytes()[:4] == b"RIFF"
    assert "saved:" in capsys.readouterr().out
