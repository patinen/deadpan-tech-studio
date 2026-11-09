"""Generate representative-frame artifacts for human editorial review."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .graphics import BG, LIME, MUTED, PAPER, font
from .render import probe_media
from .utils import ROOT, assert_tool, run, slugify


def sample_timestamps(duration: float, count: int = 8) -> list[float]:
    if duration <= 0 or count < 2:
        raise ValueError("Contact sheet requires positive duration and at least two frames")
    start, end = min(0.6, duration * 0.05), max(0.0, duration - 0.6)
    step = (end - start) / (count - 1)
    return [round(start + index * step, 3) for index in range(count)]


def generate_contact_sheet(project: dict, video: Path) -> tuple[Path, Path]:
    assert_tool("ffmpeg")
    media = probe_media(video)
    duration = float(media["format"]["duration"])
    slug = slugify(project["id"])
    work = ROOT / "cache" / slug / "visual-qa"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    timestamps = sample_timestamps(duration)
    frames: list[Path] = []
    for index, timestamp in enumerate(timestamps):
        frame = work / f"frame-{index:02d}.jpg"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(timestamp),
             "-i", str(video), "-frames:v", "1", "-q:v", "2", str(frame)])
        frames.append(frame)

    cell_w, cell_h, label_h = 270, 480, 34
    sheet = Image.new("RGB", (cell_w * 4, (cell_h + label_h) * 2 + 58), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((22, 13), "DEADPAN TECH — VISUAL QA CONTACT SHEET",
              font=font(24, True), fill=PAPER)
    for index, (path, timestamp) in enumerate(zip(frames, timestamps)):
        with Image.open(path) as source:
            source = source.convert("RGB")
            source.thumbnail((cell_w - 12, cell_h - 12), Image.Resampling.LANCZOS)
            column, row = index % 4, index // 4
            x = column * cell_w + (cell_w - source.width) // 2
            y = 58 + row * (cell_h + label_h)
            sheet.paste(source, (x, y))
            draw.rectangle((column*cell_w+6, y+cell_h-5,
                            (column+1)*cell_w-6, y+cell_h+label_h-3), fill=(23, 29, 36))
            draw.text((column*cell_w+17, y+cell_h+1), f"{timestamp:05.2f}s",
                      font=font(18, True), fill=LIME)
    output = video.parent / f"{slug}.contact-sheet.jpg"
    sheet.save(output, quality=92, optimize=True)
    report = video.parent / f"{slug}.visual-qa.json"
    report.write_text(json.dumps({
        "video": str(video), "contact_sheet": str(output), "timestamps": timestamps,
        "media": media,
        "verified": ["representative frames extracted successfully"],
        "manual_review_required": [
            "first-two-second hook", "subtitle and callout collisions", "platform-safe crop",
            "narration naturalness", "full-video pacing", "final editorial approval"
        ],
    }, indent=2), encoding="utf-8")
    return output, report
