"""
project モジュールの単体テスト。
"""
import pytest
from src.project import Project, TakeInfo


class TestTakeInfo:
    """TakeInfo のテスト。"""

    def test_display_name_はindexなしでwav_filenameを返す(self) -> None:
        t = TakeInfo(id="a", wav_filename="take_01.wav")
        assert t.display_name() == "take_01.wav"

    def test_display_name_はindexとcreated_atでTake形式を返す(self) -> None:
        t = TakeInfo(id="a", wav_filename="x.wav", created_at="2025-02-19T14:30:00")
        assert "Take 1" in t.display_name(0)
        assert "02/19" in t.display_name(0)

    def test_memo_favorite_created_at_adoptedのデフォルト(self) -> None:
        t = TakeInfo(id="b", wav_filename="x.wav")
        assert t.memo == ""
        assert t.favorite is False
        assert t.created_at == ""
        assert t.adopted is False


class TestProject:
    """Project のテスト。"""

    def test_初期状態は空(self) -> None:
        p = Project()
        assert p.script_path == ""
        assert p.script_text == ""
        assert p.takes == []
        assert p.has_script() is False
        assert p.has_project_dir() is False

    def test_set_scriptで台本を設定(self) -> None:
        p = Project()
        p.set_script("/path/to/script.txt", "こんにちは")
        assert p.script_path == "/path/to/script.txt"
        assert p.script_text == "こんにちは"
        assert p.has_script() is True

    def test_空の台本ではhas_scriptがFalse(self) -> None:
        p = Project()
        p.set_script("", "   \n  ")
        assert p.has_script() is False

    def test_add_takeでテイク追加(self) -> None:
        p = Project()
        t = TakeInfo(id="1", wav_filename="a.wav", memo="メモ")
        p.add_take(t)
        assert len(p.takes) == 1
        assert p.get_take("1") is t
        assert p.get_take("999") is None

    def test_update_take_memo(self) -> None:
        p = Project()
        t = TakeInfo(id="1", wav_filename="a.wav", memo="旧")
        p.add_take(t)
        assert p.update_take_memo("1", "新") is True
        assert t.memo == "新"
        assert p.update_take_memo("999", "x") is False

    def test_update_take_favorite(self) -> None:
        p = Project()
        t = TakeInfo(id="1", wav_filename="a.wav", favorite=False)
        p.add_take(t)
        assert p.update_take_favorite("1", True) is True
        assert t.favorite is True
        assert p.update_take_favorite("999", True) is False

    def test_update_take_adopted_とget_adopted_take(self) -> None:
        p = Project()
        t1 = TakeInfo(id="1", wav_filename="a.wav", adopted=False)
        t2 = TakeInfo(id="2", wav_filename="b.wav", adopted=False)
        p.add_take(t1)
        p.add_take(t2)
        assert p.get_adopted_take() is None
        assert p.update_take_adopted("1", True) is True
        assert t1.adopted is True
        assert t2.adopted is False
        assert p.get_adopted_take() is t1
        assert p.update_take_adopted("2", True) is True
        assert t1.adopted is False
        assert t2.adopted is True
        assert p.get_adopted_take() is t2
