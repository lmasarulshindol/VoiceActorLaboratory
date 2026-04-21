"""
アプリ全体フォントの初期値を保持し、上書き/リストアを行うヘルパー。

QApplication 起動直後に `remember_default_app_font()` を呼んでおくと、
後から `apply_override(size)` / `restore_default()` で切り替えできる。
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

_default_font: QFont | None = None


def remember_default_app_font() -> None:
    """起動時のシステム既定フォントを記録する（初回のみ効果あり）。"""
    global _default_font
    if _default_font is not None:
        return
    app = QApplication.instance()
    if app is None:
        return
    _default_font = QFont(app.font())


def apply_override(size: int) -> None:
    """アプリ全体フォントの pt サイズを上書きする。"""
    app = QApplication.instance()
    if app is None:
        return
    base = QFont(_default_font) if _default_font is not None else QFont(app.font())
    base.setPointSize(int(size))
    app.setFont(base)


def restore_default() -> None:
    """上書きを解除して、起動時のシステム既定フォントに戻す。"""
    app = QApplication.instance()
    if app is None:
        return
    if _default_font is not None:
        app.setFont(QFont(_default_font))


def apply_from_settings() -> None:
    """現在の設定値に従ってフォントを上書き/リストアする。"""
    from src.ui.settings import get_app_font_size
    size = get_app_font_size()
    if size > 0:
        apply_override(size)
    else:
        restore_default()
