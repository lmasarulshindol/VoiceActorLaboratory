"""音声ファイルの読込・チャンネル変換・リサンプル。

WAV/FLAC/OGG は soundfile で読む。
MP3 等で soundfile が失敗した場合は ffmpeg（あれば）で pcm_f32le にデコードする。
ピーク正規化は行わない（音量制御はミキサー側の責務）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Union

import numpy as np

PathLike = Union[str, Path]


class SampleLoaderError(Exception):
    """音声読込に失敗したとき。"""


def _linear_resample(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """単純な線形補間でリサンプルする。

    Args:
        data: shape (N,) または (N, C)
        src_sr: 元サンプルレート
        dst_sr: 目標サンプルレート
    """
    if src_sr == dst_sr or data.size == 0:
        return data.astype(np.float32, copy=False)

    n_src = data.shape[0]
    if n_src == 1:
        n_dst = max(1, int(round(n_src * dst_sr / src_sr)))
        if data.ndim == 1:
            return np.full(n_dst, data[0], dtype=np.float32)
        return np.repeat(data.astype(np.float32), n_dst, axis=0)

    n_dst = max(1, int(round(n_src * dst_sr / src_sr)))
    x_src = np.linspace(0.0, 1.0, n_src, dtype=np.float64)
    x_dst = np.linspace(0.0, 1.0, n_dst, dtype=np.float64)

    if data.ndim == 1:
        out = np.interp(x_dst, x_src, data.astype(np.float64)).astype(np.float32)
        return out

    channels = data.shape[1]
    out = np.empty((n_dst, channels), dtype=np.float32)
    src = data.astype(np.float64, copy=False)
    for c in range(channels):
        out[:, c] = np.interp(x_dst, x_src, src[:, c]).astype(np.float32)
    return out


def _convert_channels(data: np.ndarray, target_channels: int) -> np.ndarray:
    """チャンネル数を変換する（ピーク正規化なし）。"""
    if target_channels < 1:
        raise SampleLoaderError(f"target_channels は 1 以上である必要があります: {target_channels}")

    if data.ndim == 1:
        # (N,) → モノラル扱い
        if target_channels == 1:
            return data.astype(np.float32, copy=False)
        # モノラルを複製してマルチチャンネルへ
        return np.column_stack([data.astype(np.float32)] * target_channels)

    # (N, C)
    src_ch = data.shape[1]
    if src_ch == target_channels:
        return data.astype(np.float32, copy=False)

    if target_channels == 1:
        # ステレオ等 → モノラル（単純平均）
        return np.mean(data.astype(np.float64), axis=1).astype(np.float32)

    if src_ch == 1:
        mono = data[:, 0]
        return np.column_stack([mono.astype(np.float32)] * target_channels)

    # チャンネル数が違う場合: 足りなければ最後を複製、多ければ切り詰め
    if src_ch > target_channels:
        return data[:, :target_channels].astype(np.float32, copy=False)

    pad = np.column_stack(
        [data[:, -1].astype(np.float32)] * (target_channels - src_ch)
    )
    return np.column_stack([data.astype(np.float32), pad])


def _load_with_soundfile(path: Path) -> tuple[np.ndarray, int]:
    """soundfile で読み込む。失敗時は例外を再送出。"""
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return np.asarray(data, dtype=np.float32), int(sr)


def _load_with_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    """ffmpeg で pcm_f32le raw にデコードして読む。

    ステレオ想定でデコードし、後段でチャンネル変換する。
    サンプルレートはファイルから ffprobe 相当で取るのが理想だが、
    ここでは ffmpeg に -ar を付けず元レート維持し、チャンネルは 2 固定で読む。
    実際の sr/channels は ffprobe で取得する。
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SampleLoaderError(
            f"音声のデコードに失敗しました（soundfile 非対応）。"
            f" ffmpeg が見つかりません: {path}"
        )

    ffprobe = shutil.which("ffprobe")
    sample_rate = 48000
    channels = 2

    if ffprobe:
        try:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=sample_rate,channels",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            lines = [ln.strip() for ln in probe.stdout.splitlines() if ln.strip()]
            if len(lines) >= 2:
                sample_rate = int(float(lines[0]))
                channels = int(lines[1])
            elif len(lines) == 1:
                # 片方だけ取れた場合
                try:
                    sample_rate = int(float(lines[0]))
                except ValueError:
                    channels = int(lines[0])
        except Exception:
            pass

    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise SampleLoaderError(f"ffmpeg の実行に失敗しました: {exc}") from exc

    if result.returncode != 0 or not result.stdout:
        err = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        raise SampleLoaderError(
            f"ffmpeg でのデコードに失敗しました: {path}\n{err}".strip()
        )

    raw = np.frombuffer(result.stdout, dtype=np.float32)
    if channels > 1:
        if raw.size % channels != 0:
            raw = raw[: raw.size - (raw.size % channels)]
        data = raw.reshape(-1, channels)
    else:
        data = raw

    return data.astype(np.float32, copy=False), sample_rate


def load_audio(
    path: PathLike,
    target_sr: int = 48000,
    target_channels: int = 1,
) -> np.ndarray:
    """音声ファイルを読み込み、目標レート・チャンネルに変換する。

    Args:
        path: 音声ファイルパス
        target_sr: 目標サンプルレート（Hz）
        target_channels: 目標チャンネル数（1=モノラル）

    Returns:
        float32 の ndarray。モノラルは shape (N,)、それ以外は (N, C)。

    Raises:
        SampleLoaderError: ファイルが無い、またはデコード不能な場合。
    """
    p = Path(path)
    if not p.exists():
        raise SampleLoaderError(f"ファイルが見つかりません: {p}")
    if not p.is_file():
        raise SampleLoaderError(f"ファイルではありません: {p}")

    if target_sr < 1:
        raise SampleLoaderError(f"target_sr は 1 以上である必要があります: {target_sr}")

    data: np.ndarray | None = None
    sr: int | None = None

    try:
        data, sr = _load_with_soundfile(p)
    except ImportError as exc:
        raise SampleLoaderError(
            "soundfile がインストールされていません。"
            " pip install soundfile を実行してください。"
        ) from exc
    except Exception:
        # soundfile 失敗 → ffmpeg フォールバック
        try:
            data, sr = _load_with_ffmpeg(p)
        except SampleLoaderError:
            raise
        except Exception as exc:
            raise SampleLoaderError(
                f"音声の読込に失敗しました（soundfile / ffmpeg）: {p}\n{exc}"
            ) from exc

    assert data is not None and sr is not None

    data = _convert_channels(data, target_channels)
    data = _linear_resample(data, sr, target_sr)

    # モノラルは (N,)、マルチは (N, C) を保証
    if target_channels == 1 and data.ndim == 2 and data.shape[1] == 1:
        data = data[:, 0]

    return np.asarray(data, dtype=np.float32)
