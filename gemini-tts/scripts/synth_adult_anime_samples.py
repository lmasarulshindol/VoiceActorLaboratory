"""R18シーン別サンプルセリフを Eleven v4 で複数声質候補として合成する."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402

OUT = ROOT / "output" / "adult_anime_samples"
SEED = 11


@dataclass(frozen=True)
class VoiceCand:
    key: str
    voice_id: str
    label: str
    stability: float


@dataclass(frozen=True)
class SceneLine:
    scene_id: str
    scene_label: str
    text: str


VOICES: tuple[VoiceCand, ...] = (
    VoiceCand("Hina", "lhTvHflPVOqgSWyuWQry", "ロリ寄り・アイドル系ハイ", 0.32),
    VoiceCand("Romaco", "KgETZ36CCLD1Cob4xpkv", "明るいアニメ声", 0.33),
    VoiceCand("Kuon", "B8gJV1IhpuegLxdpXFOE", "萌えヒロイン・元気寄り", 0.34),
    VoiceCand("Sumire", "KtSs8OSniRPofXnr5PeA", "息っぽい・儚いハイ", 0.30),
    VoiceCand("Yuko", "J6YFreR6shJoaDfv7tLf", "クリアで高トーン", 0.33),
)

SCENES: tuple[SceneLine, ...] = (
    SceneLine(
        "01_kiss",
        "キス",
        "[high-pitched][breathy][soft] んっ……ちゅ、……はむ……。……キス、上手……",
    ),
    SceneLine(
        "02_caress",
        "愛撫",
        "[high-pitched][shy][gasps][soft] ひゃっ……そこ、ダメ……。……ん、んっ……触らないで……",
    ),
    SceneLine(
        "03_oral",
        "フェラ",
        "[high-pitched][muffled][breathy] んむ……っ、ん……ちゅ……。……ん、……",
    ),
    SceneLine(
        "04_sex",
        "本番",
        "[high-pitched][moaning][breathy] あっ、んんっ……！　深い……っ、ゆっくり……して……",
    ),
    SceneLine(
        "05_after",
        "事後",
        "[high-pitched][sleepy][soft][content] はぁ……はぁ……。……身体、まだ……じんじんする……",
    ),
)


def remaining_chars(key: str) -> int:
    req = Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
    with urlopen(req, timeout=30) as res:
        data = json.load(res)
    return int(data["character_limit"]) - int(data["character_count"])


def estimated_chars() -> int:
    return sum(len(s.text) for s in SCENES) * len(VOICES)


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY が未設定です。")
        return 2

    need = estimated_chars()
    rem = remaining_chars(key)
    print(f"remaining_chars={rem} need_about={need}")
    if rem < need:
        print("文字数枠が不足しています。")
        return 3

    client = ElevenV4Client(key)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    failed: list[str] = []

    for scene in SCENES:
        for voice in VOICES:
            fname = f"{scene.scene_id}_{voice.key}.mp3"
            dest = OUT / fname
            manifest.append(
                {
                    "file": fname,
                    "scene": scene.scene_label,
                    "voice_key": voice.key,
                    "voice_label": voice.label,
                    "text": scene.text,
                }
            )
            if dest.is_file() and dest.stat().st_size > 1000:
                print(f"skip: {fname}")
                continue
            try:
                audio = client.synthesize(
                    scene.text,
                    voice.voice_id,
                    stability=voice.stability,
                    seed=SEED,
                )
                dest.write_bytes(audio)
                print(f"saved: {fname} bytes={dest.stat().st_size}")
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{fname}: {exc}")
                print(f"fail: {fname}: {exc}")
                if "invalid_api_key" in str(exc) or "authentication_error" in str(exc):
                    break
            time.sleep(0.45)

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if failed:
        print("FAILED")
        for item in failed:
            print(item)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
