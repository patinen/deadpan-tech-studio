"""Data-driven local browser and command capture primitives."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .capture import _make_terminal_clip
from .utils import ROOT, slugify


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _browser_capture(plan: dict, work: Path) -> tuple[Path, list[dict]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install capture dependency: pip install playwright") from exc
    fixture = (ROOT / plan["fixture"]).resolve()
    if not fixture.is_file() or ROOT not in fixture.parents:
        raise ValueError(f"Browser fixture must be a project file: {fixture}")
    video_dir = work / "playwright-video"
    video_dir.mkdir()
    evidence: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1080, "height": 1400},
            record_video_dir=str(video_dir), record_video_size={"width": 1080, "height": 1400})
        page = context.new_page()
        page.goto(fixture.as_uri())
        for action in plan.get("actions", []):
            kind = action["type"]
            if kind == "wait":
                page.wait_for_timeout(int(action["ms"]))
            elif kind == "click":
                page.locator(action["selector"]).click()
            elif kind == "select_text":
                page.locator(action["selector"]).select_text()
            elif kind == "press":
                page.keyboard.press(action["keys"])
            else:
                raise ValueError(f"Unsupported browser action: {kind}")
            evidence.append({"action": kind, **{k: v for k, v in action.items() if k != "type"}})
        for assertion in plan.get("assertions", []):
            locator = page.locator(assertion["selector"])
            actual = locator.inner_text().strip()
            if actual != assertion["text"]:
                raise RuntimeError(f"Browser assertion failed for {assertion['selector']}: {actual!r}")
            if assertion.get("plain_text") and locator.locator("*").count():
                raise RuntimeError(f"Expected plain text in {assertion['selector']}")
            evidence.append({"assertion": assertion["selector"], "actual": actual})
        page.wait_for_timeout(1600)
        video = page.video
        context.close()
        browser.close()
        recorded = Path(video.path())
    output = work / "demo-real.mp4"
    shutil.move(recorded, output)
    shutil.rmtree(video_dir, ignore_errors=True)
    return output, evidence


def _expand(value: str, work: Path) -> str:
    return value.replace("{work}", str(work)).replace("{python}", sys.executable).replace(
        "{root}", str(ROOT))


def _command_capture(plan: dict, work: Path) -> tuple[Path, list[dict]]:
    fixture = (ROOT / plan["fixture_dir"]).resolve()
    if not fixture.is_dir() or ROOT not in fixture.parents:
        raise ValueError(f"Command fixture must be a project directory: {fixture}")
    sandbox = work / "sandbox"
    shutil.copytree(fixture, sandbox)
    stages: list[tuple[float, list[str]]] = []
    transcript: list[str] = []
    evidence: list[dict] = []
    for step in plan.get("steps", []):
        label = step["label"]
        if step.get("reset"):
            transcript = []
        if step["type"] == "list":
            patterns = step.get("patterns", ["*"])
            names = sorted({path.name for pattern in patterns for path in sandbox.glob(pattern)})
            lines = [f"$ {label}", *names]
            evidence.append({"step": label, "files": names})
        elif step["type"] == "run":
            command = [_expand(part, sandbox) for part in step["command"]]
            completed = subprocess.run(command, cwd=sandbox, input=step.get("stdin"), text=True,
                capture_output=True, timeout=float(step.get("timeout", 30)), check=False)
            if completed.returncode:
                raise RuntimeError(f"Capture command failed ({completed.returncode}): {completed.stderr.strip()}")
            verify = step.get("verify_file")
            if verify and not (sandbox / verify).is_file():
                raise RuntimeError(f"Capture command did not create expected file: {verify}")
            lines = [f"$ {label}"]
            lines.extend(line for line in completed.stdout.splitlines() if line.strip())
            if verify:
                lines.append(f"Created {verify} ({(sandbox / verify).stat().st_size:,} bytes)")
            evidence.append({"step": label, "command": command, "returncode": completed.returncode,
                             "verified_file": verify})
        else:
            raise ValueError(f"Unsupported command capture step: {step['type']}")
        transcript.extend(lines)
        stages.append((float(step.get("duration", 3)), transcript.copy()))
    return _make_terminal_clip(work, "demo-real", stages), evidence


def capture_recipe(project: dict) -> dict:
    """Execute a trusted project recipe in an isolated cache directory."""
    slug = slugify(project["id"])
    plan = project.get("production", {}).get("capture_plan")
    if not isinstance(plan, dict):
        raise ValueError("Recipe capture requires production.capture_plan")
    final = ROOT / "cache" / slug / "capture"
    work = ROOT / "cache" / slug / "capture-staging"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        if plan.get("type") == "browser":
            asset, steps = _browser_capture(plan, work)
        elif plan.get("type") == "command":
            asset, steps = _command_capture(plan, work)
        else:
            raise ValueError(f"Unknown recipe capture type: {plan.get('type')}")
        manifest = {"capture_type": f"recipe_{plan['type']}", "asset": str(final / asset.name),
                    "steps": steps, "sha256": _digest(asset), "verified": True}
        (work / "capture-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        shutil.rmtree(final, ignore_errors=True)
        shutil.move(str(work), str(final))
        return manifest
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
