"""script_parse / project のテスト."""

from __future__ import annotations

from pathlib import Path

from gemini_tts.project import create_project_from_script, enrich_items
from gemini_tts.script_parse import parse_script_text, summarize


SAMPLE = """
## タイトル

### 登場人物

| 人物 | 概要 |
| 佐藤 | 主人公 |

---

語り手 「これは序章です」

---

シーン１：オフィス

＜夜のオフィス＞

（カチッ、という電子音）

（画面に「3日後」のテロップ）

田中（後輩） 「お疲れ様です」

佐藤 「（驚愕）嘘だろ……」

田中（1.5倍速） 「エ？ナニ言ッテルンデスカ」

【全編再生終了】

エピローグ：

語り手 「おしまい」
"""


def test_parse_kinds_and_speakers():
    items = parse_script_text(SAMPLE)
    summary = summarize(items)
    assert summary["by_kind"]["narration"] >= 2
    assert summary["by_kind"]["dialogue"] >= 3
    assert summary["by_kind"]["caption"] >= 2
    assert summary["by_kind"]["sfx"] >= 1
    assert "佐藤" in summary["speakers"]
    assert "田中" in summary["speakers"]


def test_parse_speed_and_acting():
    items = parse_script_text(SAMPLE)
    sato = next(i for i in items if i.speaker == "佐藤")
    assert "驚愕" in sato.style_hints
    assert sato.spoken_text.startswith("嘘だろ")
    fast = next(i for i in items if i.speaker == "田中" and i.speed == 1.5)
    assert fast.speed == 1.5


def test_location_caption():
    items = parse_script_text(SAMPLE)
    loc = next(i for i in items if i.notes == ["location"])
    assert loc.kind == "caption"
    assert loc.spoken_text == "夜のオフィス"


def test_popup_caption():
    items = parse_script_text(SAMPLE)
    pop = next(i for i in items if "全編再生終了" in (i.spoken_text or ""))
    assert pop.kind == "caption"
    assert pop.tts is True


def test_sfx_not_tts():
    items = parse_script_text(SAMPLE)
    sfx = next(i for i in items if i.kind == "sfx")
    assert sfx.tts is False


def test_create_project(tmp_path: Path):
    script = tmp_path / "sample.md"
    script.write_text(SAMPLE, encoding="utf-8")
    project = tmp_path / "proj"
    manifest = create_project_from_script(script, project, title="テスト")
    assert (project / "manifest.json").is_file()
    assert (project / "voice_map.yaml").is_file()
    assert (project / "LINES.md").is_file()
    assert manifest["summary"]["tts_targets"] >= 5
    enriched = enrich_items(parse_script_text(SAMPLE))
    assert all(
        (e["voice"] is not None) == e["tts"] for e in enriched
    )
