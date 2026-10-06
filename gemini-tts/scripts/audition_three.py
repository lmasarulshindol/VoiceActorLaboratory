"""オーディション3本のセリフを Gemini TTS で WAV にする."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gemini_tts.audio import save_wav  # noqa: E402
from gemini_tts.client import GeminiTTSClient  # noqa: E402
from gemini_tts.config import load_config  # noqa: E402

OUT = Path(r"c:\Users\MasaruShindo\work2\003_ゲーム\novel-studio\projects\audition\audio")

BASE = "日本語の男性。ミドルからロー。張り上げず、間を残す。"

LINES: list[tuple[str, str, str]] = [
    ("w1", "Enceladus", f"{BASE} 苛立ちを抑え、短く突き放す。声量は上げない。"),
    ("w2", "Enceladus", f"{BASE} 冷たく距離を置く。仲間ではないと言い切るが、強がりが混じる。"),
    ("w3", "Enceladus", f"{BASE} 嫌いだと言いながら言い淀む。本音を隠す苦しさ。"),
    ("w4", "Enceladus", f"{BASE} 静かに覚悟を決める。嘘の報告を告げる重さと罪悪感。"),
    ("w5", "Enceladus", f"{BASE} 声を落とし、切なく頼む。突き放したあとに優しさが漏れる。"),
    ("c1", "Sulafat", f"{BASE} 二十代後半。帰られそうで焦る。言葉は少し早いが、叫ばない。"),
    ("c2", "Sulafat", f"{BASE} 言いかけて照れで濁す。息が浅い。"),
    ("c3", "Sulafat", f"{BASE} 何度も逃した悔しさを、静かに認める。"),
    ("c4", "Sulafat", f"{BASE} 笑うなと先に言う。不器用で、声が少し上ずるが張り上げない。"),
    ("c5", "Sulafat", f"{BASE} 一拍置いてから、真剣に、小さく好きだと告げる。"),
    ("n1", "Gacrux", f"{BASE} 三十代の企業ナレーション。落ち着いた低音。端正で、感情を乗せすぎない。"),
    ("n2", "Gacrux", f"{BASE} 企業ナレーション。三つの言葉を均等に、信頼感を持って読む。"),
    ("n3", "Gacrux", f"{BASE} 企業ナレーション。積み重ねを語る。誇張しない。"),
    ("n4", "Gacrux", f"{BASE} 企業ナレーションの結び。堂々としているが、熱くなりすぎない。"),
]

TEXT = {
    "w1": "何度言えばわかるんだ。",
    "w2": "僕はお前たちの仲間じゃない。ただ監視役を任せられただけだ。",
    "w3": "……お前のように図々しくて、脳天気で、馴れ馴れしい奴は嫌いなんだよ。",
    "w4": "……報告には、魔物に襲われて死んだと書いておく。",
    "w5": "だからもう、僕に関わらないでくれ……頼むから。",
    "c1": "ちょっと待って、今帰られると困る……いや、困るっていうか。",
    "c2": "ずっと……言おうと思ってたことがあるんだ。",
    "c3": "何度も言おうとして、そのたびにタイミング逃してさ……。",
    "c4": "絶対、笑うなよ……こういうの得意じゃないんだからさ。",
    "c5": "……お前のこと――ずっと好きだった。",
    "n1": "技術は、目に見えるものだけではない。",
    "n2": "より速く、より正確に、そしてより安全に。",
    "n3": "積み重ねてきた一つひとつの工夫が、社会の新しい基準をつくっていく。",
    "n4": "私たちは、まだ誰も見たことのない明日を、確かな技術で支えていく。",
}


def main() -> int:
    cfg = load_config(env_path=ROOT / ".env")
    client = GeminiTTSClient(cfg.require_api_key(), model=cfg.model, sample_rate=cfg.sample_rate)
    OUT.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for line_id, voice, style in LINES:
        dest = OUT / f"{line_id}.wav"
        if dest.is_file() and dest.stat().st_size > 1000:
            print(f"skip: {dest.name}")
            continue
        try:
            result = client.synthesize(TEXT[line_id], voice=voice, style=style, language_code="ja-JP")
            save_wav(dest, result.audio_wav, sample_rate=cfg.sample_rate)
            print(f"saved: {dest.name} voice={voice} bytes={dest.stat().st_size}")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{line_id}: {exc}")
            print(f"fail: {line_id}: {exc}")
        time.sleep(0.6)
    if failed:
        print("FAILED")
        for item in failed:
            print(item)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
