"""全セリフを Gemini TTS で合成する（既存ファイルはスキップ）.

使い方:
  py -3 tts.py                                   # 未生成の行だけ合成
  py -3 tts.py 126 164                           # 指定行を作り直す
  py -3 tts.py --model gemini-3.8-flash-lite-tts # モデルを変えて合成
  py -3 tts.py --upgrade                         # 既定モデル以外で作った行を作り直す

どの行をどのモデルで作ったかは build/voice_models.json に記録する。
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from cues import ROOT, parse_script, voice_filename

GEMINI_ROOT = ROOT.parents[2] / "gemini-tts"
sys.path.insert(0, str(GEMINI_ROOT / "src"))

from gemini_tts.audio import save_wav  # noqa: E402
from gemini_tts.client import GeminiTTSClient  # noqa: E402
from gemini_tts.config import DEFAULT_MODEL, load_config  # noqa: E402

VOICE_DIR = ROOT / "build" / "voice"
MODELS_JSON = ROOT / "build" / "voice_models.json"
DELAY_SEC = 2.0
MAX_RETRIES = 5


def load_models() -> dict[str, str]:
    if MODELS_JSON.is_file():
        return json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    return {}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lines", nargs="*", type=int)
    ap.add_argument("--model")
    ap.add_argument("--upgrade", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(env_path=GEMINI_ROOT / ".env", overrides={"model": args.model})
    client = GeminiTTSClient(cfg.require_api_key(), model=cfg.model, sample_rate=cfg.sample_rate)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    models = load_models()

    redo = set(args.lines)
    if args.upgrade:
        redo |= {int(no) for no, m in models.items() if m != DEFAULT_MODEL}

    targets = [ln for ln in parse_script() if not ln.silent]
    errors: list[int] = []
    for ln in targets:
        out = VOICE_DIR / voice_filename(ln)
        if out.is_file() and out.stat().st_size > 0 and ln.no not in redo:
            models.setdefault(str(ln.no), DEFAULT_MODEL)
            continue
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = client.synthesize(ln.spoken, voice=ln.voice or "Kore", style=ln.style)
                save_wav(out, result.audio_wav, sample_rate=client.sample_rate)
                models[str(ln.no)] = result.model
                MODELS_JSON.write_text(json.dumps(models, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"[ok] {ln.no:03d} {ln.speaker} {result.model} {ln.spoken[:24]}", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if "PerDay" in msg:
                    print(f"[daily quota] {ln.no:03d} {cfg.model}: 本日の上限に達しました", flush=True)
                    errors.append(ln.no)
                    MODELS_JSON.write_text(json.dumps(models, ensure_ascii=False, indent=1), encoding="utf-8")
                    print(f"done: stopped at {ln.no}", flush=True)
                    return 2
                low = msg.lower()
                retryable = "429" in low or "resource_exhausted" in low or "503" in low or "500" in low
                if retryable and attempt < MAX_RETRIES:
                    wait = 20.0 * (attempt + 1)
                    print(f"[wait {wait:.0f}s] {ln.no:03d}", flush=True)
                    time.sleep(wait)
                    continue
                print(f"[error] {ln.no:03d} {exc}", flush=True)
                errors.append(ln.no)
                break
        time.sleep(DELAY_SEC)

    MODELS_JSON.write_text(json.dumps(models, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: targets={len(targets)} errors={errors}", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
