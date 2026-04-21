"""
プロジェクトの保存・読み込み・エクスポート。
1プロジェクト = 1フォルダ（台本テキスト + takes/ に WAV + メタ JSON）。
"""
import json
import logging

logger = logging.getLogger(__name__)
import uuid
from pathlib import Path
from datetime import datetime
import shutil

from src.project import Project, TakeInfo
from src.script_format import sanitize_for_filename

SCRIPT_FILENAME = "script.txt"
SCRIPT_FILENAME_MD = "script.md"
_SCRIPT_FILENAMES = (SCRIPT_FILENAME_MD, SCRIPT_FILENAME)

# 台本読み込みで試すエンコーディングの順（BOM付きUTF-8 → UTF-8 → CP932）
_SCRIPT_ENCODINGS = ("utf-8-sig", "utf-8", "cp932")


def decode_script_bytes(data: bytes) -> str:
    """
    バイト列を台本テキストとしてデコードする。
    UTF-8 → UTF-8(BOM) → CP932 の順で試し、最初に成功したものを返す。
    すべて失敗した場合は UTF-8 でデコードを試み、例外をそのまま上げる。
    """
    last_error: Exception | None = None
    for enc in _SCRIPT_ENCODINGS:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError) as e:
            last_error = e
            continue
    if last_error is not None:
        raise last_error
    return data.decode("utf-8")
META_FILENAME = "project_meta.json"
TAKES_DIR = "takes"


def get_takes_dir(project_dir: str) -> str:
    """プロジェクト内の takes/ フォルダの絶対パスを返す（未作成でもパスを返す）。"""
    return str(Path(project_dir) / TAKES_DIR)


def reveal_in_file_manager(target_path: str) -> bool:
    """
    OS のファイルマネージャでパスを表示する。
    - ファイルパスを渡した場合: Windows は explorer /select,<file>、macOS は open -R、
      Linux は親ディレクトリを xdg-open で開く。
    - ディレクトリパスを渡した場合: そのまま開く。
    戻り値は成功したかどうか。
    """
    import os
    import subprocess
    import sys

    if not target_path:
        return False
    path = Path(target_path)
    if not path.exists():
        # ファイルが消えていた場合は親フォルダで代替
        if path.parent.exists():
            path = path.parent
        else:
            return False

    try:
        if sys.platform.startswith("win"):
            if path.is_dir():
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                # /select, と対象ファイルはカンマ直後（空白なし）に続ける
                subprocess.Popen(
                    ["explorer", f"/select,{str(path)}"],
                    close_fds=True,
                )
            return True
        if sys.platform == "darwin":
            if path.is_dir():
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["open", "-R", str(path)])
            return True
        # Linux / その他 POSIX
        target = path if path.is_dir() else path.parent
        subprocess.Popen(["xdg-open", str(target)])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("reveal_in_file_manager failed: %s", e)
        return False


def create_project(project_dir: str) -> Project:
    """
    新規プロジェクトフォルダを作成し、空の Project を返す。
    既存の場合は上書きしない（フォルダが存在すればそのまま読み込みに委譲はしない。呼び出し側で分岐すること）。
    """
    path = Path(project_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / TAKES_DIR).mkdir(exist_ok=True)
    proj = Project(project_dir=project_dir)
    _save_meta(project_dir, proj)
    return proj


def find_script_file(project_dir: str) -> Path | None:
    """プロジェクトフォルダ内の台本ファイルを探す。.md を優先し、なければ .txt を返す。"""
    path = Path(project_dir)
    for name in _SCRIPT_FILENAMES:
        f = path / name
        if f.exists():
            return f
    return None


def load_project(project_dir: str) -> Project | None:
    """
    プロジェクトフォルダから Project を読み込む。
    フォルダや script がなければ None を返す。
    """
    path = Path(project_dir)
    if not path.is_dir():
        return None
    script_file = find_script_file(project_dir)
    if script_file is None:
        script_file = path / SCRIPT_FILENAME
    script_text = ""
    if script_file.exists():
        script_text = decode_script_bytes(script_file.read_bytes())
    meta = _load_meta(project_dir)
    takes = []
    if meta and "takes" in meta:
        for t in meta["takes"]:
            raw_tags = t.get("tags", [])
            tags = [str(x) for x in raw_tags] if isinstance(raw_tags, list) else []
            peak = t.get("peak_dbfs")
            try:
                peak_value = float(peak) if peak is not None else None
            except (TypeError, ValueError):
                peak_value = None
            lufs_raw = t.get("integrated_lufs")
            try:
                lufs_value = float(lufs_raw) if lufs_raw is not None else None
            except (TypeError, ValueError):
                lufs_value = None
            takes.append(
                TakeInfo(
                    id=t.get("id", ""),
                    wav_filename=t.get("wav_filename", ""),
                    memo=t.get("memo", ""),
                    favorite=t.get("favorite", False),
                    created_at=t.get("created_at", ""),
                    adopted=t.get("adopted", False),
                    script_line_number=t.get("script_line_number"),
                    script_line_text=t.get("script_line_text", ""),
                    rating=int(t.get("rating", 0) or 0),
                    tags=tags,
                    has_clipping=bool(t.get("has_clipping", False)),
                    peak_dbfs=peak_value,
                    integrated_lufs=lufs_value,
                )
            )
    # script が無い場合は script_path を空にして不整合を防ぐ
    script_path = str(script_file) if (script_file and script_file.exists()) else ""
    return Project(
        script_path=script_path,
        script_text=script_text,
        takes=takes,
        project_dir=project_dir,
    )


def save_script(project_dir: str, text: str, *, use_md: bool | None = None) -> None:
    """台本テキストを保存する。既存ファイルの拡張子を維持し、なければ use_md に従う（デフォルトは .md）。
    フォルダを新規作成した場合は takes/ と project_meta も用意し、後続の add_take と不整合にならないようにする。"""
    path = Path(project_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / TAKES_DIR).mkdir(exist_ok=True)
    if not _meta_path(project_dir).exists():
        _save_meta(project_dir, Project(project_dir=project_dir))
    existing = find_script_file(project_dir)
    if existing is not None:
        existing.write_text(text, encoding="utf-8")
    else:
        filename = SCRIPT_FILENAME_MD if (use_md is None or use_md) else SCRIPT_FILENAME
        (path / filename).write_text(text, encoding="utf-8")


def add_take_from_file(
    project_dir: str,
    wav_path: str,
    memo: str = "",
    favorite: bool = False,
    preferred_basename: str | None = None,
    script_line_number: int | None = None,
    script_line_text: str = "",
) -> TakeInfo:
    """
    既存の WAV ファイルをプロジェクトの takes/ にコピーし、メタを追加して TakeInfo を返す。
    wav_path は録音結果の一時パス。
    preferred_basename を渡すと、ファイル名を「preferred_basename.wav」形式にする（台本から取得した名前など）。
    """
    path = Path(project_dir)
    takes_dir = path / TAKES_DIR
    takes_dir.mkdir(parents=True, exist_ok=True)
    take_id = str(uuid.uuid4())
    if preferred_basename:
        safe = sanitize_for_filename(preferred_basename, max_length=120)
        dest_name = f"{safe}.wav" if safe else f"{take_id}.wav"
        if (takes_dir / dest_name).exists():
            dest_name = f"{safe}_{take_id[:8]}.wav"
    else:
        base = Path(wav_path).name
        if not base.lower().endswith(".wav"):
            base = f"{base}.wav"
        dest_name = f"{take_id}_{base}"
    dest_path = takes_dir / dest_name
    shutil.copy2(wav_path, dest_path)
    created_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    take = TakeInfo(
        id=take_id,
        wav_filename=dest_name,
        memo=memo,
        favorite=favorite,
        created_at=created_at,
        adopted=False,
        script_line_number=script_line_number,
        script_line_text=script_line_text,
    )
    proj = load_project(project_dir)
    if proj is None:
        proj = Project(project_dir=project_dir)
    proj.add_take(take)
    _save_meta(project_dir, proj)
    return take


def update_take_meta(
    project_dir: str,
    take_id: str,
    memo: str | None = None,
    favorite: bool | None = None,
    adopted: bool | None = None,
    rating: int | None = None,
    tags: list[str] | None = None,
    has_clipping: bool | None = None,
    peak_dbfs: float | None = None,
    integrated_lufs: float | None = None,
    wav_filename: str | None = None,
) -> bool:
    """テイクのメタ（メモ・お気に入り・採用・★・タグ・クリップ情報）を JSON に反映する。

    ``adopted=True`` のとき他はすべて False。``rating`` は 0〜5 に丸められる。
    ``tags`` は空白トリムと重複除去を行う。``peak_dbfs`` は None または数値。
    """
    proj = load_project(project_dir)
    if proj is None:
        return False
    t = proj.get_take(take_id)
    if t is None:
        return False
    if memo is not None:
        t.memo = memo
    if favorite is not None:
        t.favorite = favorite
    if adopted is not None:
        proj.update_take_adopted(take_id, adopted)
    if rating is not None:
        proj.update_take_rating(take_id, rating)
    if tags is not None:
        proj.update_take_tags(take_id, tags)
    if has_clipping is not None:
        t.has_clipping = bool(has_clipping)
    if peak_dbfs is not None:
        try:
            t.peak_dbfs = float(peak_dbfs)
        except (TypeError, ValueError):
            pass
    if integrated_lufs is not None:
        try:
            t.integrated_lufs = float(integrated_lufs)
        except (TypeError, ValueError):
            pass
    if wav_filename is not None:
        t.wav_filename = str(wav_filename)
    _save_meta(project_dir, proj)
    return True


def update_takes_meta_bulk(
    project_dir: str,
    take_ids: list[str],
    *,
    favorite: bool | None = None,
    rating: int | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    clear_adopted: bool = False,
) -> int:
    """複数テイクに一括でメタ変更を適用する。成功件数を返す。

    ``add_tags`` は既存タグに追加（重複は無視）、``remove_tags`` は削除する。
    ``clear_adopted`` は採用フラグの解除（採用付与はプロジェクト内で単一のため一括では扱わない）。
    """
    proj = load_project(project_dir)
    if proj is None:
        return 0
    ok = 0
    for take_id in take_ids:
        t = proj.get_take(take_id)
        if t is None:
            continue
        if favorite is not None:
            t.favorite = bool(favorite)
        if rating is not None:
            t.rating = max(0, min(5, int(rating)))
        if add_tags:
            new_tags = list(t.tags)
            for tag in add_tags:
                s = str(tag).strip()
                if s and s not in new_tags:
                    new_tags.append(s)
            t.tags = new_tags
        if remove_tags:
            t.tags = [tag for tag in t.tags if tag not in remove_tags]
        if clear_adopted and t.adopted:
            t.adopted = False
        ok += 1
    _save_meta(project_dir, proj)
    return ok


def analyze_wav_clipping(wav_path: str, threshold_ratio: float = 0.995) -> dict:
    """WAV ファイルを読み、クリッピング情報を返す。

    戻り値: ``{"has_clipping": bool, "peak_dbfs": float | None, "clipped_samples": int}``。
    読み込み失敗時は全て安全側（False / None / 0）を返す。
    """
    import math
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return {"has_clipping": False, "peak_dbfs": None, "clipped_samples": 0}
    try:
        data, _sr = sf.read(str(wav_path), always_2d=False)
    except Exception:
        return {"has_clipping": False, "peak_dbfs": None, "clipped_samples": 0}
    if data.size == 0:
        return {"has_clipping": False, "peak_dbfs": None, "clipped_samples": 0}
    if data.ndim > 1:
        mono = np.max(np.abs(data), axis=1)
    else:
        mono = np.abs(data)
    peak = float(np.max(mono))
    clipped = int(np.sum(mono >= threshold_ratio))
    if peak > 0:
        peak_dbfs = 20.0 * math.log10(peak)
    else:
        peak_dbfs = None
    return {
        "has_clipping": clipped >= 3,  # 単発の瞬間ピークは許容し 3 サンプル以上で判定
        "peak_dbfs": peak_dbfs,
        "clipped_samples": clipped,
    }


def get_take_wav_path(project_dir: str, wav_filename: str) -> str:
    """takes/ 内の WAV の絶対パスを返す。"""
    return str(Path(project_dir) / TAKES_DIR / wav_filename)


def get_wav_duration_seconds(project_dir: str, wav_filename: str) -> float:
    """WAV の長さを秒で返す。ファイルが存在しない・読めない場合は 0.0。"""
    try:
        import soundfile as sf
        path = Path(project_dir) / TAKES_DIR / wav_filename
        if not path.is_file():
            return 0.0
        info = sf.info(str(path))
        return float(info.duration)
    except Exception:
        return 0.0


def list_take_wav_paths(project_dir: str) -> list[tuple[str, str]]:
    """(take_id, wav_path) のリストを返す。メタに登録されているテイクのみ。"""
    proj = load_project(project_dir)
    if proj is None:
        return []
    return [(t.id, get_take_wav_path(project_dir, t.wav_filename)) for t in proj.takes]


def delete_take(project_dir: str, take_id: str) -> bool:
    """テイクをメタから削除し、WAV ファイルも削除する。"""
    import time
    proj = load_project(project_dir)
    if proj is None:
        return False
    t = proj.get_take(take_id)
    if t is None:
        return False
    wav_path = Path(get_take_wav_path(project_dir, t.wav_filename))
    if wav_path.exists():
        # ファイルがロックされている場合に備えてリトライ
        max_retries = 3
        for i in range(max_retries):
            try:
                wav_path.unlink()
                break
            except PermissionError:
                if i < max_retries - 1:
                    time.sleep(0.1)  # 100ms待ってからリトライ
                else:
                    return False  # リトライしても削除できなかった
    proj.takes = [x for x in proj.takes if x.id != take_id]
    _save_meta(project_dir, proj)
    return True


def format_export_filename(
    template: str,
    *,
    project_name: str,
    take: TakeInfo,
    index: int,
) -> str:
    """エクスポート用の命名テンプレート解決。

    利用可能なプレースホルダ:
    ``{project}`` ``{index}`` ``{n}``（index+1 の 3 桁ゼロ埋め）``{line}``（台本行番号）
    ``{text}`` （セリフ先頭 20 文字）``{rating}`` ``{original}``（元の wav_filename・拡張子なし）
    """
    original = Path(take.wav_filename).stem
    text_preview = sanitize_for_filename((take.script_line_text or "")[:20], max_length=40)
    line_str = str(take.script_line_number) if take.script_line_number else ""
    try:
        return template.format(
            project=project_name,
            index=index,
            n=f"{index + 1:03d}",
            line=line_str,
            text=text_preview,
            rating=take.rating or 0,
            original=original,
        )
    except (KeyError, IndexError, ValueError):
        return f"{project_name}_Take{index + 1}"


def export_takes(
    project_dir: str,
    take_ids: list[str],
    dest_dir: str,
    *,
    use_friendly_names: bool = False,
    name_template: str | None = None,
    fmt: str = "wav",
    mp3_bitrate_kbps: int = 192,
    do_noise_reduce: bool = False,
    do_trim_silence: bool = False,
    do_lufs_normalize: bool = False,
    target_lufs: float = -16.0,
) -> list[str]:
    """
    指定した take_id の音声を dest_dir にエクスポートする。

    ``fmt`` には ``wav`` / ``flac`` / ``mp3`` を指定可能。
    ``do_noise_reduce`` / ``do_trim_silence`` / ``do_lufs_normalize`` を有効にすると、
    書き出し前にノイズ除去 → 無音トリム → LUFS 正規化の順でチェーン処理を行う。

    ``name_template`` が与えられた場合は最優先（``{project}_{n}`` など）。
    さもなくば ``use_friendly_names=True`` で ``{プロジェクト名}_Take{N}``。
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    proj = load_project(project_dir)
    if proj is None:
        return []
    project_name = Path(project_dir).name or "project"

    fmt_lower = (fmt or "wav").lower()
    do_post = bool(do_noise_reduce or do_trim_silence or do_lufs_normalize)
    need_conversion = fmt_lower != "wav" or do_post

    # 必要なときだけ audio_processing をロード（テストの依存を緩和）
    ap = None
    if need_conversion:
        from src import audio_processing as ap  # type: ignore

    ext = ap.output_extension_for(fmt_lower) if ap is not None else ".wav"

    copied: list[str] = []
    for idx, take_id in enumerate(take_ids):
        t = proj.get_take(take_id)
        if t is None:
            continue
        src = Path(get_take_wav_path(project_dir, t.wav_filename))
        if not src.exists():
            continue
        if name_template:
            base = format_export_filename(name_template, project_name=project_name, take=t, index=idx)
            base_stem = base[:-4] if base.lower().endswith(".wav") else base
            out_name = f"{base_stem}{ext}"
        elif use_friendly_names:
            out_name = f"{project_name}_Take{idx + 1}{ext}"
        else:
            out_name = Path(t.wav_filename).stem + ext
        out_path = dest / out_name
        try:
            if need_conversion and ap is not None:
                ap.apply_post_processing(
                    str(src),
                    str(out_path),
                    do_noise_reduce=do_noise_reduce,
                    do_trim_silence=do_trim_silence,
                    do_lufs_normalize=do_lufs_normalize,
                    target_lufs=target_lufs,
                    fmt=fmt_lower,
                    mp3_bitrate_kbps=mp3_bitrate_kbps,
                )
            else:
                shutil.copy2(src, out_path)
        except OSError as e:
            raise OSError(f"エクスポート先への書き出しに失敗しました: {out_path}\n{e}") from e
        except Exception as e:  # 処理ライブラリ由来の例外も OSError として拾う
            raise OSError(f"エクスポート処理に失敗しました: {out_path}\n{e}") from e
        copied.append(str(out_path))
    return copied


def _meta_path(project_dir: str) -> Path:
    return Path(project_dir) / META_FILENAME


def _load_meta(project_dir: str) -> dict | None:
    p = _meta_path(project_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("project_meta の読み込みに失敗しました: %s (%s)", project_dir, e)
        return None


def _save_meta(project_dir: str, proj: Project) -> None:
    meta = {
        "takes": [
            {
                "id": t.id,
                "wav_filename": t.wav_filename,
                "memo": t.memo,
                "favorite": t.favorite,
                "created_at": t.created_at,
                "adopted": t.adopted,
                "script_line_number": t.script_line_number,
                "script_line_text": t.script_line_text,
                "rating": t.rating,
                "tags": list(t.tags),
                "has_clipping": t.has_clipping,
                "peak_dbfs": t.peak_dbfs,
                "integrated_lufs": t.integrated_lufs,
            }
            for t in proj.takes
        ],
    }
    _meta_path(project_dir).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
