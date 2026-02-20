"""
テーマ用色定義。メインウィンドウ・設定ダイアログ・リスト等で共有し視認性を統一する。
"""
from src.ui.settings import get_theme

# ダーク／ライト共通
COLOR_ACCENT = "#0d9488"
SIDEBAR_BG_LIGHT = "#f5f5f5"
SIDEBAR_BG_DARK = "#1e293b"
CARD_BG_LIGHT = "#ffffff"
CARD_BORDER_LIGHT = "#e5e7eb"
CARD_BG_DARK = "#334155"
CARD_BORDER_DARK = "#475569"

# ライト
TEXT_HEADING_LIGHT = "#111827"
TEXT_BODY_LIGHT = "#374151"
TEXT_CAPTION_LIGHT = "#6b7280"

# ダーク
TEXT_HEADING_DARK = "#f1f5f9"
TEXT_BODY_DARK = "#cbd5e1"
TEXT_CAPTION_DARK = "#94a3b8"
SCRIPT_BG_DARK = "#1e293b"
SCRIPT_TEXT_DARK = "#e2e8f0"

# テイク一覧の再生中ハイライト
TAKE_LIST_HIGHLIGHT_LIGHT = "#b4d0e8"
TAKE_LIST_HIGHLIGHT_DARK = "#475569"


def is_dark() -> bool:
    return get_theme() == "dark"
