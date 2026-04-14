"""台本MarkdownファイルをPDFに変換するスクリプト
1ページ目: タイトル・登場人物・演技ポイント
2ページ目以降: 本編セリフ
"""

import re
import sys
from pathlib import Path
from fpdf import FPDF

FONT_REGULAR = "C:/Windows/Fonts/BIZ-UDGothicR.ttc"
FONT_BOLD = "C:/Windows/Fonts/BIZ-UDGothicB.ttc"


class ScriptPDF(FPDF):
    def __init__(self, title_text=""):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.title_text = title_text
        self.set_auto_page_break(auto=True, margin=20)
        self.add_font("Gothic", "", FONT_REGULAR)
        self.add_font("Gothic", "B", FONT_BOLD)

    def header(self):
        if self.page_no() >= 2:
            self.set_font("Gothic", "", 7)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, self.title_text, align="L")
            self.cell(0, 5, f"- {self.page_no()} -", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(200, 200, 200)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

    def footer(self):
        pass


def parse_markdown(md_text: str) -> dict:
    """Markdownを解析して構造化データにする"""
    result = {
        "title": "",
        "subtitle": "",
        "setting": "",
        "characters": [],
        "tone": "",
        "acting_notes": [],
        "relationship_notes": [],
        "scenes": [],
    }

    lines = md_text.split("\n")
    i = 0
    current_section = None

    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith("# 掛け合い台本"):
            result["title"] = line.replace("# 掛け合い台本 — ", "").replace("# 掛け合い台本 —", "").strip()
            i += 1
            continue

        if line == "# 設定":
            current_section = "setting"
            i += 1
            continue

        if re.match(r"^# 登場人物", line):
            result["subtitle"] = line.replace("# ", "")
            current_section = "characters"
            i += 1
            continue

        if line == "# トーン":
            current_section = "tone"
            i += 1
            continue

        if line == "# 演技メモ":
            current_section = "acting"
            i += 1
            continue

        if re.match(r"^# (キャラクター関係性メモ|4人の掛け合い構造|3人の掛け合い)", line):
            current_section = "relationship"
            i += 1
            continue

        scene_match = re.match(r"^# (シーン\d+_.+)$", line)
        if scene_match:
            current_section = "scene"
            result["scenes"].append({"name": scene_match.group(1), "lines": []})
            i += 1
            continue

        if line == "---":
            i += 1
            continue

        if current_section == "setting" and line.strip():
            if result["setting"]:
                result["setting"] += " "
            result["setting"] += line.strip()

        elif current_section == "characters" and line.startswith("- "):
            result["characters"].append(line[2:].strip())

        elif current_section == "tone" and line.strip():
            if result["tone"]:
                result["tone"] += " "
            result["tone"] += line.strip()

        elif current_section == "acting" and line.strip():
            result["acting_notes"].append(line.strip())

        elif current_section == "relationship" and line.strip():
            result["relationship_notes"].append(line.strip())

        elif current_section == "scene" and result["scenes"]:
            result["scenes"][-1]["lines"].append(line)

        i += 1

    return result


def build_cover_page(pdf: ScriptPDF, data: dict):
    """1ページ目: タイトル・登場人物・演技ポイント"""
    pdf.add_page()

    # タイトルエリア
    pdf.ln(8)
    pdf.set_font("Gothic", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "掛け合い台本", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Gothic", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 14, data["title"], align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Gothic", "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "原作: この素晴らしい世界に祝福を！", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_draw_color(60, 60, 60)
    cx = pdf.w / 2
    pdf.line(cx - 30, pdf.get_y(), cx + 30, pdf.get_y())
    pdf.ln(5)

    # 設定
    pdf.set_font("Gothic", "B", 10)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 7, "■ 設定", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Gothic", "", 8.5)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 5, data["setting"])
    pdf.ln(3)

    # 登場人物
    pdf.set_font("Gothic", "B", 10)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 7, "■ 登場人物", new_x="LMARGIN", new_y="NEXT")

    for char_text in data["characters"]:
        name_match = re.match(r"^(.+?)[（(](.+?)[）)][:：](.+)$", char_text)
        if name_match:
            name = name_match.group(1).strip()
            voice_type = name_match.group(2).strip()
            desc = name_match.group(3).strip()

            pdf.set_font("Gothic", "B", 9)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 5.5, f"● {name}（{voice_type}）", new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Gothic", "", 8)
            pdf.set_text_color(70, 70, 70)
            x_indent = pdf.l_margin + 6
            w_indent = pdf.w - pdf.l_margin - pdf.r_margin - 6
            pdf.set_x(x_indent)
            pdf.multi_cell(w_indent, 4.5, desc)
            pdf.ln(1)
        else:
            pdf.set_font("Gothic", "", 8.5)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 5, char_text)
            pdf.ln(1)

    pdf.ln(2)

    # 演技ポイント
    acting_lines = data["acting_notes"]
    if acting_lines:
        pdf.set_font("Gothic", "B", 10)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 7, "■ 演技ポイント", new_x="LMARGIN", new_y="NEXT")

        for note in acting_lines:
            clean = note.lstrip("- ").strip()
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean)

            char_match = re.match(r"^(.+?):(.+)$", clean)
            if char_match:
                char_name = char_match.group(1).strip()
                char_desc = char_match.group(2).strip()

                pdf.set_font("Gothic", "B", 8.5)
                pdf.set_text_color(40, 40, 40)
                pdf.cell(0, 5, f"> {char_name}", new_x="LMARGIN", new_y="NEXT")

                pdf.set_font("Gothic", "", 7.5)
                pdf.set_text_color(80, 80, 80)
                x_indent = pdf.l_margin + 6
                w_indent = pdf.w - pdf.l_margin - pdf.r_margin - 6
                pdf.set_x(x_indent)
                pdf.multi_cell(w_indent, 4, char_desc)
                pdf.ln(0.5)
            else:
                pdf.set_font("Gothic", "", 8)
                pdf.set_text_color(70, 70, 70)
                pdf.multi_cell(0, 4.5, f"  {clean}")
                pdf.ln(0.5)


def build_script_pages(pdf: ScriptPDF, data: dict):
    """2ページ目以降: 本編セリフ"""
    pdf.add_page()

    for scene_idx, scene in enumerate(data["scenes"]):
        if scene_idx > 0:
            pdf.ln(2)
            pdf.set_draw_color(180, 180, 180)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(4)

        scene_name = scene["name"]
        scene_name = re.sub(r"^シーン(\d+)_", r"Scene \1  ", scene_name)

        pdf.set_font("Gothic", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 8, scene_name, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        for raw_line in scene["lines"]:
            line = raw_line.rstrip()
            if not line:
                continue

            dialogue_match = re.match(r"^(.+?):\s*(.*)$", line)
            if dialogue_match:
                char_name = dialogue_match.group(1).strip()
                dialogue = dialogue_match.group(2).strip()

                if pdf.get_y() > pdf.h - 30:
                    pdf.add_page()

                pdf.set_font("Gothic", "B", 9.5)
                pdf.set_text_color(30, 30, 120)
                pdf.cell(0, 6, char_name, new_x="LMARGIN", new_y="NEXT")

                if dialogue:
                    pdf.set_font("Gothic", "", 9.5)
                    pdf.set_text_color(30, 30, 30)
                    x_indent = pdf.l_margin + 4
                    w_indent = pdf.w - pdf.l_margin - pdf.r_margin - 4
                    pdf.set_x(x_indent)
                    pdf.multi_cell(w_indent, 6, dialogue)

                pdf.ln(2)

            elif line.startswith("（") or line.startswith("("):
                if pdf.get_y() > pdf.h - 25:
                    pdf.add_page()
                pdf.set_font("Gothic", "", 8.5)
                pdf.set_text_color(100, 100, 100)
                x_indent = pdf.l_margin + 4
                w_indent = pdf.w - pdf.l_margin - pdf.r_margin - 4
                pdf.set_x(x_indent)
                pdf.multi_cell(w_indent, 5, line)
                pdf.ln(1)


def convert_md_to_pdf(md_path: Path, output_dir: Path):
    """Markdownファイル→PDF変換のメインロジック"""
    md_text = md_path.read_text(encoding="utf-8")
    data = parse_markdown(md_text)

    if not data["title"]:
        data["title"] = md_path.stem

    full_title = f"掛け合い台本「{data['title']}」"
    pdf = ScriptPDF(title_text=full_title)
    pdf.set_margin(18)

    build_cover_page(pdf, data)
    build_script_pages(pdf, data)

    pdf_name = md_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name
    pdf.output(str(pdf_path))
    return pdf_path


def main():
    script_dir = Path(r"c:\Users\MasaruShindo\work2\001_声優・音声\VoiceActorLaboratory\台本")
    output_dir = script_dir / "PDF"
    output_dir.mkdir(exist_ok=True)

    targets = [
        "掛け合い台本_このすば_カズマとアクアの駄女神クエスト日和.md",
        "掛け合い台本_このすば_三人寄れば文殊の知恵は出ない.md",
        "掛け合い台本_このすば_ポンコツパーティーの休日大作戦.md",
    ]

    for filename in targets:
        md_path = script_dir / filename
        if not md_path.exists():
            print(f"[SKIP] {filename} が見つかりません")
            continue

        try:
            pdf_path = convert_md_to_pdf(md_path, output_dir)
            print(f"[OK] {pdf_path.name}")
        except Exception as e:
            print(f"[ERROR] {filename}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n出力先: {output_dir}")


if __name__ == "__main__":
    main()
