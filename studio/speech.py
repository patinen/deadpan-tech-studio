from __future__ import annotations

import asyncio
import json
import os
import subprocess
import hashlib
import base64
from pathlib import Path

from .utils import ROOT, assert_tool, slugify, voice_file


def narration_config(project: dict, engine: str | None = None, speed: int | None = None,
                     voice: str | None = None) -> dict:
    configured = project.get("production", {}).get("narration", {})
    return {
        "engine": engine or configured.get("engine", "espeak"),
        "speed": speed if speed is not None else int(configured.get("speed", 158)),
        "voice": voice or configured.get("voice"),
        "pronunciations": configured.get("pronunciations", {}),
        "model": configured.get("model", "models/voice.onnx"),
    }


def make_voice(project: dict, engine: str | None = None, speed: int | None = None,
               voice: str | None = None) -> list[Path]:
    """Create narration per scene. espeak = offline draft; edge/piper optional.

    SAPI: Windows built-in voice, offline and credential-free.
    Piper: place the voice model under models/voice.onnx and its matching .json next to it.
    Edge: pip install edge-tts (online, confirm service usage rights before production).
    """
    config = narration_config(project, engine, speed, voice)
    engine, speed, selected_voice = config["engine"], config["speed"], config["voice"]
    signature = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]
    outputs = []
    for i, scene in enumerate(project["scenes"]):
        narration = scene["narration"].strip()
        spoken = narration
        for written, pronounced in config["pronunciations"].items():
            spoken = spoken.replace(written, pronounced)
        ext = "mp3" if engine == "edge" else "wav"
        output = voice_file(project, i, narration, ext, f"{engine}-{signature}")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            outputs.append(output)
            continue
        if engine == "espeak":
            assert_tool("espeak")
            proc = subprocess.run(
                ["espeak", "-v", selected_voice or "en-us", "-s", str(speed),
                 "-w", str(output), spoken],
                capture_output=True, text=True
            )
            if proc.returncode:
                raise RuntimeError(proc.stderr)
        elif engine == "sapi":
            assert_tool("powershell")
            text64 = base64.b64encode(spoken.encode("utf-8")).decode("ascii")
            path64 = base64.b64encode(str(output).encode("utf-8")).decode("ascii")
            sapi_rate = max(-10, min(10, round((speed - 158) / 8)))
            voice_line = ""
            if selected_voice:
                escaped_voice = selected_voice.replace("'", "''")
                voice_line = f"$speaker.SelectVoice('{escaped_voice}');"
            script = (
                "$speaker=New-Object -ComObject SAPI.SpVoice;"
                f"{voice_line}$speaker.Rate={sapi_rate};"
                "$stream=New-Object -ComObject SAPI.SpFileStream;"
                f"$path=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{path64}'));"
                f"$text=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{text64}'));"
                "$stream.Open($path,3,$false);$speaker.AudioOutputStream=$stream;"
                "$null=$speaker.Speak($text);$stream.Close()"
            )
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            try:
                proc = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded],
                                      capture_output=True, text=True)
            except OSError as exc:
                raise RuntimeError(f"Windows SAPI could not start PowerShell: {exc}") from exc
            if proc.returncode or not output.exists():
                raise RuntimeError(proc.stderr or "Windows SAPI did not produce narration audio")
        elif engine == "piper":
            assert_tool("piper")
            model = ROOT / config["model"]
            if not model.exists():
                raise RuntimeError(f"Piper model not found at {config['model']}")
            proc = subprocess.run(
                ["piper", "--model", str(model), "--output_file", str(output),
                 "--length-scale", f"{158 / speed:.3f}", "--sentence-silence", "0.18"],
                input=spoken + "\n", capture_output=True, text=True
            )
            if proc.returncode:
                raise RuntimeError(proc.stderr)
        elif engine == "edge":
            try:
                import edge_tts
            except ImportError as exc:
                raise RuntimeError("Install optional dependency: pip install edge-tts") from exc
            edge_voice = selected_voice or os.environ.get("EDGE_VOICE", "en-US-AndrewNeural")
            rate = f"{max(-50, min(50, round((speed - 158) / 1.58))):+d}%"
            try:
                asyncio.run(edge_tts.Communicate(spoken, edge_voice, rate=rate).save(str(output)))
            except Exception as exc:
                raise RuntimeError(f"Edge TTS did not return audio: {exc}") from exc
        else:
            raise ValueError("Engine must be 'espeak', 'sapi', 'piper', or 'edge'")
        outputs.append(output)
    manifest = ROOT / "cache" / slugify(project["id"]) / "voice_manifest.json"
    manifest.write_text(json.dumps({"engine": engine, "voice": selected_voice, "speed": speed,
        "files": [str(p) for p in outputs],
        "narrations": [scene["narration"] for scene in project["scenes"]]}, indent=2), encoding="utf-8")
    return outputs
