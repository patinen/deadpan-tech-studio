"""Brand-styled 9:16 layouts (no generative imagery required)."""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 540, 960
PANEL = (39, 329, 501, 702)
FOCUS_PANEL = (16, 150, 524, 800)
FOCUS_LAYOUTS = {"focus", "focus_alt", "browser_demo", "audio_demo", "automation_demo"}
BG = (12, 15, 22)
LIME = (201, 244, 87)
PAPER = (244, 244, 237)
MUTED = (154, 162, 167)
CORAL = (249, 119, 103)


def font(size: int, bold: bool = False):
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(text: str, draw: ImageDraw.ImageDraw, face, width: int) -> list[str]:
    words = text.split()
    result, line = [], ""
    for word in words:
        test = f"{line} {word}".strip()
        if draw.textbbox((0, 0), test, font=face)[2] <= width:
            line = test
        else:
            if line:
                result.append(line)
            line = word
    if line:
        result.append(line)
    return result


def text_lines(draw, xy, text: str, face, fill, width: int, line_height: int | None = None,
               max_lines: int = 4):
    x, y = xy
    line_height = line_height or int(face.size * 1.22)
    lines = wrap(text, draw, face, width)
    for line in lines[:max_lines]:
        draw.text((x, y), line, font=face, fill=fill, stroke_width=0)
        y += line_height
    return y


def scene_panel(scene: dict) -> tuple[int, int, int, int]:
    """Return responsive demo geometry while preserving legacy inset projects."""
    layout = scene.get("visual", {}).get("layout")
    if layout not in FOCUS_LAYOUTS:
        return PANEL
    headline = scene.get("headline", "DEMONSTRATION").upper()
    size = 38 if len(headline) <= 22 else 31
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    line_count = max(1, min(2, len(wrap(headline, draw, font(size, True), 492))))
    headline_bottom = 92 + line_count * int(size * 1.05)
    top = max(150, headline_bottom + 18)
    if layout == "audio_demo":
        return (28, top, 512, 790)
    if layout == "automation_demo":
        return (16, top, 524, 810)
    return (16, top, 524, 800)


def _draw_placeholder(draw, scene, number: int):
    x1, y1, x2, y2 = PANEL
    draw.rounded_rectangle((x1+12, y1+12, x2-12, y2-12), radius=14,
                           fill=(23, 29, 36), outline=(63, 73, 70), width=2)
    kind = scene.get("kind", "demo")
    if kind == "problem":
        lines = [("file_01.pdf", "COPY  →  PASTE"), ("file_02.pdf", "COPY  →  PASTE"),
                 ("file_03.pdf", "COPY  →  PASTE")]
        for idx, (file, action) in enumerate(lines):
            y = y1 + 65 + idx * 80
            draw.rounded_rectangle((x1+30, y, x2-30, y+60), 8, fill=(32,39,46))
            draw.text((x1+44, y+8), file, font=font(17), fill=PAPER)
            draw.text((x1+44, y+32), action, font=font(14, True), fill=CORAL)
    elif kind == "demo":
        draw.text((x1+40,y1+52), "# a better workflow", font=font(24,True), fill=LIME)
        for idx, line in enumerate(["extract_fields(files)", "validate(data)", "write_to_spreadsheet(data)"]):
            draw.text((x1+38,y1+108+idx*53), line, font=font(17), fill=PAPER)
        draw.rounded_rectangle((x1+38,y1+286,x2-38,y1+323),radius=8,fill=(49,72,51))
        draw.text((x1+60,y1+294),"✓ PROCESS COMPLETE",font=font(16,True),fill=LIME)
    elif kind == "payoff":
        draw.text((x1+46,y1+88), "BEFORE", font=font(22,True), fill=CORAL)
        draw.text((x1+46,y1+128), "too many clicks", font=font(26), fill=PAPER)
        draw.line((x1+40,y1+188,x2-40,y1+188),fill=(70,80,79),width=2)
        draw.text((x1+46,y1+218), "AFTER", font=font(22,True), fill=LIME)
        draw.text((x1+46,y1+258), "one repeatable flow", font=font(25), fill=PAPER)
    else:
        for n in range(5):
            start = x1+50+n*75
            endy = y1+175 + int(33*math.sin(n))
            draw.rounded_rectangle((start,endy,start+52,endy+52),radius=11,
                                   fill=LIME if n == 2 else (50,60,66))
        draw.text((x1+62,y1+265),"HOW IS THIS STILL A THING?",font=font(17,True),fill=PAPER)
    # This notice is intentionally visible in prototypes.
    draw.text((x1+35,y2-43),"ILLUSTRATIVE • ADD REAL FOOTAGE",font=font(12,True),fill=MUTED)


def _draw_local_demo(draw, scene: dict):
    """Reusable terminal/browser visual for workflows reproducible on the local machine."""
    x1, y1, x2, y2 = PANEL
    visual = scene.get("visual", {})
    mode = visual.get("mode", "terminal")
    draw.rounded_rectangle((x1+12, y1+12, x2-12, y2-12), radius=14,
                           fill=(17, 22, 29), outline=(80, 94, 82), width=2)
    draw.rounded_rectangle((x1+25, y1+28, x2-25, y1+66), radius=8, fill=(32, 39, 47))
    for n, color in enumerate((CORAL, (246, 201, 90), LIME)):
        draw.ellipse((x1+40+n*24, y1+40, x1+52+n*24, y1+52), fill=color)
    if mode == "browser":
        draw.rounded_rectangle((x1+125, y1+37, x2-43, y1+58), radius=7, fill=(48, 57, 66))
        draw.text((x1+140, y1+39), visual.get("address", "localhost:8000"),
                  font=font(12), fill=PAPER)
        draw.text((x1+45, y1+105), visual.get("title", "PROJECT FILES"),
                  font=font(20, True), fill=LIME)
        for idx, item in enumerate(visual.get("items", ["index.html", "notes.txt", "assets/"])):
            y = y1 + 154 + idx * 48
            draw.rounded_rectangle((x1+42, y, x2-42, y+35), radius=7, fill=(31, 38, 46))
            draw.text((x1+57, y+7), item, font=font(15), fill=PAPER)
    else:
        draw.text((x1+42, y1+98), visual.get("prompt", "C:\\project>"),
                  font=font(16, True), fill=MUTED)
        draw.text((x1+42, y1+137), visual.get("command", "python -m http.server"),
                  font=font(21, True), fill=LIME)
        draw.text((x1+42, y1+203), visual.get("result", "Serving on port 8000"),
                  font=font(16), fill=PAPER)
        draw.rounded_rectangle((x1+42, y1+254, x2-42, y1+296), radius=8, fill=(38, 61, 43))
        draw.text((x1+58, y1+265), "LOCAL SERVER RUNNING", font=font(15, True), fill=LIME)
    draw.text((x1+35, y2-43), "LOCALLY REPRODUCIBLE DEMO", font=font(12, True), fill=MUTED)


def build_frame(scene: dict, number: int, count: int, brand: str | None = None,
                draft: bool = True, has_video: bool = False) -> Image.Image:
    brand = brand or os.environ.get("BRAND_NAME", "DEADPAN TECH")
    img = Image.new("RGB", (W,H))
    pix = img.load()
    for y in range(H):
        factor = y/H
        for x in range(W):
            v = int(5 * factor + 3*math.sin(x/96 + y/240))
            pix[x,y] = (BG[0]+v, BG[1]+v, BG[2]+v)
    d = ImageDraw.Draw(img)
    d.rectangle((0,0, W,13), fill=LIME)
    layout = scene.get("visual", {}).get("layout")
    if layout in FOCUS_LAYOUTS:
        d.rounded_rectangle((24, 35, 67, 79), radius=9, fill=LIME)
        d.text((36, 45), "D/", font=font(23, True), fill=BG)
        brand_color = LIME if layout in {"focus_alt", "audio_demo"} else PAPER
        d.text((80, 44), brand[:24].upper(), font=font(18, True), fill=brand_color)
        d.text((450, 46), f"{number:02d}/{count:02d}", font=font(14, True), fill=MUTED)
        if layout in {"focus_alt", "browser_demo", "audio_demo", "automation_demo"}:
            d.rectangle((24, 84, 190, 89), fill=LIME)
        if layout == "browser_demo":
            d.text((405, 82), "BROWSER", font=font(12, True), fill=LIME)
        elif layout == "audio_demo":
            for bar, height in enumerate((8, 18, 30, 16, 25, 11)):
                x = 404 + bar * 17
                d.rounded_rectangle((x, 86-height//2, x+8, 86+height//2), 3, fill=LIME)
        elif layout == "automation_demo":
            d.text((384, 82), "BEFORE  →  AFTER", font=font(11, True), fill=LIME)
        headline = scene.get("headline", "DEMONSTRATION").upper()
        size = 38 if len(headline) <= 22 else 31
        text_lines(d, (24, 92), headline, font(size, True), PAPER, 492,
                   line_height=int(size*1.05), max_lines=2)
        panel = scene_panel(scene)
        d.rounded_rectangle(panel, radius=18, fill=(18, 23, 30),
                            outline=(75, 88, 80), width=2)
        if not has_video:
            x1, y1, x2, y2 = panel
            label = scene.get("visual", {}).get("placeholder", "AUTHENTIC RECORDING REQUIRED")
            label = str(label).upper()
            d.rounded_rectangle((x1 + 30, (y1 + y2) // 2 - 54,
                                 x2 - 30, (y1 + y2) // 2 + 54),
                                radius=14, fill=(27, 34, 42), outline=CORAL, width=2)
            d.text((x1 + 48, (y1 + y2) // 2 - 30), "MISSING REAL FOOTAGE",
                   font=font(17, True), fill=CORAL)
            text_lines(d, (x1 + 48, (y1 + y2) // 2 + 4), label,
                       font(13, True), MUTED, x2 - x1 - 96, max_lines=2)
        d.line((24, 885, 516, 885), fill=(67, 75, 72), width=2)
        status = "DRAFT · NOT APPROVED" if draft else "ORIGINAL TECH EXPLAINERS"
        d.text((24, 902), status, font=font(13, True), fill=CORAL if draft else MUTED)
        d.text((458, 902), "9:16", font=font(13, True), fill=MUTED)
        return img
    # offset tech stripes
    for i in range(6):
        x= W-185+i*47
        d.polygon([(x,50),(x+24,50),(x-25,105),(x-49,105)], fill=(34,43,43))
    d.rounded_rectangle((38,47,81,91),radius=9, fill=LIME)
    d.text((50,57),"D/",font=font(23,True),fill=BG)
    d.text((95,57), brand[:24].upper(),font=font(20,True),fill=PAPER)
    d.text((39,125),f"TECH, MINUS THE NONSENSE   /   {number:02d}.{count:02d}",
           font=font(12,True),fill=LIME)
    headline = scene.get("headline", "NO HEADLINE").upper()
    size = 50 if len(headline) <= 19 else 40 if len(headline) <= 29 else 33
    text_lines(d,(38,166),headline,font(size,True),PAPER,470,line_height=int(size*1.1),max_lines=3)
    x1,y1,x2,y2 = PANEL
    d.rounded_rectangle(PANEL,radius=22,fill=(23,28,37),outline=(74,84,72),width=2)
    if not has_video:
        if scene.get("visual", {}).get("template") == "local_demo":
            _draw_local_demo(d, scene)
        else:
            _draw_placeholder(d, scene, number)
    d.text((39,731),"THE SHORT VERSION",font=font(15,True),fill=LIME)
    caption = scene.get("caption", "")
    text_lines(d,(39,770),caption,font(33,True),PAPER,455,line_height=43,max_lines=3)
    d.line((39,893,501,893), fill=(67,75,72), width=2)
    status = "DRAFT · NOT APPROVED" if draft else "ORIGINAL TECH EXPLAINERS"
    d.text((39,907),status,font=font(13,True),fill=CORAL if draft else MUTED)
    d.text((441,907),"9:16",font=font(13,True),fill=MUTED)
    return img


def paste_still(frame: Image.Image, path: Path):
    x1,y1,x2,y2 = PANEL
    with Image.open(path) as source:
        source = ImageOps.exif_transpose(source.convert("RGB"))
        available = (x2-x1-28,y2-y1-28)
        source.thumbnail(available, Image.Resampling.LANCZOS)
        pos = ((x1+x2-source.width)//2, (y1+y2-source.height)//2)
        frame.paste(source,pos)
