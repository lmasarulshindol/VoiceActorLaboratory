"""全セリフを ElevenLabs v4 で合成する（既存ファイルはスキップ）.

使い方:
  py -3 tts.py            # 未生成の行だけ合成
  py -3 tts.py 126 164    # 指定行を作り直す

MP3 で受け取り、ミックス用に build/voice/*.wav（44.1kHz mono）へ変換する。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from cues import ROOT, STABILITY, parse_script, voice_filename

GEMINI_TTS_ROOT = ROOT.parents[2] / "gemini-tts"
sys.path.insert(0, str(GEMINI_TTS_ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402

VOICE_DIR = ROOT / "build" / "voice"
MP3_DIR = ROOT / "build" / "voice_mp3"
DELAY_SEC = 0.4
MAX_RETRIES = 3
SEED = 7


def load_api_key() -> str:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(GEMINI_TTS_ROOT / ".env")
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def mp3_to_wav(src, dest) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "44100", str(dest)],
        check=True,
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lines", nargs="*", type=int)
    args = ap.parse_args(argv)

    key = load_api_key()
    if not key:
        print("ELEVENLABS_API_KEY が未設定です。gemini-tts/.env に記入してください。")
        return 2
    client = ElevenV4Client(key)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    MP3_DIR.mkdir(parents=True, exist_ok=True)

    redo = set(args.lines)
    targets = [ln for ln in parse_script() if not ln.silent]
    errors: list[int] = []
    for ln in targets:
        wav = VOICE_DIR / voice_filename(ln)
        if wav.is_file() and wav.stat().st_size > 0 and ln.no not in redo:
            continue
        mp3 = MP3_DIR / wav.with_suffix(".mp3").name
        for attempt in range(MAX_RETRIES + 1):
            try:
                audio = client.synthesize(
                    ln.tts_text, ln.voice or "", stability=STABILITY.get(ln.speaker, 0.4), seed=SEED
                )
                mp3.write_bytes(audio)
                mp3_to_wav(mp3, wav)
                print(f"[ok] {ln.no:03d} {ln.speaker} {ln.tts_text[:40]}", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "invalid_api_key" in msg or "authentication" in msg or "quota_exceeded" in msg:
                    print(f"[fatal] {ln.no:03d} {msg}", flush=True)
                    return 2
                if attempt < MAX_RETRIES and ("429" in msg or " 5" in msg[:20]):
                    time.sleep(10.0 * (attempt + 1))
                    continue
                print(f"[error] {ln.no:03d} {msg}", flush=True)
                errors.append(ln.no)
                break
        time.sleep(DELAY_SEC)

    print(f"done: targets={len(targets)} errors={errors}", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
