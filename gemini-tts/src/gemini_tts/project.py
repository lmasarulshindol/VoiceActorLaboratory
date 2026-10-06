"""台本プロジェクト（マニフェスト・ボイス割当）."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .script_parse import ScriptLine, parse_script_text, summarize
from .voices import get_voice


DEFAULT_VOICE_MAP: dict[str, str] = {
    "語り手": "Alnilam",
    "佐藤": "Orus",
    "田中": "Puck",
    "恵美": "Aoede",
    "部長": "Charon",
    "看護師": "Despina",
    "サキ": "Leda",
    "謎の女性": "Leda",
    "女性": "Leda",
    "車内アナウンス": "Schedar",
    "同僚たち": "Fenrir",
    "_caption": "Schedar",
    "_default": "Kore",
}

SPEAKER_ALIASES: dict[str, str] = {
    "謎の女性": "サキ",
    "女性": "サキ",
}


def resolve_speaker(speaker: str | None) -> str | None:
    if speaker is None:
        return None
    return SPEAKER_ALIASES.get(speaker, speaker)


def build_style(item: ScriptLine) -> str | None:
    parts: list[str] = []
    if item.style_hints:
        parts.extend(item.style_hints)
    if item.notes:
        # 演技寄りのメモだけ style へ
        for n in item.notes:
            if n.startswith("alias:"):
                continue
            if "倍速" in n:
                continue
            parts.append(n)
    if item.speed is not None and item.speed != 1.0:
        if item.speed >= 8:
            parts.append(f"極端な早口（約{item.speed}倍速のイメージ）、甲高く早回し")
        elif item.speed >= 2:
            parts.append(f"早口（約{item.speed}倍速のイメージ）")
    if item.kind == "caption":
        parts.append("簡潔なキャプション読み上げ、淡々と")
    if item.kind == "narration":
        parts.append("落ち着いたナレーション、達観したトーン")
    if not parts:
        return None
    # 重複除去（順序維持）
    seen: set[str] = set()
    uniq: list[str] = []
    for p in parts:
        p = p.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return "、".join(uniq)


def assign_voice(item: ScriptLine, voice_map: dict[str, str]) -> str:
    if item.kind == "caption":
        return voice_map.get("_caption", voice_map.get("_default", "Kore"))
    speaker = resolve_speaker(item.speaker) or ""
    if speaker in voice_map:
        return voice_map[speaker]
    if item.speaker and item.speaker in voice_map:
        return voice_map[item.speaker]
    return voice_map.get("_default", "Kore")


def enrich_items(
    items: list[ScriptLine],
    voice_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """ScriptLine に voice / style / output パス案を付与して dict 化."""
    vmap = {**DEFAULT_VOICE_MAP, **(voice_map or {})}
    # バリデーション
    for name, voice in vmap.items():
        if name.startswith("_"):
            get_voice(voice)
        else:
            get_voice(voice)

    out: list[dict[str, Any]] = []
    for item in items:
        d = item.to_dict()
        d["resolved_speaker"] = resolve_speaker(item.speaker)
        d["voice"] = assign_voice(item, vmap) if item.tts else None
        d["style"] = build_style(item) if item.tts else None
        scene_slug = _slug(item.scene)
        d["output"] = f"audio/{scene_slug}/{item.id}_{_file_stem(item)}.wav"
        out.append(d)
    return out


def _slug(text: str) -> str:
    s = text.strip().replace(" ", "_").replace("/", "-")
    for ch in '<>:"\\|?*':
        s = s.replace(ch, "")
    return s or "scene"


def _file_stem(item: ScriptLine) -> str:
    if item.kind == "caption":
        return "caption"
    if item.kind in {"sfx", "direction"}:
        return item.kind
    speaker = resolve_speaker(item.speaker) or item.kind
    return _slug(speaker)


def build_manifest(
    *,
    title: str,
    source: str | Path,
    items: list[ScriptLine],
    voice_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    enriched = enrich_items(items, voice_map)
    return {
        "title": title,
        "source": str(source),
        "summary": summarize(items),
        "voice_map": {**DEFAULT_VOICE_MAP, **(voice_map or {})},
        "items": enriched,
    }


def save_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_voice_map_yaml(path: Path, voice_map: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 役名 → Gemini プリビルトボイス", "voices:"]
    for k, v in voice_map.items():
        lines.append(f"  {k}: {v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_voice_map_yaml(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML が必要です") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, dict) and "voices" in data:
        data = data["voices"]
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def create_project_from_script(
    script_path: Path,
    project_dir: Path,
    *,
    title: str | None = None,
    voice_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """台本からプロジェクト一式を生成する（音声生成はしない）."""
    text = script_path.read_text(encoding="utf-8")
    items = parse_script_text(text)
    vmap = {**DEFAULT_VOICE_MAP, **(voice_map or {})}
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "audio").mkdir(exist_ok=True)

    # ソース参照を残す
    rel_note = project_dir / "SOURCE.txt"
    rel_note.write_text(str(script_path.resolve()) + "\n", encoding="utf-8")

    save_voice_map_yaml(project_dir / "voice_map.yaml", vmap)
    manifest = build_manifest(
        title=title or script_path.stem,
        source=script_path,
        items=items,
        voice_map=vmap,
    )
    save_manifest(project_dir / "manifest.json", manifest)

    # 人間が眺める用の一覧
    lines = [
        f"# {manifest['title']}",
        "",
        f"- 総要素: {manifest['summary']['total']}",
        f"- TTS対象: {manifest['summary']['tts_targets']}",
        f"- 種別: {manifest['summary']['by_kind']}",
        f"- 話者: {manifest['summary']['speakers']}",
        "",
        "| id | scene | kind | speaker | voice | tts | spoken |",
        "|----|-------|------|---------|-------|-----|--------|",
    ]
    for it in manifest["items"]:
        spoken = (it.get("spoken_text") or "").replace("|", "\\|").replace("\n", " ")
        if len(spoken) > 40:
            spoken = spoken[:40] + "…"
        lines.append(
            f"| {it['id']} | {it['scene']} | {it['kind']} | {it.get('resolved_speaker') or it.get('speaker') or ''} "
            f"| {it.get('voice') or ''} | {'Y' if it.get('tts') else 'N'} | {spoken} |"
        )
    (project_dir / "LINES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    readme = f"""# {manifest['title']}

台本からの音声化プロジェクト（APIキー投入前の準備済み）。

## ファイル

- `manifest.json` … 全行の構造化データ（TTS対象フラグ付き）
- `voice_map.yaml` … 役→ボイス割当
- `LINES.md` … 一覧（確認用）
- `SOURCE.txt` … 元台本パス
- `audio/` … 生成WAVの出力先（git管理外）

## 種別

| kind | 意味 | 既定TTS |
|------|------|---------|
| dialogue | セリフ | する |
| narration | 語り手 | する |
| caption | 場所・テロップ・ポップアップ | する |
| sfx | 効果音ト書き | しない |
| direction | ト書き・演出 | しない |

## キー投入後

```powershell
$env:PYTHONPATH = "src"
py -3 -m gemini_tts synthesize-project projects/{project_dir.name}
```
"""
    (project_dir / "README.md").write_text(readme, encoding="utf-8")
    return manifest
