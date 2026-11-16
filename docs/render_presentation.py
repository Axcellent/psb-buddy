"""Создание PDF из presentation.md; не используется приложением и ZIP-сабмитом.

pip install -r docs/requirements-presentation.txt
python docs/render_presentation.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1066, 600


def font_path(explicit: str | None, bold: bool) -> Path:
    paths = [Path(explicit)] if explicit else [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in paths:
        if path.is_file():
            return path
    raise SystemExit("Укажите шрифты с кириллицей: --font PATH --bold-font PATH")


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.replace("`", "").split():
        candidate = f"{current} {word}".strip()
        if current and pdfmetrics.stringWidth(candidate, font, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return [*lines, current] if current else lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font")
    parser.add_argument("--bold-font")
    args = parser.parse_args()
    pdfmetrics.registerFont(TTFont("Body", str(font_path(args.font, False))))
    pdfmetrics.registerFont(TTFont("Bold", str(font_path(args.bold_font, True))))
    slides = []
    for section in re.split(r"(?m)^# ", (HERE / "presentation.md").read_text(encoding="utf-8")):
        if not section.strip():
            continue
        title, body = section.split("\n", 1)
        paragraphs = [" ".join(part.split()) for part in body.strip().split("\n\n")]
        slides.append((title, paragraphs))
    target = HERE / "presentation.pdf"
    canvas = Canvas(str(target), pagesize=(WIDTH, HEIGHT))
    canvas.setTitle("PSB Buddy — юридический ассистент")
    canvas.setAuthor("PSB Buddy")
    for index, (title, paragraphs) in enumerate(slides, 1):
        canvas.setFillColor(HexColor("#F1F5FC"))
        canvas.rect(0, 0, WIDTH, HEIGHT, stroke=0, fill=1)
        canvas.setFillColor(HexColor("#173B75"))
        canvas.setFont("Bold", 14)
        canvas.drawString(56, HEIGHT - 42, "PSB BUDDY  /  HACK&CHANGE 2026")
        canvas.setFillColor(HexColor("#F26532"))
        canvas.rect(56, HEIGHT - 102, 5, 34, stroke=0, fill=1)
        canvas.setFillColor(HexColor("#142D50"))
        canvas.setFont("Bold", 29)
        canvas.drawString(75, HEIGHT - 94, title)
        canvas.setFillColor(white)
        canvas.roundRect(48, 61, WIDTH - 96, HEIGHT - 189, 16, stroke=0, fill=1)
        size = 21.0
        while size > 14:
            line_groups = [wrap(text, "Body", size, WIDTH - 156) for text in paragraphs]
            needed = sum(len(lines) * size * 1.42 + 14 for lines in line_groups)
            if needed <= HEIGHT - 225:
                break
            size -= 0.5
        y = HEIGHT - 161
        canvas.setFillColor(HexColor("#253B56"))
        canvas.setFont("Body", size)
        for lines in line_groups:
            for line in lines:
                canvas.drawString(76, y, line)
                for match in re.finditer(r"https?://\S+", line):
                    left = 76 + pdfmetrics.stringWidth(line[:match.start()], "Body", size)
                    right = left + pdfmetrics.stringWidth(match.group(0), "Body", size)
                    canvas.linkURL(match.group(0), (left, y - 3, right, y + size), relative=0)
                y -= size * 1.42
            y -= 14
        canvas.setFillColor(HexColor("#63748B"))
        canvas.setFont("Body", 11)
        canvas.drawString(56, 30, "Учебная база кейса ПСБ. Результаты нового прогона не заявлены.")
        canvas.drawRightString(WIDTH - 56, 30, f"{index:02d} / {len(slides):02d}")
        canvas.showPage()
    canvas.save()
    print(f"Создан {target}")


if __name__ == "__main__":
    main()
