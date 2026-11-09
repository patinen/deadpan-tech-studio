from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def slugify(text: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return name[:62] or "untitled"


def load_project(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def narr_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def voice_file(project: dict, idx: int, text: str, ext: str, engine: str) -> Path:
    return ROOT / "cache" / slugify(project["id"]) / f"scene-{idx:02d}-{narr_hash(text)}-{engine}.{ext}"


def run(command: list[str], *, input_text: str | None = None) -> None:
    proc = subprocess.run(
        command, input=input_text, text=input_text is not None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if proc.returncode:
        stderr = proc.stderr.decode(errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(command)}\n{stderr[-3000:]}")


def assert_tool(name: str) -> None:
    if not shutil.which(name):
        raise RuntimeError(f"Required executable '{name}' is not installed or not in PATH.")


def duration_seconds(path: Path) -> float:
    assert_tool("ffprobe")
    output = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True)
    return float(output.strip())
