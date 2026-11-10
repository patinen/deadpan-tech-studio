# Trend Scout

Trend Scout gathers metadata from configured public RSS/Atom feeds, preserves
canonical article and feed URLs separately, classifies research material, and
produces a shortlist of at most ten actionable opportunities. It is not a
popularity oracle: source credibility and recency are not audience demand.

## Run it

```powershell
python studio.py scout --limit 15
```

Each run creates new timestamped JSON and Markdown archives in `research/`;
earlier runs are never overwritten. JSON schema version 2 retains `proposals` for
the actionable shortlist and adds `research_material` plus discovered,
shortlisted, research-only, filtered, and rejected counts. Generated reports are
ignored by Git. To exercise the workflow without network access:

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

Production readiness now requires a concrete problem, visible demonstration and
specific payoff. Evidence confidence and demand confidence are reported
separately. Demand stays `unknown` unless independent evidence is supplied; feed
presence never becomes a popularity score. Product news, opinion, roundups,
maintenance releases and unsupported metadata remain in research-only material.

## Optional assisted analysis

An editor may use any LLM/provider outside the scout and supply a cached JSON file:

```powershell
python studio.py scout --analysis-file research/analysis.json --analysis-limit 10
```

This interface is provider-independent and makes no network model call itself.
`--analysis-limit` bounds how many rows can be accepted, making cost control
explicit. Every row must include a canonical `url`, one supported
`editorial_category`, optional approved brief fields, and a `demand_evidence`
list whose entries each contain a public URL and a bounded observation. Invalid
categories or fields fail the run. Analysis can refine a brief but
cannot replace, add, or invent source URLs. Empty demand evidence leaves demand
unknown. This path is fully testable offline.

Example shape:

```json
{"analyses":[{"url":"https://vendor.example/article","editorial_category":"tool demo","brief":{"hook":"Play the measured result first."},"demand_evidence":[]}]}
```

## Editorial workflow

1. Read the evidence and score reasons; do not select by total alone.
2. Independently open the cited source and verify availability, version, platform,
   plan, license, and the exact proposed payoff.
3. Confirm the viewer problem with an additional source or real audience evidence.
4. Reproduce the proposed demonstration with owned test data in an isolated setup.
5. Manually create a content project. Scouting never generates, approves, renders,
   or publishes a video.

Known limitations: feeds are a narrow discovery surface, classification is a
conservative metadata heuristic, summaries can omit restrictions, and no system
here measures demand. Canonicalization removes known tracking parameters but does
not follow redirects. The allow-list includes official vendor sources and one
reputable independent technology publication; independent coverage is discovery,
not proof of popularity. Community feeds should only be added when their access
rules permit it, and community claims need authoritative corroboration.
