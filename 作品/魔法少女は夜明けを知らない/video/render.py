"""タイムライン構築 → 音声ミックス → ASS字幕 → ffmpeg で動画化.

使い方:
  py -3 render.py            # 全工程
  py -3 render.py --audio    # 音声ミックスと字幕だけ（動画は作らない）
  py -3 render.py --subs     # 場面映像は再利用し、音声・字幕を作り直して最終エンコード
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import audio_fx as fx
from cues import (
    BGM_SECTIONS,
    FLASH,
    ROOT,
    SCENES,
    SHAKE,
    SPEAKER_COLORS,
    TITLE,
    VOICE_NAMES,
    Line,
    parse_script,
    section_at,
    voice_filename,
)

BUILD = ROOT / "build"
VOICE_DIR = BUILD / "voice"
IMAGE_DIR = ROOT / "images"
OUT_MP4 = ROOT.parent / f"{TITLE}.mp4"
W, H, FPS = 1920, 1080, 30

TITLE_SEC = 7.0
END_SEC = 9.0
GAP = 0.38
SILENT_SEC = 1.7
MONSTER_LINES = {41, 58, 98, 143, 149}
SPIRIT_LINES = {151}
INNER_LINES = {164, 166, 169, 171}
VOICE_PEAK = 0.82
DISPLAY_NAME = {151: "詩織"}


@dataclass
class Event:
    line: Line
    start: float
    end: float
    audio: np.ndarray | None = None


def direction_seconds(line: Line) -> float:
    return float(np.clip(len(line.display) * 0.085, 2.4, 4.8))


def load_line_audio(line: Line) -> np.ndarray:
    path = VOICE_DIR / voice_filename(line)
    if not path.is_file():
        raise FileNotFoundError(f"音声がありません: {path.name}（tts.py を実行してください）")
    x = fx.norm(fx.trim_silence(fx.load_voice(path)), VOICE_PEAK)
    if line.no in MONSTER_LINES:
        x = fx.monster_voice(x)
    elif line.no in SPIRIT_LINES:
        x = fx.spirit_voice(x)
    elif line.no in INNER_LINES:
        x = fx.inner_voice(x)
    return x


def build_timeline(lines: list[Line]) -> tuple[list[Event], float]:
    events: list[Event] = []
    t = TITLE_SEC
    prev_dir = False
    for ln in lines:
        if ln.is_direction:
            t += 0.25
            dur = direction_seconds(ln)
            events.append(Event(ln, t, t + dur))
            t += dur + 0.2
            prev_dir = True
            continue
        if ln.silent:
            events.append(Event(ln, t, t + SILENT_SEC))
            t += SILENT_SEC + GAP
            prev_dir = False
            continue
        audio = load_line_audio(ln)
        dur = len(audio) / fx.SR
        tail = 0.0
        if ln.no in MONSTER_LINES or ln.no in SPIRIT_LINES:
            tail = 1.6
        events.append(Event(ln, t, t + dur - tail * 0.6, audio))
        t += dur - tail + GAP + (0.1 if prev_dir else 0.0)
        prev_dir = False
    total = t + END_SEC
    return events, total


def start_of_line(events: list[Event], no: int) -> float:
    for ev in events:
        if ev.line.no == no:
            return ev.start
    raise KeyError(no)


# ---------------------------------------------------------------- 音声

def mix_audio(events: list[Event], total: float) -> np.ndarray:
    n = int(total * fx.SR) + fx.SR
    voice = np.zeros(n)
    sfx = np.zeros(n)
    bgm = np.zeros(n)

    for ev in events:
        if ev.audio is not None:
            fx.place(voice, ev.audio, ev.start)
        for name in ev.line.sfx:
            clip = fx.SFX_BANK[name]()
            offset = 0.0 if ev.line.is_direction else max(0.0, (ev.end - ev.start) * 0.55)
            fx.place(sfx, clip, ev.start + offset, fx.SFX_GAIN.get(name, 1.0))

    bounds = [(start_of_line(events, s) if s > 1 else 0.0, name) for s, name in BGM_SECTIONS]
    for i, (s, name) in enumerate(bounds):
        e = bounds[i + 1][0] if i + 1 < len(bounds) else total
        if name is None:
            continue
        xf = 1.5
        length = e - s + xf
        clip = fx.BGM_BANK[name](length)
        clip = fx.fade(clip, 1.2 if s > 0 else 3.0, xf if i + 1 < len(bounds) else 5.0)
        fx.place(bgm, clip, s, fx.BGM_GAIN[name])

    bgm *= fx.duck_curve(voice, 0.5)
    master = voice * 1.0 + sfx * 0.7 + bgm * 0.5
    master = np.tanh(master * 1.1) / np.tanh(1.1)
    master = fx.norm(master, 0.95)
    return np.stack([master, master], axis=1)


# ---------------------------------------------------------------- 字幕

def ass_time(sec: float) -> str:
    sec = max(sec, 0.0)
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text: str) -> str:
    return text.replace("{", "｛").replace("}", "｝").replace("\n", " ")


BREAK_AFTER = "、。！？…）」　"


def wrap_jp(text: str, width: int) -> str:
    """空白のない日本語を、なるべく句読点の直後で width 文字以内に折り返す."""
    rows: list[str] = []
    rest = text.strip()
    while len(rest) > width:
        cut = max((i + 1 for i in range(width // 2, width) if rest[i] in BREAK_AFTER), default=width)
        while cut < len(rest) and rest[cut] in BREAK_AFTER:
            cut += 1
        rows.append(rest[:cut].strip("　"))
        rest = rest[cut:].lstrip("　")
    if rest:
        rows.append(rest)
    return r"\N".join(rows)


ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line,BIZ UDPGothic,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,1,0,1,4,2,2,160,160,70,1
Style: Direction,BIZ UDPMincho Medium,40,&H00E6E6E6,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,3,1,8,200,200,60,1
Style: Title,BIZ UDPMincho Medium,104,&H00FFFFFF,&H00FFFFFF,&H00301020,&H00000000,1,0,0,0,100,100,10,0,1,5,4,5,100,100,0,1
Style: Sub,BIZ UDPMincho Medium,40,&H00E0D8F0,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,6,0,1,3,2,5,100,100,0,1
Style: Flash,BIZ UDPGothic,10,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

FLASH_COLORS = {"white": ("&HFFFFFF&", 350), "red": ("&H2020D0&", 300), "white_long": ("&HFFFFFF&", 2600)}


def build_ass(events: list[Event], total: float) -> str:
    rows: list[str] = []

    def add(layer: int, start: float, end: float, style: str, text: str) -> None:
        rows.append(f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}")

    add(5, 0.6, TITLE_SEC - 0.4, "Title", r"{\fad(1200,900)\blur2}" + TITLE)
    add(5, 1.6, TITLE_SEC - 0.4, "Sub", r"{\fad(1200,900)\pos(960,660)}― ボイスドラマ ―")

    for ev in events:
        ln = ev.line
        if ln.is_direction:
            add(2, ev.start, ev.end, "Direction", r"{\fad(400,400)}" + wrap_jp(ass_escape(ln.display), 34))
        else:
            color = SPEAKER_COLORS.get(ln.speaker, "&H00FFFFFF")
            label = DISPLAY_NAME.get(ln.no, ln.speaker)
            if label != ln.speaker:
                color = "&H00C0E8FF"
            name = rf"{{\fs40\c{color}&}}{label}\N{{\r}}"
            end = max(ev.end + 0.25, ev.start + 1.0)
            add(3, ev.start, end, "Line", r"{\fad(120,150)}" + name + wrap_jp(ass_escape(ln.display), 26))
        if ln.no in FLASH:
            color, ms = FLASH_COLORS[FLASH[ln.no]]
            at = ev.start if ln.is_direction else ev.start + (ev.end - ev.start) * 0.55
            box = rf"{{\an7\pos(0,0)\p1\bord0\shad0\c{color}\1a&H30&\fad(40,{ms})}}m 0 0 l {W} 0 {W} {H} 0 {H}{{\p0}}"
            add(9, at, at + ms / 1000 + 0.05, "Flash", box)

    end_start = total - END_SEC + 1.0
    credits = [
        ("Title", 0.0, r"\pos(960,300)", "おわり"),
        ("Sub", 1.5, r"\pos(960,560)\fsp2", "出演（AI音声：ElevenLabs v4）"),
        ("Sub", 1.5, r"\pos(960,630)\fsp2", f"灯里：{VOICE_NAMES['灯里']}　　澪：{VOICE_NAMES['澪']}"),
        ("Sub", 1.5, r"\pos(960,690)\fsp2", f"ノクス：{VOICE_NAMES['ノクス']}　　災禍：{VOICE_NAMES['災禍']}"),
        ("Sub", 1.5, r"\pos(960,790)\fsp2", "脚本・演出：Voice Actor Laboratory　　イラスト：AI生成"),
    ]
    for style, delay, pos, text in credits:
        add(6, end_start + delay, total - 0.3, style, "{" + pos + r"\fad(1000,1200)}" + text)
    return ASS_HEADER + "\n".join(rows) + "\n"


# ---------------------------------------------------------------- 映像

def shake_expr(starts: list[float], amp: float, freq: float, phase: float) -> str:
    terms = [
        f"if(between(t,{s:.3f},{s + 0.7:.3f}),{amp}*(1-(t-{s:.3f})/0.7)*sin((t-{s:.3f})*{freq}+{phase}),0)"
        for s in starts
    ]
    return "+".join(terms) if terms else "0"


def render_scene(img: Path, out: Path, dur: float, idx: int, shakes: list[float], dark: bool) -> None:
    sw, sh = int(W * 1.14), int(H * 1.14)
    margin_x, margin_y = (sw - W), (sh - H)
    span = margin_x - 60
    direction = 1 if idx % 2 == 0 else -1
    base_x = f"30+{span}*t/{dur:.3f}" if direction > 0 else f"{30 + span}-{span}*t/{dur:.3f}"
    base_y = f"{margin_y / 2:.1f}"
    x = f"{base_x}+({shake_expr(shakes, 26, 95, 0)})"
    y = f"{base_y}+({shake_expr(shakes, 18, 83, 1.3)})"
    vf = [
        f"scale={sw}:{sh}:flags=lanczos",
        f"crop={W}:{H}:x='{x}':y='{y}'",
        "vignette=PI/4.5" if dark else "vignette=PI/6",
        "eq=contrast=1.05:saturation=1.05",
        f"fade=t=in:st=0:d=0.6,fade=t=out:st={max(dur - 0.6, 0):.3f}:d=0.6",
        "format=yuv420p",
    ]
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-i", str(img),
        "-t", f"{dur:.3f}", "-vf", ",".join(vf),
        "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def render_video(events: list[Event], total: float) -> Path:
    seg_dir = BUILD / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    starts = [0.0] + [start_of_line(events, s) - 0.25 for s, _ in SCENES[1:]]
    ends = starts[1:] + [total]
    shake_times = {}
    for ev in events:
        if ev.line.no in SHAKE:
            shake_times[ev.line.no] = ev.start if ev.line.is_direction else ev.start + (ev.end - ev.start) * 0.55
    list_lines = []
    for i, ((first, image_id), s, e) in enumerate(zip(SCENES, starts, ends)):
        last = SCENES[i + 1][0] if i + 1 < len(SCENES) else 10_000
        local = [t - s for no, t in shake_times.items() if first <= no < last]
        out = seg_dir / f"{i:02d}_{image_id}.mp4"
        print(f"  scene {image_id}: {e - s:.1f}s shakes={len(local)}", flush=True)
        render_scene(IMAGE_DIR / f"{image_id}.jpg", out, e - s, i, local, image_id not in {"10_shiori", "11_dawn"})
        list_lines.append(f"file 'segments/{out.name}'")
    (BUILD / "concat.txt").write_text("\n".join(list_lines) + "\n", encoding="utf-8")
    raw = BUILD / "video_raw.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", raw.name],
        check=True,
        cwd=BUILD,
    )
    return raw


def prepare_fonts() -> None:
    fonts = BUILD / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for name in ("BIZ-UDGothicB.ttc", "BIZ-UDGothicR.ttc", "BIZ-UDMinchoM.ttc"):
        src = Path("C:/Windows/Fonts") / name
        if src.is_file() and not (fonts / name).is_file():
            shutil.copy(src, fonts / name)


def finalize(raw: Path) -> None:
    tmp = BUILD / "final.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-stats",
            "-i", raw.name, "-i", "mix.wav",
            "-vf", "ass=subs.ass:fontsdir=fonts",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-af", "volume=-1.5dB",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            tmp.name,
        ],
        check=True,
        cwd=BUILD,
    )
    shutil.copy(tmp, OUT_MP4)


def main(argv: list[str]) -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    lines = parse_script()
    print("timeline...", flush=True)
    events, total = build_timeline(lines)
    print(f"  total {total / 60:.1f} min", flush=True)
    print("mix...", flush=True)
    fx.write_wav(BUILD / "mix.wav", mix_audio(events, total))
    (BUILD / "subs.ass").write_text(build_ass(events, total), encoding="utf-8-sig")
    if "--audio" in argv:
        return 0
    prepare_fonts()
    raw = BUILD / "video_raw.mp4"
    if "--subs" in argv and raw.is_file():
        print("reuse scenes (subtitles only)", flush=True)
    else:
        print("scenes...", flush=True)
        raw = render_video(events, total)
    print("final encode...", flush=True)
    finalize(raw)
    print(f"done: {OUT_MP4}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
