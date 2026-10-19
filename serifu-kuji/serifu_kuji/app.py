"""セリフくじのウィンドウ。"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from serifu_kuji.catalog import Catalog, CatalogError, Line, load_catalog
from serifu_kuji.history import DrawHistory, Favorites, FavoritesError

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = APP_ROOT / "data" / "lines"
FAV_PATH = APP_ROOT / "data" / "favorites.json"

BG = "#FFF4EC"
CARD = "#FFFFFF"
ACCENT = "#E07A5F"
ACCENT_HOVER = "#C96A52"
ACCENT_TEXT = "#FFFFFF"
SUB = "#F3D6C8"
SUB_HOVER = "#E7C6B6"
INK = "#3D3A45"
MUTED = "#8A8175"
FONT = "Yu Gothic UI"

KIND_LABELS = ("指定なし", "セリフ", "ナレーション")
KIND_TO_VALUE = {"指定なし": "all", "セリフ": "dialogue", "ナレーション": "narration"}
BADGE_LABEL = {"dialogue": "セリフ", "narration": "ナレーション"}
UNSPECIFIED = "指定なし"
ANY_TAG = UNSPECIFIED
ANY_TONE = UNSPECIFIED
ANY_SECONDS = UNSPECIFIED
ANY_GENDER = UNSPECIFIED
ANY_CATEGORY = UNSPECIFIED
RECENT_SHOW = 8
SECONDS_VALUE = {"10秒": 10, "20秒": 20, "30秒": 30}
GENDER_LABEL = {"male": "男性", "female": "女性", "any": "不問"}
GENDER_VALUE = {label: value for value, label in GENDER_LABEL.items()}


def main() -> None:
    """ウィンドウを開く。"""
    ctk.set_appearance_mode("light")
    SerifuKujiApp().mainloop()


class SerifuKujiApp(ctk.CTk):
    """台本を引いて、コピーし、お気に入りに残す画面。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("セリフくじ")
        self.geometry("980x760")
        self.minsize(900, 680)
        self.configure(fg_color=BG)

        self.font_title = ctk.CTkFont(family=FONT, size=28, weight="bold")
        self.font_sub = ctk.CTkFont(family=FONT, size=15)
        self.font_body = ctk.CTkFont(family=FONT, size=22)
        self.font_ui = ctk.CTkFont(family=FONT, size=15)
        self.font_small = ctk.CTkFont(family=FONT, size=13)
        self.font_button = ctk.CTkFont(family=FONT, size=16, weight="bold")

        self.catalog: Catalog | None = None
        self.by_id: dict[str, Line] = {}
        self.current: Line | None = None
        self.history = DrawHistory(limit=30)
        self.favorites: Favorites | None = None
        self._suspend_filters = False

        self._build_header()
        self._build_filters()
        self._build_card()
        self._build_actions()
        self._build_recent()
        self._build_status()

        self._open_favorites()
        self._reload(draw_first=True)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 8))
        ctk.CTkLabel(
            header,
            text="今日のひとこと",
            font=self.font_title,
            text_color=INK,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="台本を直して、読みたい声を引く。",
            font=self.font_sub,
            text_color=MUTED,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        self.grid_columnconfigure(0, weight=1)

    def _build_filters(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=28, pady=(4, 12))

        self.kind_button = ctk.CTkSegmentedButton(
            row,
            values=list(KIND_LABELS),
            command=self._on_filter_changed,
            font=self.font_ui,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=SUB,
            unselected_hover_color=SUB_HOVER,
            text_color=INK,
        )
        self.kind_button.set(UNSPECIFIED)
        self.kind_button.grid(row=0, column=0, rowspan=2, padx=(0, 18), sticky="sw")

        self.seconds_menu = self._option_menu(
            row, 1, "想定時間", [ANY_SECONDS, *SECONDS_VALUE.keys()]
        )
        self.gender_menu = self._option_menu(
            row, 2, "性別", [ANY_GENDER, *GENDER_LABEL.values()]
        )
        self.category_menu = self._option_menu(row, 3, "サブカテゴリ", [ANY_CATEGORY])

        more = ctk.CTkFrame(self, fg_color="transparent")
        more.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 12))
        self.tag_menu = self._option_menu(more, 0, "タグ", [ANY_TAG])
        self.tone_menu = self._option_menu(more, 1, "読み方", [ANY_TONE])

    def _option_menu(
        self,
        parent: ctk.CTkFrame,
        column: int,
        caption: str,
        values: list[str],
    ) -> ctk.CTkOptionMenu:
        ctk.CTkLabel(
            parent,
            text=caption,
            font=self.font_small,
            text_color=MUTED,
            anchor="w",
        ).grid(row=0, column=column, sticky="sw", padx=(0, 12))
        menu = ctk.CTkOptionMenu(
            parent,
            values=values,
            command=self._on_filter_changed,
            font=self.font_ui,
            dropdown_font=self.font_ui,
            fg_color=CARD,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            text_color=INK,
            dropdown_fg_color=CARD,
            dropdown_text_color=INK,
            dropdown_hover_color=SUB,
            width=160,
        )
        menu.set(values[0])
        menu.grid(row=1, column=column, sticky="ew", padx=(0, 12), pady=(2, 0))
        return menu

    def _build_card(self) -> None:
        self.card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=20)
        self.card.grid(row=3, column=0, sticky="nsew", padx=28, pady=(0, 12))
        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.badge = ctk.CTkLabel(
            self.card,
            text="",
            font=self.font_small,
            text_color=ACCENT_TEXT,
            fg_color=ACCENT,
            corner_radius=10,
            width=96,
            height=28,
        )
        self.badge.grid(row=0, column=0, sticky="w", padx=28, pady=(22, 0))

        self.direction_label = ctk.CTkLabel(
            self.card,
            text="",
            font=self.font_small,
            text_color=ACCENT,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.direction_label.grid(row=1, column=0, sticky="ew", padx=28, pady=(10, 0))

        self.body_label = ctk.CTkLabel(
            self.card,
            text="",
            font=self.font_body,
            text_color=INK,
            anchor="nw",
            justify="left",
            wraplength=760,
        )
        self.body_label.grid(row=2, column=0, sticky="nsew", padx=28, pady=(12, 8))

        self.meta_label = ctk.CTkLabel(
            self.card,
            text="",
            font=self.font_small,
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.meta_label.grid(row=3, column=0, sticky="ew", padx=28, pady=(0, 22))
        self.card.bind("<Configure>", self._fit_wrap)

    def _build_actions(self) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=4, column=0, sticky="ew", padx=28, pady=(0, 8))

        self.draw_button = ctk.CTkButton(
            row,
            text="引く",
            command=self._draw,
            font=self.font_button,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            width=160,
            height=48,
            corner_radius=14,
        )
        self.draw_button.pack(side="left", padx=(0, 10))

        self.copy_button = self._sub_button(row, "コピー", self._copy)
        self.favorite_button = self._sub_button(row, "☆ お気に入り", self._toggle_favorite)
        self.reload_button = self._sub_button(row, "読み直す", self._reload_clicked)

    def _sub_button(self, parent: ctk.CTkFrame, text: str, command) -> ctk.CTkButton:
        button = ctk.CTkButton(
            parent,
            text=text,
            command=command,
            font=self.font_ui,
            fg_color=SUB,
            hover_color=SUB_HOVER,
            text_color=INK,
            width=140,
            height=48,
            corner_radius=14,
        )
        button.pack(side="left", padx=(0, 10))
        return button

    def _build_recent(self) -> None:
        box = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=5, column=0, sticky="ew", padx=28, pady=(4, 4))
        ctk.CTkLabel(
            box,
            text="さっき引いたもの",
            font=self.font_small,
            text_color=MUTED,
            anchor="w",
        ).pack(anchor="w")
        self.recent_row = ctk.CTkFrame(box, fg_color="transparent")
        self.recent_row.pack(anchor="w", fill="x", pady=(6, 0))
        self._refresh_recent()

    def _build_status(self) -> None:
        self.status = ctk.CTkLabel(
            self,
            text="",
            font=self.font_small,
            text_color=MUTED,
            anchor="w",
        )
        self.status.grid(row=6, column=0, sticky="ew", padx=28, pady=(4, 16))

    def _fit_wrap(self, event) -> None:
        width = max(240, event.width - 56)
        self.direction_label.configure(wraplength=width)
        self.body_label.configure(wraplength=width)
        self.meta_label.configure(wraplength=width)

    def _open_favorites(self) -> None:
        try:
            self.favorites = Favorites(FAV_PATH)
        except FavoritesError as exc:
            self.favorites = None
            self._set_status(str(exc))

    def _reload_clicked(self) -> None:
        self._reload(draw_first=False)

    def _reload(self, draw_first: bool = False) -> None:
        try:
            lines = load_catalog(DATA_PATH)
        except CatalogError as exc:
            self._fail_catalog(str(exc))
            return
        except OSError:
            self._fail_catalog("台本を読めませんでした。ファイルを確認して、もう一度読み直してください。")
            return

        self.catalog = Catalog(lines)
        self.by_id = {line.id: line for line in lines}
        self._rebuild_filters()
        self._refresh_recent()
        self._update_status()
        if self.current is not None:
            self._show_line(self.by_id.get(self.current.id, self.current))
        if draw_first:
            self._draw()

    def _fail_catalog(self, message: str) -> None:
        self.catalog = None
        self.by_id = {}
        self._show_error(message)
        self._refresh_recent()

    def _rebuild_filters(self) -> None:
        if self.catalog is None:
            return
        self._suspend_filters = True
        try:
            self._reset_menu(self.tag_menu, [ANY_TAG, *self.catalog.tags()])
            self._reset_menu(self.tone_menu, [ANY_TONE, *self.catalog.tones()])
            self._sync_category_menu()
        finally:
            self._suspend_filters = False

    def _reset_menu(self, menu: ctk.CTkOptionMenu, values: list[str]) -> None:
        current = menu.get()
        menu.configure(values=values)
        menu.set(current if current in values else values[0])

    def _sync_category_menu(self) -> None:
        names: list[str] = []
        kind = self._selected_kind()
        if self.catalog is not None and kind is not None:
            names = self.catalog.categories(kind)
        self._reset_menu(self.category_menu, [ANY_CATEGORY, *names])

    def _on_filter_changed(self, _value: str | None = None) -> None:
        if self._suspend_filters:
            return
        self._suspend_filters = True
        try:
            self._sync_category_menu()
        finally:
            self._suspend_filters = False
        self._update_status()

    def _selected_kind(self) -> str | None:
        kind_value = KIND_TO_VALUE.get(self.kind_button.get(), "all")
        if kind_value == "all":
            return None
        return kind_value

    def _criteria(self) -> dict[str, object]:
        seconds_label = self.seconds_menu.get()
        return {
            "kind": self._selected_kind(),
            "tag": _or_none(self.tag_menu.get(), ANY_TAG),
            "tone": _or_none(self.tone_menu.get(), ANY_TONE),
            "seconds": None if seconds_label == ANY_SECONDS else SECONDS_VALUE.get(seconds_label),
            "gender": _gender_value(_or_none(self.gender_menu.get(), ANY_GENDER)),
            "category": _or_none(self.category_menu.get(), ANY_CATEGORY),
        }

    def _filtered(self) -> list[Line]:
        if self.catalog is None:
            return []
        return self.catalog.filter(**self._criteria())

    def _draw(self) -> None:
        if self.catalog is None:
            self._show_error("台本を読めませんでした。読み直すと、もう一度試せます。")
            return
        try:
            line = self.catalog.draw(
                **self._criteria(),
                avoid_ids=self.history.avoid_ids(5),
            )
        except CatalogError as exc:
            self._show_error(str(exc))
            return
        self.history.record(line.id)
        self.by_id[line.id] = line
        self._show_line(line)
        self._refresh_recent()
        self._update_status()

    def _recall(self, line_id: str) -> None:
        line = self.by_id.get(line_id)
        if line is None:
            self._set_status("その台本は見つかりませんでした。")
            return
        self._show_line(line)
        self._update_status()

    def _show_line(self, line: Line) -> None:
        self.current = line
        label = BADGE_LABEL.get(line.kind, line.kind)
        self.badge.configure(text=label, fg_color=ACCENT, text_color=ACCENT_TEXT)
        self.direction_label.configure(text=_direction_text(line))
        self.body_label.configure(text=line.text, text_color=INK)
        self.meta_label.configure(text=_meta_text(line))
        self._sync_favorite_button()

    def _show_error(self, message: str) -> None:
        self.current = None
        self.badge.configure(text="お知らせ", fg_color=SUB, text_color=INK)
        self.direction_label.configure(text="")
        self.body_label.configure(text=message, text_color=INK)
        self.meta_label.configure(text="")
        self._sync_favorite_button()
        self._set_status(message)

    def _copy(self) -> None:
        if self.current is None:
            self._set_status("まだコピーできる台本がありません。")
            return
        self.clipboard_clear()
        self.clipboard_append(_copy_text(self.current))
        self.update()
        self._set_status("コピーしました。")

    def _toggle_favorite(self) -> None:
        if self.current is None:
            self._set_status("お気に入りにする台本が、まだありません。")
            return
        if self.favorites is None:
            self._set_status("お気に入りを読めませんでした。")
            return
        try:
            self.favorites.toggle(self.current.id)
        except FavoritesError as exc:
            self._set_status(str(exc))
            return
        self._sync_favorite_button()
        self._update_status()

    def _sync_favorite_button(self) -> None:
        starred = (
            self.current is not None
            and self.favorites is not None
            and self.favorites.contains(self.current.id)
        )
        self.favorite_button.configure(text="★ お気に入り" if starred else "☆ お気に入り")

    def _refresh_recent(self) -> None:
        for child in self.recent_row.winfo_children():
            child.destroy()
        ids = self.history.recent()[:RECENT_SHOW]
        if not ids:
            ctk.CTkLabel(
                self.recent_row,
                text="まだありません",
                font=self.font_small,
                text_color=MUTED,
            ).pack(side="left")
            return
        for line_id in ids:
            line = self.by_id.get(line_id)
            label = _recent_label(line, line_id)
            button = ctk.CTkButton(
                self.recent_row,
                text=label,
                command=lambda lid=line_id: self._recall(lid),
                font=self.font_small,
                fg_color=CARD,
                hover_color=SUB,
                text_color=INK,
                height=34,
                corner_radius=10,
            )
            button.pack(side="left", padx=(0, 8))

    def _update_status(self) -> None:
        if self.catalog is None:
            return
        count = len(self._filtered())
        self._set_status(f"{count}件から引けます")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)


def _gender_value(label: str | None) -> str | None:
    if label is None:
        return None
    return GENDER_VALUE.get(label, label)


def _or_none(value: str, placeholder: str) -> str | None:
    if value == "" or value == placeholder:
        return None
    return value


def _direction_text(line: Line) -> str:
    parts: list[str] = []
    if line.tone:
        parts.append(f"読み方：{line.tone}")
    if line.situation:
        parts.append(f"状況：{line.situation}")
    return "\n".join(parts)


def _copy_text(line: Line) -> str:
    return line.text


def _meta_text(line: Line) -> str:
    parts: list[str] = []
    if line.seconds:
        parts.append(f"{line.seconds}秒")
    if line.gender:
        parts.append(GENDER_LABEL.get(line.gender, line.gender))
    if line.category:
        parts.append(line.category)
    if line.tags:
        parts.append("  ".join(f"#{tag}" for tag in line.tags))
    return "    ".join(parts)


def _recent_label(line: Line | None, line_id: str) -> str:
    if line is None:
        return _clip(line_id, 12)
    head = f"{line.situation} " if line.situation else ""
    return _clip(f"{head}{line.text}", 16)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
