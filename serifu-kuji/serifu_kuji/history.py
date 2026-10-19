"""抽選履歴とお気に入り。"""

from __future__ import annotations

import json
from pathlib import Path


class FavoritesError(Exception):
    """お気に入りファイルが壊れている。"""


class DrawHistory:
    """メモリ上の抽選履歴。新しい順に保持する。"""

    def __init__(self, limit: int = 30) -> None:
        """履歴を空で用意する。

        limit は 1 以上。それ未満は ValueError。
        メモリ上のみ。新しい順に保持する。同じ id が連続しても記録する。
        """
        if limit < 1:
            raise ValueError("limit は 1 以上である必要があります")
        self._limit = limit
        self._ids: list[str] = []

    def record(self, line_id: str) -> None:
        """抽選した id を先頭に記録する。

        空文字は ValueError。上限を超えたら古いものから捨てる。
        """
        if line_id == "":
            raise ValueError("line_id は空にできません")
        self._ids.insert(0, line_id)
        del self._ids[self._limit :]

    def recent(self) -> list[str]:
        """新しい順の id 一覧を返す。"""
        return list(self._ids)

    def avoid_ids(self, n: int = 5) -> set[str]:
        """直近 n 件の id を返す。

        n < 1 は ValueError。履歴が少なければあるだけ返す。
        """
        if n < 1:
            raise ValueError("n は 1 以上である必要があります")
        return set(self._ids[:n])


class Favorites:
    """JSON ファイルに保存するお気に入り id。"""

    def __init__(self, path: Path) -> None:
        """お気に入りを読み込む。

        JSONファイルがあれば読む。無ければ空。壊れたJSONは FavoritesError。
        形式は {"ids": ["n001", ...]} 。重複は除く。文字列以外は FavoritesError。
        """
        self._path = path
        self._ids: list[str] = []
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise FavoritesError("お気に入りファイルのJSONが壊れています") from exc
        self._ids = _parse_ids(data)

    def ids(self) -> list[str]:
        """追加順の id 一覧を返す。"""
        return list(self._ids)

    def contains(self, line_id: str) -> bool:
        """指定 id がお気に入りに含まれるかを返す。"""
        return line_id in self._ids

    def toggle(self, line_id: str) -> bool:
        """お気に入りを切り替えてすぐ保存する。

        お気に入りなら外して False、なければ追加して True。
        空文字は ValueError。
        """
        if line_id == "":
            raise ValueError("line_id は空にできません")
        if line_id in self._ids:
            self._ids.remove(line_id)
            added = False
        else:
            self._ids.append(line_id)
            added = True
        self.save()
        return added

    def save(self) -> None:
        """お気に入りを UTF-8 の JSON として保存する。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"ids": self._ids}, ensure_ascii=False, indent=2)
        self._path.write_text(f"{text}\n", encoding="utf-8")


def _parse_ids(data: object) -> list[str]:
    """お気に入り JSON から重複を除いた id 列を取り出す。"""
    if not isinstance(data, dict):
        raise FavoritesError("お気に入りファイルの形式が不正です")
    ids = data.get("ids", _MISSING)
    if ids is _MISSING or not isinstance(ids, list):
        raise FavoritesError("ids は文字列のリストである必要があります")
    unique: list[str] = []
    seen: set[str] = set()
    for item in ids:
        if not isinstance(item, str):
            raise FavoritesError("ids の要素は文字列である必要があります")
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


_MISSING = object()
