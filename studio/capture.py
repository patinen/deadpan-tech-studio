"""Deterministic capture of a real localhost-only Python server demonstration."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw

from .graphics import BG, LIME, MUTED, PAPER, font
from .utils import ROOT, assert_tool, run, slugify

HOST = "127.0.0.1"
PORT = 8000


def demo_command(site: Path) -> list[str]:
    return [sys.executable, "-m", "http.server", str(PORT), "--bind", HOST,
            "--directory", str(site)]


def prepare_demo_site(site: Path) -> list[Path]:
    site.mkdir(parents=True, exist_ok=True)
    files = {
        "index.html": """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Local Demo</title>
<link rel="stylesheet" href="style.css"></head><body><main>
<p class="eyebrow">LOCALHOST-ONLY DEMO</p><h1>Your folder is being served.</h1>
<p>These harmless files came from an isolated capture fixture.</p>
<button id="inspect">Inspect the demo</button><section id="result" hidden>
<strong>It works.</strong><span>Python served this page from 127.0.0.1.</span></section>
<aside><b>Local only</b><code>--bind 127.0.0.1</code>
<p>Other devices cannot connect. Omit the bind flag only when LAN access is intentional.</p></aside>
</main><script src="demo.js"></script></body></html>""",
        "style.css": """*{box-sizing:border-box}body{margin:0;background:#0c0f16;color:#f4f4ed;
font:24px Arial,sans-serif}main{max-width:900px;margin:0 auto;padding:90px 72px}.eyebrow{color:#c9f457;
font-weight:800;letter-spacing:.12em}h1{font-size:64px;line-height:1.02;margin:28px 0}p{line-height:1.45;
color:#bac1c4}button{background:#c9f457;border:0;border-radius:14px;padding:20px 30px;font-size:24px;
font-weight:800;cursor:pointer}section,aside{margin-top:36px;padding:28px;border:2px solid #526058;
border-radius:18px;background:#171d24}section{display:grid;gap:12px}section strong{color:#c9f457;font-size:34px}
aside b{display:block;color:#f97767;font-size:28px}code{display:block;margin:18px 0;color:#c9f457;
font-size:27px}aside p{font-size:21px;margin-bottom:0}.pulse{outline:8px solid rgba(201,244,87,.3)}""",
        "demo.js": """document.querySelector('#inspect').addEventListener('click',e=>{
document.querySelector('#result').hidden=false;e.currentTarget.classList.add('pulse');
document.querySelector('#result').scrollIntoView({behavior:'smooth',block:'center'});});""",
        "readme.txt": "This file is harmless and exists only for the automated localhost demo.\n",
    }
    paths = []
    for name, contents in files.items():
        path = site / name
        path.write_text(contents, encoding="utf-8")
        paths.append(path)
    return paths


def _wait_for_server(url: str, timeout: float = 8.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return response.status
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Local demo server did not become ready at {url}")


def _terminal_frame(lines: list[str], path: Path, cursor: bool = False) -> None:
    image = Image.new("RGB", (1080, 1400), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((55, 55, 1025, 1345), radius=28, fill=(17, 22, 29),
                           outline=(75, 88, 80), width=3)
    draw.rounded_rectangle((55, 55, 1025, 135), radius=28, fill=(31, 39, 47))
    for i, color in enumerate(((249, 119, 103), (246, 201, 90), LIME)):
        draw.ellipse((92+i*42, 82, 116+i*42, 106), fill=color)
    draw.text((245, 80), "VERIFIED PROCESS TRANSCRIPT", font=font(27, True), fill=MUTED)
    y = 205
    for index, line in enumerate(lines):
        color = LIME if line.startswith("$") else PAPER
        draw.text((105, y), line, font=font(31, index == 0), fill=color)
        y += 62
    if cursor:
        draw.rectangle((106, y+4, 128, y+42), fill=LIME)
    draw.text((105, 1260), "Captured from an isolated test folder", font=font(23), fill=MUTED)
    image.save(path)


def _make_terminal_clip(work: Path, name: str, stages: list[tuple[float, list[str]]]) -> Path:
    assert_tool("ffmpeg")
    frames = work / f"{name}-frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    fps = 12
    number = 0
    for duration, lines in stages:
        count = max(1, round(duration * fps))
        for _ in range(count):
            _terminal_frame(lines, frames / f"{number:05d}.png", cursor=number % fps < fps // 2)
            number += 1
    output = work / f"{name}.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps),
         "-i", str(frames / "%05d.png"), "-r", "30", "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)])
    shutil.rmtree(frames)
    return output


def _record_browser(url: str, work: Path) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install capture dependency: pip install playwright") from exc
    video_dir = work / "playwright-video"
    if video_dir.exists():
        shutil.rmtree(video_dir)
    video_dir.mkdir()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1080, "height": 1400},
            record_video_dir=str(video_dir), record_video_size={"width": 1080, "height": 1400},
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.mouse.move(860, 260, steps=18)
        page.wait_for_timeout(1300)
        page.locator("#inspect").hover()
        page.wait_for_timeout(700)
        page.locator("#inspect").click()
        page.wait_for_timeout(3000)
        page.locator("aside").scroll_into_view_if_needed()
        page.mouse.move(800, 1120, steps=14)
        page.wait_for_timeout(6000)
        video = page.video
        context.close()
        browser.close()
        recorded = Path(video.path())
    output = work / "browser-real.mp4"
    shutil.move(recorded, output)
    shutil.rmtree(video_dir, ignore_errors=True)
    return output


def capture_http_server_demo(project: dict) -> dict:
    """Capture real server/browser behavior and return an evidence manifest."""
    slug = slugify(project["id"])
    work = ROOT / "cache" / slug / "capture"
    site = work / "site"
    if site.exists():
        shutil.rmtree(site)
    site_files = prepare_demo_site(site)
    url = f"http://{HOST}:{PORT}/"
    command = demo_command(site)
    command_display = f"python -m http.server {PORT} --bind {HOST}"
    try:
        process_options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                           if os.name == "nt" else {"start_new_session": True})
        server = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, cwd=site, **process_options)
    except OSError as exc:
        raise RuntimeError(f"Could not start isolated demo server: {exc}") from exc
    try:
        status = _wait_for_server(url)
        start_clip = _make_terminal_clip(work, "server-start-real", [
            (1.2, [f"$ {command_display}"]),
            (3.8, [f"$ {command_display}", f"Process started: PID {server.pid}",
                   f"Verified GET /: HTTP {status}"])
        ])
        browser_clip = _record_browser(url, work)
    finally:
        if os.name == "nt":
            server.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            server.send_signal(signal.SIGINT)
        try:
            server.wait(timeout=4)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=2)
    exit_code = server.returncode
    stop_clip = _make_terminal_clip(work, "server-stop-real", [
        (1.5, [f"$ {command_display}", "^C"]),
        (2.8, [f"$ {command_display}", "^C", f"Process exited: code {exit_code}", "$ "]),
    ])
    if server.poll() is None:
        raise RuntimeError("Demo server remained running after capture")
    evidence = {
        "capture_type": "real_local_process_and_browser",
        "host": HOST, "port": PORT, "url": url,
        "command": command_display, "server_pid": server.pid,
        "verified_http_status": status, "server_stopped": True, "exit_code": exit_code,
        "site_directory": str(site),
        "files": [{"name": path.name,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                  for path in site_files],
        "assets": {"start": str(start_clip), "browser": str(browser_clip),
                   "stop": str(stop_clip)},
    }
    manifest = work / "capture-manifest.json"
    manifest.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence
