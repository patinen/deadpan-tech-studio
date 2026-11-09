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
    q = sub.add_parser("review", help="Quality checks; --strict checks publication approval")
    q.add_argument("project")
    q.add_argument("--strict", action="store_true")
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
