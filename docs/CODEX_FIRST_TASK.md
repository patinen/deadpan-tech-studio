# Codex task 01 — Make the video engine editorially usable

## Why
The current prototype produces 540x960 vertical videos with static scene layouts and placeholder art. It can render and mix narration, but it does not have modern, readable, well-timed on-screen subtitles. Before building agents, autopublishing, or SaaS-oriented analytics, we need one publishable **format**.

## Objective
Improve video rendering quality and subtitle support while keeping the existing CLI and source JSON scripts working.

### Required deliverables
1. Add a configurable output preset: draft (existing fast workflow) and production (1080x1920 H.264/AAC, 9:16). Preserve compatibility with `studio.py render` and `studio.py build`; add intuitive CLI flags.
2. Implement timed short-form subtitles that follow the **actual narration audio**. Use per-scene timing, phrase-level grouping, and legible emphasis; prevent clipping and maintain platform-safe margins. For now, an editable timing manifest is acceptable if accurate word-level timestamps are not available offline. Do not manufacture fake precise word timestamps or depend on a paid API.
3. Improve visual pacing with subtle motion/layout improvements and a robust fallback for scenes without footage. A real screenshot/video in `scenes[].asset` must remain clearly visible; do not overlay subtitles over key demo actions by default.
4. Add a deterministic preview path that works offline with available local TTS (`espeak`) and FFmpeg. No paid credentials for the core rendering test.
5. Add meaningful tests for subtitle/timing logic, output dimensions/config, review gates, and backward compatibility with the sample JSON. Document exact CLI commands in README.

### Guardrails
- Do NOT start social-platform publishing, trend scraping, a GUI/dashboard, or multi-agent orchestration yet.
- Do NOT silently mark final videos as approved.
- Do NOT generate made-up footage or claim it demonstrates a real product.
- Do NOT use copyrighted third-party music or media.
- Existing project: `content/001-stop-copy-pasting.json`.
- Preserve the original script narrator voice and brand bible.

### Acceptance criteria
- `python -m unittest discover -s tests -v` succeeds.
- A local command produces `output/...mp4`, at 1080x1920 for the production preset.
- Subtitles are visible and aligned to their corresponding narration/scene; an editor can inspect or edit the timing.
- Sample JSON works without schema migration.
- README describes dependencies, commands, review gates, and known caveats.
- Provide a clear summary of improvements and what remains before the first real public upload.

### Working approach
First inspect the pipeline and report a concise implementation plan. Then implement and test the feature end-to-end. If a prerequisite is unavailable, keep the working fallback and explain the constraint; don't replace functioning components merely to introduce new dependencies.
