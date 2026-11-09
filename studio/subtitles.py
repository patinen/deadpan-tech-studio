"""Editable phrase-level subtitle timing for short-form narration."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .utils import narr_hash


def group_phrases(text: str, max_words: int = 6) -> list[str]:
    """Split narration into readable phrases without inventing word timestamps."""
    words = text.split()
    phrases: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        boundary = bool(re.search(r"[.!?;:,]$", word)) and len(current) >= 2
        if len(current) >= max_words or boundary:
            phrases.append(" ".join(current))
            current = []
    if current:
        phrases.append(" ".join(current))
    return phrases


def time_phrases(text: str, duration: float, *, lead: float = 0.12,
                 tail: float = 0.20) -> list[dict]:
    """Allocate phrase windows proportionally inside a measured scene duration."""
    phrases = group_phrases(text)
    if not phrases:
        return []
    usable = max(0.2, duration - lead - tail)
    weights = [max(1, len(re.findall(r"\w+", phrase))) for phrase in phrases]
    unit = usable / sum(weights)
    cues, cursor = [], lead
    for index, (phrase, weight) in enumerate(zip(phrases, weights)):
        end = duration - tail if index == len(phrases) - 1 else cursor + weight * unit
        cues.append({"start": round(cursor, 3), "end": round(end, 3), "text": phrase})
        cursor = end
    return cues


def build_manifest(project: dict, durations: list[float], audio_aligned: list[bool]) -> dict:
    return {
        "version": 1,
        "note": "Editable phrase timing in seconds, relative to each scene.",
        "scenes": [
            {
                "index": index,
                "narration_hash": narr_hash(scene["narration"]),
                "timing_source": "measured_audio" if aligned else "nominal_scene_duration",
                "duration": round(duration, 3),
                "cues": time_phrases(scene["narration"], duration),
            }
            for index, (scene, duration, aligned) in enumerate(
                zip(project["scenes"], durations, audio_aligned)
            )
        ],
    }


def validate_manifest(manifest: dict, project: dict, durations: list[float]) -> None:
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(project["scenes"]):
        raise ValueError("Subtitle manifest must contain one entry per scene")
    for index, (entry, scene, duration) in enumerate(zip(scenes, project["scenes"], durations)):
        if entry.get("narration_hash") != narr_hash(scene["narration"]):
            raise ValueError(f"Subtitle scene {index + 1} is stale; narration changed")
        previous = 0.0
        for cue in entry.get("cues", []):
            start, end = float(cue["start"]), float(cue["end"])
            if not str(cue.get("text", "")).strip() or start < previous or end <= start or end > duration + 0.05:
                raise ValueError(f"Invalid subtitle timing in scene {index + 1}")
            previous = end


def load_or_create_manifest(path: Path, project: dict, durations: list[float],
                            audio_aligned: list[bool]) -> dict:
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validate_manifest(manifest, project, durations)
        return manifest
    manifest = build_manifest(project, durations, audio_aligned)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def _ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, hundredths = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{hundredths:02d}"


def write_ass(path: Path, cues: list[dict], width: int, height: int) -> None:
    """Write safe-margin, high-contrast ASS subtitles for one scene."""
    size = 31 if width == 540 else 62
    margin_v = 92 if height == 960 else 184
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Dynamic,Arial,{size},&H00F4F4ED,&H000000FF,&H00101518,&HCC101518,-1,0,0,0,100,100,0,0,3,2,0,2,42,42,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cue in cues:
        text = str(cue["text"]).replace("{", "(").replace("}", ")").replace("\n", " ")
        first, separator, rest = text.partition(" ")
        if separator:
            text = rf"{{\c&H57F4C9&}}{first}{{\rDynamic}} {rest}"
        events.append(f"Dialogue: 0,{_ass_time(float(cue['start']))},{_ass_time(float(cue['end']))},Dynamic,,0,0,0,,{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
