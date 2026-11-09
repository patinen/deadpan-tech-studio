# DEADPAN TECH — Content Studio (MVP)

English-language, faceless (but not personality-free) tech channel. This is the **first runnable prototype**, not an autoposter.

**Pipeline:** Idea → AI draft (optional) → editorial checks → narration → 9:16 MP4 preview → human approval. The sample runs entirely offline (with espeak), once the dependencies below are installed.

## What's inside

- `prompts/brand_voice.md` — permanent channel personality and style guidance
- `prompts/script_system.md` — AI script generator prompt, outputs structured JSON
- `content/*.json` — editable scripts and scene layouts
- `studio.py` — CLI: `generate`, `review`, `voice`, `render`, `build`
- `studio/graphics.py` — original 9:16 visual identity in Pillow
- `studio/render.py` — FFmpeg video rendering, supports real screen recordings & screenshots
- `studio/quality.py` — pre-publication QA checks and explicit human-review gates
- `output/` — rendered videos and JSON reports (ignored by git)
- `cache/` — generated narration and intermediates (ignored by git)

## Setup (Windows / PowerShell)

Prerequisites: Python 3.11+, FFmpeg available on PATH. For offline draft narration, install `espeak` (otherwise use a premium/local TTS engine below).

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python studio.py review content/001-stop-copy-pasting.json
python studio.py render content/001-stop-copy-pasting.json --preset draft
```

That first render is **silent**, with clear illustrative placeholders. For narration use one of:

```powershell
# Low-quality, offline proof-of-concept voice (requires espeak installed)
python studio.py build content/001-stop-copy-pasting.json --engine espeak

# Higher quality, may require internet and the optional package
pip install edge-tts
python studio.py build content/001-stop-copy-pasting.json --engine edge

# Local voice after installing Piper CLI and placing a licensed model at models/voice.onnx
python studio.py build content/001-stop-copy-pasting.json --engine piper
```

## Production presets and editable subtitles

`draft` preserves the fast 540x960 workflow. `production` renders 1080x1920 H.264/AAC with a higher-quality encoder preset:

```powershell
python studio.py build content/001-stop-copy-pasting.json --engine espeak --preset production
```

Every render burns short, high-contrast phrase subtitles into the safe area below the demo panel. When narration exists, phrase windows are allocated within the measured audio duration; silent previews use the declared scene duration and are labelled as nominal timing. The editable sidecar is created at `cache/<project-id>/subtitles.json`. To keep a reviewed timing file elsewhere, copy it and pass it explicitly:

```powershell
python studio.py render content/001-stop-copy-pasting.json --preset production --subtitles content/001-subtitles.json
```

Each cue uses seconds relative to its scene. Edit `start`, `end`, or `text`, keeping cues ordered and within the scene duration. If narration changes, rendering rejects the stale manifest instead of silently showing mismatched text. Timing is deterministic phrase-level timing, based on measured scene audio unless manually edited; it is not claimed to be word-level transcription.

The default cache manifest refreshes automatically when measured narration replaces a silent preview or its measured duration changes. Explicit files passed with `--subtitles` are never overwritten in that situation; rendering stops and asks the editor to update them.

## Task 02 production project

The first production-oriented project is a locally reproducible Python folder-server demo. Its JSON config selects the production preset, narration voice, speed, pronunciation replacements, reusable terminal/browser visuals, and a small set of caption emphasis terms:

```powershell
# One command: narration, 1080x1920 render, thumbnail, and quality report
python studio.py build content/002-instant-local-file-server.json

# Fully offline editorial fallback (rough voice; requires eSpeak)
python studio.py build content/002-instant-local-file-server.json --engine espeak
```

The sample config uses the local Piper voice `en_US-lessac-medium`. Install `piper-tts`, then download the model locally (the model and cache remain gitignored):

```powershell
pip install piper-tts
python -m piper.download_voices en_US-lessac-medium --download-dir models
```

Piper is the preferred production-oriented local path. Windows SAPI is also supported as a credential-free fallback, installed voices permitting; eSpeak remains the deliberately rough proof voice. The optional `edge-tts` adapter is network-dependent and uses an unofficial service that may return no audio; the pipeline reports that failure rather than pretending it worked. CLI `--engine`, `--voice`, and `--speed` values override project settings. Narration cache keys include the complete voice configuration, so changing speed, model, or pronunciation cannot accidentally reuse stale audio.

Successful renders create:

- `output/<id>.mp4` — H.264/AAC video
- `output/<id>.thumbnail.jpg` — portrait preview/thumbnail frame
- `output/<id>.quality.json` — technical details, narration configuration, warnings, blockers, and publication-readiness state
- `cache/<id>/subtitles.json` — editable phrase-level timing

The reusable `visual.template: "local_demo"` supports terminal and browser modes. It is labelled as locally reproducible rather than real captured footage, and the quality report still requires human verification. Selective caption emphasis is configured with `production.caption_emphasis`; unmatched phrases stay visually quiet.

## Task 03 authentic demonstration capture

Task 03 replaces the sample's illustrated terminal/browser cards with evidence-backed source recordings. The capture harness creates an isolated folder containing four harmless fixture files, starts the real command below as a subprocess, verifies an HTTP 200 response, records real Chromium interaction with Playwright, interrupts the server, and writes hashes plus process evidence to `cache/<id>/capture/capture-manifest.json`. Browser footage is a direct Playwright recording. Terminal clips are clearly labelled process transcripts rendered from the observed PID, HTTP status, and exit code; they are not presented as camera footage of a terminal window.

```text
python -m http.server 8000 --bind 127.0.0.1
```

The explicit bind makes the tutorial localhost-only. Omitting `--bind 127.0.0.1` may expose the server to other devices on reachable interfaces; do that only when LAN access is deliberate and the served files are safe to share. Python's simple server is a convenience tool, not a hardened public server.

Install the capture dependency once:

```powershell
pip install playwright
playwright install chromium
```

Then capture and build separately, or use the repeatable one-command path:

```powershell
python studio.py capture content/002-instant-local-file-server.json
python studio.py build content/002-instant-local-file-server.json

# Capture + local narration + production render
python studio.py build content/002-instant-local-file-server.json --capture
```

Capture refuses to start when port 8000 is already occupied, verifies a unique
marker before treating the server as ready, and stops only the subprocess it
started. A failed run leaves the previous successful recordings intact. The
generated result panel is also tested in a real browser: it remains hidden until
the demo button is clicked.

After rendering, create a repeatable representative-frame review artifact:

```powershell
python studio.py visual-qa content/002-instant-local-file-server.json `
  --video output/002-instant-local-file-server-task04.mp4
```

This writes an ignored `output/<project>.contact-sheet.jpg` plus a machine-readable
`output/<project>.visual-qa.json`. The contact sheet supports human review; it does
not automatically approve the video or replace full playback on a phone.

Generated fixture files, recordings, evidence, narration, subtitle timing, rendered videos, thumbnails, and reports remain under ignored `cache/` and `output/` directories. No browser profile, personal file, API credential, or generated media is committed.

Scenes with `visual.layout: "focus"` give the authentic recording most of the portrait canvas. Optional `edit.asset_start`, `edit.motion`, and timed `edit.callouts` provide deliberate cuts and short emphasis without applying a constant zoom to every scene. Existing projects without these fields retain the original inset layout.

The audience-first sample is a 20–28 second narration-led edit that opens on the
already revealed browser result, then cuts back to the command and shows the real
button interaction. Optional `edit.zoom`, `edit.focus_x`, and `edit.focus_y`
provide a static focal crop for phone readability. Values are deliberately
scene-specific; projects that omit them retain their existing framing.

## Task 05 reusable capture recipes

Projects 003–005 demonstrate two reusable, local-first capture primitives:

- `production.capture_plan.type: "browser"` opens a committed harmless fixture in
  real Chromium, executes declarative click/keyboard/select steps, and fails when
  declared DOM assertions are not satisfied.
- `production.capture_plan.type: "command"` copies a committed fixture into an
  isolated cache folder, runs argument-array commands without a shell, verifies
  expected files, and records observed before/after output.

Run any recipe-backed project with the same commands:

```powershell
python studio.py capture content/003-paste-without-formatting.json
python studio.py build content/003-paste-without-formatting.json
```

The three samples cover plain-text browser paste, local Piper neural speech, and
selective batch renaming. Their fixtures, scripts, sources, narration and review
flags are editable JSON/repository files; recordings, generated WAV files,
models, MP4s, contact sheets and evidence manifests remain ignored. Command
recipes are trusted repository configuration and must be reviewed before use.

### Linux / Server

```bash
sudo apt-get install -y ffmpeg espeak
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python studio.py build content/001-stop-copy-pasting.json --engine espeak
```

## Generate new video scripts using Gemini (optional)

Copy `.env.example` to `.env`, add your API key, then run:

```powershell
python studio.py generate "A practical browser hack that saves repetitive clicks"
```

For product-specific claims, supply independently verified URLs (repeat `--source`). The model does **not** do live research; it only drafts. All facts and demos still need verification.

```powershell
python studio.py generate "A testable new AI tool" --source https://example.org/verified-source
```

The generator saves a NEW `content/<slug>.json`. Review/edit its narration, add real recordings and build:

```powershell
python studio.py review content/my-video.json
python studio.py build content/my-video.json --engine edge
```

**Never commit `.env`.**

## Add genuine screenshots or screen recordings

Put owned/licensed recordings and images under `assets/`. For each scene set `"asset": "assets/my-demo.mp4"` or `"asset": "assets/screenshot.png"`. Video audio is ignored; narration is the sound track. Videos are fitted in the central screen frame, not stretched. The example intentionally shows `ILLUSTRATIVE • ADD REAL FOOTAGE`, because claiming an AI tool was tested without testing it would be dishonest. That banner disappears when real media is added to that scene.

Current renderer intentionally uses simple scene cuts; word-by-word kinetic captions, multi-clip scenes, motion templates and publishing connectors are **next-stage work** after proving the format.

## Review / publishing gate

Do **not** automatically upload drafts. Only when a human has checked the facts, legal rights to all assets, and final video quality should these JSON booleans be switched to true:

```json
"review": { "facts_checked": true, "assets_licensed": true, "final_approved": true }
```

Check `python studio.py review content/your-video.json --strict` before publication. Draft renders are marked as drafts. Review flags are assertions by the operator, not actual automated content moderation.

## Possible production architecture

Later:

1. Researcher: RSS/search APIs + score ideas (with attribution)
2. Writer: JSON drafts, script QA, source tracking
3. Demo recorder: genuine footage automation (Playwright where lawful)
4. Video: reusable scene templates + better local/hosted voice + captions
5. Approval: internal web panel / Discord controls
6. Publish: platform-specific official APIs subject to approvals
7. Analytics: view retention, follows per 1k views, repeatable formats

Prioritize **audience growth** over short-term affiliate revenue. Cross-post without watermarks. Never mass-upload near-identical, unoriginal videos.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Caveats

- eSpeak is an intentionally rough offline timing/reference voice. Before public release, use a properly licensed production voice, inspect the editable subtitle timing, and replace illustrative scenes with authentic owned/licensed footage.
- Working brand name is provisional. Rename by setting `BRAND_NAME` in `.env` and updating the text in `prompts/brand_voice.md`.
- Visuals are intentionally illustrative until you record actual demos.
- Preview is 540×960 to keep local rendering fast. It can be raised to 1080×1920 later with more detailed graphics.
- The `edge-tts` integration depends on an unofficial service and may change; check its applicable terms before commercial use.
- Real short videos should have authentic demonstrations, good audio and proper fact checking. A fully unattended system is not the first milestone.
