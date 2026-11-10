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
One command analyzes one candidate, the request has a 4,096-token output cap, and
temperature is fixed at 0.2. Provider errors and malformed responses stop the run.
No key is logged or written. There is no batch mode or uncapped analysis loop.

The model receives the selected Scout candidate, the fetched article text, and an
explicit allow-list containing that article URL. Validation rejects invented
citations, unsupported claims without evidence, unknown/unavailable features
marked accepted, unsuitable categories marked accepted, vague fields, scripts
outside 45–85 words, and shot plans outside 20–30 seconds.

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

## Pilot limitation

The committed Gemini file-editing pilot uses harmless fictional meeting notes and
specifies an authenticated web capture plan. This environment had no Gemini API
credential or authenticated Gemini product session, so AI-assisted live analysis
and the proposed product demonstration were not executed. No illustrative mockup
is an acceptable substitute.
