# Codex project instructions — Deadpan Tech Studio

## Mission
Build a reliable, human-approved production system for an English-language, faceless AI and tech-hacks content brand. Optimize for **audience growth and originality**, not immediate monetization, publishing volume, or flashy feature count.

The brand is faceless, **not personality-free**. It has a smart, understated narrator with occasional observational dry humor about poor UX, software friction, and exaggerated AI marketing. Do not use generic AI hype or a forced joke in every sentence.

## Start here
1. Read `README.md`, `ALOITA_TASTA.md`, `prompts/brand_voice.md`, `prompts/script_system.md`, and `docs/CODEX_FIRST_TASK.md`.
2. Inspect the existing code. Run `python -m unittest discover -s tests -v` and document any failures.
3. Continue the MVP in small, tested increments. Keep it runnable without paid APIs or credentials.

## Stack & architecture
- Python CLI with FFmpeg, ffprobe, Pillow, JSON-based scene descriptions.
- Keep the CLI (`studio.py`) and the established script JSON format backwards-compatible.
- Separate research/script generation, quality checks, narration, graphics/rendering, and review.
- Avoid premature full-stack dashboards, trend agents, database migrations, or cloud services for the first task.
- Default to cross-platform operation (Windows/PowerShell and Linux).
- Add focused automated tests for changed logic and concise usage docs.

## Editorial requirements
- English-language content; global audience, no face required.
- Useful first: authentic demos, verified facts, honest limitations; a dry joke is seasoning.
- Show a surprising outcome or clear problem fast. No "Hey guys", generic hype, or forced viral hooks.
- Do not pretend a mocked UI is actual footage or claim a tool was tested unless it really was.
- Re-use approved brand presentation, but improve visual quality and pace with care.
- Visual placeholders must remain visibly identified as illustrative.

## Safety & publishing
- Human approval is mandatory before any public publishing.
- Never set `review.facts_checked`, `review.assets_licensed`, or `review.final_approved` to true automatically.
- No automatic uploading, TikTok/YouTube/Meta credentials, or platform login automation in the first task.
- Never commit `.env`, API keys, TTS model binaries, cached output, personal data, or unlicensed media.
- Prefer official APIs for future publishing, subject to their permissions and terms.

## Definition of done for any Codex task
- Updated code runs on at least the available local test environment.
- `python -m unittest discover -s tests -v` passes.
- A demo render can be produced, or any absent external prerequisites are explicitly listed.
- Document how to run the new feature and any known limitations.
- Report changed files, tests executed, and a short list of remaining risks.
