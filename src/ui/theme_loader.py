"""
QSS テーマの読み込みとアプリ全体への適用。
ライト/ダークの .qss を読み、プレースホルダを theme_colors の値で置換して QApplication に setStyleSheet する。
"""
from pathlib import Path

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from src.ui.settings import get_theme, set_theme
from src.ui.theme_colors import (
    COLOR_ACCENT,
    SIDEBAR_BG_LIGHT,
    SIDEBAR_BG_DARK,
    CARD_BG_LIGHT,
    CARD_BORDER_LIGHT,
    CARD_BG_DARK,
    CARD_BORDER_DARK,
    TEXT_HEADING_LIGHT,
    TEXT_BODY_LIGHT,
    TEXT_CAPTION_LIGHT,
    TEXT_HEADING_DARK,
    TEXT_BODY_DARK,
    TEXT_CAPTION_DARK,
    SCRIPT_BG_DARK,
    SCRIPT_TEXT_DARK,
)

# プレースホルダ名 → 値（ライト）
_LIGHT_VARS = {
    "WINDOW_BG": "#ffffff",
    "CARD_BG": CARD_BG_LIGHT,
    "CARD_BORDER": CARD_BORDER_LIGHT,
    "TEXT_HEADING": TEXT_HEADING_LIGHT,
    "TEXT_BODY": TEXT_BODY_LIGHT,
    "TEXT_CAPTION": TEXT_CAPTION_LIGHT,
    "SIDEBAR_BG": SIDEBAR_BG_LIGHT,
    "SCRIPT_BG": CARD_BG_LIGHT,
    "SCRIPT_TEXT": TEXT_BODY_LIGHT,
    "COLOR_ACCENT": COLOR_ACCENT,
    "TAKE_SELECTION_BG": CARD_BORDER_LIGHT,
}

# プレースホルダ名 → 値（ダーク）
_DARK_VARS = {
    "WINDOW_BG": SIDEBAR_BG_DARK,
    "CARD_BG": CARD_BG_DARK,
    "CARD_BORDER": CARD_BORDER_DARK,
    "TEXT_HEADING": TEXT_HEADING_DARK,
    "TEXT_BODY": TEXT_BODY_DARK,
    "TEXT_CAPTION": TEXT_CAPTION_DARK,
    "SIDEBAR_BG": SIDEBAR_BG_DARK,
    "SCRIPT_BG": SCRIPT_BG_DARK,
    "SCRIPT_TEXT": SCRIPT_TEXT_DARK,
    "COLOR_ACCENT": COLOR_ACCENT,
    "TAKE_SELECTION_BG": CARD_BORDER_DARK,
}


def load_stylesheet(theme: str) -> str:
    """指定テーマの .qss を読み、プレースホルダを置換して返す。"""
    theme = theme if theme in ("light", "dark") else "light"
    path = Path(__file__).parent / "themes" / f"theme_{theme}.qss"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    vars_map = _DARK_VARS if theme == "dark" else _LIGHT_VARS
    for key, value in vars_map.items():
        content = content.replace("{{" + key + "}}", value)
    return content


def _set_palette(app: QApplication, theme: str) -> None:
    """アプリのパレットをテーマに合わせて設定（QSS でカバーされない部分のフォールバック）。"""
    palette = QPalette()
    if theme == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor(0x1E, 0x29, 0x3B))
        palette.setColor(QPalette.ColorRole.Base, QColor(0x33, 0x41, 0x55))
        palette.setColor(QPalette.ColorRole.Text, QColor(0xE2, 0xE8, 0xF0))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(0xF1, 0xF5, 0xF9))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(0xF1, 0xF5, 0xF9))
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor(0xFF, 0xFF, 0xFF))
        palette.setColor(QPalette.ColorRole.Base, QColor(0xFF, 0xFF, 0xFF))
        palette.setColor(QPalette.ColorRole.Text, QColor(0x11, 0x18, 0x27))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(0x11, 0x18, 0x27))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(0x11, 0x18, 0x27))
    app.setPalette(palette)


def apply_app_theme(theme: str) -> None:
    """テーマを保存し、QSS とパレットをアプリ全体に適用する。"""
    set_theme(theme)
    app = QApplication.instance()
    if not app:
        return
    qss = load_stylesheet(theme)
    app.setStyleSheet(qss)
    _set_palette(app, theme)
