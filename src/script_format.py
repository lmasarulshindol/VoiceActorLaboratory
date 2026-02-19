"""
台本の構成と、録音ファイル名の導出ルール。

台本フォーマット:
- 行頭が "# " または "## " の行は見出し（シーン・カット名）。ファイル名のベースに利用する。
- 見出しは「# シーン名」の形式。カーソル位置より前の直近の見出しが現在のシーンとなる。
- 同一シーン内のテイクは "シーン名_01.wav", "シーン名_02.wav" のように連番になる。
"""
import re
import unicodedata


def get_current_section(script_text: str, cursor_position: int) -> str:
    """
    カーソル位置に対応する「現在のシーン名」を取得する。
    カーソルを含む行まで含めた範囲で、直近の行頭 "# " または "## " の見出しを返す。
    見出しがない場合は空文字列。
    """
    before = script_text[:cursor_position]
    line_start = before.rfind("\n") + 1
    rest_of_line = script_text[cursor_position:].split("\n")[0] if cursor_position > line_start else ""
    full_before = before + rest_of_line
    lines = full_before.splitlines()
    section = ""
    for line in reversed(lines):
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip()
            break
        if s.startswith("# "):
            section = s[2:].strip()
            break
    return section


def sanitize_for_filename(name: str, max_length: int = 64) -> str:
    """
    ファイル名に使えない文字を除去し、安全な文字列にする。
    空白はアンダースコアに、制御文字と \\/:*?\"<>| は除去。先頭の . も除去。
    """
    if not name:
        return ""
    # 正規化
    n = unicodedata.normalize("NFKC", name)
    # 禁止文字をアンダースコアに
    n = re.sub(r"[\\/:*?\"<>|\s]+", "_", n)
    n = re.sub(r"\s+", "_", n)
    # 先頭の . と _ の連続を1つに
    n = n.lstrip("._ ")
    if not n:
        return ""
    return n[:max_length].rstrip("._ ")


def suggest_take_basename(
    script_text: str,
    cursor_position: int,
    existing_wav_filenames: list[str],
) -> str:
    """
    台本とカーソル位置・既存テイクのファイル名から、今回のテイク用ベース名を提案する。
    返り値は拡張子なし（例: "朝の挨拶_01"）。既存がなければ "シーン名_01" または "take_01"。
    """
    section = get_current_section(script_text, cursor_position)
    prefix = sanitize_for_filename(section) if section else "take"
    # 既存の "prefix_NN.wav" または "prefix_NN_xxxx.wav" 形式をカウント
    pattern = re.compile(re.escape(prefix) + r"_(\d+)", re.IGNORECASE)
    max_n = 0
    for f in existing_wav_filenames:
        base = f
        if base.lower().endswith(".wav"):
            base = base[:-4]
        m = pattern.match(base) or pattern.search(base)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}_{max_n + 1:02d}"
