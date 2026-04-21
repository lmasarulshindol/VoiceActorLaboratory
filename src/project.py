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
    script_line_number: int | None = None  # 台本の何行目に対応するか（1-based、紐付け用）
    script_line_text: str = ""  # 録音時点のセリフテキスト（表示・ファイル名用）
    rating: int = 0  # 0=未評価、1〜5 の星評価
    tags: list[str] = field(default_factory=list)  # 自由ラベル（色タグ等も文字列で格納）
    has_clipping: bool = False  # 録音がクリップしていたか（D2）
    peak_dbfs: float | None = None  # 解析時の最大ピーク dBFS（-inf は None）
    integrated_lufs: float | None = None  # BS.1770 統合ラウドネス（-inf/短すぎは None）

    def display_name(self, index: int | None = None) -> str:
        """一覧表示用。index を渡すと 'Take 1  02/19 14:32  「セリフ」' 形式、否則 wav_filename。"""
        if index is not None and self.created_at:
            try:
                dt = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
                short = dt.strftime("%m/%d %H:%M")
            except (ValueError, TypeError):
                short = self.created_at[:16] if len(self.created_at) >= 16 else self.created_at
            if self.script_line_text:
                preview = self.script_line_text[:20]
                if len(self.script_line_text) > 20:
                    preview += "…"
                line_part = f"  「{preview}」"
            else:
                line_part = ""
            return f"Take {index + 1}  {short}{line_part}"
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

    def update_take_rating(self, take_id: str, rating: int) -> bool:
        """テイクの星評価を 0〜5 で更新する。"""
        t = self.get_take(take_id)
        if t is None:
            return False
        t.rating = max(0, min(5, int(rating)))
        return True

    def update_take_tags(self, take_id: str, tags: list[str]) -> bool:
        """テイクのタグを更新する。重複除去と空白トリムを行う。"""
        t = self.get_take(take_id)
        if t is None:
            return False
        cleaned: list[str] = []
        for tag in tags or []:
            s = str(tag).strip()
            if s and s not in cleaned:
                cleaned.append(s)
        t.tags = cleaned
        return True

    def all_tags(self) -> list[str]:
        """プロジェクト内で使われているタグの一覧（出現順、重複なし）。"""
        seen: list[str] = []
        for t in self.takes:
            for tag in t.tags:
                if tag not in seen:
                    seen.append(tag)
        return seen

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
