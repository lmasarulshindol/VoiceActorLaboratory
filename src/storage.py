"""
プロジェクトの保存・読み込み・エクスポート。
1プロジェクト = 1フォルダ（台本テキスト + takes/ に WAV + メタ JSON）。
"""
import json
import uuid
from pathlib import Path
from datetime import datetime
import shutil

from src.project import Project, TakeInfo
from src.script_format import sanitize_for_filename

SCRIPT_FILENAME = "script.txt"
META_FILENAME = "project_meta.json"
TAKES_DIR = "takes"


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


def load_project(project_dir: str) -> Project | None:
    """
    プロジェクトフォルダから Project を読み込む。
    フォルダや script がなければ None を返す。
    """
    path = Path(project_dir)
    if not path.is_dir():
        return None
    script_file = path / SCRIPT_FILENAME
    script_text = ""
    if script_file.exists():
        script_text = script_file.read_text(encoding="utf-8")
    meta = _load_meta(project_dir)
    takes = []
    if meta and "takes" in meta:
        for t in meta["takes"]:
            takes.append(
                TakeInfo(
                    id=t.get("id", ""),
                    wav_filename=t.get("wav_filename", ""),
                    memo=t.get("memo", ""),
                    favorite=t.get("favorite", False),
                    created_at=t.get("created_at", ""),
                    adopted=t.get("adopted", False),
                )
            )
    return Project(
        script_path=str(script_file) if script_file.exists() else "",
        script_text=script_text,
        takes=takes,
        project_dir=project_dir,
    )


def save_script(project_dir: str, text: str) -> None:
    """台本テキストを script.txt に保存する。"""
    path = Path(project_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / SCRIPT_FILENAME).write_text(text, encoding="utf-8")


def add_take_from_file(
    project_dir: str,
    wav_path: str,
    memo: str = "",
    favorite: bool = False,
    preferred_basename: str | None = None,
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
) -> bool:
    """テイクのメモ・お気に入り・採用をメタ JSON に反映する。adopted=True のとき他はすべて False。"""
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
    _save_meta(project_dir, proj)
    return True


def get_take_wav_path(project_dir: str, wav_filename: str) -> str:
    """takes/ 内の WAV の絶対パスを返す。"""
    return str(Path(project_dir) / TAKES_DIR / wav_filename)


def list_take_wav_paths(project_dir: str) -> list[tuple[str, str]]:
    """(take_id, wav_path) のリストを返す。メタに登録されているテイクのみ。"""
    proj = load_project(project_dir)
    if proj is None:
        return []
    return [(t.id, get_take_wav_path(project_dir, t.wav_filename)) for t in proj.takes]


def delete_take(project_dir: str, take_id: str) -> bool:
    """テイクをメタから削除し、WAV ファイルも削除する。"""
    proj = load_project(project_dir)
    if proj is None:
        return False
    t = proj.get_take(take_id)
    if t is None:
        return False
    wav_path = Path(get_take_wav_path(project_dir, t.wav_filename))
    if wav_path.exists():
        wav_path.unlink()
    proj.takes = [x for x in proj.takes if x.id != take_id]
    _save_meta(project_dir, proj)
    return True


def export_takes(
    project_dir: str,
    take_ids: list[str],
    dest_dir: str,
    *,
    use_friendly_names: bool = False,
) -> list[str]:
    """
    指定した take_id の WAV を dest_dir にコピーする。
    use_friendly_names=True のときファイル名を {プロジェクト名}_Take{N}.wav にする。
    返り値はコピーしたファイルのパスリスト。
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    proj = load_project(project_dir)
    if proj is None:
        return []
    project_name = Path(project_dir).name or "project"
    copied: list[str] = []
    for idx, take_id in enumerate(take_ids):
        t = proj.get_take(take_id)
        if t is None:
            continue
        src = Path(get_take_wav_path(project_dir, t.wav_filename))
        if not src.exists():
            continue
        if use_friendly_names:
            out_name = f"{project_name}_Take{idx + 1}.wav"
        else:
            out_name = t.wav_filename
        out_path = dest / out_name
        shutil.copy2(src, out_path)
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
    except (json.JSONDecodeError, OSError):
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
            }
            for t in proj.takes
        ],
    }
    _meta_path(project_dir).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
