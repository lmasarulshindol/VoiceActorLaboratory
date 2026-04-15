"""熱血関西弁セリフ集Markdown → PDF変換スクリプト

テーブル・コードブロック・引用ブロック・見出し階層に対応した
高機能Markdown→PDF変換。

Usage:
    python _convert_kansai_md_to_pdf.py <input.md>
"""
import sys, re
from pathlib import Path
from fpdf import FPDF

md_path = Path(sys.argv[1])
pdf_path = md_path.parent / "PDF" / md_path.with_suffix(".pdf").name

pdf_path.parent.mkdir(parents=True, exist_ok=True)

FONT_DIR = Path(r"C:/Windows/Fonts")
FONT_REGULAR = str(FONT_DIR / "yumin.ttf")
FONT_BOLD = str(FONT_DIR / "yumindb.ttf")

COLORS = {
    "title_bg": (45, 55, 72),
    "title_fg": (255, 255, 255),
    "h2_bg": (237, 242, 247),
    "h2_accent": (49, 130, 206),
    "h2_fg": (45, 55, 72),
    "h3_fg": (49, 130, 206),
    "body": (33, 33, 33),
    "quote_bg": (255, 250, 240),
    "quote_accent": (221, 107, 32),
    "quote_fg": (100, 80, 60),
    "code_bg": (40, 44, 52),
    "code_fg": (171, 178, 191),
    "table_header_bg": (45, 55, 72),
    "table_header_fg": (255, 255, 255),
    "table_row_even": (247, 250, 252),
    "table_row_odd": (255, 255, 255),
    "table_border": (200, 210, 220),
    "table_fg": (33, 33, 33),
    "hr": (180, 190, 200),
    "footer": (150, 150, 150),
    "bullet_accent": (49, 130, 206),
}


class ScriptPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("yumin", size=7)
            self.set_text_color(*COLORS["footer"])
            self.cell(0, 5, "熱血関西弁キャラ セリフ集 ＆ イントネーションアドバイス", align="C")
            self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("yumin", size=8)
        self.set_text_color(*COLORS["footer"])
        self.cell(0, 10, f"- {self.page_no()} -", align="C")


pdf = ScriptPDF(orientation="P", unit="mm", format="A4")
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_font("yumin", style="", fname=FONT_REGULAR)
pdf.add_font("yumin", style="B", fname=FONT_BOLD)
pdf.set_margins(18, 15, 18)
pdf.add_page()

lines = md_path.read_text(encoding="utf-8").splitlines()


def set_color(pdf, key):
    pdf.set_text_color(*COLORS[key])


def strip_bold(text):
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def write_rich_text(pdf, text, size=10, bold=False, indent=0):
    """**太字**を含むテキストを適切に描画"""
    style = "B" if bold else ""
    pdf.set_font("yumin", style=style, size=size)

    if indent:
        pdf.set_x(pdf.l_margin + indent)

    parts = re.split(r"(\*\*.+?\*\*)", text)
    x_start = pdf.get_x()
    w_avail = pdf.epw - (x_start - pdf.l_margin)

    plain_text = strip_bold(text)
    pdf.set_font("yumin", style="", size=size)
    total_w = pdf.get_string_width(plain_text)

    if total_w > w_avail:
        cleaned = strip_bold(text)
        pdf.set_font("yumin", style=style, size=size)
        if indent:
            pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(w=pdf.epw - indent, h=size * 0.5, text=cleaned,
                        align="L", new_x="LMARGIN", new_y="NEXT")
        return

    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            pdf.set_font("yumin", style="B", size=size)
            pdf.write(size * 0.45, part[2:-2])
        else:
            pdf.set_font("yumin", style=style, size=size)
            pdf.write(size * 0.45, part)
    pdf.ln(size * 0.5)


def draw_table(pdf, header_line, rows):
    """Markdownテーブルを描画"""
    headers = [c.strip() for c in header_line.strip("|").split("|")]
    data_rows = []
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        data_rows.append(cells)

    num_cols = len(headers)
    col_w = (pdf.epw) / num_cols

    pdf.set_font("yumin", style="B", size=8.5)
    content_widths = [0] * num_cols
    for i, h in enumerate(headers):
        w = pdf.get_string_width(h)
        content_widths[i] = max(content_widths[i], w)
    for row_data in data_rows:
        for i, cell in enumerate(row_data):
            if i < num_cols:
                pdf.set_font("yumin", style="", size=8.5)
                w = pdf.get_string_width(strip_bold(cell))
                content_widths[i] = max(content_widths[i], w)

    total_content = sum(content_widths)
    padding = 4
    if total_content > 0:
        col_widths = [(w / total_content) * (pdf.epw - padding * num_cols) + padding
                      for w in content_widths]
    else:
        col_widths = [col_w] * num_cols

    total_w = sum(col_widths)
    scale = pdf.epw / total_w if total_w > pdf.epw else 1.0
    col_widths = [w * scale for w in col_widths]

    row_h = 7

    needed = row_h * (len(data_rows) + 1) + 5
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()

    pdf.set_fill_color(*COLORS["table_header_bg"])
    pdf.set_text_color(*COLORS["table_header_fg"])
    pdf.set_draw_color(*COLORS["table_border"])
    pdf.set_font("yumin", style="B", size=8.5)
    pdf.set_line_width(0.3)

    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], row_h, " " + h, border=1, fill=True, align="L")
    pdf.ln()

    pdf.set_text_color(*COLORS["table_fg"])
    pdf.set_font("yumin", style="", size=8.5)

    for row_idx, row_data in enumerate(data_rows):
        if row_idx % 2 == 0:
            pdf.set_fill_color(*COLORS["table_row_even"])
        else:
            pdf.set_fill_color(*COLORS["table_row_odd"])

        if pdf.get_y() + row_h > pdf.h - pdf.b_margin:
            pdf.add_page()

        for i in range(num_cols):
            cell_text = row_data[i] if i < len(row_data) else ""
            cell_text = strip_bold(cell_text)
            pdf.cell(col_widths[i], row_h, " " + cell_text, border=1, fill=True, align="L")
        pdf.ln()

    pdf.ln(2)


def draw_code_block(pdf, code_lines):
    """コードブロックを描画"""
    line_h = 5
    needed = len(code_lines) * line_h + 8
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()

    x = pdf.l_margin
    y = pdf.get_y()
    block_h = len(code_lines) * line_h + 6

    pdf.set_fill_color(*COLORS["code_bg"])
    pdf.set_draw_color(60, 65, 75)
    pdf.rect(x, y, pdf.epw, block_h, style="DF")

    corner_r = 2
    pdf.set_fill_color(*COLORS["code_bg"])

    pdf.set_font("yumin", style="", size=8.5)
    set_color(pdf, "code_fg")

    pdf.set_y(y + 3)
    for cl in code_lines:
        pdf.set_x(x + 4)
        pdf.cell(pdf.epw - 8, line_h, cl, align="L")
        pdf.ln(line_h)

    pdf.set_y(y + block_h + 2)
    set_color(pdf, "body")


def draw_quote_block(pdf, quote_lines):
    """引用ブロックを描画"""
    text = "\n".join(quote_lines)
    pdf.set_font("yumin", style="", size=9)
    text_plain = strip_bold(text)

    line_h = 4.5
    test_lines = text_plain.split("\n")
    total_lines = 0
    for tl in test_lines:
        w = pdf.get_string_width(tl)
        avail = pdf.epw - 12
        total_lines += max(1, int(w / avail) + 1)

    block_h = total_lines * line_h + 6
    needed = block_h + 4
    if pdf.get_y() + needed > pdf.h - pdf.b_margin:
        pdf.add_page()

    x = pdf.l_margin
    y = pdf.get_y()

    pdf.set_fill_color(*COLORS["quote_bg"])
    pdf.rect(x, y, pdf.epw, block_h, style="F")

    pdf.set_fill_color(*COLORS["quote_accent"])
    pdf.rect(x, y, 2.5, block_h, style="F")

    set_color(pdf, "quote_fg")
    pdf.set_font("yumin", style="", size=9)
    pdf.set_y(y + 3)

    for ql in quote_lines:
        pdf.set_x(x + 6)
        parts = re.split(r"(\*\*.+?\*\*)", ql)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                pdf.set_font("yumin", style="B", size=9)
                pdf.write(line_h, part[2:-2])
                pdf.set_font("yumin", style="", size=9)
            else:
                pdf.write(line_h, part)
        pdf.ln(line_h)

    pdf.set_y(y + block_h + 2)
    set_color(pdf, "body")


i = 0
in_code = False
code_lines = []
in_quote = False
quote_lines = []
table_header = None
table_sep_seen = False
table_rows = []

while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    if stripped.startswith("```"):
        if in_code:
            draw_code_block(pdf, code_lines)
            code_lines = []
            in_code = False
        else:
            in_code = True
            code_lines = []
        i += 1
        continue

    if in_code:
        code_lines.append(line)
        i += 1
        continue

    if stripped.startswith("> ") or (in_quote and stripped.startswith(">")):
        content = stripped[2:] if stripped.startswith("> ") else stripped[1:]
        quote_lines.append(content)
        in_quote = True
        i += 1
        continue
    elif in_quote:
        draw_quote_block(pdf, quote_lines)
        quote_lines = []
        in_quote = False

    if "|" in stripped and not stripped.startswith("|--") and not re.match(r"^\|[\s\-:|]+\|$", stripped):
        if table_header is None:
            table_header = stripped
            i += 1
            continue
        elif table_sep_seen:
            table_rows.append(stripped)
            i += 1
            continue
    elif re.match(r"^\|[\s\-:|]+\|$", stripped) and table_header is not None:
        table_sep_seen = True
        i += 1
        continue
    else:
        if table_header is not None and table_sep_seen:
            draw_table(pdf, table_header, table_rows)
        table_header = None
        table_sep_seen = False
        table_rows = []

    if not stripped:
        pdf.ln(2)
        i += 1
        continue

    if stripped == "---":
        pdf.ln(3)
        y = pdf.get_y()
        pdf.set_draw_color(*COLORS["hr"])
        pdf.set_line_width(0.4)
        pdf.line(pdf.l_margin + 10, y, pdf.w - pdf.r_margin - 10, y)
        pdf.set_line_width(0.2)
        pdf.ln(4)
        i += 1
        continue

    if stripped.startswith("# ") and not stripped.startswith("## "):
        title = stripped[2:]
        pdf.ln(8)
        y = pdf.get_y()
        pdf.set_fill_color(*COLORS["title_bg"])
        box_h = 16
        pdf.rect(pdf.l_margin, y, pdf.epw, box_h, style="F")
        pdf.set_font("yumin", style="B", size=16)
        set_color(pdf, "title_fg")
        pdf.set_y(y + 3)
        pdf.cell(0, 10, title, align="C")
        pdf.set_y(y + box_h + 4)
        set_color(pdf, "body")
        i += 1
        continue

    if stripped.startswith("## "):
        heading = stripped[3:]
        if pdf.get_y() + 15 > pdf.h - pdf.b_margin:
            pdf.add_page()
        pdf.ln(4)
        y = pdf.get_y()
        pdf.set_fill_color(*COLORS["h2_bg"])
        box_h = 9
        pdf.rect(pdf.l_margin, y, pdf.epw, box_h, style="F")
        pdf.set_fill_color(*COLORS["h2_accent"])
        pdf.rect(pdf.l_margin, y, 3, box_h, style="F")
        pdf.set_font("yumin", style="B", size=12)
        set_color(pdf, "h2_fg")
        pdf.set_xy(pdf.l_margin + 5, y + 1)
        pdf.cell(0, 7, heading, align="L")
        pdf.set_y(y + box_h + 2)
        set_color(pdf, "body")
        i += 1
        continue

    if stripped.startswith("### "):
        heading = stripped[4:]
        if pdf.get_y() + 12 > pdf.h - pdf.b_margin:
            pdf.add_page()
        pdf.ln(3)
        set_color(pdf, "h3_fg")
        pdf.set_font("yumin", style="B", size=10.5)
        pdf.cell(0, 6, "■ " + heading, align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        set_color(pdf, "body")
        i += 1
        continue

    if stripped.startswith("- ") or stripped.startswith("* "):
        bullet_text = stripped[2:]
        set_color(pdf, "bullet_accent")
        pdf.set_font("yumin", style="B", size=10)
        pdf.set_x(pdf.l_margin + 3)
        pdf.write(5, "● ")
        set_color(pdf, "body")
        write_rich_text(pdf, bullet_text, size=10, indent=8)
        i += 1
        continue

    if re.match(r"^\d+\.\s", stripped):
        m = re.match(r"^(\d+)\.\s(.+)", stripped)
        if m:
            num = m.group(1)
            text = m.group(2)
            set_color(pdf, "h3_fg")
            pdf.set_font("yumin", style="B", size=10)
            pdf.set_x(pdf.l_margin + 3)
            pdf.write(5, f"{num}. ")
            set_color(pdf, "body")
            write_rich_text(pdf, text, size=10, indent=8)
        i += 1
        continue

    set_color(pdf, "body")
    write_rich_text(pdf, stripped, size=10)
    i += 1

if in_quote and quote_lines:
    draw_quote_block(pdf, quote_lines)
if table_header is not None and table_sep_seen:
    draw_table(pdf, table_header, table_rows)
if in_code and code_lines:
    draw_code_block(pdf, code_lines)

pdf.output(str(pdf_path))
print(f"PDF saved: {pdf_path}")
