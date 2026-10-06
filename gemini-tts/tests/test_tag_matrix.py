"""tag_matrix のマトリクス生成・タグ合成・F0・出力のテスト."""

from __future__ import annotations

import csv

import numpy as np
import pytest

from eleven_tts.tag_matrix import (
    LINES, VARIANTS, VOICES, Clip, build_matrix, clip_row, estimated_chars,
    filter_matrix, median_f0, render_index, write_manifest,
)


def clip(voice=0, line=0, variant=0) -> Clip:
    return Clip(VOICES[voice], LINES[line], VARIANTS[variant])


def test_全組み合わせが揃う():
    m = build_matrix()
    assert len(m) == len(VOICES) * len(LINES) * len(VARIANTS)
    assert len({c.relpath for c in m}) == len(m)


@pytest.mark.parametrize("variant_key, expected", [
    ("a_plain", ""),
    ("b_emo", "[excited]"),
    ("c_child", "[childlike]"),
    ("d_child_emo", "[childlike][excited]"),
    ("e_max", "[childlike][high-pitched][excited]"),
])
def test_タグの組み立て(variant_key, expected):
    var = next(v for v in VARIANTS if v.key == variant_key)
    c = Clip(VOICES[0], LINES[0], var)
    assert c.tags == expected
    assert c.text == f"{expected} {LINES[0].text}".strip()


def test_タグなしは本文だけ():
    assert clip(variant=0).text == LINES[0].text


def test_ファイル名():
    assert clip().relpath == f"{VOICES[0].key}/{LINES[0].key}_{VARIANTS[0].key}.mp3"


@pytest.mark.parametrize("kw, n", [
    ({}, len(VOICES) * len(LINES) * len(VARIANTS)),
    ({"voices": ["hina"]}, len(LINES) * len(VARIANTS)),
    ({"voices": ["Hina"], "lines": ["04"]}, len(VARIANTS)),
    ({"voices": ["Hina"], "lines": ["04"], "variants": ["e"]}, 1),
    ({"voices": ["nobody"]}, 0),
])
def test_絞り込み(kw, n):
    assert len(filter_matrix(build_matrix(), **kw)) == n


def test_文字数見積もり():
    cs = [clip(variant=0), clip(variant=4)]
    assert estimated_chars(cs) == len(cs[0].text) + len(cs[1].text)
    assert estimated_chars([]) == 0


@pytest.mark.parametrize("hz", [200.0, 330.0, 450.0])
def test_F0推定(hz):
    sr = 22050
    t = np.arange(sr) / sr
    x = 0.5 * np.sin(2 * np.pi * hz * t)
    assert median_f0(x, sr) == pytest.approx(hz, rel=0.03)


@pytest.mark.parametrize("x", [np.zeros(22050), np.zeros(10)])
def test_F0無音や短すぎは0(x):
    assert median_f0(x, 22050) == 0.0


def test_manifest書き出し(tmp_path):
    rows = [clip_row(clip(variant=3), duration=3.456, f0=351.7)]
    p = tmp_path / "m.csv"
    write_manifest(p, rows)
    with p.open(encoding="utf-8-sig") as f:
        got = list(csv.DictReader(f))
    assert got[0]["tags"] == "[childlike][excited]"
    assert got[0]["duration_s"] == "3.46"
    assert got[0]["f0_hz"] == "352"


def test_試聴ページ():
    cs = filter_matrix(build_matrix(), voices=["Hina", "Kuon"], lines=["01"])
    page = render_index(cs, {cs[0].relpath: 400.0})
    assert page.count("<audio") == len(cs)
    assert "F0 400Hz" in page
    assert "（なし）" in page
    assert "[childlike][high-pitched][excited]" in page


def test_試聴ページ欠けたセルはハイフン():
    cs = [clip(voice=0, variant=0), clip(voice=1, variant=1)]
    page = render_index(cs)
    assert page.count("<td>-</td>") == 2
