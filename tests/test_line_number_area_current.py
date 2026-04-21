"""
LineNumberArea のカーソル行マーカーおよびテイク情報表示の基本動作を検証する。
実際の描画は行わず、内部状態と setter API が正しく動作することを確認する。
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _make_area(qapp):
    from PyQt6.QtWidgets import QPlainTextEdit
    from src.ui.script_edit_with_line_numbers import LineNumberArea
    edit = QPlainTextEdit()
    edit.setPlainText("line1\nline2\nline3\nline4\n")
    area = LineNumberArea(edit)
    return edit, area


class TestLineNumberAreaCursor:
    def test_初期状態_current_lineはNone(self, qapp):
        _, area = _make_area(qapp)
        assert area._current_line is None

    def test_set_current_line_で値が反映される(self, qapp):
        _, area = _make_area(qapp)
        area.set_current_line(3)
        assert area._current_line == 3

    def test_set_current_line_Noneでマーカー非表示(self, qapp):
        _, area = _make_area(qapp)
        area.set_current_line(2)
        area.set_current_line(None)
        assert area._current_line is None

    def test_同値で呼んでもエラーにならない(self, qapp):
        _, area = _make_area(qapp)
        area.set_current_line(5)
        area.set_current_line(5)
        assert area._current_line == 5

    def test_sizeHint_にカーソル領域分の幅が含まれる(self, qapp):
        _, area = _make_area(qapp)
        hint = area.sizeHint()
        assert hint.width() >= area._CURSOR_DOT_AREA


class TestLineNumberAreaTakeInfo:
    def test_set_line_take_info_で状態が保持される(self, qapp):
        _, area = _make_area(qapp)
        area.set_line_take_info({1: 3, 2: 1}, {2})
        assert area._line_take_counts == {1: 3, 2: 1}
        assert area._line_adopted == {2}

    def test_set_line_take_info_Noneで空になる(self, qapp):
        _, area = _make_area(qapp)
        area.set_line_take_info({1: 2}, {1})
        area.set_line_take_info({}, set())
        assert area._line_take_counts == {}
        assert area._line_adopted == set()


class TestScriptContainerCurrentLineAPI:
    def test_container_set_current_script_line_がガターへ伝搬する(self, qapp):
        from src.ui.script_edit_with_line_numbers import ScriptEditWithLineNumbers
        container = ScriptEditWithLineNumbers()
        container.script_edit().setPlainText("a\nb\nc\n")
        container.set_current_script_line(2)
        assert container._line_number_area._current_line == 2
        container.set_current_script_line(None)
        assert container._line_number_area._current_line is None
