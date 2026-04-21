"""
storage モジュールの単体テスト。一時ディレクトリでプロジェクト作成・読み書き・エクスポートを検証。
"""
import tempfile
from pathlib import Path
import pytest
from src.project import Project, TakeInfo
import src.storage as storage


class TestDecodeScriptBytes:
    def test_UTF8でデコード(self) -> None:
        data = "台本テキスト".encode("utf-8")
        assert storage.decode_script_bytes(data) == "台本テキスト"

    def test_UTF8_BOMでデコード(self) -> None:
        data = b"\xef\xbb\xbf" + "見出し".encode("utf-8")
        assert storage.decode_script_bytes(data) == "見出し"

    def test_CP932でフォールバック(self) -> None:
        data = "日本語".encode("cp932")
        assert storage.decode_script_bytes(data) == "日本語"

    def test_全エンコーディング失敗で例外(self) -> None:
        import pytest
        # UTF-8/UTF-8-sig/CP932 のいずれでもデコードできないバイト列（不完全なマルチバイト等）
        data = bytes([0x81, 0x00, 0xFE, 0xFF])
        with pytest.raises((UnicodeDecodeError, LookupError)):
            storage.decode_script_bytes(data)


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
            script_file = storage.find_script_file(tmp)
            assert script_file is not None
            assert script_file.read_text(encoding="utf-8") == "台本テキスト"
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == "台本テキスト"

    def test_save_script_既存txtがあればtxtに保存(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "script.txt").write_text("旧台本", encoding="utf-8")
            storage.save_script(tmp, "新台本")
            assert (Path(tmp) / "script.txt").read_text(encoding="utf-8") == "新台本"
            assert not (Path(tmp) / "script.md").exists()

    def test_save_script_既存mdがあればmdに保存(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "script.md").write_text("旧台本", encoding="utf-8")
            storage.save_script(tmp, "新台本")
            assert (Path(tmp) / "script.md").read_text(encoding="utf-8") == "新台本"

    def test_load_project_mdファイルを読める(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            (Path(tmp) / "script.md").write_bytes("# シーン1\nセリフ".encode("utf-8"))
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == "# シーン1\nセリフ"

    def test_load_project_mdが優先される(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            (Path(tmp) / "script.txt").write_text("txtの内容", encoding="utf-8")
            (Path(tmp) / "script.md").write_text("mdの内容", encoding="utf-8")
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == "mdの内容"

    def test_load_project_CP932のscriptを読める(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            script_path = Path(tmp) / "script.txt"
            script_path.write_bytes("シーン1".encode("cp932"))
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == "シーン1"

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

    def test_load_project_scriptが無いフォルダ_takesのみ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            (Path(tmp) / "project_meta.json").write_text('{"takes":[]}', encoding="utf-8")
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.script_text == ""
            assert proj.script_path == ""
            assert proj.takes == []

    def test_save_script_use_md_Falseでtxtに保存(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.save_script(tmp, "台本", use_md=False)
            assert (Path(tmp) / "script.txt").read_text(encoding="utf-8") == "台本"
            assert not (Path(tmp) / "script.md").exists()

    def test_update_take_meta_adoptedで他がFalse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "d.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            t1 = storage.add_take_from_file(tmp, str(wav))
            t2 = storage.add_take_from_file(tmp, str(wav))
            storage.update_take_meta(tmp, t1.id, adopted=True)
            proj = storage.load_project(tmp)
            assert proj is not None
            adopted = [t for t in proj.takes if t.adopted]
            assert len(adopted) == 1 and adopted[0].id == t1.id
            storage.update_take_meta(tmp, t2.id, adopted=True)
            proj2 = storage.load_project(tmp)
            adopted2 = [t for t in proj2.takes if t.adopted]
            assert len(adopted2) == 1 and adopted2[0].id == t2.id

    def test_list_take_wav_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            proj = storage.create_project(tmp)
            wav = Path(tmp) / "d.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            take = storage.add_take_from_file(tmp, str(wav))
            pairs = storage.list_take_wav_paths(tmp)
            assert len(pairs) == 1
            assert pairs[0][0] == take.id
            assert pairs[0][1] == storage.get_take_wav_path(tmp, take.wav_filename)

    def test_load_project_壊れたmetaでtakesは空(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "takes").mkdir()
            (Path(tmp) / "project_meta.json").write_text("{ invalid json }", encoding="utf-8")
            proj = storage.load_project(tmp)
            assert proj is not None
            assert proj.takes == []

    def test_add_take_from_file_preferred_basename重複でuuid付き(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.create_project(tmp)
            wav = Path(tmp) / "d.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            t1 = storage.add_take_from_file(tmp, str(wav), preferred_basename="scene")
            t2 = storage.add_take_from_file(tmp, str(wav), preferred_basename="scene")
            assert t1.wav_filename == "scene.wav" or t1.wav_filename.startswith("scene_")
            assert t2.wav_filename != t1.wav_filename
            assert (Path(tmp) / "takes" / t1.wav_filename).exists()
            assert (Path(tmp) / "takes" / t2.wav_filename).exists()

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


class TestExportTakesWithFormat:
    """A/B/C: export_takes のフォーマット指定・後処理チェーンのテスト。"""

    def _make_take(self, project_dir: str) -> str:
        import numpy as np
        import soundfile as sf
        storage.create_project(project_dir)
        wav = Path(project_dir) / "src.wav"
        t = np.linspace(0, 1.5, int(44100 * 1.5), endpoint=False)
        sig = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        sf.write(str(wav), sig, 44100, subtype="PCM_16")
        take = storage.add_take_from_file(project_dir, str(wav))
        return take.id

    def test_flac形式で書き出せる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            take_id = self._make_take(tmp)
            dest = Path(tmp) / "export"
            paths = storage.export_takes(tmp, [take_id], str(dest), fmt="flac")
            assert len(paths) == 1
            assert Path(paths[0]).suffix.lower() == ".flac"
            assert Path(paths[0]).exists()

    def test_mp3形式で書き出せる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            take_id = self._make_take(tmp)
            dest = Path(tmp) / "export"
            paths = storage.export_takes(
                tmp, [take_id], str(dest), fmt="mp3", mp3_bitrate_kbps=128
            )
            assert len(paths) == 1
            assert Path(paths[0]).suffix.lower() == ".mp3"
            assert Path(paths[0]).stat().st_size > 500

    def test_lufs正規化を伴うwav書き出し(self) -> None:
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            take_id = self._make_take(tmp)
            dest = Path(tmp) / "export"
            paths = storage.export_takes(
                tmp, [take_id], str(dest), fmt="wav",
                do_lufs_normalize=True, target_lufs=-16.0,
            )
            assert len(paths) == 1
            assert Path(paths[0]).exists()
            info = sf.info(paths[0])
            assert info.samplerate == 44100

    def test_後処理なしのwavはコピーで動作(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            take_id = self._make_take(tmp)
            dest = Path(tmp) / "export"
            paths = storage.export_takes(tmp, [take_id], str(dest), fmt="wav")
            assert len(paths) == 1
            assert Path(paths[0]).suffix.lower() == ".wav"

    def test_拡張子はテンプレート適用後でも正しい(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            take_id = self._make_take(tmp)
            dest = Path(tmp) / "export"
            paths = storage.export_takes(
                tmp, [take_id], str(dest),
                name_template="{project}_{n}",
                fmt="flac",
            )
            assert len(paths) == 1
            assert Path(paths[0]).suffix.lower() == ".flac"


class TestTakeInfoIntegratedLufs:
    """TakeInfo.integrated_lufs の往復永続化テスト。"""

    def test_integrated_lufs_が保存ロードで保持される(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "d.wav"
            wav.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
            take = storage.add_take_from_file(tmp, str(wav))
            assert storage.update_take_meta(tmp, take.id, integrated_lufs=-18.2) is True
            proj = storage.load_project(tmp)
            assert proj is not None
            t = proj.get_take(take.id)
            assert t is not None
            assert t.integrated_lufs == pytest.approx(-18.2, rel=1e-3)
