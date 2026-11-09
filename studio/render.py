"""Render a project as a 9:16 H.264/AAC short, using FFmpeg + Pillow."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from .graphics import FOCUS_PANEL, PANEL, W, H, build_frame, paste_still
from .subtitles import load_or_create_manifest, write_ass, write_callouts_ass
from .quality import check
from .utils import ROOT, assert_tool, duration_seconds, run, slugify

STILL_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
PRESETS = {
    "draft": {"width": 540, "height": 960, "crf": 23, "encoder_preset": "veryfast"},
    "production": {"width": 1080, "height": 1920, "crf": 19, "encoder_preset": "medium"},
}


def ffmpeg_filter_path(path: Path) -> str:
    """Escape an absolute path for an FFmpeg filter argument on Windows/POSIX."""
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def probe_media(path: Path) -> dict:
    output = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_name,codec_type,width,height,pix_fmt,sample_rate,channels:format=duration,size",
        "-of", "json", str(path),
    ], text=True)
    return json.loads(output)


def resolve_asset(asset: str | None, project_file: Path) -> Path | None:
    if not asset:
        return None
    path = Path(asset)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Scene asset not found: {path}. Paths are relative to project root.")
    return path


def locate_voice(project: dict, index: int, narration: str) -> Path | None:
    manifest = ROOT / "cache" / slugify(project["id"]) / "voice_manifest.json"
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    try:
        if data["narrations"][index] != narration:
            return None
        path = Path(data["files"][index])
        return path if path.exists() else None
    except (IndexError, KeyError):
        return None


def render(project: dict, project_file: Path, output: Path | None = None, *,
           preset: str = "draft", subtitle_manifest: Path | None = None,
           ) -> tuple[Path, list[str]]:
    assert_tool("ffmpeg")
    assert_tool("ffprobe")
    slug = slugify(project["id"])
    if preset not in PRESETS:
        raise ValueError(f"Unknown render preset: {preset}")
    config = PRESETS[preset]
    work = ROOT / "cache" / slug / "render"
    work.mkdir(parents=True, exist_ok=True)
    output = output or ROOT / "output" / f"{slug}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    approved = bool(project.get("review", {}).get("final_approved"))
    warnings = []
    scene_files: list[Path] = []
    actual_times, subtitle_times, voices = [], [], []
    for idx, scene in enumerate(project["scenes"]):
        voice = locate_voice(project, idx, scene["narration"])
        requested_duration = float(scene.get("duration", 6))
        voice_duration = duration_seconds(voice) if voice else None
        duration = max(requested_duration, voice_duration + 0.40) if voice_duration else requested_duration
        voices.append(voice)
        actual_times.append(duration)
        subtitle_times.append(voice_duration + 0.20 if voice_duration else requested_duration)
    custom_subtitles = subtitle_manifest is not None
    subtitle_manifest = subtitle_manifest or ROOT / "cache" / slug / "subtitles.json"
    subtitles = load_or_create_manifest(
        subtitle_manifest, project, subtitle_times, [voice is not None for voice in voices],
        auto_refresh=not custom_subtitles,
    )
    for idx, scene in enumerate(project["scenes"]):
        path = resolve_asset(scene.get("asset"), project_file)
        has_video = bool(path and path.suffix.lower() in VIDEO_EXTS)
        if path and path.suffix.lower() not in VIDEO_EXTS | STILL_EXTS:
            raise ValueError(f"Unsupported media type: {path.suffix}")
        if not path and scene.get("visual", {}).get("template") != "local_demo":
            warnings.append(f"Scene {idx+1}: placeholder art instead of a recorded demo")
        elif not path:
            warnings.append(f"Scene {idx+1}: designed local demonstration; visually verify before release")
        frame = build_frame(scene, idx+1, len(project["scenes"]), draft=not approved,
                            has_video=bool(path))
        if path and path.suffix.lower() in STILL_EXTS:
            paste_still(frame, path)
        frame_path = work / f"frame-{idx:02d}.png"
        if (config["width"], config["height"]) != (W, H):
            frame = frame.resize((config["width"], config["height"]))
        frame.save(frame_path, optimize=True)
        voice = voices[idx]
        duration = actual_times[idx]
        ass_path = work / f"subtitles-{idx:02d}.ass"
        write_ass(ass_path, subtitles["scenes"][idx]["cues"], config["width"], config["height"])
        ass_filter = ffmpeg_filter_path(ass_path)
        callout_path = work / f"callouts-{idx:02d}.ass"
        write_callouts_ass(callout_path, scene.get("edit", {}).get("callouts", []),
                           config["width"], config["height"])
        callout_filter = ffmpeg_filter_path(callout_path)
        motion = (f"zoompan=z='min(zoom+0.00018,1.012)':"
                  "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
                  f"s={config['width']}x{config['height']}:fps=30")
        if not voice:
            warnings.append(f"Scene {idx+1}: no recorded narration found (silent render)")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-threads", "2",
               "-loop", "1", "-framerate", "30", "-i", str(frame_path)]
        if has_video:
            cmd += ["-stream_loop", "-1"]
            asset_start = float(scene.get("edit", {}).get("asset_start", 0))
            if asset_start:
                cmd += ["-ss", f"{asset_start:.3f}"]
            cmd += ["-i", str(path)]
        if voice:
            cmd += ["-i", str(voice)]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        if has_video:
            scale = config["width"] / W
            focus = scene.get("visual", {}).get("layout") == "focus"
            panel = FOCUS_PANEL if focus else PANEL
            x1, y1, x2, y2 = [round(value * scale) for value in panel]
            inset = round((8 if focus else 14) * scale)
            insert_w, insert_h = x2-x1-2*inset, y2-y1-2*inset
            x, y = x1+inset, y1+inset
            if focus:
                insert = (f"[1:v]scale={insert_w}:{insert_h}:force_original_aspect_ratio=increase,"
                          f"crop={insert_w}:{insert_h},fps=30,setsar=1")
                if scene.get("edit", {}).get("motion") == "punch_in":
                    insert += (f",zoompan=z='min(zoom+0.0007,1.035)':"
                               "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
                               f"s={insert_w}x{insert_h}:fps=30")
                filt = (f"[0:v]null[base];{insert}[insert];"
                        f"[base][insert]overlay={x}:{y}:shortest=0,"
                        f"ass='{callout_filter}',ass='{ass_filter}',format=yuv420p[v]")
            else:
                filt = (f"[0:v]{motion}[base];"
                        f"[1:v]scale={insert_w}:{insert_h}:force_original_aspect_ratio=decrease,"
                        f"pad={insert_w}:{insert_h}:(ow-iw)/2:(oh-ih)/2:color=0x171d26,"
                        f"fps=30,setsar=1[insert];[base][insert]overlay={x}:{y}:shortest=0,"
                        f"ass='{callout_filter}',ass='{ass_filter}',format=yuv420p[v]")
            cmd += ["-filter_complex", filt, "-map", "[v]", "-map", "2:a:0"]
        else:
            cmd += ["-vf", f"{motion},ass='{callout_filter}',ass='{ass_filter}'",
                    "-map", "0:v:0", "-map", "1:a:0"]
        out = work / f"scene-{idx:02d}.mp4"
        cmd += ["-t", f"{duration:.3f}", "-r", "30", "-c:v", "libx264",
                "-preset", config["encoder_preset"], "-crf", str(config["crf"]), "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
                "-af", "apad", "-movflags", "+faststart", str(out)]
        run(cmd)
        scene_files.append(out)
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in scene_files), encoding="utf-8")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
         "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(output)])
    thumbnail = output.parent / f"{slug}.thumbnail.jpg"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "1.2",
         "-i", str(output), "-frames:v", "1", "-q:v", "2", str(thumbnail)])
    quality_errors, quality_warnings = check(project, require_approval=True)
    voice_manifest = ROOT / "cache" / slug / "voice_manifest.json"
    voice_info = json.loads(voice_manifest.read_text(encoding="utf-8")) if voice_manifest.exists() else {}
    if voice_info.get("engine") == "espeak":
        warnings.append("Offline eSpeak narration is a rough editorial reference, not release-quality voice")
    blockers = quality_errors + ([] if all(voices) else ["Narration audio is missing for one or more scenes"])
    capture_manifest = ROOT / "cache" / slug / "capture" / "capture-manifest.json"
    capture_evidence = (json.loads(capture_manifest.read_text(encoding="utf-8"))
                        if capture_manifest.exists() else None)
    details = {
        "project": str(project_file), "video": str(output), "thumbnail": str(thumbnail),
        "duration_seconds": sum(actual_times), "audio_present": all(voices),
        "status": "approved" if approved else "draft", "preset": preset,
        "width": config["width"], "height": config["height"],
        "subtitle_manifest": str(subtitle_manifest), "narration": voice_info,
        "capture_evidence": capture_evidence,
        "media": probe_media(output),
        "publication_ready": not blockers, "blockers": blockers,
        "warnings": quality_warnings + warnings,
    }
    (output.parent / f"{slug}.quality.json").write_text(
        json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return output, warnings
