"""パッケージバージョンのテスト。"""
import pytest


def test_version_が定義されている() -> None:
    from src import __version__
    assert __version__ == "0.1.0"
