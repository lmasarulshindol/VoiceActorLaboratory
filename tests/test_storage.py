"""
storage モジュールの単体テスト。一時ディレクトリでプロジェクト作成・読み書き・エクスポートを検証。
"""
import tempfile
from pathlib import Path
import pytest
from src.project import Project, TakeInfo
import src.storage as storage


class TestStorage:
    """storage のテスト。"""

    def test_create_projectでフォルダとtakesができる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = storage.create_project(tmp)
            assert proj.project_dir == tmp
            assert (Path(tmp) / "takes").is_dir()
            assert (Path(tmp) / "project_meta.json").exists()

    def test_load_project_空フォルダ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == ""
            assert proj.takes == []

    def test_save_scriptとloadで台本が往復する(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.save_script(tmp, "台本テキスト")
            assert (Path(tmp) / "script.txt").read_text(encoding="utf-8") == "台本テキスト"
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == "台本テキスト"

    def test_add_take_from_fileでWAVをコピーしメタに追加(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # ダミー WAV ファイル（最小ヘッダ + 少しデータ）
            wav = Path(tmp) / "dummy.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            proj = storage.create_project(tmp)
            take = storage.add_take_from_file(tmp, str(wav), memo="テスト", favorite=True)
            assert take.id
            assert take.wav_filename.endswith(".wav")
            assert take.memo == "テスト"
            assert take.favorite is True
            assert take.created_at != ""
            assert take.adopted is False
            proj2 = storage.load_project(tmp)
            assert proj2 is not None
            assert len(proj2.takes) == 1
            assert (Path(tmp) / "takes" / take.wav_filename).exists()

    def test_get_take_wav_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = storage.get_take_wav_path(tmp, "foo.wav")
            assert path == str(Path(tmp) / "takes" / "foo.wav")

    def test_export_takesでコピーされる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = storage.create_project(tmp)
            wav = Path(tmp) / "dummy.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            take = storage.add_take_from_file(tmp, str(wav))
            dest = Path(tmp) / "export"
            paths = storage.export_takes(tmp, [take.id], str(dest))
            assert len(paths) == 1
            assert Path(paths[0]).exists()
            assert Path(paths[0]).parent == dest

    def test_load_project_存在しないパスはNone(self) -> None:
        assert storage.load_project("/nonexistent/path/12345") is None

    def test_delete_take(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "dummy.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            take = storage.add_take_from_file(tmp, str(wav))
            wav_path = Path(storage.get_take_wav_path(tmp, take.wav_filename))
            assert wav_path.exists()
            assert storage.delete_take(tmp, take.id) is True
            assert not wav_path.exists()
            proj = storage.load_project(tmp)
            assert proj is not None
            assert len(proj.takes) == 0

    def test_export_takes_use_friendly_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "dummy.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            take = storage.add_take_from_file(tmp, str(wav))
            dest = Path(tmp) / "export"
            paths = storage.export_takes(tmp, [take.id], str(dest), use_friendly_names=True)
            assert len(paths) == 1
            assert Path(paths[0]).name.startswith(Path(tmp).name)
            assert "Take1" in Path(paths[0]).name

    def test_get_wav_duration_seconds_存在しないファイルは0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            dur = storage.get_wav_duration_seconds(tmp, "nonexistent.wav")
            assert dur == 0.0

    def test_get_wav_duration_seconds_有効なWAVで長さを返す(self) -> None:
        import numpy as np
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            takes_dir = Path(tmp) / "takes"
            takes_dir.mkdir()
            wav_path = takes_dir / "one_sec.wav"
            # 1秒分の無音 (44100 Hz, mono)
            sf.write(str(wav_path), np.zeros(44100, dtype=np.float32), 44100)
            dur = storage.get_wav_duration_seconds(tmp, "one_sec.wav")
            assert 0.99 <= dur <= 1.01
