"""効果音・BGMの手続き合成、声の加工、最終ミックス（すべて numpy）."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
RNG = np.random.default_rng(20261002)


# ---------------------------------------------------------------- 基本部品

def t_axis(sec: float) -> np.ndarray:
    return np.arange(int(sec * SR)) / SR


def noise(sec: float) -> np.ndarray:
    return RNG.standard_normal(int(sec * SR))


def band(x: np.ndarray, lo: float = 0.0, hi: float = SR / 2) -> np.ndarray:
    """FFT マスクによる帯域通過."""
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    mask = (freqs >= lo) & (freqs <= hi)
    return np.fft.irfft(spec * mask, n=len(x))


def brown(sec: float) -> np.ndarray:
    x = np.cumsum(noise(sec))
    x -= np.linspace(x[0], x[-1], len(x))
    return x / (np.max(np.abs(x)) + 1e-9)


def env_ad(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    d = np.exp(-np.clip(t - attack, 0, None) / max(decay, 1e-4))
    return a * d


def fade(x: np.ndarray, fin: float = 0.01, fout: float = 0.05) -> np.ndarray:
    y = x.copy()
    ni, no = min(len(y), int(fin * SR)), min(len(y), int(fout * SR))
    if ni:
        y[:ni] *= np.linspace(0, 1, ni)
    if no:
        y[-no:] *= np.linspace(1, 0, no)
    return y


def sweep(f0: float, f1: float, sec: float, *, exp: bool = True) -> np.ndarray:
    n = int(sec * SR)
    if exp:
        f = f0 * (f1 / f0) ** (np.arange(n) / max(n - 1, 1))
    else:
        f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = np.max(np.abs(x)) if len(x) else 0
    return x * (peak / m) if m > 0 else x


def reverb(x: np.ndarray, sec: float = 2.0, wet: float = 0.35, bright: float = 6000) -> np.ndarray:
    """指数減衰ノイズとの畳み込みによる簡易リバーブ."""
    ir = band(noise(sec), 80, bright) * np.exp(-np.arange(int(sec * SR)) / (SR * sec / 5))
    ir /= np.sqrt(np.sum(ir**2)) + 1e-9
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:n]
    dry = np.concatenate([x, np.zeros(len(ir) - 1)])
    return dry * (1 - wet) + norm(y, np.max(np.abs(x)) + 1e-9) * wet


def mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def tone(freq: float, sec: float, harmonics: int = 4, detune: float = 0.0, *, n: int | None = None) -> np.ndarray:
    t = np.arange(n) / SR if n is not None else t_axis(sec)
    y = np.zeros_like(t)
    for h in range(1, harmonics + 1):
        y += np.sin(2 * np.pi * freq * h * t * (1 + detune)) / h
    return y


# ---------------------------------------------------------------- 効果音

def _thump(f0: float, f1: float, sec: float) -> np.ndarray:
    return sweep(f0, f1, sec) * env_ad(int(sec * SR), 0.002, sec / 4)


def sfx_mist() -> np.ndarray:
    s = 3.5
    x = band(noise(s), 60, 700) * np.linspace(0, 1, int(s * SR)) ** 1.5
    x += 0.5 * tone(48, s, 3) * np.linspace(0, 1, int(s * SR))
    return fade(reverb(norm(x, 0.5), 2.5, 0.4), 0.3, 0.8)


def sfx_transform() -> np.ndarray:
    s = 3.0
    n = int(s * SR)
    x = np.zeros(n)
    for i, m in enumerate([72, 76, 79, 84, 88, 91]):
        start = int(i * 0.18 * SR)
        x[start:] += tone(mtof(m), 0, 2, n=n - start) * env_ad(n - start, 0.02, 1.2)
    x += 0.4 * band(noise(s), 3000, 12000) * np.linspace(0, 1, n) * env_ad(n, 2.0, 0.6)
    x += 0.5 * sweep(300, 2400, s) * np.linspace(0, 1, n) ** 2 * 0.3
    return fade(reverb(norm(x, 0.55), 2.5, 0.45), 0.05, 0.6)


def sfx_growl() -> np.ndarray:
    s = 1.8
    t = t_axis(s)
    x = band(noise(s), 70, 900) * (0.6 + 0.4 * np.sin(2 * np.pi * 28 * t))
    x += 0.6 * tone(65, s, 6) * (0.5 + 0.5 * np.sin(2 * np.pi * 9 * t))
    return fade(reverb(norm(x, 0.6) * env_ad(len(t), 0.15, 0.9), 1.2, 0.3), 0.02, 0.4)


def sfx_beam_small() -> np.ndarray:
    s = 1.0
    n = int(s * SR)
    x = 0.6 * sweep(500, 2200, s) + band(noise(s), 2500, 14000) * 0.7
    return fade(reverb(norm(x * env_ad(n, 0.01, 0.35), 0.6), 1.0, 0.3), 0.005, 0.2)


def sfx_slash() -> np.ndarray:
    s = 0.35
    n = int(s * SR)
    x = band(noise(s), 2000, 16000) * env_ad(n, 0.004, 0.06)
    x += 0.4 * sweep(4000, 900, s) * env_ad(n, 0.002, 0.05)
    return fade(norm(x, 0.7), 0.002, 0.05)


def sfx_impact() -> np.ndarray:
    s = 0.7
    x = _thump(90, 35, s) + 0.5 * band(noise(s), 200, 5000) * env_ad(int(s * SR), 0.001, 0.04)
    return fade(reverb(norm(x, 0.85), 0.8, 0.2), 0.001, 0.1)


def sfx_impact_big() -> np.ndarray:
    s = 2.2
    n = int(s * SR)
    x = 1.2 * _thump(70, 22, s)
    x += 0.7 * band(noise(s), 100, 6000) * env_ad(n, 0.001, 0.12)
    x += 0.5 * brown(s) * env_ad(n, 0.01, 0.6)
    return fade(reverb(np.tanh(norm(x, 1.6)) * 0.9, 1.8, 0.3), 0.001, 0.4)


def sfx_shield() -> np.ndarray:
    s = 1.6
    t = t_axis(s)
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in [(1180, 2.5), (1730, 3.2), (2460, 4.0), (3130, 5.0)])
    x += 0.5 * band(noise(s), 4000, 12000) * env_ad(len(t), 0.001, 0.05)
    return fade(reverb(norm(x, 0.5), 1.5, 0.4), 0.002, 0.3)


def sfx_burst() -> np.ndarray:
    s = 0.9
    n = int(s * SR)
    x = band(noise(s), 80, 3000) * env_ad(n, 0.003, 0.18) + 0.6 * _thump(120, 40, s)
    return fade(reverb(norm(x, 0.7), 1.2, 0.35), 0.002, 0.2)


def sfx_rumble() -> np.ndarray:
    s = 4.5
    n = int(s * SR)
    t = t_axis(s)
    x = band(brown(s), 20, 180) * (0.7 + 0.3 * np.sin(2 * np.pi * 3.3 * t))
    x *= np.minimum(1, t / 0.8) * np.minimum(1, (s - t) / 1.5)
    return norm(x, 0.9)[:n]


def _grains(sec: float, count: int, lo: float, hi: float, glen: float = 0.04) -> np.ndarray:
    n = int(sec * SR)
    x = np.zeros(n)
    g = int(glen * SR)
    for _ in range(count):
        p = RNG.integers(0, max(n - g, 1))
        amp = RNG.uniform(0.2, 1.0)
        x[p : p + g] += band(noise(glen), lo, hi)[: len(x[p : p + g])] * env_ad(g, 0.001, glen / 4)[: len(x[p : p + g])] * amp
    return x


def sfx_crumble() -> np.ndarray:
    s = 2.8
    x = _grains(s, 90, 200, 4000, 0.06) * np.linspace(1, 0.2, int(s * SR))
    x += 0.4 * band(brown(s), 30, 200) * np.linspace(1, 0, int(s * SR))
    return fade(reverb(norm(x, 0.6), 1.2, 0.25), 0.005, 0.4)


def sfx_whoosh() -> np.ndarray:
    s = 0.9
    n = int(s * SR)
    sh = np.sin(np.linspace(0, np.pi, n))
    x = np.zeros(n)
    nz = noise(s)
    for i, (lo, hi) in enumerate([(200, 800), (500, 2000), (1200, 5000), (500, 2000), (200, 800)]):
        seg = slice(i * n // 5, (i + 1) * n // 5)
        x[seg] = band(nz, lo, hi)[seg]
    return fade(norm(x * sh, 0.6), 0.01, 0.1)


def sfx_rubble() -> np.ndarray:
    s = 2.5
    return fade(norm(_grains(s, 35, 300, 3500, 0.03), 0.35), 0.01, 0.3)


def sfx_charge_dark() -> np.ndarray:
    s = 3.2
    n = int(s * SR)
    ramp = np.linspace(0, 1, n) ** 2.5
    x = (tone(55, s, 6) + tone(58.3, s, 6)) * 0.4 + band(noise(s), 50, 1500) * 0.6
    x += 0.3 * band(_grains(s, 120, 2000, 9000, 0.01), 2000, 9000) * ramp
    return fade(norm(x * ramp, 0.75), 0.05, 0.03)


def sfx_crack() -> np.ndarray:
    s = 1.0
    t = t_axis(s)
    x = _grains(s, 12, 3000, 12000, 0.008)
    x += 0.3 * np.sin(2 * np.pi * 2900 * t) * np.exp(-t * 6)
    return fade(reverb(norm(x, 0.45), 1.0, 0.35), 0.002, 0.3)


def sfx_thunder() -> np.ndarray:
    s = 3.5
    n = int(s * SR)
    crack = band(noise(s), 500, 12000) * env_ad(n, 0.002, 0.08) * 1.2
    crack += _grains(s, 60, 1000, 8000, 0.01) * np.exp(-t_axis(s) * 3)
    roll = band(brown(s), 25, 250) * env_ad(n, 0.05, 1.2)
    return fade(reverb(np.tanh(norm(crack + roll, 1.5)) * 0.85, 2.0, 0.3), 0.001, 0.6)


def sfx_shatter() -> np.ndarray:
    s = 2.4
    t = t_axis(s)
    x = _grains(s, 140, 3000, 15000, 0.02) * np.exp(-t * 1.6)
    for f in (2100, 3400, 4700, 6100):
        x += 0.15 * np.sin(2 * np.pi * f * t) * np.exp(-t * 3)
    x += 0.5 * band(noise(s), 800, 10000) * env_ad(len(t), 0.001, 0.05)
    return fade(reverb(norm(x, 0.6), 2.0, 0.4), 0.001, 0.5)


def sfx_charge() -> np.ndarray:
    s = 3.2
    n = int(s * SR)
    ramp = np.linspace(0, 1, n)
    x = 0.5 * sweep(180, 900, s) + 0.3 * sweep(270, 1350, s)
    x += 0.4 * band(noise(s), 4000, 14000) * ramp
    return fade(reverb(norm(x * ramp**1.5, 0.55), 1.5, 0.35), 0.1, 0.1)


def sfx_beam_big() -> np.ndarray:
    s = 6.5
    n = int(s * SR)
    t = t_axis(s)
    body = env_ad(n, 0.05, 2.2)
    x = 1.0 * band(noise(s), 40, 9000) * body
    x += 1.2 * tone(36, s, 8) * body
    for m in (57, 64, 69, 72, 76):
        x += 0.25 * tone(mtof(m), s, 3) * np.minimum(1, t / 0.5) * np.exp(-t / 3.5)
    x += 1.0 * _thump(60, 20, s)
    return fade(reverb(np.tanh(norm(x, 2.0)) * 0.95, 3.0, 0.4), 0.002, 1.5)


def sfx_shimmer() -> np.ndarray:
    s = 3.5
    n = int(s * SR)
    x = np.zeros(n)
    for _ in range(40):
        f = RNG.uniform(2500, 7000)
        p = RNG.integers(0, n - SR // 2)
        seg = np.sin(2 * np.pi * f * t_axis(0.5)) * env_ad(SR // 2, 0.005, 0.12)
        x[p : p + len(seg)] += seg * RNG.uniform(0.2, 0.6)
    return fade(reverb(norm(x, 0.35), 2.5, 0.5), 0.2, 0.8)


def sfx_birds() -> np.ndarray:
    s = 8.0
    n = int(s * SR)
    x = np.zeros(n)
    for _ in range(14):
        p = RNG.integers(0, n - SR)
        for k in range(RNG.integers(2, 5)):
            f0 = RNG.uniform(2800, 3600)
            seg = sweep(f0, f0 * RNG.uniform(1.2, 1.5), 0.07) * env_ad(int(0.07 * SR), 0.005, 0.02)
            q = p + int(k * 0.11 * SR)
            x[q : q + len(seg)] += seg[: len(x[q : q + len(seg)])]
    return fade(reverb(norm(x, 0.15), 1.5, 0.5), 0.5, 1.0)


def sfx_train() -> np.ndarray:
    s = 9.0
    n = int(s * SR)
    t = t_axis(s)
    x = band(brown(s), 40, 400) * 0.5
    for k in range(10):
        for off in (0.0, 0.16):
            p = int((0.6 + k * 0.8 + off) * SR)
            if p < n - SR // 10:
                x[p : p + SR // 10] += band(noise(0.1), 100, 1500) * env_ad(SR // 10, 0.002, 0.02)
    x *= np.sin(np.pi * t / s) ** 2
    return reverb(band(norm(x, 0.25), 30, 1800), 2.5, 0.5)


SFX_BANK = {
    name[4:]: fn for name, fn in globals().items() if name.startswith("sfx_") and callable(fn)
}

SFX_GAIN = {"birds": 0.6, "train": 0.8, "rubble": 0.7, "mist": 0.7, "rumble": 0.8}


# ---------------------------------------------------------------- BGM

def _pad(chords: list[list[int]], chord_sec: float, total: float, *, vol: float = 1.0, harmonics: int = 3) -> np.ndarray:
    n = int(total * SR)
    x = np.zeros(n)
    seg_n = int(chord_sec * SR)
    xf = int(0.6 * SR)
    i = 0
    pos = 0
    while pos < n:
        chord = chords[i % len(chords)]
        length = min(seg_n + xf, n - pos)
        seg = np.zeros(length)
        for m in chord:
            seg += tone(mtof(m), 0, harmonics, 0.0, n=length) + tone(mtof(m), 0, harmonics, 0.003, n=length)
        e = np.ones(length)
        a = min(xf, length)
        e[:a] = np.linspace(0, 1, a)
        e[-a:] *= np.linspace(1, 0, a)
        x[pos : pos + length] += seg * e
        pos += seg_n
        i += 1
    return band(x, 40, 3500) * vol


def _kick_track(total: float, bpm: float, pattern: list[float]) -> np.ndarray:
    n = int(total * SR)
    x = np.zeros(n)
    beat = 60 / bpm
    k = _thump(110, 40, 0.35)
    bar = beat * 4
    b = 0.0
    while b < total:
        for p in pattern:
            q = int((b + p * beat) * SR)
            if q < n - len(k):
                x[q : q + len(k)] += k
        b += bar
    return x


def _hats(total: float, bpm: float) -> np.ndarray:
    n = int(total * SR)
    x = np.zeros(n)
    step = 60 / bpm / 2
    h = band(noise(0.05), 7000, 16000) * env_ad(int(0.05 * SR), 0.001, 0.012)
    t = 0.0
    i = 0
    while t < total:
        q = int(t * SR)
        if q < n - len(h):
            x[q : q + len(h)] += h * (0.6 if i % 2 else 0.3)
        t += step
        i += 1
    return x


def _ostinato(total: float, bpm: float, notes: list[int]) -> np.ndarray:
    n = int(total * SR)
    x = np.zeros(n)
    step = 60 / bpm / 2
    t = 0.0
    i = 0
    while t < total:
        q = int(t * SR)
        seg = tone(mtof(notes[i % len(notes)]), step * 0.95, 7) * env_ad(int(step * 0.95 * SR), 0.004, step * 0.5)
        end = min(n, q + len(seg))
        x[q:end] += seg[: end - q]
        t += step
        i += 1
    return band(x, 30, 1200)


def _plucks(total: float, bpm: float, seq: list[int], vol: float = 1.0) -> np.ndarray:
    n = int(total * SR)
    x = np.zeros(n)
    step = 60 / bpm / 2
    t = 0.0
    i = 0
    while t < total:
        m = seq[i % len(seq)]
        if m > 0:
            q = int(t * SR)
            dur = 2.5
            seg = tone(mtof(m), dur, 5) * env_ad(int(dur * SR), 0.003, 0.6)
            end = min(n, q + len(seg))
            x[q:end] += seg[: end - q]
        t += step
        i += 1
    return x * vol


def bgm_night(total: float) -> np.ndarray:
    t = t_axis(total)
    wind = band(noise(total), 150, 900) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * t + 1.0) ** 2)
    pad = _pad([[45, 52, 60], [41, 48, 57]], 8.0, total, vol=0.25, harmonics=2)
    return norm(wind * 0.6 + norm(pad) * 0.4, 0.5)


def bgm_battle(total: float) -> np.ndarray:
    bpm = 150
    kick = _kick_track(total, bpm, [0, 1.5, 2, 3, 3.5])
    hats = _hats(total, bpm)
    bass = _ostinato(total, bpm, [33, 33, 45, 33, 36, 33, 43, 33, 29, 29, 41, 29, 31, 31, 43, 31])
    pad = _pad([[57, 60, 64], [53, 57, 60], [55, 59, 62], [52, 55, 59]], 60 / bpm * 4, total, vol=1.0)
    x = norm(kick) * 0.55 + norm(hats) * 0.12 + norm(bass) * 0.45 + norm(pad) * 0.3
    return norm(np.tanh(x * 1.3), 0.55)


def bgm_dread(total: float) -> np.ndarray:
    t = t_axis(total)
    drone = tone(mtof(33), total, 5) + tone(mtof(34), total, 5) * 0.7
    drone *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.2 * t)
    beat = _kick_track(total, 58, [0, 0.35])
    return norm(band(drone, 20, 800) * 0.6 + norm(beat) * 0.5, 0.5)


def bgm_truth(total: float) -> np.ndarray:
    t = t_axis(total)
    x = tone(mtof(33), total, 4) + 0.5 * tone(mtof(39), total, 3)
    x *= 0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t - np.pi / 2) ** 2
    air = band(noise(total), 200, 1200) * 0.15
    return norm(band(x, 20, 600) + air, 0.4)


def bgm_sorrow(total: float) -> np.ndarray:
    pad = _pad([[45, 52, 57, 60], [41, 48, 53, 57], [48, 55, 60, 64], [43, 50, 55, 59]], 5.0, total, vol=1.0, harmonics=2)
    pl = _plucks(total, 66, [69, 0, 72, 0, 76, 0, 74, 72, 0, 0, 0, 0, 69, 0, 67, 0, 65, 0, 64, 0, 0, 0, 0, 0], 0.5)
    return norm(norm(pad) * 0.7 + norm(pl) * 0.35, 0.45)


def bgm_climax(total: float) -> np.ndarray:
    bpm = 132
    t = t_axis(total)
    swell = np.clip(t / max(total * 0.8, 1), 0.25, 1.0)
    pad = _pad([[45, 57, 60, 64], [41, 53, 57, 60], [48, 55, 60, 64], [43, 55, 59, 62]], 60 / bpm * 4, total, vol=1.0, harmonics=4)
    bass = _ostinato(total, bpm, [33, 45, 33, 45, 29, 41, 29, 41, 36, 48, 36, 48, 31, 43, 31, 43])
    kick = _kick_track(total, bpm, [0, 1, 2, 3])
    choir = _pad([[69, 72, 76], [65, 69, 72], [67, 72, 76], [67, 71, 74]], 60 / bpm * 4, total, vol=1.0, harmonics=1)
    x = norm(pad) * 0.45 + norm(bass) * 0.35 + norm(kick) * 0.45 + norm(choir) * 0.25
    return norm(np.tanh(x * swell * 1.4), 0.6)


def bgm_dawn(total: float) -> np.ndarray:
    seq = [60, 67, 72, 76, 67, 72, 55, 62, 67, 71, 62, 67, 57, 64, 69, 72, 64, 69, 53, 60, 65, 69, 60, 65]
    pl = _plucks(total, 76, seq, 1.0)
    pad = _pad([[48, 55, 64], [43, 50, 59], [45, 52, 60], [41, 48, 57]], 60 / 76 * 3, total, vol=1.0, harmonics=2)
    return norm(reverb(norm(pl) * 0.6 + norm(pad) * 0.35, 2.5, 0.35)[: int(total * SR)], 0.45)


BGM_BANK = {
    "night": bgm_night,
    "battle": bgm_battle,
    "dread": bgm_dread,
    "truth": bgm_truth,
    "sorrow": bgm_sorrow,
    "climax": bgm_climax,
    "dawn": bgm_dawn,
}

BGM_GAIN = {"night": 0.5, "battle": 0.55, "dread": 0.6, "truth": 0.6, "sorrow": 0.55, "climax": 0.6, "dawn": 0.55}


# ---------------------------------------------------------------- 声

def load_voice(path: Path) -> np.ndarray:
    """WAV を読み込み SR に揃えた mono float にする."""
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    if ch > 1:
        raw = raw.reshape(-1, ch).mean(axis=1)
    return resample(raw, sr, SR)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or len(x) == 0:
        return x
    n_out = int(len(x) * sr_out / sr_in)
    return np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x)


def trim_silence(x: np.ndarray, thresh: float = 0.01, pad: float = 0.05) -> np.ndarray:
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    p = int(pad * SR)
    return x[max(0, idx[0] - p) : min(len(x), idx[-1] + p)]


def monster_voice(x: np.ndarray) -> np.ndarray:
    """災禍: ピッチを落とした層と元の声を重ね、深いリバーブをかける."""
    low = resample(x, SR, int(SR / 0.78))
    ghost = np.zeros_like(low)
    ghost[: len(x)] = x * 0.35
    y = np.tanh(norm(band(low, 60, 5000)) * 1.8) * 0.8 + ghost
    return reverb(norm(y, 0.9), 2.8, 0.5, bright=4000)


def spirit_voice(x: np.ndarray) -> np.ndarray:
    return reverb(x, 2.2, 0.35, bright=9000)


def inner_voice(x: np.ndarray) -> np.ndarray:
    return reverb(x, 1.2, 0.22, bright=7000)


# ---------------------------------------------------------------- ミックス

def place(buf: np.ndarray, x: np.ndarray, at: float, gain: float = 1.0) -> None:
    p = int(at * SR)
    if p >= len(buf):
        return
    end = min(len(buf), p + len(x))
    buf[p:end] += x[: end - p] * gain


def duck_curve(voice_bus: np.ndarray, depth: float = 0.45) -> np.ndarray:
    """声がある所で BGM を下げるゲインカーブ."""
    hop = SR // 50
    frames = np.abs(voice_bus[: len(voice_bus) // hop * hop]).reshape(-1, hop).max(axis=1)
    active = (frames > 0.02).astype(float)
    k = np.ones(25) / 25
    smooth = np.clip(np.convolve(active, k, mode="same") * 2, 0, 1)
    g = 1 - depth * smooth
    g = np.repeat(g, hop)
    return np.pad(g, (0, len(voice_bus) - len(g)), constant_values=1.0)


def write_wav(path: Path, stereo: np.ndarray) -> None:
    data = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(data.tobytes())
