"""オーディション3本のセリフを Eleven v4 で MP3 にする."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402

OUT = Path(r"c:\Users\MasaruShindo\work2\003_ゲーム\novel-studio\projects\audition\audio\eleven")

# プレメイドの男性声。藤優真のミドル〜ローに寄せ、張り上げない。
WATCHER = "TX3LPaxmHKxFdv7VOQHJ"  # Liam: 若め、抑制した監視役
CONFESSOR = "ErXwobaYiN019PkySvjV"  # Antoni: 二十代の告白
NARRATOR = "JBFqnCBsd6RMkjVDRZzb"  # George: 落ち着いた企業ナレーション

LINES: list[tuple[str, str, str, float]] = [
    ("w1", WATCHER, "[irritated][quietly] 何度言えばわかるんだ。", 0.35),
    ("w2", WATCHER, "[cold][firm] 僕はお前たちの仲間じゃない。ただ監視役を任せられただけだ。", 0.4),
    ("w3", WATCHER, "[hesitant][bitter] ……お前のように図々しくて、脳天気で、馴れ馴れしい奴は嫌いなんだよ。", 0.32),
    ("w4", WATCHER, "[resigned][soft] ……報告には、魔物に襲われて死んだと書いておく。", 0.4),
    ("w5", WATCHER, "[pleading][soft] だからもう、僕に関わらないでくれ……頼むから。", 0.3),
    ("c1", CONFESSOR, "[rushed][anxious] ちょっと待って、今帰られると困る……いや、困るっていうか。", 0.3),
    ("c2", CONFESSOR, "[shy][breathy] ずっと……言おうと思ってたことがあるんだ。", 0.32),
    ("c3", CONFESSOR, "[regretful][quietly] 何度も言おうとして、そのたびにタイミング逃してさ……。", 0.35),
    ("c4", CONFESSOR, "[nervous][embarrassed] 絶対、笑うなよ……こういうの得意じゃないんだからさ。", 0.3),
    ("c5", CONFESSOR, "[sincere][soft] ……お前のこと――ずっと好きだった。", 0.38),
    ("n1", NARRATOR, "技術は、目に見えるものだけではない。", 0.65),
    ("n2", NARRATOR, "より速く、より正確に、そしてより安全に。", 0.68),
    ("n3", NARRATOR, "積み重ねてきた一つひとつの工夫が、社会の新しい基準をつくっていく。", 0.65),
    ("n4", NARRATOR, "私たちは、まだ誰も見たことのない明日を、確かな技術で支えていく。", 0.62),
]


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY が未設定です。gemini-tts/.env に記入してください。")
        return 2
    client = ElevenV4Client(key)
    OUT.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for line_id, voice_id, text, stability in LINES:
        dest = OUT / f"{line_id}.mp3"
        if dest.is_file() and dest.stat().st_size > 1000:
            print(f"skip: {dest.name}")
            continue
        try:
            audio = client.synthesize(text, voice_id, stability=stability, seed=7)
            dest.write_bytes(audio)
            print(f"saved: {dest.name} bytes={dest.stat().st_size}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{line_id}: {exc}")
            print(f"fail: {line_id}: {exc}")
            if "invalid_api_key" in str(exc) or "authentication_error" in str(exc):
                break
        time.sleep(0.4)
    if failed:
        print("FAILED")
        for item in failed:
            print(item)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
