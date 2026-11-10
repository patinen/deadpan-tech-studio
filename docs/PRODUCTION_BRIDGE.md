# Editorial-to-production bridge

The bridge turns a validated editorial brief into the existing content-project
format without claiming that a product was demonstrated. It deliberately keeps
every approval false and treats missing authentic footage as a publication
blocker.

## 1. Check and convert a brief

```powershell
python studio.py editorial-check editorial/006-gemini-file-editing.json
python studio.py convert-editorial editorial/006-gemini-file-editing.json `
  content/006-gemini-file-editing.json --project-id 006-gemini-file-editing
python studio.py review content/006-gemini-file-editing.json --strict
```

The quality gate reports factual validity, production readiness, and creative
quality independently. It flags feature-list hooks, vague pain points, unclear
payoffs, unverified demonstrations, repeated shot instructions, and long static
holds. Word count is not used as a creativity score. Conversion refuses an
existing output path or a project that duplicates an existing id/source.

The converted project preserves source URLs, claims, availability, narration,
timing, warnings, blockers, and demonstration requirements. Its scenes are
editable placeholders until genuine recordings are supplied. A draft can be
rendered for layout review, but the placeholders are not evidence.

## 2. Record the Gemini pilot honestly

Use an operator-controlled, authenticated Gemini session. Do not give this
project browser-profile access and do not record private account information.
The harmless source data is
`fixtures/editorial/meeting-notes.txt`.

Record three separate clips at a readable browser zoom:

1. `shot-01`: open on the completed file, then show the harmless meeting notes
   used as input. This result-first shot needs a revised, human-approved hook.
2. `shot-02`: in the authenticated Gemini web app, supply the test notes,
   request an action-plan document, and show the real inline preview appearing.
3. `shot-03`: expand the real preview, change a harmless due date or shorten one
   paragraph, and show the saved final result.

These steps are a capture plan, not a claim that the feature was executed here.
Availability, account eligibility, rollout, and the exact supported file type
must be rechecked in the operator's session against the attached official
source.

## 3. Import owned recordings

```powershell
python studio.py intake-demo content/006-gemini-file-editing.json shot-01 C:\captures\result.mp4 `
  --start 1.2 --duration 6 --zoom 1.25 --focus-x 0.55 --focus-y 0.45
python studio.py intake-demo content/006-gemini-file-editing.json shot-02 C:\captures\create.mp4
python studio.py intake-demo content/006-gemini-file-editing.json shot-03 C:\captures\edit.mp4
```

Intake accepts MP4, MOV, MKV, or WebM video with a readable duration and video
stream. Trim bounds and the renderer's zoom/focus limits are checked. The source
is copied—never moved—to `assets/imported/<project-id>/<shot-id>/`, which is
Git-ignored. The project records its original path, imported path, SHA-256,
probe metadata, trim, reframe, and import time. Import does not verify the
interaction, ownership, or licensing.

After import, inspect the clips and explicitly review the script, claims,
rights, creative quality, and demonstration. Editorial projects require all of
`facts_checked`, `assets_licensed`, `script_approved`, `demo_verified`,
`creative_approved`, and `final_approved` before strict review can pass. No CLI
command sets those fields automatically.

`editorial.publication_blocked` is an independent fail-closed gate. Once the
recordings and all reviews are complete, run strict review and resolve every
reported item. A human may then remove only the resolved strings from
`editorial.publication_blockers` and explicitly set `publication_blocked` to
`false`; run strict review again before rendering. A non-empty blocker list or a
value other than explicit `false` keeps the watermark and quality report in
draft status. The renderer never clears either field.

The editorial quality report calls URL/citation checks `evidence_integrity`.
Matching citations establish traceability, not truth. `factual_validity` remains
`human_review_required` until the operator completes `review.facts_checked`.

## Remaining pilot work

The committed pilot project is a blocked integration example, not a finished
video. Its current 39-word script and three long shots need a human rewrite and
a faster shot plan. The real authenticated Gemini interaction is unavailable in
the automated environment, so the three recordings, availability check,
demonstration review, licensing decision, narration review, and final creative
approval remain operator tasks.
