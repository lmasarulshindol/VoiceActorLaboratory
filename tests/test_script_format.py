"""台本フォーマット・ファイル名導出のテスト。"""
import pytest
from src.script_format import (
    get_current_section,
    get_current_line_text,
    get_current_line_number,
    sanitize_for_filename,
    suggest_take_basename,
)
from src.script_template import DEFAULT_SCRIPT_TEMPLATE


class TestGetCurrentSection:
    def test_見出しなしでは空(self) -> None:
        assert get_current_section("ただのテキスト", 0) == ""
        assert get_current_section("ただのテキスト", 10) == ""

    def test_行頭シャープが現在のシーン(self) -> None:
        t = "# シーン1\n台本\n"
        assert get_current_section(t, 0) == ""
        assert get_current_section(t, 4) == "シーン1"
        assert get_current_section(t, 10) == "シーン1"

    def test_カーソルより前の直近の見出し(self) -> None:
        t = "# シーン1\nああ\n# シーン2\nいい\n"
        assert get_current_section(t, 0) == ""
        assert get_current_section(t, 5) == "シーン1"
        assert get_current_section(t, 15) == "シーン2"

    def test_サブ見出しも認識(self) -> None:
        t = "# 親\n## 子\n本文"
        assert get_current_section(t, 8) == "子"

    def test_3レベル見出しも認識(self) -> None:
        t = "# 親\n## 子\n### 孫\n本文"
        assert get_current_section(t, 14) == "孫"


class TestGetCurrentLineText:
    def test_見出し行では空(self) -> None:
        t = "# シーン1\n台本"
        assert get_current_line_text(t, 0) == ""
        assert get_current_line_text(t, 5) == ""

    def test_キャラ名コロンでセリフのみ返る(self) -> None:
        t = "キャラ名: おはようございます。"
        assert get_current_line_text(t, 0) == "おはようございます。"
        assert get_current_line_text(t, 10) == "おはようございます。"

    def test_コロンが複数ある場合は最初のコロンで分割(self) -> None:
        t = "ナレーション: はい、そうです: と答えた。"
        assert get_current_line_text(t, 0) == "はい、そうです: と答えた。"

    def test_セリフ形式でない行はそのまま返す(self) -> None:
        t = "（ト書きや演技メモ）"
        assert get_current_line_text(t, 0) == "（ト書きや演技メモ）"

    def test_空行は空文字(self) -> None:
        t = "一行目\n\n三行目"
        # 2行目（空行）は \n の直後のみ。len("一行目")=3 なので position 4 が空行
        assert get_current_line_text(t, 4) == ""

    def test_複数行のうち現在行のみ(self) -> None:
        t = "A:  first\nB:  second\nC:  third"
        assert get_current_line_text(t, 0) == "first"
        assert get_current_line_text(t, 12) == "second"
        assert get_current_line_text(t, 24) == "third"


class TestGetCurrentLineNumber:
    def test_1行目(self) -> None:
        t = "唯一の行"
        assert get_current_line_number(t, 0) == 1
        assert get_current_line_number(t, 3) == 1

    def test_最終行(self) -> None:
        t = "1\n2\n3"
        assert get_current_line_number(t, 4) == 3
        assert get_current_line_number(t, 5) == 3

    def test_空テキストでは0行(self) -> None:
        assert get_current_line_number("", 0) == 0

    def test_複数行の途中位置(self) -> None:
        t = "a\nbb\nccc"
        assert get_current_line_number(t, 0) == 1
        assert get_current_line_number(t, 2) == 2
        assert get_current_line_number(t, 6) == 3


class TestSanitizeForFilename:
    def test_空白はアンダースコア(self) -> None:
        assert sanitize_for_filename("a b") == "a_b"

    def test_禁止文字は除去(self) -> None:
        assert "/" not in sanitize_for_filename("a/b")
        assert ":" not in sanitize_for_filename("a:b")

    def test_空は空(self) -> None:
        assert sanitize_for_filename("") == ""
        assert sanitize_for_filename("   ") == ""

    def test_長さ制限(self) -> None:
        assert len(sanitize_for_filename("a" * 200, max_length=10)) <= 10


class TestSuggestTakeBasename:
    def test_見出しと連番(self) -> None:
        script = "# 朝の挨拶\nおはよう\n"
        assert suggest_take_basename(script, 10, []) == "朝の挨拶_01"
        assert suggest_take_basename(script, 10, ["朝の挨拶_01.wav"]) == "朝の挨拶_02"

    def test_見出しなしはtake連番(self) -> None:
        assert suggest_take_basename("本文のみ", 0, []) == "take_01"
        assert suggest_take_basename("本文のみ", 0, ["take_01.wav"]) == "take_02"


class TestDefaultScriptTemplate:
    """DEFAULT_SCRIPT_TEMPLATE がアプリで期待する最低限のフォーマットを満たすことを保証する。"""

    def test_見出しを含む(self) -> None:
        lines = DEFAULT_SCRIPT_TEMPLATE.splitlines()
        heading_lines = [ln.strip() for ln in lines if ln.strip().startswith("#")]
        assert len(heading_lines) >= 1
        assert any(ln.startswith("# ") or ln.startswith("## ") for ln in heading_lines)

    def test_キャラ名コロンセリフ形式を1行以上含む(self) -> None:
        lines = DEFAULT_SCRIPT_TEMPLATE.splitlines()
        dialogue_lines = [ln for ln in lines if ":" in ln and not ln.strip().startswith("#")]
        assert len(dialogue_lines) >= 1
        for ln in dialogue_lines:
            parts = ln.split(":", 1)
            assert len(parts) == 2
            assert parts[1].strip()
