"""
src/audio_processing.py のテスト。

LUFS 解析・正規化、無音トリム、ノイズ除去、フォーマット変換、チェーン適用の往復検証。
"""
import math
import struct
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from src import audio_processing as ap


SR = 44100


def _write_sine(path: Path, amp: float = 0.3, freq: int = 440, seconds: float = 1.5, sr: int = SR) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    wave = amp * np.sin(2 * np.pi * freq * t)
    sf.write(str(path), wave.astype(np.float32), sr, subtype="PCM_16")


def _write_silence(path: Path, seconds: float = 1.0, sr: int = SR) -> None:
    sf.write(str(path), np.zeros(int(sr * seconds), dtype=np.float32), sr, subtype="PCM_16")


def _write_signal_with_silence_pad(
    path: Path,
    *,
    head_silence_sec: float = 0.5,
    signal_sec: float = 1.0,
    tail_silence_sec: float = 0.3,
    sr: int = SR,
    amp: float = 0.3,
) -> None:
    head = np.zeros(int(sr * head_silence_sec), dtype=np.float32)
    t = np.linspace(0, signal_sec, int(sr * signal_sec), endpoint=False)
    sig = (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    tail = np.zeros(int(sr * tail_silence_sec), dtype=np.float32)
    sf.write(str(path), np.concatenate([head, sig, tail]), sr, subtype="PCM_16")


class TestAnalyzeLoudness:
    def test_サイン波はLUFSが測定できる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sine.wav"
            _write_sine(p, amp=0.3, seconds=2.0)
            info = ap.analyze_loudness(str(p))
            assert info["integrated_lufs"] is not None
            assert math.isfinite(info["integrated_lufs"])
            # 振幅 0.3 のサイン波は概ね -15〜-12 LUFS 付近になる
            assert -30.0 < info["integrated_lufs"] < -5.0
            assert info["peak_dbfs"] is not None
            assert info["peak_dbfs"] < 0.0
            assert info["duration_sec"] > 1.5

    def test_短すぎるサンプルはNone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "short.wav"
            _write_sine(p, seconds=0.2)
            info = ap.analyze_loudness(str(p))
            assert info["integrated_lufs"] is None

    def test_無音はLUFSが出ないかinfinite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "silence.wav"
            _write_silence(p, seconds=1.5)
            info = ap.analyze_loudness(str(p))
            # pyloudnorm は -inf を返すが、我々は None に正規化
            assert info["integrated_lufs"] is None
            assert info["peak_dbfs"] is None

    def test_存在しないファイルでも例外を投げない(self) -> None:
        info = ap.analyze_loudness("/nonexistent/no_such.wav")
        assert info["integrated_lufs"] is None
        assert info["peak_dbfs"] is None


class TestAnalyzeLoudnessSamples:
    """メモリ上サンプルからのリアルタイム LUFS 計算。"""

    def test_サイン波3秒でLUFSが計算できる(self) -> None:
        t = np.linspace(0, 3.0, SR * 3, endpoint=False)
        data = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        info = ap.analyze_loudness_samples(data, SR)
        assert info["integrated_lufs"] is not None
        assert math.isfinite(info["integrated_lufs"])
        assert -30.0 < info["integrated_lufs"] < -5.0
        assert info["peak_dbfs"] is not None
        assert info["duration_sec"] == 3.0

    def test_短すぎるとNone(self) -> None:
        t = np.linspace(0, 0.2, int(SR * 0.2), endpoint=False)
        data = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        info = ap.analyze_loudness_samples(data, SR)
        assert info["integrated_lufs"] is None
        assert info["peak_dbfs"] is not None  # peak は短くても計算できる

    def test_空配列は全てNone(self) -> None:
        info = ap.analyze_loudness_samples(np.array([], dtype=np.float32), SR)
        assert info["integrated_lufs"] is None
        assert info["peak_dbfs"] is None
        assert info["duration_sec"] == 0.0

    def test_int16入力も自動で正規化される(self) -> None:
        t = np.linspace(0, 2.0, SR * 2, endpoint=False)
        data_f = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        data_i = (data_f * 32767).astype(np.int16)
        f_info = ap.analyze_loudness_samples(data_f, SR)
        i_info = ap.analyze_loudness_samples(data_i, SR)
        assert f_info["integrated_lufs"] is not None
        assert i_info["integrated_lufs"] is not None
        # 量子化誤差を許容して 0.5 LUFS 以内
        assert abs(f_info["integrated_lufs"] - i_info["integrated_lufs"]) < 0.5

    def test_無音サンプルはNone(self) -> None:
        data = np.zeros(SR * 2, dtype=np.float32)
        info = ap.analyze_loudness_samples(data, SR)
        assert info["integrated_lufs"] is None
        assert info["peak_dbfs"] is None

    def test_None入力でも例外を投げない(self) -> None:
        info = ap.analyze_loudness_samples(None, SR)
        assert info["integrated_lufs"] is None
        assert info["peak_dbfs"] is None


class TestNormalizeToLufs:
    def test_出力が目標LUFSに近づく(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            _write_sine(src, amp=0.1, seconds=2.0)  # 小さめにして gain up を要求
            result = ap.normalize_to_lufs(str(src), str(out), target_lufs=-16.0)
            assert out.exists()
            assert result["measured_lufs"] is not None
            # 再測定して目標に近いことを確認
            after = ap.analyze_loudness(str(out))
            assert after["integrated_lufs"] is not None
            assert abs(after["integrated_lufs"] - (-16.0)) < 1.5

    def test_短すぎる入力はコピーで許容(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            _write_sine(src, seconds=0.2)
            result = ap.normalize_to_lufs(str(src), str(out), target_lufs=-16.0)
            assert out.exists()
            assert result["applied_gain_db"] == 0.0

    def test_true_peak天井でピーク超過を抑える(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            # 高ゲインを要求する小振幅 → ceiling -1 dBFS 運用
            _write_sine(src, amp=0.05, seconds=2.0)
            ap.normalize_to_lufs(str(src), str(out), target_lufs=-10.0, true_peak_ceiling_dbfs=-1.0)
            data, sr = sf.read(str(out), always_2d=False)
            peak = float(np.max(np.abs(data)))
            # -1 dBFS = 0.891 より大きくならない
            assert peak <= 0.92


class TestTrimSilence:
    def test_先頭末尾の無音が削られる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            _write_signal_with_silence_pad(
                src,
                head_silence_sec=0.5,
                signal_sec=1.0,
                tail_silence_sec=0.3,
            )
            info = ap.trim_silence(str(src), str(out), pad_ms=0)
            before = sf.info(str(src))
            after = sf.info(str(out))
            assert after.duration < before.duration
            assert info["trimmed_head_ms"] > 200
            assert info["trimmed_tail_ms"] > 100
            # 本体 1 秒 + 若干の余裕
            assert after.duration < 1.2

    def test_全体無音はコピー扱い(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            _write_silence(src, seconds=1.0)
            info = ap.trim_silence(str(src), str(out))
            assert out.exists()
            assert info["trimmed_head_ms"] == 0
            assert info["trimmed_tail_ms"] == 0


class TestReduceNoise:
    def test_ノイズ除去後もファイルが生成され長さを維持(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            rng = np.random.default_rng(42)
            # 先頭 0.5s はノイズのみ、残り 1.5s はノイズ + サイン波
            noise = rng.normal(0, 0.02, int(SR * 0.5)).astype(np.float32)
            t = np.linspace(0, 1.5, int(SR * 1.5), endpoint=False)
            tail_noise = rng.normal(0, 0.02, int(SR * 1.5)).astype(np.float32)
            sig = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32) + tail_noise
            data = np.concatenate([noise, sig])
            sf.write(str(src), data, SR, subtype="PCM_16")
            info = ap.reduce_noise(str(src), str(out))
            assert out.exists()
            before = sf.info(str(src))
            after = sf.info(str(out))
            # 長さが大きく変わっていないこと（ほぼ一致）
            assert abs(after.duration - before.duration) < 0.05
            assert info["prop_decrease"] > 0.0


class TestConvertFormat:
    def test_wav出力(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.wav"
            _write_sine(src)
            ap.convert_format(str(src), str(out), fmt="wav")
            assert out.exists()
            info = sf.info(str(out))
            assert info.samplerate == SR

    def test_flac出力(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.flac"
            _write_sine(src)
            ap.convert_format(str(src), str(out), fmt="flac")
            assert out.exists()
            info = sf.info(str(out))
            assert info.format.upper().startswith("FLAC")

    def test_mp3出力は有効なフレームヘッダを持つ(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.mp3"
            _write_sine(src, seconds=0.5)
            ap.convert_format(str(src), str(out), fmt="mp3", mp3_bitrate_kbps=128)
            assert out.exists()
            data = out.read_bytes()
            assert len(data) > 1000
            # MP3 フレーム同期ワード 0xFFE0 以上（ID3 タグもあり得るため頭だけ軽く見る）
            # ID3 で始まる or sync word が含まれる
            assert data[:3] == b"ID3" or any((data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0) for i in range(min(4096, len(data) - 1)))

    def test_未対応フォーマットはValueError(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.ogg"
            _write_sine(src, seconds=0.1)
            try:
                ap.convert_format(str(src), str(out), fmt="ogg")
                assert False, "ValueError 期待"
            except ValueError:
                pass


class TestOutputExtensionFor:
    def test_既知フォーマットの拡張子(self) -> None:
        assert ap.output_extension_for("wav") == ".wav"
        assert ap.output_extension_for("flac") == ".flac"
        assert ap.output_extension_for("mp3") == ".mp3"

    def test_未知や空は_wav(self) -> None:
        assert ap.output_extension_for("") == ".wav"
        assert ap.output_extension_for("xyz") == ".wav"


class TestApplyPostProcessingChain:
    def test_全処理をチェーンしてFLAC出力できる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.flac"
            _write_signal_with_silence_pad(src)
            info = ap.apply_post_processing(
                str(src),
                str(out),
                do_noise_reduce=True,
                do_trim_silence=True,
                do_lufs_normalize=True,
                target_lufs=-16.0,
                fmt="flac",
            )
            assert out.exists()
            assert "noise" in info
            assert "trim" in info
            assert "lufs" in info
            assert info["format"] == "flac"

    def test_処理無効時もフォーマット変換だけは行う(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.wav"
            out = Path(tmp) / "out.mp3"
            _write_sine(src, seconds=0.5)
            ap.apply_post_processing(
                str(src),
                str(out),
                do_noise_reduce=False,
                do_trim_silence=False,
                do_lufs_normalize=False,
                fmt="mp3",
                mp3_bitrate_kbps=128,
            )
            assert out.exists()
            assert out.stat().st_size > 0
