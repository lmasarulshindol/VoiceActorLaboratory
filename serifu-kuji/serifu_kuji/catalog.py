"""台本YAMLの読み込みと抽選。"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml


class CatalogError(Exception):
    """台本の読み込み・抽選に失敗したとき。"""


@dataclass(frozen=True)
class Line:
    """台本の1行。

    kind は ``dialogue``（台詞）または ``narration``（地の文）。
    """

    id: str
    kind: str
    text: str
    speaker: str = ""
    tags: tuple[str, ...] = ()
    mood: str = ""
    seconds: int | None = None
    gender: str = "any"
    category: str = ""
    tone: str = ""
    situation: str = ""


_KINDS = frozenset({"dialogue", "narration"})
_SECONDS = frozenset({10, 20, 30})
_GENDERS = frozenset({"male", "female", "any"})


def load_catalog(path: Path) -> list[Line]:
    """YAMLを読み、Lineのリストを返す。失敗時は CatalogError。

    path がフォルダなら、その直下の *.yaml / *.yml を名前順にすべて読み込んで結合する。
    id はファイルをまたいで重複できない。
    """
    if path.is_dir():
        files = sorted(
            [p for p in path.iterdir() if p.suffix in (".yaml", ".yml") and p.is_file()],
            key=lambda p: p.name,
        )
        if not files:
            raise CatalogError(f"台本フォルダにYAMLがありません: {path}")
        lines: list[Line] = []
        seen: set[str] = set()
        for file in files:
            lines.extend(_load_file(file, seen))
        return lines
    return _load_file(path, set())


def _load_file(path: Path, seen: set[str]) -> list[Line]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CatalogError(f"台本ファイルを読めません: {path}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise CatalogError(f"YAMLとして解釈できません: {path}") from exc

    if not isinstance(data, dict):
        raise CatalogError(f"トップレベルは辞書である必要があります: {path.name}")
    rows = data.get("lines")
    if "lines" not in data or not isinstance(rows, list):
        raise CatalogError(f"lines はリストである必要があります: {path.name}")

    lines: list[Line] = []
    for index, item in enumerate(rows, start=1):
        lines.append(_parse_line(item, index, seen))
    return lines


def _parse_line(item: object, index: int, seen: set[str]) -> Line:
    """1行分の辞書を Line にする。"""
    if not isinstance(item, dict):
        raise CatalogError(f"{index}件目の行が辞書ではありません")

    line_id = item.get("id")
    if not isinstance(line_id, str) or line_id == "":
        raise CatalogError(f"{index}件目の id は空でない文字列である必要があります")
    if line_id in seen:
        raise CatalogError(f"id が重複しています: {line_id}")
    seen.add(line_id)

    kind = item.get("kind")
    if not isinstance(kind, str) or kind not in _KINDS:
        raise CatalogError(
            f"{index}件目の kind は dialogue または narration である必要があります"
        )

    text = item.get("text")
    if not isinstance(text, str) or text == "":
        raise CatalogError(f"{index}件目の text は空でない文字列である必要があります")

    return Line(
        id=line_id,
        kind=kind,
        text=text,
        speaker=_optional_str(item, "speaker", index),
        tags=_parse_tags(item, index),
        mood=_optional_str(item, "mood", index),
        seconds=_parse_seconds(item, index),
        gender=_parse_gender(item, index),
        category=_optional_str(item, "category", index),
        tone=_optional_str(item, "tone", index),
        situation=_optional_str(item, "situation", index),
    )


def _optional_str(item: dict[str, object], key: str, index: int) -> str:
    """省略された文字列フィールドは空文字にする。"""
    if key not in item:
        return ""
    value = item[key]
    if not isinstance(value, str):
        raise CatalogError(f"{index}件目の {key} は文字列である必要があります")
    return value


def _parse_tags(item: dict[str, object], index: int) -> tuple[str, ...]:
    """省略された tags は空タプルにする。"""
    if "tags" not in item:
        return ()
    raw = item["tags"]
    if not isinstance(raw, list):
        raise CatalogError(f"{index}件目の tags は文字列のリストである必要があります")
    tags: list[str] = []
    for tag in raw:
        if not isinstance(tag, str):
            raise CatalogError(f"{index}件目のタグは文字列である必要があります")
        tags.append(tag)
    return tuple(tags)


def _parse_seconds(item: dict[str, object], index: int) -> int | None:
    """省略された想定時間は未設定。ある場合は 10、20、30 秒だけ。"""
    if "seconds" not in item or item["seconds"] is None or item["seconds"] == "":
        return None
    try:
        return normalize_seconds(item["seconds"])
    except CatalogError as exc:
        raise CatalogError(f"{index}件目の{exc}") from exc


def _parse_gender(item: dict[str, object], index: int) -> str:
    """省略された性別は不問。"""
    if "gender" not in item or item["gender"] is None or item["gender"] == "":
        return "any"
    gender = item["gender"]
    if not isinstance(gender, str) or gender not in _GENDERS:
        raise CatalogError(f"{index}件目の gender は male、female、any のいずれかである必要があります")
    return gender


def normalize_seconds(value: object) -> int | None:
    """絞り込み用の想定時間を 10、20、30 にそろえる。空は条件なし。"""
    if value is None or value == "":
        return None
    if isinstance(value, str) and value in {"10", "20", "30"}:
        return int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value in _SECONDS:
        return value
    raise CatalogError("想定時間は 10、20、30 秒のいずれかである必要があります")


def _unique(values: list[str], *, skip_empty: bool) -> list[str]:
    """登場順を保って重複を除く。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if skip_empty and value == "":
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


class Catalog:
    """読み込み済みの台本から絞り込みと抽選を行う。"""

    def __init__(self, lines: list[Line]) -> None:
        self._lines = tuple(lines)

    @property
    def lines(self) -> tuple[Line, ...]:
        """保持している行。"""
        return self._lines

    def speakers(self) -> list[str]:
        """空でない speaker を一意・登場順。"""
        return _unique([line.speaker for line in self._lines], skip_empty=True)

    def tags(self) -> list[str]:
        """全タグを一意・登場順。"""
        collected: list[str] = []
        for line in self._lines:
            collected.extend(line.tags)
        return _unique(collected, skip_empty=False)

    def moods(self) -> list[str]:
        """空でない mood を一意・登場順。"""
        return _unique([line.mood for line in self._lines], skip_empty=True)

    def tones(self) -> list[str]:
        """空でない読み方（tone）を一意・登場順。"""
        return _unique([line.tone for line in self._lines], skip_empty=True)

    def categories(self, kind: str | None = None) -> list[str]:
        """サブカテゴリを一意で返す。kind を渡すとその種類だけ。

        並びは id 順の初出順。台本が複数ファイルに分かれていても、
        id の若いジャンルから順に並ぶ。
        """
        _validate_kind(kind)
        collected = [
            line.category
            for line in sorted(self._lines, key=lambda line: line.id)
            if not kind or line.kind == kind
        ]
        return _unique(collected, skip_empty=True)

    def filter(
        self,
        *,
        kind: str | None = None,
        speaker: str | None = None,
        tag: str | None = None,
        mood: str | None = None,
        seconds: int | str | None = None,
        gender: str | None = None,
        category: str | None = None,
        tone: str | None = None,
    ) -> list[Line]:
        """None や空文字は「絞り込まない」。

        kind は dialogue / narration のみ許容。不正な kind は CatalogError。
        gender の any は台本側の「不問」だけに一致する。
        """
        _validate_kind(kind)
        seconds_value = normalize_seconds(seconds)
        gender_value = _normalize_gender(gender)
        selected: list[Line] = []
        for line in self._lines:
            if kind and line.kind != kind:
                continue
            if speaker and line.speaker != speaker:
                continue
            if tag and tag not in line.tags:
                continue
            if mood and line.mood != mood:
                continue
            if seconds_value is not None and line.seconds != seconds_value:
                continue
            if gender_value and line.gender != gender_value:
                continue
            if category and line.category != category:
                continue
            if tone and line.tone != tone:
                continue
            selected.append(line)
        return selected

    def draw(
        self,
        *,
        kind: str | None = None,
        speaker: str | None = None,
        tag: str | None = None,
        mood: str | None = None,
        seconds: int | str | None = None,
        gender: str | None = None,
        category: str | None = None,
        tone: str | None = None,
        avoid_ids: set[str] | None = None,
        rng: random.Random | None = None,
    ) -> Line:
        """filter 後に1件抽選する。

        avoid_ids に入っている id は、他に候補があるときだけ除外する。
        候補が全部 avoid なら繰り返しを許可する。
        該当 0 件なら CatalogError。rng 未指定なら random.Random() を使う。
        """
        candidates = self.filter(
            kind=kind,
            speaker=speaker,
            tag=tag,
            mood=mood,
            seconds=seconds,
            gender=gender,
            category=category,
            tone=tone,
        )
        if not candidates:
            raise CatalogError("該当するセリフがありません")

        pool = candidates
        if avoid_ids:
            remaining = [line for line in candidates if line.id not in avoid_ids]
            if remaining:
                pool = remaining

        chooser = rng if rng is not None else random.Random()
        return chooser.choice(pool)


def _validate_kind(kind: str | None) -> None:
    """絞り込み用の kind を検証する。空は条件なし。"""
    if kind is None or kind == "":
        return
    if kind not in _KINDS:
        raise CatalogError("kind は dialogue または narration である必要があります")


def _normalize_gender(gender: str | None) -> str | None:
    """絞り込み用の性別を検証する。空は条件なし。"""
    if gender is None or gender == "":
        return None
    if gender not in _GENDERS:
        raise CatalogError("gender は male、female、any のいずれかである必要があります")
    return gender
