"""
VoiceActorLaboratory エントリポイント。
PyQt6 でメインウィンドウを表示する。
"""
import sys
from pathlib import Path

# 実行ファイルの場所を基準に作業ディレクトリを設定（相対パス・絶対パスどちらで起動しても同じように動く）
_app_dir = Path(__file__).resolve().parent
import os
os.chdir(_app_dir)

from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.ui.settings import get_theme
from src.ui.theme_loader import apply_app_theme


def main() -> None:
    app = QApplication(sys.argv)
    apply_app_theme(get_theme())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
