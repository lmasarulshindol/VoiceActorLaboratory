import sys, re
from pathlib import Path
from fpdf import FPDF

md_path = Path(sys.argv[1])
pdf_path = md_path.with_suffix(".pdf")

FONT_DIR = Path(r"C:/Windows/Fonts")
FONT_REGULAR = str(FONT_DIR / "yumin.ttf")
FONT_BOLD = str(FONT_DIR / "yumindb.ttf")

class ScriptPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("yumin", size=8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"- {self.page_no()} -", align="C")

pdf = ScriptPDF(orientation="P", unit="mm", format="A4")
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_font("yumin", style="", fname=FONT_REGULAR)
pdf.add_font("yumin", style="B", fname=FONT_BOLD)
pdf.add_page()

lines = md_path.read_text(encoding="utf-8").splitlines()

def write_line(pdf, text, size=10.5, bold=False, align="L", fill=False, indent=0):
    style = "B" if bold else ""
    pdf.set_font("yumin", style=style, size=size)
    if indent:
        pdf.set_x(pdf.l_margin + indent)
    w = pdf.epw - indent
    pdf.multi_cell(w=w, h=size * 0.55, text=text, align=align, fill=fill, new_x="LMARGIN", new_y="NEXT")

def write_dialogue(pdf, speaker, text):
    pdf.set_font("yumin", style="B", size=10.5)
    sw = pdf.get_string_width(speaker + "：") + 1
    pdf.cell(w=sw, h=6, text=speaker + "：")
    pdf.set_font("yumin", style="", size=10.5)
    x_after_speaker = pdf.get_x()
    remaining_w = pdf.epw - (x_after_speaker - pdf.l_margin)
    if text:
        pdf.multi_cell(w=remaining_w, h=6, text=text, align="L", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.ln(6)

for line in lines:
    stripped = line.strip()
    if not stripped:
        pdf.ln(2.5)
        continue

    if stripped.startswith("# ") and not stripped.startswith("## "):
        title = stripped[2:]
        pdf.ln(5)
        write_line(pdf, title, size=18, bold=True, align="C")
        pdf.set_draw_color(80, 80, 80)
        y = pdf.get_y()
        pdf.line(pdf.l_margin + 20, y, pdf.w - pdf.r_margin - 20, y)
        pdf.ln(5)
        continue

    if stripped.startswith("## "):
        heading = stripped[3:]
        pdf.ln(3)
        pdf.set_fill_color(235, 235, 235)
        pdf.set_draw_color(100, 100, 100)
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.rect(x, y, pdf.epw, 8, style="F")
        pdf.set_line_width(0.5)
        pdf.line(x, y, x, y + 8)
        pdf.set_line_width(0.2)
        write_line(pdf, "  " + heading, size=12, bold=True, fill=False)
        pdf.ln(2)
        continue

    m = re.match(r"^\*\*(.+?)\*\*:\s*(.*)", stripped)
    if m:
        speaker = m.group(1)
        text = m.group(2)
        write_dialogue(pdf, speaker, text)
        continue

    if stripped.startswith("・"):
        write_line(pdf, stripped, size=10, indent=2)
        continue

    write_line(pdf, stripped, size=10.5)

pdf.output(str(pdf_path))
print(f"PDF saved: {pdf_path}")
