"""
LUFS / Peak のリアルタイム状態分類ヘルパーのテスト。

main_window の UI から切り出した純粋関数だけをテスト対象にするので、
Qt の初期化は不要。
"""
import math

from src.ui.main_window import _classify_lufs_status, _classify_peak_status


class TestClassifyLufsStatus:
    """現在 LUFS と目標値の差から状態を 4 段階に分類する。"""

    def test_目標と完全一致はok(self) -> None:
        assert _classify_lufs_status(-16.0, -16.0) == "ok"

    def test_差1LUFS以内はok(self) -> None:
        assert _classify_lufs_status(-15.5, -16.0) == "ok"
        assert _classify_lufs_status(-16.8, -16.0) == "ok"
        assert _classify_lufs_status(-17.0, -16.0) == "ok"

    def test_差1から3LUFSはwarn(self) -> None:
        assert _classify_lufs_status(-14.5, -16.0) == "warn"  # 差 1.5
        assert _classify_lufs_status(-19.0, -16.0) == "warn"  # 差 3.0 境界
        assert _classify_lufs_status(-13.0, -16.0) == "warn"  # 差 3.0 境界

    def test_差3LUFS超はbad(self) -> None:
        assert _classify_lufs_status(-12.9, -16.0) == "bad"
        assert _classify_lufs_status(-30.0, -16.0) == "bad"

    def test_Noneと非数は計測不能(self) -> None:
        assert _classify_lufs_status(None, -16.0) == "none"
        assert _classify_lufs_status(float("-inf"), -16.0) == "none"
        assert _classify_lufs_status(float("nan"), -16.0) == "none"

    def test_目標値を変えても相対的に判定できる(self) -> None:
        # 放送基準 -23 LUFS の場合
        assert _classify_lufs_status(-23.0, -23.0) == "ok"
        assert _classify_lufs_status(-25.5, -23.0) == "warn"
        assert _classify_lufs_status(-18.0, -23.0) == "bad"


class TestClassifyPeakStatus:
    """ピーク dBFS の状態分類（クリップ警戒ゾーン）。"""

    def test_マイナス6以下はok(self) -> None:
        assert _classify_peak_status(-20.0) == "ok"
        assert _classify_peak_status(-12.0) == "ok"
        assert _classify_peak_status(-6.01) == "ok"

    def test_マイナス6からマイナス1はwarn(self) -> None:
        assert _classify_peak_status(-6.0) == "warn"  # 境界
        assert _classify_peak_status(-3.0) == "warn"
        assert _classify_peak_status(-1.01) == "warn"

    def test_マイナス1以上はbad_クリップ寸前(self) -> None:
        assert _classify_peak_status(-1.0) == "bad"  # 境界
        assert _classify_peak_status(-0.3) == "bad"
        assert _classify_peak_status(0.0) == "bad"

    def test_Noneと非数は計測不能(self) -> None:
        assert _classify_peak_status(None) == "none"
        assert _classify_peak_status(float("-inf")) == "none"
        assert _classify_peak_status(float("nan")) == "none"
