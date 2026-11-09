from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

from .utils import ROOT, assert_tool, slugify, voice_file


def make_voice(project: dict, engine: str = "espeak", speed: int = 158) -> list[Path]:
    """Create narration per scene. espeak = offline draft; edge/piper optional.

    Piper: place the voice model under models/voice.onnx and its matching .json next to it.
    Edge: pip install edge-tts (online, confirm service usage rights before production).
    """
    outputs = []
    for i, scene in enumerate(project["scenes"]):
        narration = scene["narration"].strip()
        ext = "mp3" if engine == "edge" else "wav"
        output = voice_file(project, i, narration, ext, engine)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            outputs.append(output)
            continue
        if engine == "espeak":
            assert_tool("espeak")
            proc = subprocess.run(
                ["espeak", "-v", "en-us", "-s", str(speed), "-w", str(output), narration],
                capture_output=True, text=True
            )
            if proc.returncode:
                raise RuntimeError(proc.stderr)
        elif engine == "piper":
            assert_tool("piper")
            model = ROOT / "models" / "voice.onnx"
            if not model.exists():
                raise RuntimeError("Piper model not found at models/voice.onnx")
            proc = subprocess.run(
                ["piper", "--model", str(model), "--output_file", str(output)],
                input=narration + "\n", capture_output=True, text=True
            )
            if proc.returncode:
                raise RuntimeError(proc.stderr)
        elif engine == "edge":
            try:
                import edge_tts
            except ImportError as exc:
                raise RuntimeError("Install optional dependency: pip install edge-tts") from exc
            voice = os.environ.get("EDGE_VOICE", "en-US-AndrewNeural")
            asyncio.run(edge_tts.Communicate(narration, voice).save(str(output)))
        else:
            raise ValueError("Engine must be 'espeak', 'piper', or 'edge'")
        outputs.append(output)
    manifest = ROOT / "cache" / slugify(project["id"]) / "voice_manifest.json"
    manifest.write_text(json.dumps({"engine": engine, "files": [str(p) for p in outputs], "narrations": [scene["narration"] for scene in project["scenes"]]}, indent=2), encoding="utf-8")
    return outputs
