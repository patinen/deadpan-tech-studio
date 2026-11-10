# Editorial research and production briefs

Scout discovery remains deterministic. The optional editorial layer retrieves one
selected canonical article as inert text and can ask Gemini for a bounded JSON
analysis of that text. It does not browse arbitrary links from the article,
execute commands, infer popularity, capture product interaction, or approve a
video.

## Develop a selected candidate

```powershell
python studio.py develop `
  --report research/scout-YYYYMMDDTHHMMSSZ.json `
  --candidate "candidate-id-or-canonical-url" `
  --ai `
  --output editorial/my-topic.json
```

`--ai` requires `GEMINI_API_KEY`; `GEMINI_MODEL` or `--model` selects the model.
The documented default is `gemini-3.5-flash-lite`, which supports structured
outputs on Gemini's `generateContent` API.
One command analyzes one candidate, the request has a 4,096-token output cap, and
temperature is fixed at 0.2. Provider errors and malformed responses stop the run.
No key is logged or written. There is no batch mode or uncapped analysis loop.

The request supplies a complete JSON Schema through
`generationConfig.responseJsonSchema` as well as the JSON MIME type. The schema
defines required fields, classification/status/confidence enums, string-only
arrays, cited-claim objects, and numeric shot durations. Local semantic validation
still runs after generation; structured output is not treated as fact checking.
The prompt targets approximately 60–70 narration words. The preferred range is
45–85 words, but a 30–100 word script with a plausible 1.2–3.8 words/second pace
and valid 20–30 second shot plan may proceed with an explicit editorial warning.
More severe deviations remain errors. The workflow never pads scripts.

HTTP 429, 500, and 503 responses receive at most two retries after one- and
two-second delays. Other API errors and schema failures are not retried. If JSON
parsing or validation fails, the raw model text, model name, and field-specific
error are written under ignored `diagnostics/editorial/`. Request headers and API
keys are never included.

Revalidate a diagnostic or raw analysis without another API call:

```powershell
python studio.py replay-editorial diagnostics/editorial/gemini-editorial-....json `
  --source https://example.com/the-allowed-evidence-page
```

Only two representation differences are normalized: an accepted response may use
`null` for `rejection_reason` (treated as `""`), and an explicitly present `null`
restrictions value is treated as `[]`. Missing fields, objects in place of arrays,
and unsupported factual structures remain errors.

To recover a failed generation without paying for another call, develop directly
from its unchanged diagnostic and the original Scout candidate:

```powershell
python studio.py develop `
  --diagnostic diagnostics/editorial/gemini-editorial-....json `
  --report research/scout-....json `
  --candidate create-preview-and-edit-files-directly-in-the-gemini-app `
  --output editorial/recovered-gemini-files.json
```

Alternatively pass verified `--source` URLs instead of a Scout report. For manual
revision, copy the diagnostic or its `raw_model_output` JSON to a new file, edit
only evidence-supported fields, then run the same command with that file. The
original diagnostic is never modified. Offline development performs the same
citation, availability, timing and safety checks, adds any pacing warning to the
blocked brief, and makes no API request.

Legacy Scout archives may contain `http://workspaceupdates.googleblog.com`
article links. That recognized host is upgraded before the request, and the HTTPS
response itself must succeed. The fetcher never downgrades HTTPS, rejects other
HTTP hosts, disables automatic redirects, and only follows a bounded same-host
HTTPS redirect chain.

The model receives the selected Scout candidate, the fetched article text, and an
explicit allow-list containing that article URL. Validation rejects invented
citations, unsupported claims without evidence, unknown/unavailable features
marked accepted, unsuitable categories marked accepted, vague fields, clearly
unusable scripts, and shot plans outside 20–30 seconds.

For deterministic offline testing:

```powershell
python studio.py develop `
  --fixture fixtures/editorial/gemini-file-editing.json `
  --output editorial/006-gemini-file-editing.json
```

The fixture is a dated research snapshot, not evidence that the live product was
used. Its output remains publication-blocked until a human captures and verifies
the real interaction, reviews every factual claim, confirms asset rights, and
approves the script and final video. Re-running refuses to overwrite a brief or
create another brief using the same source.

## Promote or revise a brief

Use `--promote` only when replacing the same output path and canonical source with
a non-fixture reviewed analysis. The previous file is archived as
`editorial/history/<name>.vN.json`; its human review state is copied into the new
revision's promotion metadata for traceability. All current approval flags are
reset to false, a fresh-review blocker is added, and publication remains blocked.
Source mismatches, unrelated duplicates, fixture-to-fixture replacement, existing
archive collisions, and implicit overwrites fail without changing the brief.

## Pilot limitation

The committed Gemini file-editing pilot uses harmless fictional meeting notes and
specifies an authenticated web capture plan. This environment had no Gemini API
credential or authenticated Gemini product session, so AI-assisted live analysis
and the proposed product demonstration were not executed. No illustrative mockup
is an acceptable substitute.
