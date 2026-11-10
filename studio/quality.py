from __future__ import annotations

import hashlib
import math
from pathlib import Path
from urllib.parse import urlparse
from .utils import ROOT, slugify

HYPE = ("revolutionary", "game-changing", "insane ai", "100% guaranteed", "unbelievable")
VALID_KINDS = {"hook", "problem", "demo", "payoff", "explain", "comparison"}


def publication_review_keys(project: dict) -> tuple[str, ...]:
    base = ("facts_checked", "assets_licensed", "final_approved")
    if project.get("editorial") or project.get("production", {}).get("authentic_demo"):
        return base + ("script_approved", "demo_verified", "creative_approved")
    return base


def _asset_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def authentic_demo_issues(project: dict, scenes: list[dict]) -> list[str]:
    authentic = project.get("production", {}).get("authentic_demo")
    if not isinstance(authentic, dict) or not authentic.get("required"):
        return []
    required = authentic.get("shot_ids", [])
    if not isinstance(required, list) or not required:
        return ["Authentic editorial footage requirements do not name any shot ids"]
    by_id = {scene.get("id"): scene for scene in scenes if isinstance(scene, dict)}
    intake = project.get("editorial", {}).get("demo_intake", {})
    issues = []
    for shot_id in required:
        scene = by_id.get(shot_id, {})
        asset = scene.get("asset")
        asset_path = _asset_path(asset)
        evidence = intake.get(shot_id) if isinstance(intake, dict) else None
        if not asset_path or not asset_path.is_file():
            issues.append(f"Authentic editorial footage missing for: {shot_id}")
            continue
        if not isinstance(evidence, dict):
            issues.append(f"Authentic editorial intake evidence missing for: {shot_id}")
            continue
        if evidence.get("operator_owned") is not True:
            issues.append(f"Authentic editorial intake ownership is not asserted for: {shot_id}")
            continue
        evidence_path = _asset_path(evidence.get("imported_asset"))
        if not evidence_path or evidence_path.resolve() != asset_path.resolve():
            issues.append(f"Authentic editorial intake path does not match scene asset for: {shot_id}")
            continue
        expected_hash = evidence.get("sha256")
        try:
            actual_hash = _sha256(asset_path)
        except OSError:
            issues.append(f"Authentic editorial footage cannot be read for: {shot_id}")
            continue
        if not isinstance(expected_hash, str) or actual_hash != expected_hash:
            issues.append(f"Authentic editorial intake hash does not match footage for: {shot_id}")
    return issues


def publication_readiness(project: dict, *, extra_blockers: list[str] | None = None) -> dict:
    """Return the single publication decision used by review and rendering."""
    errors, warnings = check(project, require_approval=True)
    blockers = list(dict.fromkeys(errors + list(extra_blockers or [])))
    return {"ready": not blockers, "status": "approved" if not blockers else "draft",
            "blockers": blockers, "warnings": warnings}


def is_publication_approved(project: dict) -> bool:
    return publication_readiness(project)["ready"]


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
            if not math.isfinite(duration) or not 1 <= duration <= 40:
                errors.append(f"Scene {i}: duration must be between 1 and 40 seconds")
            total += duration
            for callout in scene.get("edit", {}).get("callouts", []):
                start, end = float(callout.get("start", -1)), float(callout.get("end", -1))
                if (not math.isfinite(start) or not math.isfinite(end) or
                        start < 0 or end <= start or end > duration):
                    errors.append(f"Scene {i}: callout timing must stay within scene duration")
            edit = scene.get("edit", {})
            zoom = float(edit.get("zoom", 1.0))
            focus_x = float(edit.get("focus_x", 0.5))
            focus_y = float(edit.get("focus_y", 0.5))
            if not math.isfinite(zoom) or not 1 <= zoom <= 2:
                errors.append(f"Scene {i}: edit.zoom must be between 1 and 2")
            if (not math.isfinite(focus_x) or not math.isfinite(focus_y) or
                    not 0 <= focus_x <= 1 or not 0 <= focus_y <= 1):
                errors.append(f"Scene {i}: edit focus coordinates must be between 0 and 1")
        except (ValueError, TypeError):
            errors.append(f"Scene {i}: invalid duration")
        combined = f"{scene.get('narration', '')} {scene.get('headline', '')}".lower()
        if any(phrase in combined for phrase in HYPE):
            warnings.append(f"Scene {i}: potential generic hype wording")
        generated_capture = (project.get("production", {}).get("capture") in {"http_server", "recipe"} and
                             str(scene.get("asset", "")).startswith("cache/"))
        if scene.get("asset") and not Path(scene["asset"]).is_absolute() and not generated_capture:
            warnings.append(f"Scene {i}: verify relative asset path resolves from project root")
    if not 20 <= total <= 60:
        warnings.append(f"Nominal duration is {total:.1f}s; target 25–40s")
    sources = project.get("sources", [])
    if not isinstance(sources, list) or any(not isinstance(url, str) or
            urlparse(url).scheme not in {"https", "http"} for url in sources):
        errors.append("sources must be an array of full http(s) URLs")
    review = project.get("review", {})
    for key in publication_review_keys(project):
        if not review.get(key, False):
            warnings.append(f"Human review pending: {key}")
            if require_approval:
                errors.append(f"Publication blocked until review.{key}=true")
    editorial = project.get("editorial")
    if isinstance(editorial, dict):
        if editorial.get("publication_blocked") is not False:
            message = ("Editorial publication_blocked must be explicitly set to false after "
                       "all listed blockers are resolved by a human")
            warnings.append(message)
            if require_approval:
                errors.append(message)
        explicit_blockers = editorial.get("publication_blockers", [])
        if explicit_blockers:
            message = f"Unresolved editorial publication blockers: {len(explicit_blockers)}"
            warnings.append(message)
            if require_approval:
                errors.append(message)
    if not sources:
        warnings.append("No source references recorded: verify any factual claims")
    if all(not scene.get("asset") and
           scene.get("visual", {}).get("template") != "local_demo"
           for scene in scenes if isinstance(scene, dict)):
        warnings.append("No real footage/screenshots added: draft preview only")
    elif any(scene.get("visual", {}).get("template") == "local_demo"
             for scene in scenes if isinstance(scene, dict)):
        warnings.append("Locally designed demo visuals require human verification against the real workflow")
    if project.get("production", {}).get("capture") == "http_server":
        missing = [scene.get("asset") for scene in scenes
                   if scene.get("asset") and not (ROOT / scene["asset"]).is_file()]
        manifest = ROOT / "cache" / slugify(project.get("id", "")) / "capture" / "capture-manifest.json"
        if missing or not manifest.is_file():
            warnings.append("Authentic demo capture is missing or stale: run studio.py capture <project>")
        else:
            warnings.append("Authentic local capture exists; human must still verify actions and framing")
    if project.get("production", {}).get("capture") == "recipe":
        manifest = ROOT / "cache" / slugify(project.get("id", "")) / "capture" / "capture-manifest.json"
        if not manifest.is_file():
            warnings.append("Verified recipe capture is missing: run studio.py capture <project>")
        else:
            warnings.append("Verified recipe capture exists; human must still verify actions and framing")
    authentic = project.get("production", {}).get("authentic_demo")
    if isinstance(authentic, dict) and authentic.get("required"):
        footage_issues = authentic_demo_issues(project, scenes)
        for message in footage_issues:
            warnings.append(message + "; placeholder draft only")
            if require_approval:
                errors.append(message)
        if not project.get("review", {}).get("demo_verified"):
            warnings.append("Imported footage has not been human-verified against the editorial demonstration")
    return errors, warnings
