"""
プロジェクト・台本の読み込みとメタデータの保持。
"""
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


@dataclass
class TakeInfo:
    """1テイク分のメタデータ。"""

    id: str
    wav_filename: str
    memo: str = ""
    favorite: bool = False
    created_at: str = ""
    adopted: bool = False

    def display_name(self, index: int | None = None) -> str:
        """一覧表示用。index を渡すと 'Take 1  02/19 14:32' 形式、否则 wav_filename。"""
        if index is not None and self.created_at:
            try:
                dt = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
                short = dt.strftime("%m/%d %H:%M")
            except (ValueError, TypeError):
                short = self.created_at[:16] if len(self.created_at) >= 16 else self.created_at
            return f"Take {index + 1}  {short}"
        return self.wav_filename


@dataclass
class Project:
    """1プロジェクト。台本テキスト・パス・テイク一覧を保持する。"""

    script_path: str = ""
    script_text: str = ""
    takes: list[TakeInfo] = field(default_factory=list)
    project_dir: str = ""

    def set_script(self, path: str, text: str) -> None:
        """台本のパスと内容を設定する。"""
        self.script_path = path
        self.script_text = text

    def add_take(self, take: TakeInfo) -> None:
        """テイクを追加する。"""
        self.takes.append(take)

    def get_take(self, take_id: str) -> TakeInfo | None:
        """ID でテイクを取得する。"""
        for t in self.takes:
            if t.id == take_id:
                return t
        return None

    def update_take_memo(self, take_id: str, memo: str) -> bool:
        """テイクのメモを更新する。"""
        t = self.get_take(take_id)
        if t is None:
            return False
        t.memo = memo
        return True

    def update_take_favorite(self, take_id: str, favorite: bool) -> bool:
        """テイクのお気に入りを更新する。"""
        t = self.get_take(take_id)
        if t is None:
            return False
        t.favorite = favorite
        return True

    def update_take_adopted(self, take_id: str, adopted: bool) -> bool:
        """テイクの採用を更新する。adopted=True のとき他はすべて False（1本だけ採用）。"""
        t = self.get_take(take_id)
        if t is None:
            return False
        if adopted:
            for x in self.takes:
                x.adopted = x.id == take_id
        else:
            t.adopted = False
        return True

    def get_adopted_take(self) -> TakeInfo | None:
        """採用されているテイクを返す。"""
        for t in self.takes:
            if t.adopted:
                return t
        return None

    def has_script(self) -> bool:
        """台本が読み込まれているか。"""
        return bool(self.script_text.strip())

    def has_project_dir(self) -> bool:
        """プロジェクトフォルダが設定されているか。"""
        return bool(self.project_dir and Path(self.project_dir).is_dir())
