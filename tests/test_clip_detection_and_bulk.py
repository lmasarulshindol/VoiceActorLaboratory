"""
D2 クリップ検出と B1/B3 のメタ拡張（rating/tags/has_clipping/peak_dbfs + bulk 更新）のテスト。
"""
import math
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

import src.storage as storage
from src.project import TakeInfo


def _write_wav(path: Path, samples: np.ndarray, sr: int = 44100) -> None:
    sf.write(str(path), samples.astype(np.float32), sr, subtype="PCM_16")


class TestAnalyzeWavClipping:
    def test_クリップなしは_has_clipping_False(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "soft.wav"
            # 振幅 0.3 のサイン波（クリップしない）
            t = np.linspace(0, 1, 44100, endpoint=False)
            _write_wav(p, 0.3 * np.sin(2 * np.pi * 440 * t))
            info = storage.analyze_wav_clipping(str(p))
            assert info["has_clipping"] is False
            assert info["clipped_samples"] < 3
            assert info["peak_dbfs"] is not None
            assert info["peak_dbfs"] < 0.0

    def test_クリップありは_has_clipping_True(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "clip.wav"
            # 明示的に 1.0 で埋める（フルスケール）
            _write_wav(p, np.ones(44100, dtype=np.float32))
            info = storage.analyze_wav_clipping(str(p))
            assert info["has_clipping"] is True
            assert info["clipped_samples"] >= 3
            assert info["peak_dbfs"] is not None
            assert info["peak_dbfs"] > -1.0

    def test_存在しないファイルは安全側(self) -> None:
        info = storage.analyze_wav_clipping("/nonexistent/does_not_exist.wav")
        assert info["has_clipping"] is False
        assert info["peak_dbfs"] is None
        assert info["clipped_samples"] == 0


class TestTakeInfoExtraFields:
    def test_デフォルト値(self) -> None:
        t = TakeInfo(id="a", wav_filename="a.wav")
        assert t.rating == 0
        assert t.tags == []
        assert t.has_clipping is False
        assert t.peak_dbfs is None

    def test_rating_tags_永続化(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "d.wav"
            _write_wav(wav, np.zeros(441, dtype=np.float32))
            storage.create_project(tmp)
            t = storage.add_take_from_file(tmp, str(wav))
            storage.update_take_meta(
                tmp,
                t.id,
                rating=4,
                tags=["OK", "キャラA", "OK"],  # 重複も許容して保存時に除去
                has_clipping=True,
                peak_dbfs=-0.25,
            )
            proj2 = storage.load_project(tmp)
            assert proj2 is not None
            saved = proj2.takes[0]
            assert saved.rating == 4
            assert saved.tags == ["OK", "キャラA"]  # 重複除去
            assert saved.has_clipping is True
            assert saved.peak_dbfs is not None and abs(saved.peak_dbfs + 0.25) < 1e-6

    def test_rating_は0_5に丸められる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "d.wav"
            _write_wav(wav, np.zeros(441, dtype=np.float32))
            storage.create_project(tmp)
            t = storage.add_take_from_file(tmp, str(wav))
            storage.update_take_meta(tmp, t.id, rating=99)
            proj2 = storage.load_project(tmp)
            assert proj2 is not None
            assert proj2.takes[0].rating == 5
            storage.update_take_meta(tmp, t.id, rating=-5)
            proj3 = storage.load_project(tmp)
            assert proj3 is not None
            assert proj3.takes[0].rating == 0


class TestUpdateTakesMetaBulk:
    def _make_three_takes(self, tmp: str) -> list[str]:
        wav = Path(tmp) / "d.wav"
        _write_wav(wav, np.zeros(441, dtype=np.float32))
        storage.create_project(tmp)
        ids = []
        for _ in range(3):
            t = storage.add_take_from_file(tmp, str(wav))
            ids.append(t.id)
        return ids

    def test_bulk_favorite_True(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ids = self._make_three_takes(tmp)
            n = storage.update_takes_meta_bulk(tmp, ids, favorite=True)
            assert n == 3
            proj = storage.load_project(tmp)
            assert proj is not None
            assert all(t.favorite for t in proj.takes)

    def test_bulk_rating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ids = self._make_three_takes(tmp)
            storage.update_takes_meta_bulk(tmp, ids, rating=3)
            proj = storage.load_project(tmp)
            assert proj is not None
            assert all(t.rating == 3 for t in proj.takes)

    def test_bulk_add_tags_then_remove_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ids = self._make_three_takes(tmp)
            storage.update_takes_meta_bulk(tmp, ids[:2], add_tags=["OK", "リテイク"])
            proj = storage.load_project(tmp)
            assert proj is not None
            assert set(proj.takes[0].tags) == {"OK", "リテイク"}
            assert set(proj.takes[1].tags) == {"OK", "リテイク"}
            assert proj.takes[2].tags == []
            storage.update_takes_meta_bulk(tmp, ids[:2], remove_tags=["OK"])
            proj2 = storage.load_project(tmp)
            assert proj2 is not None
            assert proj2.takes[0].tags == ["リテイク"]
            assert proj2.takes[1].tags == ["リテイク"]

    def test_bulk_clear_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ids = self._make_three_takes(tmp)
            storage.update_take_meta(tmp, ids[0], adopted=True)
            # 現状 1 本採用されている。bulk clear で外れる。
            storage.update_takes_meta_bulk(tmp, ids, clear_adopted=True)
            proj = storage.load_project(tmp)
            assert proj is not None
            assert all(not t.adopted for t in proj.takes)


class TestFormatExportFilename:
    def test_標準テンプレ(self) -> None:
        t = TakeInfo(
            id="x",
            wav_filename="take_1.wav",
            script_line_number=12,
            script_line_text="こんにちは世界",
            rating=3,
        )
        name = storage.format_export_filename(
            "{project}_{n}_{line}",
            project_name="myproj",
            take=t,
            index=0,
        )
        assert name == "myproj_001_12"

    def test_text_は短縮される(self) -> None:
        t = TakeInfo(
            id="x",
            wav_filename="a.wav",
            script_line_text="あ" * 50,
        )
        name = storage.format_export_filename(
            "{project}_{text}",
            project_name="p",
            take=t,
            index=0,
        )
        assert name.startswith("p_")
        assert len(name) < 100  # 異常に長くならない

    def test_未知プレースホルダでフォールバック(self) -> None:
        t = TakeInfo(id="x", wav_filename="a.wav")
        name = storage.format_export_filename(
            "{unknown_key}",
            project_name="myp",
            take=t,
            index=2,
        )
        assert name == "myp_Take3"
