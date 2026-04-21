"""
storage.get_takes_dir / reveal_in_file_manager の単体テスト。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from src import storage


class TestGetTakesDir:
    def test_takesディレクトリのパスを返す(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            got = storage.get_takes_dir(tmp)
            assert Path(got) == Path(tmp) / "takes"

    def test_未作成でもパスを返す(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            got = storage.get_takes_dir(tmp)
            assert not Path(got).exists()
            assert str(got).endswith("takes")


class TestRevealInFileManager:
    def test_空文字はFalse(self) -> None:
        assert storage.reveal_in_file_manager("") is False

    def test_存在しない親もないパスはFalse(self) -> None:
        assert storage.reveal_in_file_manager("/__absolutely_does_not_exist__/foo/bar") is False

    def test_windowsでディレクトリを開くときstartfileが呼ばれる(self) -> None:
        if not sys.platform.startswith("win"):
            return
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.startfile", create=True) as m:
                ok = storage.reveal_in_file_manager(tmp)
            assert ok is True
            m.assert_called_once()

    def test_windowsでファイルを渡すとexplorerが呼ばれる(self) -> None:
        if not sys.platform.startswith("win"):
            return
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.wav"
            f.write_bytes(b"RIFF")
            with patch("subprocess.Popen") as m:
                ok = storage.reveal_in_file_manager(str(f))
            assert ok is True
            args, _ = m.call_args
            cmd = args[0]
            assert cmd[0] == "explorer"
            assert cmd[1].startswith("/select,")
            assert str(f) in cmd[1]

    def test_存在しないファイルでも親が存在すれば親を開く(self) -> None:
        if not sys.platform.startswith("win"):
            return
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.wav"
            with patch("os.startfile", create=True) as m:
                ok = storage.reveal_in_file_manager(str(missing))
            assert ok is True
            m.assert_called_once()
