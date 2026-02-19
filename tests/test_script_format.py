"""台本フォーマット・ファイル名導出のテスト。"""
import pytest
from src.script_format import get_current_section, sanitize_for_filename, suggest_take_basename


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
