"""
音声処理ヘルパー（LUFS ラウドネス解析、正規化、ノイズ除去、無音トリム、フォーマット変換）。

外部依存:
- pyloudnorm: BS.1770 準拠 LUFS 計測・正規化
- noisereduce: スペクトルサブトラクションによるノイズ低減
- lameenc: MP3 エンコード（ffmpeg 不要）
- soundfile / numpy: WAV/FLAC 入出力と数値処理

本モジュールは I/O を伴うため、すべて "ファイルパス in, ファイルパス out" の関数を基本とする。
UI スレッドでも軽く呼べるよう、例外は極力握りつぶさずに呼び出し側へ投げる。
"""
from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------- LUFS ラウドネス ----------

def analyze_loudness(wav_path: str) -> dict:
    """
    WAV/FLAC を読み込み、BS.1770 準拠の統合ラウドネス（integrated LUFS）と True Peak 近似を返す。

    戻り値のキー:
      ``integrated_lufs`` (float | None), ``peak_dbfs`` (float | None), ``duration_sec`` (float)

    - 音が短すぎる（<=0.4 秒）場合は integrated_lufs は None。
    - 無音 / 読み込み失敗時も安全値（None / 0.0）を返す。例外は投げない。
    """
    try:
        import numpy as np
        import soundfile as sf
        import pyloudnorm as pyln
    except ImportError:
        return {"integrated_lufs": None, "peak_dbfs": None, "duration_sec": 0.0}

    try:
        data, sr = sf.read(str(wav_path), always_2d=False)
    except Exception as e:  # noqa: BLE001
        logger.debug("analyze_loudness: read failed: %s", e)
        return {"integrated_lufs": None, "peak_dbfs": None, "duration_sec": 0.0}

    if data.size == 0:
        return {"integrated_lufs": None, "peak_dbfs": None, "duration_sec": 0.0}

    duration = float(len(data)) / float(sr) if sr > 0 else 0.0
    # ピーク dBFS 計算（モノラル/マルチ共通）
    if data.ndim > 1:
        peak_val = float(np.max(np.abs(data)))
    else:
        peak_val = float(np.max(np.abs(data)))
    peak_dbfs = 20.0 * math.log10(peak_val) if peak_val > 0 else None

    if duration < 0.4:
        return {"integrated_lufs": None, "peak_dbfs": peak_dbfs, "duration_sec": duration}

    try:
        meter = pyln.Meter(sr)
        lufs = float(meter.integrated_loudness(data))
        if not math.isfinite(lufs):
            lufs = None
    except Exception as e:  # noqa: BLE001
        logger.debug("analyze_loudness: pyloudnorm failed: %s", e)
        lufs = None

    return {"integrated_lufs": lufs, "peak_dbfs": peak_dbfs, "duration_sec": duration}


def analyze_loudness_samples(
    samples,
    sample_rate: int,
) -> dict:
    """
    メモリ上のサンプル配列に対して BS.1770 LUFS と Peak dBFS を計算する。

    リアルタイム表示（直近数秒のバッファを渡す）向け。
    入力は ``numpy.ndarray`` の float/int 系サンプル（モノラル 1D か (N,C) 2D）。
    - 400ms 未満や無音の場合は ``integrated_lufs`` を None にする。
    - 例外は投げず、失敗時は安全値を返す。
    """
    try:
        import numpy as np
    except ImportError:
        return {"integrated_lufs": None, "peak_dbfs": None, "duration_sec": 0.0}

    if samples is None:
        return {"integrated_lufs": None, "peak_dbfs": None, "duration_sec": 0.0}
    data = np.asarray(samples)
    if data.size == 0 or sample_rate <= 0:
        return {"integrated_lufs": None, "peak_dbfs": None, "duration_sec": 0.0}

    # int 系は正規化、float はそのまま（想定: float32 モノラル [-1, 1]）
    if data.dtype.kind in ("i", "u"):
        info = np.iinfo(data.dtype)
        denom = max(abs(info.min), info.max) or 1
        data = data.astype(np.float32) / float(denom)
    else:
        data = data.astype(np.float32, copy=False)

    duration = float(len(data)) / float(sample_rate)
    peak_val = float(np.max(np.abs(data))) if data.size else 0.0
    peak_dbfs = 20.0 * math.log10(peak_val) if peak_val > 0 else None

    if duration < 0.4:
        return {"integrated_lufs": None, "peak_dbfs": peak_dbfs, "duration_sec": duration}

    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sample_rate)
        lufs = float(meter.integrated_loudness(data))
        if not math.isfinite(lufs):
            lufs = None
    except Exception as e:  # noqa: BLE001
        logger.debug("analyze_loudness_samples: pyloudnorm failed: %s", e)
        lufs = None

    return {"integrated_lufs": lufs, "peak_dbfs": peak_dbfs, "duration_sec": duration}


def normalize_to_lufs(
    in_path: str,
    out_path: str,
    target_lufs: float = -16.0,
    *,
    true_peak_ceiling_dbfs: float = -1.0,
) -> dict:
    """
    入力音声を target_lufs（既定 -16 LUFS：Spotify/YouTube 相当）に合わせて正規化し、out_path に書き出す。

    - ゲインを上げ過ぎてピークが ``true_peak_ceiling_dbfs`` を超える場合は、超過分をピークで抑える（簡易リミット）。
    - 元ファイルが短すぎる/無音/読み込み失敗時はコピーにフォールバック。
    - 出力はモノラル/マルチチャンネルを維持し、WAV/FLAC として soundfile で書き出す。

    戻り値: ``{"applied_gain_db": float, "measured_lufs": float | None, "target_lufs": float}``
    """
    try:
        import numpy as np
        import soundfile as sf
        import pyloudnorm as pyln
    except ImportError:
        shutil.copy2(in_path, out_path)
        return {"applied_gain_db": 0.0, "measured_lufs": None, "target_lufs": target_lufs}

    try:
        data, sr = sf.read(str(in_path), always_2d=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("normalize_to_lufs: read failed: %s", e)
        shutil.copy2(in_path, out_path)
        return {"applied_gain_db": 0.0, "measured_lufs": None, "target_lufs": target_lufs}

    if data.size == 0:
        shutil.copy2(in_path, out_path)
        return {"applied_gain_db": 0.0, "measured_lufs": None, "target_lufs": target_lufs}

    duration = float(len(data)) / float(sr) if sr > 0 else 0.0
    if duration < 0.4:
        shutil.copy2(in_path, out_path)
        return {"applied_gain_db": 0.0, "measured_lufs": None, "target_lufs": target_lufs}

    meter = pyln.Meter(sr)
    try:
        measured = float(meter.integrated_loudness(data))
    except Exception as e:  # noqa: BLE001
        logger.warning("normalize_to_lufs: measure failed: %s", e)
        shutil.copy2(in_path, out_path)
        return {"applied_gain_db": 0.0, "measured_lufs": None, "target_lufs": target_lufs}

    if not math.isfinite(measured):
        # 完全な無音
        shutil.copy2(in_path, out_path)
        return {"applied_gain_db": 0.0, "measured_lufs": None, "target_lufs": target_lufs}

    gain_db = float(target_lufs) - measured
    gain_linear = 10.0 ** (gain_db / 20.0)
    out = (data.astype(np.float64) * gain_linear).astype(np.float32)

    # 簡易 True Peak 天井：ピークが ceiling を超えたら線形に縮める
    ceiling_linear = 10.0 ** (true_peak_ceiling_dbfs / 20.0)
    peak_after = float(np.max(np.abs(out))) if out.size > 0 else 0.0
    if peak_after > ceiling_linear and peak_after > 0:
        scale = ceiling_linear / peak_after
        out = (out * scale).astype(np.float32)
        gain_db += 20.0 * math.log10(scale)

    # ファイル形式は出力拡張子に合わせる（sf.write が自動判定）。
    # ただし PCM WAV では float32 を受け付けないので、WAV は 16bit PCM に変換する。
    out_ext = Path(out_path).suffix.lower()
    if out_ext in (".wav", ".wave"):
        clipped = np.clip(out, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        sf.write(str(out_path), pcm16, sr, subtype="PCM_16")
    else:
        sf.write(str(out_path), out, sr)

    return {"applied_gain_db": gain_db, "measured_lufs": measured, "target_lufs": target_lufs}


# ---------- 無音トリム ----------

def trim_silence(
    in_path: str,
    out_path: str,
    *,
    threshold_dbfs: float = -45.0,
    pad_ms: int = 80,
) -> dict:
    """
    先頭/末尾の無音を削除する。``threshold_dbfs`` より小さい絶対振幅を無音と見做す。

    - ``pad_ms`` は検出した音声前後に残す余白（ミリ秒）。0 なら完全にカット。
    - 全体が無音なら入力をそのままコピー。
    - 戻り値: ``{"trimmed_head_ms": int, "trimmed_tail_ms": int, "result_duration_sec": float}``
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        shutil.copy2(in_path, out_path)
        return {"trimmed_head_ms": 0, "trimmed_tail_ms": 0, "result_duration_sec": 0.0}

    try:
        data, sr = sf.read(str(in_path), always_2d=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("trim_silence: read failed: %s", e)
        shutil.copy2(in_path, out_path)
        return {"trimmed_head_ms": 0, "trimmed_tail_ms": 0, "result_duration_sec": 0.0}

    if data.size == 0:
        shutil.copy2(in_path, out_path)
        return {"trimmed_head_ms": 0, "trimmed_tail_ms": 0, "result_duration_sec": 0.0}

    if data.ndim > 1:
        amp = np.max(np.abs(data), axis=1)
    else:
        amp = np.abs(data)

    threshold = 10.0 ** (threshold_dbfs / 20.0)
    voiced = np.where(amp > threshold)[0]
    orig_len = len(data)
    orig_duration = float(orig_len) / float(sr) if sr > 0 else 0.0

    if voiced.size == 0:
        shutil.copy2(in_path, out_path)
        return {
            "trimmed_head_ms": 0,
            "trimmed_tail_ms": 0,
            "result_duration_sec": orig_duration,
        }

    pad_samples = max(0, int(sr * pad_ms / 1000))
    start = max(0, int(voiced[0]) - pad_samples)
    end = min(orig_len, int(voiced[-1]) + 1 + pad_samples)
    trimmed = data[start:end]

    out_ext = Path(out_path).suffix.lower()
    if out_ext in (".wav", ".wave"):
        if trimmed.dtype.kind == "f":
            clipped = np.clip(trimmed, -1.0, 1.0)
            pcm16 = (clipped * 32767.0).astype(np.int16)
            sf.write(str(out_path), pcm16, sr, subtype="PCM_16")
        else:
            sf.write(str(out_path), trimmed, sr)
    else:
        sf.write(str(out_path), trimmed, sr)

    trimmed_head_ms = int(start * 1000 / sr) if sr > 0 else 0
    trimmed_tail_ms = int((orig_len - end) * 1000 / sr) if sr > 0 else 0
    result_duration = float(len(trimmed)) / float(sr) if sr > 0 else 0.0
    return {
        "trimmed_head_ms": trimmed_head_ms,
        "trimmed_tail_ms": trimmed_tail_ms,
        "result_duration_sec": result_duration,
    }


# ---------- ノイズ除去 ----------

def reduce_noise(
    in_path: str,
    out_path: str,
    *,
    noise_profile_seconds: float = 0.5,
    prop_decrease: float = 0.85,
) -> dict:
    """
    先頭 ``noise_profile_seconds`` 秒をノイズプロファイルとみなし、noisereduce でノイズ低減する。

    - ``prop_decrease`` は 0〜1。大きいほど強くノイズを削るが声も痩せる。既定 0.85。
    - 短すぎる/読み込み失敗時は入力をそのままコピー。
    - 戻り値: ``{"prop_decrease": float, "used_noise_seconds": float}``
    """
    try:
        import numpy as np
        import soundfile as sf
        import noisereduce as nr
    except ImportError:
        shutil.copy2(in_path, out_path)
        return {"prop_decrease": 0.0, "used_noise_seconds": 0.0}

    try:
        data, sr = sf.read(str(in_path), always_2d=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("reduce_noise: read failed: %s", e)
        shutil.copy2(in_path, out_path)
        return {"prop_decrease": 0.0, "used_noise_seconds": 0.0}

    if data.size == 0 or sr <= 0:
        shutil.copy2(in_path, out_path)
        return {"prop_decrease": 0.0, "used_noise_seconds": 0.0}

    # マルチチャンネルはチャンネル毎に処理する
    noise_samples = int(max(0.1, noise_profile_seconds) * sr)
    used_seconds = min(noise_profile_seconds, float(len(data)) / float(sr))

    def _reduce_channel(channel: "np.ndarray") -> "np.ndarray":
        n = min(noise_samples, len(channel))
        y = channel.astype(np.float32, copy=False)
        if n <= 128:
            # プロファイル取得に足りるサンプルが無い: 非定常モードで処理
            try:
                return nr.reduce_noise(
                    y=y, sr=sr, prop_decrease=prop_decrease, stationary=False
                ).astype(np.float32)
            except Exception as e:  # noqa: BLE001
                logger.debug("reduce_noise: non-stationary failed: %s", e)
                return y
        noise_clip = y[:n]
        try:
            return nr.reduce_noise(
                y=y,
                sr=sr,
                y_noise=noise_clip,
                prop_decrease=prop_decrease,
                stationary=True,
            ).astype(np.float32)
        except Exception as e:  # noqa: BLE001
            logger.debug("reduce_noise: stationary failed: %s", e)
            return y

    if data.ndim == 1:
        out = _reduce_channel(data)
    else:
        out = np.stack([_reduce_channel(data[:, ch]) for ch in range(data.shape[1])], axis=1)

    out_ext = Path(out_path).suffix.lower()
    if out_ext in (".wav", ".wave"):
        clipped = np.clip(out, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        sf.write(str(out_path), pcm16, sr, subtype="PCM_16")
    else:
        sf.write(str(out_path), out, sr)

    return {"prop_decrease": float(prop_decrease), "used_noise_seconds": float(used_seconds)}


# ---------- フォーマット変換 ----------

# 対応している出力フォーマット
SUPPORTED_EXPORT_FORMATS = ("wav", "flac", "mp3")

# MP3 ビットレート（kbps）の選択肢
MP3_BITRATES = (128, 192, 256, 320)


def convert_format(
    in_path: str,
    out_path: str,
    *,
    fmt: str = "wav",
    mp3_bitrate_kbps: int = 192,
) -> None:
    """
    入力音声を ``fmt`` (wav/flac/mp3) に変換して ``out_path`` に書き出す。

    - wav/flac は soundfile で処理。
    - mp3 は lameenc で CBR エンコード。モノラル/ステレオのみ対応。
    - ``out_path`` の拡張子は呼び出し側で付与する前提（本関数は fmt を優先）。

    失敗時は例外をそのまま上げる。
    """
    fmt = (fmt or "wav").lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"未対応のフォーマット: {fmt}")

    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        raise RuntimeError("soundfile/numpy が利用できません") from e

    data, sr = sf.read(str(in_path), always_2d=False)
    if data.size == 0:
        # 空 WAV を出す（MP3 は作らない方が安全なのでエラー扱いしない）
        if fmt == "mp3":
            raise RuntimeError("空の音声は MP3 に変換できません")
        sf.write(str(out_path), data, sr)
        return

    if fmt == "wav":
        # 16bit PCM で統一
        if data.dtype.kind == "f":
            clipped = np.clip(data, -1.0, 1.0)
            pcm16 = (clipped * 32767.0).astype(np.int16)
            sf.write(str(out_path), pcm16, sr, subtype="PCM_16")
        else:
            sf.write(str(out_path), data, sr, subtype="PCM_16")
        return

    if fmt == "flac":
        # FLAC は整数 PCM 推奨。float を PCM_16 に寄せる。
        if data.dtype.kind == "f":
            clipped = np.clip(data, -1.0, 1.0)
            pcm16 = (clipped * 32767.0).astype(np.int16)
            sf.write(str(out_path), pcm16, sr, format="FLAC", subtype="PCM_16")
        else:
            sf.write(str(out_path), data, sr, format="FLAC")
        return

    # mp3
    try:
        import lameenc
    except ImportError as e:
        raise RuntimeError("MP3 エンコードには lameenc が必要です") from e

    if data.ndim == 1:
        channels = 1
        pcm = data
    else:
        channels = int(data.shape[1])
        if channels > 2:
            # MP3 はステレオまで。余分チャンネルは先頭 2ch に丸める。
            pcm = data[:, :2]
            channels = 2
        else:
            pcm = data

    if pcm.dtype.kind == "f":
        pcm = np.clip(pcm, -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16)
    elif pcm.dtype == np.int16:
        pcm16 = pcm
    else:
        pcm16 = pcm.astype(np.int16)

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(int(mp3_bitrate_kbps))
    encoder.set_in_sample_rate(int(sr))
    encoder.set_channels(channels)
    encoder.set_quality(2)  # 2: high quality (slow-ish). 0=best slowest, 9=worst fastest

    raw = pcm16.tobytes()
    mp3_data = encoder.encode(raw)
    mp3_data += encoder.flush()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(mp3_data)


def output_extension_for(fmt: str) -> str:
    """フォーマット名から拡張子（.wav/.flac/.mp3）を返す。不明は .wav。"""
    fmt = (fmt or "wav").lower()
    if fmt == "flac":
        return ".flac"
    if fmt == "mp3":
        return ".mp3"
    return ".wav"


# ---------- 後処理チェーン ----------

def apply_post_processing(
    in_path: str,
    out_path: str,
    *,
    do_noise_reduce: bool = False,
    do_trim_silence: bool = False,
    do_lufs_normalize: bool = False,
    target_lufs: float = -16.0,
    fmt: str = "wav",
    mp3_bitrate_kbps: int = 192,
    trim_threshold_dbfs: float = -45.0,
    trim_pad_ms: int = 80,
    noise_prop_decrease: float = 0.85,
) -> dict:
    """
    ``in_path`` に対し ノイズ除去 → 無音トリム → LUFS 正規化 → フォーマット変換 の順に適用し、
    ``out_path`` に最終ファイルを書き出す。

    チェーン中の中間ファイルは一時ディレクトリに置かれる。
    戻り値は各処理の結果辞書をまとめたもの。
    """
    import tempfile

    info: dict = {}
    with tempfile.TemporaryDirectory(prefix="valab_proc_") as tmpdir:
        current = Path(in_path)

        if do_noise_reduce:
            nxt = Path(tmpdir) / "after_nr.wav"
            info["noise"] = reduce_noise(str(current), str(nxt))
            current = nxt

        if do_trim_silence:
            nxt = Path(tmpdir) / "after_trim.wav"
            info["trim"] = trim_silence(
                str(current),
                str(nxt),
                threshold_dbfs=trim_threshold_dbfs,
                pad_ms=trim_pad_ms,
            )
            current = nxt

        if do_lufs_normalize:
            nxt = Path(tmpdir) / "after_lufs.wav"
            info["lufs"] = normalize_to_lufs(
                str(current), str(nxt), target_lufs=target_lufs
            )
            current = nxt

        # 最終フォーマット変換（未処理でもフォーマット変換だけは行う）
        convert_format(
            str(current),
            str(out_path),
            fmt=fmt,
            mp3_bitrate_kbps=mp3_bitrate_kbps,
        )
        info["format"] = fmt

    return info


__all__ = [
    "analyze_loudness",
    "normalize_to_lufs",
    "trim_silence",
    "reduce_noise",
    "convert_format",
    "apply_post_processing",
    "output_extension_for",
    "SUPPORTED_EXPORT_FORMATS",
    "MP3_BITRATES",
]
