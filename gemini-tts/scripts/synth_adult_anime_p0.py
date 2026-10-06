"""P0 台本クリップを Eleven v4 で合成（1 ID = 1 MP3）."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402

OUT = ROOT / "output" / "adult_anime_p0"
SCRIPT_MD = (
    ROOT.parent
    / "台本"
    / "サンプルボイス_アニメハイ_R18シーン候補_2026-10-02.md"
)

ROMACO = "KgETZ36CCLD1Cob4xpkv"
STABILITY = 0.33
SEED = 11

# 再生順（台本 P0 節と同期）
CLIP_ORDER: tuple[str, ...] = (
    "01-01", "01-02", "01-03", "01-04", "01-05", "01-06", "01-07", "01-08",
    "02-01", "02-02", "02-03", "02-04", "02-05", "02-06", "02-07", "02-08", "02-09", "02-10",
    "03-01", "03-02", "03-03", "03-04", "03-05", "03-06", "03-07", "03-08", "03-09", "03-10", "03-11",
    "04-00a", "04-00b", "04-00c", "04-01", "04-02", "04-03", "04-04", "04-05", "04-06",
    "04-6a1", "04-6a2", "04-6a3", "04-6a4", "04-6a5",
    "04-6b1", "04-6b2", "04-6b3", "04-07", "04-08",
    "05-01", "05-02", "05-03", "05-04", "05-05",
    "06-01", "06-02", "06-03",
    "07-01", "07-02", "07-03", "07-04", "07-05", "07-06",
    "08-01", "08-02", "08-03", "08-04", "08-05", "08-6b1", "08-6b2", "08-07", "08-08", "08-09", "08-10",
    "09-01", "09-02", "09-03", "09-04",
)

_ROW = re.compile(
    r"^\|\s*([0-9]{2}-[0-9a-z]+)\s*\|[^|]+\|[^|]+\|\s*`(.+)`\s*\|"
)


def load_clips_from_md(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    start = text.find("## P0 セリフ台本全文")
    end = text.find("**クリップ数**:", start)
    if start < 0 or end < 0:
        raise RuntimeError("P0 節が見つかりません")
    block = text[start:end]
    clips: dict[str, str] = {}
    for line in block.splitlines():
        m = _ROW.match(line.strip())
        if m:
            clips[m.group(1)] = m.group(2).strip()
    return clips


def remaining_chars(key: str) -> int:
    req = Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
    with urlopen(req, timeout=30) as res:
        data = json.load(res)
    return int(data["character_limit"]) - int(data["character_count"])


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

    clips = load_clips_from_md(SCRIPT_MD)
    missing_order = [cid for cid in CLIP_ORDER if cid not in clips]
    if missing_order:
        print("ORDER に無い ID:", missing_order)
        return 3

    need = sum(len(clips[cid]) for cid in CLIP_ORDER)
    rem = remaining_chars(key)
    print(f"clips={len(CLIP_ORDER)} remaining_chars={rem} need_about={need}")
    if rem < need:
        print("文字数枠が不足しています。")
        return 4

    voice_key = "Romaco"
    out_dir = OUT / voice_key
    out_dir.mkdir(parents=True, exist_ok=True)

    client = ElevenV4Client(key)
    failed: list[str] = []
    manifest: list[dict[str, str]] = []

    for cid in CLIP_ORDER:
        text = clips[cid]
        dest = out_dir / f"{cid}.mp3"
        manifest.append({"id": cid, "file": dest.name, "text": text})
        if dest.is_file() and dest.stat().st_size > 800:
            print(f"skip: {dest.name}")
            continue
        try:
            audio = client.synthesize(text, ROMACO, stability=STABILITY, seed=SEED)
            dest.write_bytes(audio)
            print(f"saved: {dest.name} bytes={dest.stat().st_size}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{cid}: {exc}")
            print(f"fail: {cid}: {exc}")
            if "invalid_api_key" in str(exc) or "authentication_error" in str(exc):
                break
        time.sleep(0.42)

    (out_dir / "manifest.json").write_text(
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
