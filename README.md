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
