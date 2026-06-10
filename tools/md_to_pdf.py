"""
D001.md を縦書き／横書きの2種類でPDF化するスクリプト。

- Markdown → HTML（横書き／縦書き）を生成
- Microsoft Edge ヘッドレスで HTML → PDF に変換

実行: py -3 tools/md_to_pdf.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import markdown

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DOCS_DIR = PROJECT_DIR / "docs"
SRC_MD = DOCS_DIR / "D001.md"
OUT_DIR = DOCS_DIR
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def find_edge() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Microsoft Edge (msedge.exe) が見つかりませんでした。")


HORIZONTAL_CSS = """
@page {
    size: A4;
    margin: 18mm 16mm;
}
html, body {
    font-family: "Yu Mincho", "Yu Mincho Light", "ヒラギノ明朝 Pro", "MS PMincho", serif;
    font-size: 11pt;
    line-height: 1.85;
    color: #111;
    background: #fff;
}
body {
    margin: 0;
    padding: 0;
}
h1 {
    font-size: 20pt;
    text-align: center;
    margin: 0 0 1.2em;
    letter-spacing: 0.1em;
    border-bottom: 1px solid #999;
    padding-bottom: 0.4em;
}
h2 {
    font-size: 14pt;
    margin: 1.6em 0 0.8em;
    padding-left: 0.4em;
    border-left: 4px solid #555;
}
h3 {
    font-size: 12pt;
    margin: 1.2em 0 0.6em;
}
blockquote {
    border-left: 3px solid #bbb;
    margin: 0.8em 0;
    padding: 0.2em 0.8em;
    color: #555;
    font-size: 0.95em;
}
hr {
    border: none;
    border-top: 1px dashed #aaa;
    margin: 1.6em 0;
}
p {
    margin: 0.4em 0;
    text-indent: 0;
}
strong {
    font-weight: 700;
    color: #222;
}
code {
    font-family: "Consolas", "MS Gothic", monospace;
    background: #f4f4f4;
    padding: 0.1em 0.3em;
    border-radius: 3px;
    font-size: 0.9em;
}
ul, ol {
    margin: 0.4em 0 0.4em 1.4em;
    padding: 0;
}
"""

VERTICAL_CSS = """
@page {
    size: A4 landscape;
    margin: 18mm 16mm;
}
html, body {
    font-family: "Yu Mincho", "Yu Mincho Light", "ヒラギノ明朝 Pro", "MS PMincho", serif;
    font-size: 11pt;
    line-height: 1.9;
    color: #111;
    background: #fff;
}
html {
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
    text-orientation: mixed;
}
body {
    margin: 0;
    padding: 0;
    height: 100vh;
}
h1 {
    font-size: 20pt;
    margin: 0 0 1.4em;
    letter-spacing: 0.2em;
    border-right: 1px solid #999;
    padding-right: 0.4em;
}
h2 {
    font-size: 14pt;
    margin: 1.6em 0 0.8em;
    padding-right: 0.4em;
    border-right: 4px solid #555;
}
h3 {
    font-size: 12pt;
    margin: 1.2em 0 0.6em;
}
blockquote {
    border-right: 3px solid #bbb;
    margin: 0.8em 0;
    padding: 0.2em 0.8em;
    color: #555;
    font-size: 0.95em;
}
hr {
    border: none;
    border-right: 1px dashed #aaa;
    margin: 1.6em 0;
}
p {
    margin: 0.4em 0;
}
strong {
    font-weight: 700;
    color: #222;
}
/* 縦書きで英数字を正立させたい箇所 */
.tcy {
    text-combine-upright: all;
    -webkit-text-combine: horizontal;
}
ul, ol {
    margin: 0.4em 1.4em 0.4em 0;
    padding: 0;
}
table {
    /* テーブルは縦書きと相性が悪いので横書きに戻す */
    writing-mode: horizontal-tb;
    border-collapse: collapse;
    margin: 0.6em 0;
}
table th, table td {
    border: 1px solid #999;
    padding: 0.2em 0.5em;
}
code {
    writing-mode: horizontal-tb;
    display: inline-block;
    font-family: "Consolas", "MS Gothic", monospace;
    background: #f4f4f4;
    padding: 0 0.3em;
    border-radius: 3px;
    font-size: 0.9em;
}
"""

HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_html(md_text: str, css: str, title: str) -> str:
    body_html = markdown.markdown(
        md_text,
        extensions=["extra", "sane_lists", "tables", "nl2br"],
    )
    return HTML_TEMPLATE.format(title=title, css=css, body=body_html)


def html_to_pdf(edge: Path, html_path: Path, pdf_path: Path) -> None:
    url = html_path.resolve().as_uri()
    cmd = [
        str(edge),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        url,
    ]
    print("  > ", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"PDF生成に失敗しました: {pdf_path}")


def main() -> None:
    if not SRC_MD.exists():
        raise FileNotFoundError(f"対象MDが見つかりません: {SRC_MD}")
    edge = find_edge()
    md_text = SRC_MD.read_text(encoding="utf-8")
    title = "本を読み終えるまで"

    targets = [
        ("D001_横書き", HORIZONTAL_CSS),
        ("D001_縦書き", VERTICAL_CSS),
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = OUT_DIR / "_pdf_tmp"
    tmp_dir.mkdir(exist_ok=True)
    try:
        for name, css in targets:
            html_path = tmp_dir / f"{name}.html"
            pdf_path = OUT_DIR / f"{name}.pdf"
            print(f"[{name}] HTML生成 -> {html_path}")
            html_path.write_text(render_html(md_text, css, title), encoding="utf-8")
            print(f"[{name}] PDF生成 -> {pdf_path}")
            html_to_pdf(edge, html_path, pdf_path)
            size_kb = pdf_path.stat().st_size / 1024
            print(f"  完了: {pdf_path}  ({size_kb:,.1f} KB)")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
