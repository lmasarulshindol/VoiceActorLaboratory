"""D001.md を横書き・縦書き PDF に変換する。

出力:
  docs/D001_横書き.pdf
  docs/D001_縦書き.pdf
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "D001.md"
OUT_YOKO = ROOT / "D001_横書き.pdf"
OUT_TATE = ROOT / "D001_縦書き.pdf"
HTML_DIR = ROOT / ".pdf_build"

EDGE_CANDIDATES = [
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]

FONT_STACK = '"BIZ UDGothic", "Yu Gothic UI", "Meiryo", sans-serif'
FONT_STACK_TATE = '"Yu Mincho", "MS Mincho", "BIZ UDPMincho", serif'


def find_browser() -> Path:
    for path in EDGE_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError("Edge / Chrome が見つかりません。")


def parse_md(text: str) -> list[tuple]:
    blocks: list[tuple] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if stripped == "---":
            blocks.append(("hr",))
            i += 1
            continue

        if stripped.startswith("> "):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote_lines.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append(("meta", "\n".join(quote_lines)))
            continue

        if stripped.startswith("# "):
            blocks.append(("h1", stripped[2:].strip()))
            i += 1
            continue

        if stripped.startswith("## "):
            blocks.append(("h2", stripped[3:].strip()))
            i += 1
            continue

        if not stripped:
            blocks.append(("blank",))
            i += 1
            continue

        m = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", stripped)
        if m:
            speaker, rest = m.group(1), m.group(2).strip()
            blocks.append(("dialogue", speaker, rest) if rest else ("char", speaker))
            i += 1
            continue

        blocks.append(("para", stripped))
        i += 1

    return blocks


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def render_html(blocks: list[tuple], vertical: bool) -> str:
    parts: list[str] = []
    pending_char: str | None = None

    for block in blocks:
        kind = block[0]

        if kind == "blank":
            parts.append('<div class="spacer"></div>')
        elif kind == "hr":
            parts.append("<hr>")
        elif kind == "h1":
            parts.append(f'<h1 class="title">{esc(block[1])}</h1>')
        elif kind == "h2":
            parts.append(f'<h2 class="scene">{esc(block[1])}</h2>')
        elif kind == "meta":
            body = esc(block[1]).replace("\n", "<br>")
            parts.append(f'<div class="meta"><p>{body}</p></div>')
        elif kind == "char":
            pending_char = block[1]
        elif kind == "dialogue":
            speaker, text = block[1], block[2]
            parts.append(
                f'<p class="dialogue"><span class="speaker">{esc(speaker)}</span>'
                f'<span class="line">{esc(text)}</span></p>'
            )
        elif kind == "para":
            if pending_char:
                parts.append(
                    f'<div class="character"><p class="char-name"><strong>{esc(pending_char)}</strong></p>'
                    f'<p class="char-desc">{esc(block[1])}</p></div>'
                )
                pending_char = None
            else:
                parts.append(f'<p class="stage">{esc(block[1])}</p>')

    if pending_char:
        parts.append(f'<p class="char-name"><strong>{esc(pending_char)}</strong></p>')

    body_class = "tate" if vertical else "yoko"
    mode = "vertical-rl" if vertical else "horizontal-tb"
    font = FONT_STACK_TATE if vertical else FONT_STACK
    body = "".join(parts)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>本を読み終えるまで</title>
<style>
@page {{ size: A4; margin: 18mm 16mm 20mm 16mm; }}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  writing-mode: {mode};
  font-family: {font};
  font-size: 11pt; line-height: 1.75; color: #1a1a1a;
}}
body.tate {{ min-height: 257mm; }}
h1.title {{ font-size: 20pt; font-weight: 700; text-align: center; margin: 0 0 1.2em; }}
h2.scene {{
  font-size: 13pt; font-weight: 700; background: #ececec;
  border-inline-start: 3px solid #555; padding: 0.35em 0.6em; margin: 1.4em 0 0.8em;
}}
.meta {{ font-size: 9pt; color: #555; margin-bottom: 1em; }}
.character {{ margin: 0.6em 0 1em; }}
.char-name {{ margin: 0 0 0.2em; font-weight: 700; }}
.char-desc {{ margin: 0; font-size: 10pt; }}
.dialogue {{ margin: 0.35em 0; }}
.dialogue .speaker {{ font-weight: 700; margin-inline-end: 0.35em; }}
.stage {{ margin: 0.35em 0; font-size: 10.5pt; color: #333; }}
hr {{ border: none; border-top: 1px solid #ccc; margin: 1.2em 0; }}
body.tate hr {{
  border-top: none; border-inline-start: 1px solid #ccc;
  height: 2em; width: 0; margin: 1em 0.5em;
}}
.spacer {{ height: 0.6em; }}
</style>
</head>
<body class="{body_class}">
{body}
</body>
</html>
"""


def print_html_to_pdf(html_path: Path, pdf_path: Path, browser: Path) -> None:
    url = html_path.resolve().as_uri()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path.resolve()}",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not pdf_path.is_file():
        raise RuntimeError(f"PDF生成失敗: {pdf_path}\n{result.stderr}")


def main() -> int:
    md_path = Path(sys.argv[1]) if len(sys.argv) > 1 else MD_PATH
    if not md_path.is_file():
        print(f"ファイルが見つかりません: {md_path}", file=sys.stderr)
        return 1

    blocks = parse_md(md_path.read_text(encoding="utf-8"))
    browser = find_browser()
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    yoko_html = HTML_DIR / "D001_yoko.html"
    tate_html = HTML_DIR / "D001_tate.html"
    yoko_html.write_text(render_html(blocks, vertical=False), encoding="utf-8")
    tate_html.write_text(render_html(blocks, vertical=True), encoding="utf-8")

    print_html_to_pdf(yoko_html, OUT_YOKO, browser)
    print(f"[OK] {OUT_YOKO}")
    print_html_to_pdf(tate_html, OUT_TATE, browser)
    print(f"[OK] {OUT_TATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
