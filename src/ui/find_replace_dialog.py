"""
台本エリア用の検索・置換ダイアログ。Ctrl+F / Ctrl+H で表示。
"""
import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QGroupBox,
)
from PyQt6.QtGui import QTextDocument


class FindReplaceDialog(QDialog):
    """検索・置換ダイアログ。QPlainTextEdit を対象に検索・置換を行う。"""

    def __init__(self, parent=None, script_edit=None, replace_mode: bool = False):
        super().__init__(parent)
        self._script_edit = script_edit
        self._replace_mode = replace_mode
        self.setWindowTitle("置換" if replace_mode else "検索")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        # 検索
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("検索:"))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("検索する文字列")
        self._find_edit.textChanged.connect(self._on_find_text_changed)
        find_layout.addWidget(self._find_edit)
        layout.addLayout(find_layout)

        # 置換（置換モード時のみ）
        if replace_mode:
            replace_layout = QHBoxLayout()
            replace_layout.addWidget(QLabel("置換:"))
            self._replace_edit = QLineEdit()
            self._replace_edit.setPlaceholderText("置換後の文字列")
            replace_layout.addWidget(self._replace_edit)
            layout.addLayout(replace_layout)
        else:
            self._replace_edit = None

        # オプション
        opt_group = QGroupBox("オプション")
        opt_layout = QVBoxLayout(opt_group)
        self._case_check = QCheckBox("大文字・小文字を区別する")
        opt_layout.addWidget(self._case_check)
        layout.addWidget(opt_group)

        # ボタン
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._find_next_btn = QPushButton("次を検索")
        self._find_next_btn.setDefault(True)
        self._find_next_btn.clicked.connect(self._on_find_next)
        self._find_next_btn.setEnabled(False)
        btn_layout.addWidget(self._find_next_btn)

        if replace_mode:
            self._replace_btn = QPushButton("置換")
            self._replace_btn.clicked.connect(self._on_replace)
            self._replace_btn.setEnabled(False)
            btn_layout.addWidget(self._replace_btn)
            self._replace_all_btn = QPushButton("すべて置換")
            self._replace_all_btn.clicked.connect(self._on_replace_all)
            self._replace_all_btn.setEnabled(False)
            btn_layout.addWidget(self._replace_all_btn)
        else:
            self._replace_btn = None
            self._replace_all_btn = None

        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def set_replace_mode(self, replace_mode: bool) -> None:
        self._replace_mode = replace_mode
        self.setWindowTitle("置換" if replace_mode else "検索")

    def _on_find_text_changed(self, text: str) -> None:
        enabled = bool(text.strip())
        self._find_next_btn.setEnabled(enabled)
        if self._replace_btn is not None:
            self._replace_btn.setEnabled(enabled)
        if self._replace_all_btn is not None:
            self._replace_all_btn.setEnabled(enabled)

    def _find_flags(self) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if self._case_check.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def _on_find_next(self) -> None:
        if not self._script_edit:
            return
        needle = self._find_edit.text()
        if not needle:
            return
        flags = self._find_flags()
        found = self._script_edit.find(needle, flags)
        if not found:
            # 先頭から再検索（ラップ）
            cursor = self._script_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._script_edit.setTextCursor(cursor)
            found = self._script_edit.find(needle, flags)
        if not found and self.parent():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "検索", "指定の文字列は見つかりませんでした。")

    def _on_replace(self) -> None:
        if not self._script_edit or not self._replace_edit:
            return
        cursor = self._script_edit.textCursor()
        if not cursor.hasSelection():
            self._on_find_next()
            return
        cursor.insertText(self._replace_edit.text())
        self._on_find_next()

    def _on_replace_all(self) -> None:
        if not self._script_edit or not self._replace_edit:
            return
        needle = self._find_edit.text()
        if not needle:
            return
        replace_with = self._replace_edit.text()
        text = self._script_edit.toPlainText()
        case_sensitive = self._case_check.isChecked()
        if case_sensitive:
            new_text = text.replace(needle, replace_with)
            count = text.count(needle)
        else:
            pattern = re.compile(re.escape(needle), re.IGNORECASE)
            count = len(pattern.findall(text))
            new_text = pattern.sub(replace_with, text)
        self._script_edit.setPlainText(new_text)
        if self.parent():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "すべて置換", f"{count} 件置換しました。")
