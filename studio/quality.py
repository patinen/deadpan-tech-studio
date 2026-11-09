from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

HYPE = ("revolutionary", "game-changing", "insane ai", "100% guaranteed", "unbelievable")
VALID_KINDS = {"hook", "problem", "demo", "payoff", "explain", "comparison"}


def check(project: dict, require_approval: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for key in ("id", "title", "hook"):
        if not isinstance(project.get(key), str) or not project[key].strip():
            errors.append(f"Missing/empty required field: {key}")
    scenes = project.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 3:
        errors.append("Expected at least 3 scenes")
        scenes = []
    total = 0
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            errors.append(f"Scene {i} must be an object")
            continue
        if scene.get("kind") not in VALID_KINDS:
            warnings.append(f"Scene {i}: unknown kind '{scene.get('kind')}'")
        if not scene.get("narration", "").strip():
            errors.append(f"Scene {i}: narration missing")
        if not scene.get("headline", "").strip():
            errors.append(f"Scene {i}: headline missing")
        if len(scene.get("headline", "")) > 55:
            warnings.append(f"Scene {i}: headline may not fit")
        if len(scene.get("caption", "")) > 80:
            warnings.append(f"Scene {i}: caption may not fit")
        try:
            duration = float(scene.get("duration", 5))
            if not 1 <= duration <= 40:
                errors.append(f"Scene {i}: duration must be between 1 and 40 seconds")
            total += duration
        except (ValueError, TypeError):
            errors.append(f"Scene {i}: invalid duration")
        combined = f"{scene.get('narration', '')} {scene.get('headline', '')}".lower()
        if any(phrase in combined for phrase in HYPE):
            warnings.append(f"Scene {i}: potential generic hype wording")
        if scene.get("asset") and not Path(scene["asset"]).is_absolute():
            warnings.append(f"Scene {i}: verify relative asset path resolves from project root")
    if not 20 <= total <= 60:
        warnings.append(f"Nominal duration is {total:.1f}s; target 25–40s")
    sources = project.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(url, str) or
            urlparse(url).scheme not in {"https", "http"} for url in sources):
        errors.append("sources must be an array of full http(s) URLs")
    review = project.get("review", {})
    for key in ("facts_checked", "assets_licensed", "final_approved"):
        if not review.get(key, False):
            warnings.append(f"Human review pending: {key}")
            if require_approval:
                errors.append(f"Publication blocked until review.{key}=true")
    if not sources:
        warnings.append("No source references recorded: verify any factual claims")
    if all(not scene.get("asset") and
           scene.get("visual", {}).get("template") != "local_demo"
           for scene in scenes if isinstance(scene, dict)):
        warnings.append("No real footage/screenshots added: draft preview only")
    elif any(scene.get("visual", {}).get("template") == "local_demo"
             for scene in scenes if isinstance(scene, dict)):
        warnings.append("Locally designed demo visuals require human verification against the real workflow")
    return errors, warnings
