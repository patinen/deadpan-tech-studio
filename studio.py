#!/usr/bin/env python3
"""Deadpan Tech: original tech video pipeline."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from studio.quality import check
from studio.render import render
from studio.speech import make_voice
from studio.utils import ROOT, load_project, slugify
from studio.writer import create_script
from studio.capture import capture_http_server_demo
from studio.visual_qa import generate_contact_sheet
from studio.recipe_capture import capture_recipe
from studio.scout import run_scout
from studio.editorial import (build_production_brief, fetch_article, gemini_analyze,
                              load_fixture, replay_model_response, save_brief,
                              select_candidate)


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    load_env()
    p = argparse.ArgumentParser(description="DEADPAN TECH — faceless, not personality-free")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="Generate a draft JSON script from an idea (Gemini API key required)")
    g.add_argument("idea")
    g.add_argument("--source", action="append", default=[], help="Verified source URL (repeatable)")
    g.add_argument("--model", default=None)
    s = sub.add_parser("scout", help="Rank evidence-backed topic proposals without producing videos")
    s.add_argument("--limit", type=int, default=15)
    s.add_argument("--fixture", action="store_true", help="Use clearly labelled offline sample data")
    s.add_argument("--sources", default=str(ROOT / "scout" / "sources.json"))
    s.add_argument("--weights", default=str(ROOT / "scout" / "weights.json"))
    s.add_argument("--output-dir", default=str(ROOT / "research"))
    s.add_argument("--include-known", action="store_true", help="Do not filter prior research/content")
    s.add_argument("--analysis-file", default=None, help="Optional validated provider-neutral analysis JSON")
    s.add_argument("--analysis-limit", type=int, default=10, help="Maximum assisted-analysis rows")
    d = sub.add_parser("develop", help="Turn one Scout candidate into a blocked editorial production brief")
    d.add_argument("--report", help="Scout JSON report containing the selected candidate")
    d.add_argument("--candidate", help="Candidate id, exact title, or canonical URL")
    d.add_argument("--fixture", help="Offline article + validated analysis fixture")
    d.add_argument("--ai", action="store_true", help="Analyze fetched article content with bounded Gemini JSON")
    d.add_argument("--model", default=None)
    d.add_argument("--output", required=True)
    d.add_argument("--promote", action="store_true", help="Archive and replace the same-topic draft as a new unapproved revision")
    replay = sub.add_parser("replay-editorial", help="Revalidate saved Gemini editorial JSON without an API call")
    replay.add_argument("response")
    replay.add_argument("--source", action="append", required=True, help="Allowed evidence URL (repeatable)")
    q = sub.add_parser("review", help="Quality checks; --strict checks publication approval")
    q.add_argument("project")
    q.add_argument("--strict", action="store_true")
    c = sub.add_parser("capture", help="Generate authentic local demo recordings")
    c.add_argument("project")
    v = sub.add_parser("voice", help="Narrate each scene (espeak/sapi/edge/piper)")
    v.add_argument("project")
    v.add_argument("--engine", choices=["espeak", "sapi", "piper", "edge"], default=None)
    v.add_argument("--speed", type=int, default=None)
    v.add_argument("--voice", default=None)
    r = sub.add_parser("render", help="Render a preview MP4 from a JSON script")
    r.add_argument("project")
    r.add_argument("--output", default=None)
    r.add_argument("--preset", choices=["draft", "production"], default=None)
    r.add_argument("--subtitles", default=None, help="Editable subtitle timing JSON path")
    b = sub.add_parser("build", help="Voice + render in one command")
    b.add_argument("project")
    b.add_argument("--engine", choices=["espeak", "sapi", "piper", "edge"], default=None)
    b.add_argument("--speed", type=int, default=None)
    b.add_argument("--voice", default=None)
    b.add_argument("--output", default=None)
    b.add_argument("--preset", choices=["draft", "production"], default=None)
    b.add_argument("--subtitles", default=None, help="Editable subtitle timing JSON path")
    b.add_argument("--capture", action="store_true", help="Capture configured real demo first")
    qa = sub.add_parser("visual-qa", help="Create a contact sheet for human video review")
    qa.add_argument("project")
    qa.add_argument("--video", default=None)
    args = p.parse_args()
    try:
        if args.cmd == "generate":
            result = create_script(args.idea, model=args.model, sources=args.source)
            errors, warnings = check(result)
            if errors:
                print("Generated script has schema errors:\n- " + "\n- ".join(errors), file=sys.stderr)
                return 1
            dest = ROOT / "content" / f"{slugify(result['id'])}.json"
            if dest.exists():
                print(f"Refusing to overwrite existing project: {dest}", file=sys.stderr)
                return 1
            dest.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Draft saved: {dest}")
            print("Review script, verify factual claims, and add genuine footage to scenes[].asset")
            return 0
        if args.cmd == "scout":
            fixture = ROOT / "fixtures" / "scout" / "sample-items.json" if args.fixture else None
            json_path, markdown_path, report = run_scout(
                limit=args.limit, fixture_path=fixture, sources_path=Path(args.sources).resolve(),
                weights_path=Path(args.weights).resolve(), output_dir=Path(args.output_dir).resolve(),
                include_known=args.include_known,
                analysis_path=Path(args.analysis_file).resolve() if args.analysis_file else None,
                analysis_limit=args.analysis_limit)
            print(f"Research status: {report['status']} ({len(report['proposals'])} shortlisted opportunities)")
            print("Counts:", ", ".join(f"{key}={value}" for key, value in report["counts"].items()))
            print("JSON report:", json_path)
            print("Markdown report:", markdown_path)
            if report["source_failures"]:
                for failure in report["source_failures"]:
                    print("WARNING:", failure)
            print("No demos executed. Select and verify a proposal manually before scripting.")
            return 0
        if args.cmd == "develop":
            if args.fixture:
                candidate, article, analysis = load_fixture(Path(args.fixture).resolve())
                mode = "offline-fixture"
            else:
                if not args.report or not args.candidate:
                    raise ValueError("develop requires --report and --candidate, or --fixture")
                report = json.loads(Path(args.report).resolve().read_text(encoding="utf-8"))
                candidate = select_candidate(report, args.candidate)
                source = candidate["evidence"][0]["url"]
                article = fetch_article(source)
                if not args.ai:
                    raise ValueError("Live article development requires --ai; use --fixture for offline validation")
                analysis = gemini_analyze(candidate, article, model=args.model)
                mode = "gemini"
            brief = build_production_brief(candidate, analysis, analysis_mode=mode)
            output = save_brief(brief, Path(args.output).resolve(), promote=args.promote)
            print("Editorial brief:", output)
            print("Publication blocked:", brief["publication_blocked"])
            for blocker in brief["publication_blockers"]:
                print("BLOCKER:", blocker)
            return 0
        if args.cmd == "replay-editorial":
            replay_model_response(Path(args.response).resolve(), args.source)
            print("Editorial response is valid for the supplied evidence URLs.")
            return 0
        path = Path(args.project).resolve()
        project = load_project(path)
        errors, warnings = check(project, require_approval=args.cmd == "review" and args.strict)
        for warning in warnings:
            print("WARNING:", warning)
        if errors:
            print("ERRORS:\n- " + "\n- ".join(errors), file=sys.stderr)
            return 1
        if args.cmd == "review":
            print("Draft schema OK" if not args.strict else "Ready for publishing (review flags confirmed)")
        if args.cmd == "capture" or (args.cmd == "build" and args.capture):
            capture_type = project.get("production", {}).get("capture")
            if capture_type == "http_server":
                evidence = capture_http_server_demo(project)
                print("Captured real local demo:", evidence["url"])
                print("Capture assets:", ", ".join(evidence["assets"].values()))
            elif capture_type == "recipe":
                evidence = capture_recipe(project)
                print("Captured verified recipe:", evidence["asset"])
            else:
                raise ValueError("Project production.capture must be 'http_server' or 'recipe'")
        if args.cmd == "visual-qa":
            video = (Path(args.video).resolve() if args.video else
                     ROOT / "output" / f"{slugify(project['id'])}.mp4")
            if not video.is_file():
                raise FileNotFoundError(f"Rendered video not found: {video}")
            sheet, qa_report = generate_contact_sheet(project, video)
            print("Contact sheet:", sheet)
            print("Visual QA data:", qa_report)
        if args.cmd in {"voice", "build"}:
            for voice_path in make_voice(project, engine=args.engine,
                                         speed=getattr(args, "speed", None),
                                         voice=getattr(args, "voice", None)):
                print("Narration:", voice_path)
        if args.cmd in {"render", "build"}:
            dest = Path(args.output).resolve() if args.output else None
            subtitles = Path(args.subtitles).resolve() if args.subtitles else None
            preset = args.preset or project.get("production", {}).get("preset", "draft")
            output, render_warnings = render(project, path, dest, preset=preset,
                                             subtitle_manifest=subtitles)
            print(f"Rendered: {output} ({output.stat().st_size / 1024 / 1024:.1f} MB)")
            for warning in render_warnings:
                print("WARNING:", warning)
            print("This is a DRAFT until facts, footage rights, and final quality are approved.")
        return 0
    except (ValueError, FileNotFoundError, RuntimeError, KeyError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
