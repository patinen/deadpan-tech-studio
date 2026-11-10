"""Convert editorial briefs to blocked projects and intake operator-owned footage."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .quality import check
from .render import VIDEO_EXTS, probe_media
from .utils import ROOT, slugify


class BridgeError(RuntimeError):
    pass


GENERIC_HOOKS = ("see how", "learn how", "generate files", "discover how", "this feature", "you can now")
GENERIC_PROBLEMS = ("causes friction", "saves time", "boost productivity", "switching apps")


def evaluate_editorial(brief: dict) -> dict:
    """Separate evidence integrity, production readiness, and creative quality."""
    factual_reasons, production_reasons, creative_reasons, suggestions = [], [], [], []
    sources = brief.get("sources", [])
    claims = brief.get("claims", [])
    source_set = set(sources) if isinstance(sources, list) else set()
    unsupported = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            unsupported.append("(malformed claim)")
            continue
        evidence = claim.get("evidence_urls", [])
        if (not isinstance(evidence, list) or not evidence or
                any(not isinstance(url, str) for url in evidence) or
                not set(evidence).issubset(source_set)):
            unsupported.append(str(claim.get("text", "(malformed claim)")))
    if not source_set:
        factual_reasons.append("No canonical source URL is attached.")
    if unsupported:
        factual_reasons.append(f"{len(unsupported)} claim(s) lack attached evidence URLs.")
    factual_score = 100 - (50 if not source_set else 0) - min(50, len(unsupported) * 20)

    shots = brief.get("shots", [])
    demonstrations = brief.get("required_real_demonstrations", [])
    if not demonstrations:
        production_reasons.append("No required real demonstration is defined.")
        suggestions.append("Specify the exact input, action, and visible result that must be captured.")
    if not isinstance(shots, list) or len(shots) < 3:
        production_reasons.append("Fewer than three planned shots cannot establish result, action, and payoff.")
    long_shots = []
    for index, shot in enumerate(shots if isinstance(shots, list) else []):
        try:
            if isinstance(shot, dict) and float(shot.get("seconds", 0)) >= 8:
                long_shots.append(index + 1)
        except (TypeError, ValueError):
            production_reasons.append(f"Shot {index + 1} has an invalid duration.")
    if len(long_shots) >= 2:
        production_reasons.append(f"Shots {long_shots} are long static holds unless real interaction proves otherwise.")
        suggestions.append("Split long shots around visible cursor actions, edits, and result changes.")
    review = brief.get("review", {})
    if not review.get("demo_verified"):
        production_reasons.append("The real product demonstration is not verified.")
    production_score = max(0, 100 - len(production_reasons) * 22)

    script = brief.get("script", [])
    hook = script[0].strip() if script and isinstance(script[0], str) else ""
    problem = str(brief.get("viewer_pain_point", ""))
    benefit = str(brief.get("proposed_benefit", ""))
    demo_text = " ".join(str(item) for item in demonstrations)
    if not hook or hook.lower().startswith(GENERIC_HOOKS):
        creative_reasons.append("The opening repeats a product feature instead of showing a specific result or frustration.")
        suggestions.append("Open on the harmless finished file and name the concrete task it fixes.")
    if any(phrase in problem.lower() for phrase in GENERIC_PROBLEMS) or len(problem.split()) < 8:
        creative_reasons.append("The viewer problem is generic and does not identify a recognizable task or consequence.")
        suggestions.append("Name the exact before-state, such as copying rough meeting notes into a second editor.")
    if len(benefit.split()) < 9 or not any(word in benefit.lower() for word in ("file", "document", "notes", "draft", "copy", "edit")):
        creative_reasons.append("The payoff is not a concrete, observable before/after result.")
        suggestions.append("State what usable artifact exists at the end and what manual step disappeared.")
    if len(demo_text.split()) < 12 or not any(word in demo_text.lower() for word in ("upload", "type", "edit", "highlight", "select", "click", "result")):
        creative_reasons.append("The demonstration plan lacks sufficiently specific on-screen actions.")
        suggestions.append("List the harmless input, exact interaction, correction, and final visible output.")
    shot_phrases = [re.sub(r"\W+", " ", str(shot.get("shot", "")).lower()).strip()
                    for shot in shots if isinstance(shot, dict)]
    if len(shot_phrases) != len(set(shot_phrases)):
        creative_reasons.append("The visual plan repeats the same shot instruction.")
        suggestions.append("Assign a distinct purpose to every shot: result, input/action, correction, payoff.")
    creative_score = max(0, 100 - len(creative_reasons) * 22)
    return {
        "factual_validity": {"score": factual_score, "status": "pass" if not factual_reasons else "blocked",
                             "reasons": factual_reasons},
        "production_readiness": {"score": production_score, "status": "ready_for_capture" if not production_reasons else "blocked",
                                 "reasons": production_reasons},
        "creative_quality": {"score": creative_score, "status": "human_review_required" if creative_reasons else "candidate",
                             "reasons": creative_reasons},
        "revision_suggestions": list(dict.fromkeys(suggestions)),
        "human_creative_approval_required": True,
    }


def _headline(narration: str, index: int, total: int) -> str:
    if index == 0:
        return "SHOW THE RESULT FIRST"
    if index == total - 1:
        return "VERIFY THE PAYOFF"
    words = re.findall(r"[A-Za-z0-9]+", narration)[:6]
    return " ".join(words).upper()[:55] or "REAL DEMONSTRATION"


def convert_brief(brief: dict, *, project_id: str | None = None,
                  source_brief: str | None = None) -> dict:
    gate = evaluate_editorial(brief)
    if gate["factual_validity"]["status"] != "pass":
        raise BridgeError("Editorial brief failed factual integrity: " + "; ".join(gate["factual_validity"]["reasons"]))
    shots = brief.get("shots", [])
    if not isinstance(shots, list) or len(shots) < 3 or any(not isinstance(shot, dict) for shot in shots):
        raise BridgeError("Editorial brief requires at least three shots")
    project_id = slugify(project_id or brief.get("id") or brief.get("title", "editorial-project"))
    layouts = ("focus", "focus_alt", "browser_demo", "focus")
    scenes = []
    for index, shot in enumerate(shots):
        narration = shot.get("narration", "")
        if not isinstance(narration, str) or not narration.strip():
            raise BridgeError(f"Editorial shot {index + 1} requires narration")
        narration = narration.strip()
        try:
            seconds = float(shot["seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BridgeError(f"Editorial shot {index + 1} has an invalid duration") from exc
        if not isinstance(shot.get("shot"), str) or not shot["shot"].strip():
            raise BridgeError(f"Editorial shot {index + 1} requires a visual instruction")
        scenes.append({
            "id": f"shot-{index + 1:02d}",
            "kind": "hook" if index == 0 else "payoff" if index == len(shots) - 1 else "demo",
            "headline": _headline(narration, index, len(shots)),
            "narration": narration,
            "caption": narration[:80],
            "asset": None,
            "duration": seconds,
            "visual": {"layout": layouts[index % len(layouts)],
                       "placeholder": "AUTHENTIC RECORDING REQUIRED"},
            "edit": {"asset_start": 0.0, "zoom": 1.0, "focus_x": 0.5, "focus_y": 0.5},
            "editorial_shot": shot["shot"],
        })
    blockers = list(brief.get("publication_blockers", []))
    blockers.extend(gate["creative_quality"]["reasons"])
    blockers.append("Converted project requires human creative approval and verified operator-owned footage.")
    project = {
        "id": project_id, "title": brief["title"],
        "description": brief.get("proposed_benefit", "Editorial production draft"),
        "hook": scenes[0]["narration"], "sources": list(brief["sources"]),
        "production": {"preset": "production", "source_brief": source_brief,
                       "authentic_demo": {"required": True, "shot_ids": [scene["id"] for scene in scenes]}},
        "scenes": scenes,
        "claims": brief.get("claims", []),
        "editorial": {"quality_gate": gate, "warnings": brief.get("editorial_warnings", []),
                      "required_real_demonstrations": brief.get("required_real_demonstrations", []),
                      "availability": brief.get("availability", {}), "publication_blocked": True,
                      "publication_blockers": list(dict.fromkeys(blockers)), "demo_intake": {}},
        "review": {"facts_checked": False, "assets_licensed": False, "script_approved": False,
                   "demo_verified": False, "creative_approved": False, "final_approved": False},
    }
    errors, warnings = check(project)
    if errors:
        raise BridgeError("Converted project failed schema checks: " + "; ".join(errors))
    project["editorial"]["conversion_warnings"] = warnings
    return project


def save_project(project: dict, output: Path) -> Path:
    if output.exists():
        raise BridgeError(f"Refusing to overwrite existing project: {output}")
    for path in output.parent.glob("*.json"):
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if existing.get("id") == project["id"] or set(existing.get("sources", [])) & set(project["sources"]):
            raise BridgeError(f"Duplicate project already exists: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def intake_recording(project_path: Path, shot_id: str, media_path: Path, *,
                     start: float = 0.0, duration: float | None = None,
                     zoom: float = 1.0, focus_x: float = 0.5, focus_y: float = 0.5,
                     asset_root: Path | None = None, probe=probe_media) -> dict:
    if not media_path.is_file() or media_path.suffix.lower() not in VIDEO_EXTS:
        raise BridgeError("Demo intake requires an existing MP4, MOV, MKV, or WebM recording")
    project = json.loads(project_path.read_text(encoding="utf-8"))
    matches = [scene for scene in project.get("scenes", []) if scene.get("id") == shot_id]
    if len(matches) != 1:
        raise BridgeError(f"Expected one scene mapped to {shot_id!r}; found {len(matches)}")
    scene = matches[0]
    try:
        metadata = probe(media_path)
    except Exception as exc:
        raise BridgeError(f"Recording could not be inspected by ffprobe: {media_path}") from exc
    try:
        media_duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BridgeError("Recording has no readable media duration") from exc
    clip_duration = float(duration if duration is not None else scene["duration"])
    if start < 0 or not 1 <= clip_duration <= 40 or start + clip_duration > media_duration + 0.02:
        raise BridgeError("Requested trim must be 1–40 seconds and remain inside the recording")
    if not 1 <= zoom <= 2 or not 0 <= focus_x <= 1 or not 0 <= focus_y <= 1:
        raise BridgeError("Reframe zoom/focus values are outside renderer limits")
    if not any(stream.get("codec_type") == "video" for stream in metadata.get("streams", [])):
        raise BridgeError("Recording does not contain a video stream")
    asset_root = asset_root or ROOT / "assets" / "imported" / slugify(project["id"])
    destination = asset_root / shot_id / media_path.name
    if destination.exists():
        raise BridgeError(f"Imported recording already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(media_path, destination)
    try:
        relative = destination.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        relative = str(destination.resolve())
    scene["asset"] = relative
    scene["duration"] = clip_duration
    scene["edit"].update({"asset_start": float(start), "zoom": float(zoom),
                          "focus_x": float(focus_x), "focus_y": float(focus_y)})
    evidence = {"shot_id": shot_id, "source_original": str(media_path.resolve()),
                "imported_asset": relative, "sha256": _sha256(destination),
                "media": metadata, "trim": {"start": float(start), "duration": clip_duration},
                "reframe": {"zoom": zoom, "focus_x": focus_x, "focus_y": focus_y},
                "imported_at": datetime.now(timezone.utc).isoformat(), "operator_owned": True,
                "verified_by_human": False}
    project.setdefault("editorial", {}).setdefault("demo_intake", {})[shot_id] = evidence
    project["review"]["demo_verified"] = False
    project["review"]["assets_licensed"] = False
    project["review"]["final_approved"] = False
    project["editorial"]["publication_blocked"] = True
    project_path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    return evidence
