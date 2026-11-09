from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from .utils import ROOT, slugify


def create_script(idea: str, *, model: str | None = None, sources: list[str] | None = None) -> dict:
    """Draft a script with Gemini; the draft still needs fact checking and footage."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY in your environment or .env file")
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    system = (ROOT / "prompts" / "script_system.md").read_text(encoding="utf-8")
    voice = (ROOT / "prompts" / "brand_voice.md").read_text(encoding="utf-8")
    supplied = "\n".join(sources or []) or "No verified sources supplied. Don't invent any."
    payload = {
        "system_instruction": {"parts": [{"text": system + "\n\n" + voice}]},
        "contents": [{"role": "user", "parts": [{"text": f"Idea: {idea}\nVerified URLs supplied: {supplied}"}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}
    }
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    try:
        script = data["candidates"][0]["content"]["parts"][0]["text"]
        output = json.loads(script)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("Model did not return valid project JSON") from exc
    output["id"] = slugify(output.get("id") or idea)
    output["sources"] = sources or []
    output["review"] = {"facts_checked": False, "assets_licensed": False, "final_approved": False}
    for scene in output.get("scenes", []):
        scene["asset"] = None
    return output
