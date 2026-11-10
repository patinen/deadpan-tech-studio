# Trend Scout

Trend Scout gathers metadata from configured public RSS/Atom feeds, preserves the
evidence link and date, and ranks possible Deadpan Tech topics. It is a research
aid, not a popularity oracle: feed presence is not viewer demand, and a high score
does not approve a claim or prove that a demonstration works.

## Run it

```powershell
python studio.py scout --limit 15
```

Each run creates new timestamped JSON and Markdown files in `research/`; earlier
runs are never overwritten. Generated reports are ignored by Git. To exercise the
workflow without network access:

```powershell
python studio.py scout --fixture --limit 12
```

Fixture proposals are labelled `fixture`, use reserved example URLs, and must not
be described as current trends. Use `--include-known` to inspect scoring without
filtering topics already present in `content/` or earlier scout reports.

## Sources and costs

`scout/sources.json` contains the source allow-list. The default sources are public
official feeds and require no API key or paid service. The scout makes one normal
HTTP GET per enabled feed with a descriptive user agent, a timeout, and a 5 MB
response limit. It parses RSS/Atom only; it does not crawl linked pages, bypass
authentication or paywalls, run browser automation, or execute commands found in
external content. Disable a feed with `"enabled": false` if its policy changes.

Availability and feed terms remain the operator's responsibility. A blocked,
malformed, or unavailable source is reported. Partial results are marked
`incomplete`; if every source fails, the command exits without inventing results.

## Ranking

Weights live in `scout/weights.json`. Every dimension is scored from 1 to 5 and
includes a reason in the report. Higher production effort and misleading-claim
risk reduce the total. The normalized 0–100 result evaluates:

- problem strength and audience breadth;
- visual hook and practical usefulness;
- current relevance and demonstration feasibility;
- source confidence;
- production effort and misleading-claim risk.

The heuristic deliberately treats unavailable dates, product access, platform,
version, pricing, and licensing as uncertainty. It never creates popularity
metrics. Adjusted weights must be non-negative and use the documented dimensions.

## Editorial workflow

1. Read the evidence and score reasons; do not select by total alone.
2. Independently open the cited source and verify availability, version, platform,
   plan, license, and the exact proposed payoff.
3. Confirm the viewer problem with an additional source or real audience evidence.
4. Reproduce the proposed demonstration with owned test data in an isolated setup.
5. Manually create a content project. Scouting never generates, approves, renders,
   or publishes a video.

Known limitations: feeds are a narrow discovery surface, dates may describe a feed
update rather than feature launch, metadata summaries can omit restrictions, and
the keyword heuristic cannot measure actual demand. Community sources should only
be added when their public access rules allow automated feed retrieval; community
claims need corroboration from authoritative documentation.
