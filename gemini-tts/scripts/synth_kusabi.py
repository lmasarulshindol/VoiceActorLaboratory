"""ボイスドラマ「楔」を Eleven v4 で1行ずつ合成し、台本の間に合わせて1本に結合する."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402

LAB = ROOT.parent
SCRIPT = LAB / "台本" / "楔.md"
OUT_DIR = LAB / "作品" / "楔"
LINE_DIR = OUT_DIR / "lines"
FX_DIR = OUT_DIR / "processed"
FINAL = OUT_DIR / "楔.mp3"

VOICES = {
    "カイ": "DOL4zlUH4vnnX1hByxsw",  # Akira
    "朔": "EbuvaInXUGWtpYRUnKLQ",  # Sawaro
}

# 合成時だけ読みを固定する語。台本の表記は変えない。
READINGS = {
    "地鳴り落とし": "じなりおとし",
    "終焉の守人": "しゅうえんのもりびと",
    "星雨突き": "ほしさめづき",
    "星穿ち": "ほしうがち",
    "山割り": "やまわり",
    "灯閃": "とうせん",
    "黒曜": "こくよう",
    "鍔": "つば",
}

FAST_SCENES = {"場3", "場5"}
LEAD_IN = 1.2
TAIL = 3.0
SCENE_BREAK = 2.6

LINE_RE = re.compile(r"^(カイ|朔)(（遠く）)?「(.*)」$")
TAG_RE = re.compile(r"\[[^\]]+\]")


@dataclass
class Line:
    index: int
    scene: str
    speaker: str
    tags: str
    text: str
    distant: bool
    gap_before: float

    @property
    def silent(self) -> bool:
        return not self.text.strip("…・ 　")

    @property
    def cold(self) -> bool:
        return self.speaker == "朔" and "[cold]" in self.tags

    @property
    def stability(self) -> float:
        if "[shouting]" in self.tags:
            return 0.3
        if "[cold]" in self.tags or "[calm]" in self.tags:
            return 0.5
        return 0.4


def se_pause(body: str, fast: bool) -> float:
    """【】の中身から、セリフの前に置く無音の長さを決める."""
    if body.startswith("長い間"):
        return 3.2
    if body.startswith("間"):
        return 1.6
    heavy = ("門が開く", "門が閉じる", "石段を", "立ち上がる", "膝をつく", "砕け散る", "途切れる")
    if any(word in body for word in heavy):
        return 1.3
    return 0.5 if fast else 0.75


def parse() -> list[Line]:
    text = SCRIPT.read_text(encoding="utf-8")
    body = text.split("## 本編", 1)[1].split("―了―", 1)[0]
    lines: list[Line] = []
    scene = ""
    pending = 0.0
    scene_changed = False
    previous_speaker = ""
    for raw in body.splitlines():
        row = raw.strip()
        if not row:
            continue
        if row.startswith("### "):
            scene = row[4:].split()[0]
            scene_changed = bool(lines)
            pending = 0.0
            continue
        if row.startswith("【") and row.endswith("】"):
            pending += se_pause(row[1:-1].removeprefix("SE："), scene in FAST_SCENES)
            continue
        match = LINE_RE.match(row)
        if not match:
            continue
        speaker, distant, content = match.groups()
        tags = "".join(TAG_RE.findall(content))
        spoken = TAG_RE.sub("", content).strip()
        if pending:
            gap = pending
        elif scene in FAST_SCENES:
            gap = 0.22 if speaker != previous_speaker else 0.3
        else:
            gap = 0.5 if speaker != previous_speaker else 0.4
        if scene_changed:
            gap += SCENE_BREAK
            scene_changed = False
        lines.append(Line(len(lines) + 1, scene, speaker, tags, spoken, bool(distant), gap))
        pending = 0.0
        previous_speaker = speaker
    return lines


def to_spoken(line: Line) -> str:
    text = line.text
    for word, reading in READINGS.items():
        text = text.replace(word, reading)
    return f"{line.tags} {text}".strip()


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])


def process(line: Line, src: Path, dest: Path) -> None:
    """前後の無音を詰め、朔の冷たい声と遠くの叫びに残響をかける."""
    trim = (
        "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05,"
        "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.12,areverse"
    )
    chain = [trim]
    if line.distant:
        chain.append("lowpass=f=3200,aecho=0.8:0.85:180|420:0.45|0.3,volume=0.55")
    elif line.cold:
        chain.append("aecho=0.85:0.6:35|70:0.22|0.12")
    chain.append("aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono")
    run_ffmpeg(["-i", str(src), "-af", ",".join(chain), "-c:a", "pcm_s16le", str(dest)])


def silence(path: Path, seconds: float) -> None:
    run_ffmpeg(
        ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds:.2f}", "-c:a", "pcm_s16le", str(path)]
    )


def synthesize(lines: list[Line]) -> list[str]:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY が未設定です。gemini-tts/.env に記入してください。")
    client = ElevenV4Client(key)
    LINE_DIR.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for line in lines:
        if line.silent:
            continue
        dest = LINE_DIR / f"{line.index:03d}_{line.speaker}.mp3"
        if dest.is_file() and dest.stat().st_size > 1000:
            continue
        spoken = to_spoken(line)
        try:
            dest.write_bytes(client.synthesize(spoken, VOICES[line.speaker], stability=line.stability, seed=11))
            print(f"saved {dest.name}: {spoken}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{dest.name}: {exc}")
            print(f"fail {dest.name}: {exc}", flush=True)
            if "invalid_api_key" in str(exc) or "quota" in str(exc):
                break
        time.sleep(0.3)
    return failed


def assemble(lines: list[Line]) -> None:
    FX_DIR.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    lead = FX_DIR / "lead.wav"
    silence(lead, LEAD_IN)
    parts.append(lead)
    carry = 0.0
    for line in lines:
        if line.silent:
            carry += line.gap_before + 1.1
            continue
        gap = FX_DIR / f"{line.index:03d}_gap.wav"
        silence(gap, line.gap_before + carry)
        carry = 0.0
        voice = FX_DIR / f"{line.index:03d}_{line.speaker}.wav"
        process(line, LINE_DIR / f"{line.index:03d}_{line.speaker}.mp3", voice)
        parts.extend([gap, voice])
    tail = FX_DIR / "tail.wav"
    silence(tail, TAIL + carry)
    parts.append(tail)
    listing = FX_DIR / "concat.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run_ffmpeg(
        [
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-codec:a", "libmp3lame", "-qscale:a", "2", str(FINAL),
        ]
    )


def main() -> int:
    lines = parse()
    spoken = [line for line in lines if not line.silent]
    chars = sum(len(to_spoken(line)) for line in spoken)
    print(f"lines={len(lines)} spoken={len(spoken)} chars={chars}", flush=True)
    if "--dry-run" in sys.argv:
        for line in lines:
            print(f"{line.index:03d} {line.scene} gap={line.gap_before:.2f} {line.speaker} {to_spoken(line)}")
        return 0
    failed = synthesize(lines)
    if failed:
        print("FAILED")
        for item in failed:
            print(item)
        return 1
    assemble(lines)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(FINAL)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    print(f"done: {FINAL} duration={float(result.stdout.strip()):.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
