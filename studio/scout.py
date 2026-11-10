"""Evidence-preserving, non-executing topic research for Deadpan Tech."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests

from .utils import ROOT, slugify

DEFAULT_WEIGHTS = {
    "problem_strength": 1.5, "audience_breadth": 1.2, "visual_demo": 1.5,
    "specific_payoff": 1.5, "practical_usefulness": 1.3,
    "current_relevance": 0.5, "demo_feasibility": 1.2,
    "source_confidence": 0.7, "production_effort": 0.8,
    "misleading_risk": 1.3,
}
NEGATIVE = {"production_effort", "misleading_risk"}
ACTIONABLE = {"actionable hack", "tool demo", "automation"}
EDITORIAL_CATEGORIES = ACTIONABLE | {"product news", "opinion", "roundup", "maintenance release", "unsupported"}
TAG_RE = re.compile(r"<[^>]+>")
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


class ScoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    kind: str = "official"
    category: str = "Useful software features"
    confidence: int = 5
    role: str = "evidence"


def _text(value: str | None) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", value or "")).split())


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    query = urlencode(sorted((key, val) for key, val in parse_qsl(parsed.query)
                             if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS))
    return urlunparse((parsed.scheme.lower(), host, path, "", query, ""))


def _is_article_link(url: str, feed_url: str) -> bool:
    normalized = canonicalize_url(url)
    path = urlparse(normalized).path.lower()
    return (urlparse(normalized).scheme in {"http", "https"}
            and normalized != canonicalize_url(feed_url)
            and "/comments/" not in path
            and not path.endswith(("/comments", "/feed", ".xml", ".rss", ".atom")))


def _atom_article_link(entry: ET.Element, feed_url: str) -> str | None:
    ns = "{http://www.w3.org/2005/Atom}"
    links = []
    for node in entry.findall(f"{ns}link"):
        href = (node.get("href") or "").strip()
        rel = (node.get("rel") or "alternate").lower()
        media_type = (node.get("type") or "").lower()
        if href:
            priority = 0 if rel == "alternate" and (not media_type or "html" in media_type) else 1
            links.append((priority, rel, href))
    for _, rel, href in sorted(links):
        if rel not in {"self", "replies", "comments", "enclosure"} and _is_article_link(href, feed_url):
            return canonicalize_url(href)
    return None


def parse_feed(payload: bytes, source: SourceSpec) -> list[dict]:
    """Parse RSS/Atom, preferring alternate HTML and rejecting comment/feed links."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ScoutError(f"Malformed feed from {source.name}: {exc}") from exc
    ns = "{http://www.w3.org/2005/Atom}"
    items = root.findall(".//item")
    atom = False
    if not items:
        items, atom = root.findall(f".//{ns}entry"), True
    output = []
    for entry in items:
        if atom:
            title = entry.findtext(f"{ns}title")
            summary = entry.findtext(f"{ns}summary") or entry.findtext(f"{ns}content")
            published = entry.findtext(f"{ns}published") or entry.findtext(f"{ns}updated")
            link = _atom_article_link(entry, source.url)
        else:
            title = entry.findtext("title")
            summary = entry.findtext("description") or entry.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            published = entry.findtext("pubDate") or entry.findtext("{http://purl.org/dc/elements/1.1/}date")
            candidates = [entry.findtext("link"), entry.findtext("guid")]
            link = next((canonicalize_url(value) for value in candidates if value and _is_article_link(value, source.url)), None)
        if _text(title) and link:
            output.append({"title": _text(title), "summary": _text(summary), "url": link,
                           "feed_url": source.url, "published_at": _iso_date(published),
                           "source_name": source.name, "source_kind": source.kind,
                           "source_role": source.role, "category": source.category,
                           "source_confidence": source.confidence})
    if not output:
        raise ScoutError(f"No usable article entries from {source.name}")
    return output


def fetch_feed(source: SourceSpec, timeout: float = 15) -> list[dict]:
    response = requests.get(source.url, timeout=timeout, headers={
        "User-Agent": "DeadpanTechStudio/1.1 (editorial research; one request per configured feed)"})
    response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ScoutError(f"Feed from {source.name} exceeds the 5 MB safety limit")
    return parse_feed(response.content, source)


def title_key(title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    ignored = {"new", "now", "introducing", "available", "update", "updates", "the", "a", "an"}
    return " ".join(word for word in words if word not in ignored)


def url_key(url: str) -> str:
    return "url:" + hashlib.sha256(canonicalize_url(url).encode()).hexdigest()[:16]


def candidate_key(item: dict) -> str:
    value = f"{title_key(item.get('title', ''))}|{canonicalize_url(item.get('url', ''))}"
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def classify_item(item: dict) -> tuple[str, list[str]]:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    title = item.get("title", "").lower()
    if not item.get("summary") or len(_text(item.get("summary"))) < 35:
        return "unsupported", ["The feed metadata does not describe a concrete feature or outcome."]
    article_url = item.get("url", "").lower()
    if (any(term in title for term in ("weekly recap", "roundup", "announcements", "things we announced"))
            or re.match(r"^\d+\s+(ways|things|features|tips)\b", title)):
        return "roundup", ["The entry combines multiple announcements rather than one demonstrable payoff."]
    if any(term in title for term in ("stable channel update", "dev channel update", "release notes", "security update")):
        return "maintenance release", ["The title describes a release container, not a viewer-facing task."]
    if (any(term in text for term in ("opinion", "why we believe", "open letter", "policy", "regulator", "lawsuit"))
            or "internet-policy" in article_url or title.startswith("why is ")
            or " days later:" in title or "still steers" in title):
        return "opinion", ["The subject is commentary or policy rather than a reproducible software action."]
    if (any(term in title for term in ("generally available", "hackers exploited", "vulnerability", "malware", "security flaw"))
            and not title.startswith(("how to ", "patch "))):
        return "product news", ["The entry reports availability or an incident; it does not yet provide a safe visual workflow."]
    if " now in " in title or (re.search(r"\b\d+\.\d+\b", title) and " with " in title):
        return "product news", ["The title is version/availability news; a concrete user workflow must be identified separately."]
    action = any(term in text for term in ("how to", "shortcut", "keyboard", "click", "drag", "paste", "search", "edit", "create", "remove", "convert", "export", "upload", "apply"))
    automation = any(term in text for term in ("automat", "batch", "schedule", "one-click", "trigger"))
    tool = any(term in text for term in (" ai ", "gemini", "copilot", "model", "tool", "assistant", "generator"))
    release = any(term in text for term in ("launch", "introduc", "available", "beta", "release", "new feature"))
    if automation:
        return "automation", ["The metadata describes a repeatable manual-to-automatic workflow."]
    if action and tool:
        return "tool demo", ["The metadata describes an observable input and tool-produced result."]
    if action:
        return "actionable hack", ["The metadata contains a concrete action suitable for a before/after demonstration."]
    if release:
        return "product news", ["The entry announces availability but does not establish a concrete viewer workflow."]
    return "unsupported", ["No concrete action, input/output demonstration, or specific payoff was found."]


def _feature_text(item: dict) -> str:
    summary = _text(item.get("summary"))
    first = re.split(r"(?<=[.!?])\s+", summary)[0] if summary else item["title"]
    return first[:240].rstrip(" .")


def build_brief(item: dict, category: str) -> dict:
    feature = _feature_text(item)
    subject = re.sub(r"^(introducing|new|now available:?|how to)\s+", "", item["title"], flags=re.I).strip()
    pains = {"actionable hack": f"People doing this task may be missing a faster path: {subject}.",
             "tool demo": f"People need to know whether {subject} produces a useful result, not another polished promise.",
             "automation": f"The workflow behind {subject} may remove a repetitive manual step."}
    hooks = {"actionable hack": f"Open on the finished result, then reveal the shorter way to use {subject}.",
             "tool demo": f"Play the real output from {subject} first. Then show exactly what produced it.",
             "automation": "Show the completed batch first, then put the repetitive version out of its misery."}
    before = {"actionable hack": "Before: use the normal multi-step path. After: repeat with the documented action and compare.",
              "tool demo": "Before: show the bounded input and manual alternative. After: reveal the real, unedited tool output.",
              "automation": "Before: perform and time one safe manual example. After: run the verified automation on the same fixture."}
    return {"audience": "English-speaking everyday software users" if category == "actionable hack" else "Tech-curious professionals who value verified results",
            "pain_point": pains.get(category, "No demonstrated viewer problem yet; retain for research only."),
            "actual_feature": feature,
            "hook": hooks.get(category, "Do not script a hook until a concrete task and payoff are verified."),
            "before_after": before.get(category, "No honest before/after is supported by the current metadata."),
            "demonstration_plan": ("Use an isolated account or harmless fixture. Capture the full input, action, and unedited result."
                                   if category in ACTIONABLE else "Research-only: identify a supported workflow before capture."),
            "limitations": "Feed metadata does not prove availability, quality, price, licensing, platform support, or demand.",
            "verification_needs": ["Open the canonical article", "Verify current product/version and plan", "Reproduce the exact result", "Find independent audience-problem evidence"]}


def _scores(item: dict, category: str, now: datetime) -> tuple[dict, dict]:
    text = f"{item['title']} {item.get('summary', '')}".lower()
    concrete = category in ACTIONABLE
    visible = concrete and any(term in text for term in ("click", "screen", "tab", "edit", "create", "upload", "drag", "select", "preview", "before", "after"))
    payoff = concrete and any(term in text for term in ("faster", "save", "remove", "create", "edit", "search", "convert", "export", "automat", "one-click"))
    broad = any(term in text for term in ("browser", "email", "document", "file", "photo", "meeting", "search", "phone", "slides", "sheets"))
    restricted = any(term in text for term in ("enterprise", "admin", "api", "developer", "beta", "education", "workspace customers"))
    relevance, age_reason = 2, "Publication date unavailable; relevance is uncertain."
    if item.get("published_at"):
        try:
            age = max(0, (now - datetime.fromisoformat(item["published_at"])).days)
            relevance = 5 if age <= 14 else 4 if age <= 45 else 3 if age <= 120 else 2
            age_reason = f"Published {age} days before this run; recency is not demand."
        except ValueError:
            pass
    scores = {"problem_strength": 4 if concrete and payoff else 2 if concrete else 1,
              "audience_breadth": 4 if broad and not restricted else 2,
              "visual_demo": 5 if visible else 3 if concrete else 1,
              "specific_payoff": 5 if payoff else 2 if concrete else 1,
              "practical_usefulness": 4 if concrete else 2 if category == "product news" else 1,
              "current_relevance": relevance,
              "demo_feasibility": 4 if concrete and not restricted else 2 if concrete else 1,
              "source_confidence": max(1, min(5, int(item.get("source_confidence", 3)))),
              "production_effort": 4 if restricted else 2 if concrete else 3,
              "misleading_risk": 4 if restricted or not concrete else 2}
    reasons = {"problem_strength": "Concrete pain/payoff language is present." if scores["problem_strength"] >= 4 else "A concrete viewer frustration is not established.",
               "audience_breadth": "The task uses broadly relevant software." if scores["audience_breadth"] >= 4 else "The metadata suggests a narrower or restricted audience.",
               "visual_demo": "A visible state change is described." if visible else "No strong visible before/after is established.",
               "specific_payoff": "The metadata names an observable outcome." if payoff else "The payoff remains general or announcement-led.",
               "practical_usefulness": "The candidate describes something a viewer can do." if concrete else "This is research material, not an actionable workflow.",
               "current_relevance": age_reason,
               "demo_feasibility": "Likely capturable with an isolated browser/local fixture." if scores["demo_feasibility"] >= 4 else "Access or a reproducible workflow remains unclear.",
               "source_confidence": f"Evidence-source confidence is {scores['source_confidence']}/5; this does not measure demand.",
               "production_effort": "Restricted access increases setup effort." if restricted else "Likely low-to-moderate setup effort.",
               "misleading_risk": "Restrictions or missing workflow increase claim risk." if scores["misleading_risk"] >= 4 else "Claims still require hands-on verification."}
    return scores, reasons


def score_candidate(scores: dict, weights: dict) -> float:
    if set(weights) != set(DEFAULT_WEIGHTS) or any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()):
        raise ValueError("Score weights must contain every documented dimension as non-negative numbers")
    numerator = sum((6 - scores[key] if key in NEGATIVE else scores[key]) * weight for key, weight in weights.items())
    return round(100 * numerator / (5 * sum(weights.values())), 2) if sum(weights.values()) else 0.0


def build_candidate(item: dict, weights: dict, *, fixture: bool, discovered_at: str, analysis: dict | None = None) -> dict:
    category, category_reasons = classify_item(item)
    if analysis:
        category = analysis.get("editorial_category", category)
    scores, reasons = _scores(item, category, datetime.fromisoformat(discovered_at))
    brief = build_brief(item, category)
    if analysis:
        brief.update(analysis.get("brief", {}))
    readiness = score_candidate(scores, weights)
    demand = (analysis or {}).get("demand_evidence", [])
    evidence = [{"url": canonicalize_url(item["url"]), "feed_url": item.get("feed_url"),
                 "source_name": item.get("source_name"), "source_kind": item.get("source_kind"),
                 "source_role": item.get("source_role", "evidence"), "published_at": item.get("published_at"),
                 "discovered_at": discovered_at}]
    return {"id": slugify(item["title"]), "dedup_key": candidate_key(item), "working_title": item["title"],
            "category": item.get("category") or "Useful software features", "editorial_category": category,
            "classification_reasons": category_reasons, "actionable": category in ACTIONABLE, "brief": brief,
            "viewer_pain_point": brief["pain_point"], "hook_suggestion": brief["hook"],
            "proposed_payoff": brief["before_after"], "what_it_does": brief["actual_feature"],
            "evidence": evidence, "verified_claims": ["The canonical source published this title and feed summary."],
            "uncertain_claims": ["Availability, behavior, quality, restrictions, licensing, demand, and demo outcome remain unverified."],
            "restrictions": {"version": "unknown", "platform": "unknown", "licensing": "unknown"},
            "research_confidence": "fixture-only" if fixture else ("high" if scores["source_confidence"] >= 4 else "medium"),
            "demand_confidence": "unknown" if not demand else "evidence-present / human-review-required",
            "demand_evidence": demand, "production_readiness": readiness, "score": readiness,
            "scores": scores, "score_reasons": reasons,
            "demonstration": {"screen_action": brief["demonstration_plan"], "capture_compatibility": "requires editorial verification", "external_requirements": "unknown", "claims_to_verify": brief["verification_needs"], "rights_privacy_safety": "Use isolated owned data; avoid personal accounts and third-party media."},
            "production_complexity": "high" if scores["production_effort"] >= 4 else "medium" if scores["production_effort"] == 3 else "low",
            "fixture_data": fixture, "executed_demo": False}


def load_sources(path: Path) -> list[SourceSpec]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = [SourceSpec(**{k: v for k, v in item.items() if k != "enabled"}) for item in data["sources"] if item.get("enabled", True)]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ScoutError(f"Invalid source configuration {path}: {exc}") from exc
    if not sources:
        raise ScoutError(f"No enabled sources in {path}")
    return sources


def load_weights(path: Path | None) -> dict:
    if path is None:
        return DEFAULT_WEIGHTS.copy()
    try:
        weights = json.loads(path.read_text(encoding="utf-8"))["weights"]
        score_candidate({key: 3 for key in DEFAULT_WEIGHTS}, weights)
        return weights
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ScoutError(f"Invalid weight configuration {path}: {exc}") from exc


def load_analysis(path: Path | None, max_items: int) -> dict[str, dict]:
    """Load provider-neutral cached LLM analysis after strict validation."""
    if path is None:
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["analyses"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ScoutError(f"Invalid analysis file {path}: {exc}") from exc
    if not isinstance(rows, list) or len(rows) > max_items:
        raise ScoutError(f"Analysis file exceeds --analysis-limit {max_items}")
    allowed = {"audience", "pain_point", "actual_feature", "hook", "before_after", "demonstration_plan", "limitations", "verification_needs"}
    result = {}
    for row in rows:
        demand_evidence = row.get("demand_evidence", [])
        valid_demand = (isinstance(demand_evidence, list) and all(
            isinstance(evidence, dict)
            and isinstance(evidence.get("url"), str)
            and urlparse(evidence["url"]).scheme in {"http", "https"}
            and isinstance(evidence.get("observation"), str)
            for evidence in demand_evidence))
        if (not isinstance(row, dict) or not isinstance(row.get("url"), str)
                or row.get("editorial_category") not in EDITORIAL_CATEGORIES
                or not isinstance(row.get("brief", {}), dict) or set(row.get("brief", {})) - allowed
                or not valid_demand):
            raise ScoutError("Analysis rows require URL, valid editorial_category, validated brief fields, and cited demand_evidence")
        result[url_key(row["url"])] = row
    return result


def known_keys(output_dir: Path) -> set[str]:
    keys = set()
    for path in (ROOT / "content").glob("*.json"):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            keys.add("title:" + title_key(project.get("title", "")))
            keys.update(url_key(url) for url in project.get("sources", []))
        except (OSError, json.JSONDecodeError):
            continue
    for path in output_dir.glob("scout-*.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            for row in report.get("proposals", []) + report.get("research_material", []):
                keys.add("title:" + title_key(row.get("working_title", "")))
                keys.update(url_key(e["url"]) for e in row.get("evidence", []) if e.get("url"))
        except (OSError, json.JSONDecodeError):
            continue
    return keys


def _markdown(report: dict) -> str:
    c = report["counts"]
    lines = [f"# Deadpan Tech Scout — {report['generated_at']}", "", f"**Status:** {report['status']}  ",
             f"**Mode:** {report['mode']}  ", f"**Discovered:** {c['discovered']} · **Shortlisted:** {c['shortlisted']} · **Research-only:** {c['research_only']} · **Filtered:** {c['filtered']} · **Rejected:** {c['rejected']}", "",
             "Demand remains **unknown** unless independently reviewed demand evidence is attached.", ""]
    if report["source_failures"]:
        lines += ["## Source failures", ""] + [f"- {x}" for x in report["source_failures"]] + [""]
    lines += ["## Video opportunity shortlist", ""]
    if not report["proposals"]:
        lines += ["No candidate met the actionable and production-readiness gate.", ""]
    for rank, item in enumerate(report["proposals"], 1):
        brief = item["brief"]
        lines += [f"### {rank}. {item['working_title']} — {item['production_readiness']}/100", "",
                  f"- **Editorial category:** {item['editorial_category']}", f"- **Research confidence:** {item['research_confidence']}",
                  f"- **Demand confidence:** {item['demand_confidence']}", f"- **Audience:** {brief['audience']}",
                  f"- **Pain:** {brief['pain_point']}", f"- **Actual feature:** {brief['actual_feature']}",
                  f"- **Hook:** {brief['hook']}", f"- **Before / after:** {brief['before_after']}",
                  f"- **Demo:** {brief['demonstration_plan']}", f"- **Limitations:** {brief['limitations']}",
                  f"- **Evidence:** {item['evidence'][0]['url']}", ""]
    lines += ["## Research-only material", ""]
    for item in report["research_material"]:
        lines.append(f"- **{item['editorial_category']}** — [{item['working_title']}]({item['evidence'][0]['url']}): {item['classification_reasons'][0]}")
    lines += ["", "## Editorial gate", "", "No demonstration was executed. Verify claims, access, demand, rights, and the actual before/after before creating a project.", ""]
    return "\n".join(lines)


def run_scout(*, limit: int, fixture_path: Path | None, sources_path: Path,
              weights_path: Path | None, output_dir: Path, include_known: bool = False,
              fetcher=fetch_feed, now: datetime | None = None,
              analysis_path: Path | None = None, analysis_limit: int = 10) -> tuple[Path, Path, dict]:
    if not 1 <= limit <= 50:
        raise ValueError("Scout limit must be between 1 and 50")
    if not 0 <= analysis_limit <= 50:
        raise ValueError("Analysis limit must be between 0 and 50")
    now = now or datetime.now(timezone.utc)
    generated_at = now.isoformat()
    weights, analyses = load_weights(weights_path), load_analysis(analysis_path, analysis_limit)
    raw, failures = [], []
    fixture = fixture_path is not None
    if fixture:
        try:
            raw = json.loads(fixture_path.read_text(encoding="utf-8"))["items"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ScoutError(f"Invalid scout fixture {fixture_path}: {exc}") from exc
    else:
        for source in load_sources(sources_path):
            try:
                raw.extend(fetcher(source))
            except Exception as exc:
                failures.append(f"{source.name}: {exc}")
    if not raw:
        raise ScoutError("No research items were available; no trend report was fabricated")
    known = set() if include_known else known_keys(output_dir)
    seen_urls, seen_topics, candidates = set(), set(), []
    counts = {"discovered": len(raw), "shortlisted": 0, "research_only": 0, "filtered": 0, "rejected": 0}
    for item in raw:
        if not isinstance(item, dict) or not item.get("title") or not item.get("url"):
            counts["rejected"] += 1
            failures.append("Skipped malformed item without title or URL")
            continue
        if not _is_article_link(item["url"], item.get("feed_url", "https://invalid.local/feed")):
            counts["rejected"] += 1
            failures.append(f"Rejected non-article URL: {item['url']}")
            continue
        item = item | {"url": canonicalize_url(item["url"])}
        ukey, tkey = url_key(item["url"]), "title:" + title_key(item["title"])
        if ukey in seen_urls or tkey in seen_topics or ukey in known or tkey in known:
            counts["filtered"] += 1
            continue
        seen_urls.add(ukey)
        seen_topics.add(tkey)
        candidates.append(build_candidate(item, weights, fixture=fixture, discovered_at=generated_at, analysis=analyses.get(ukey)))
    actionable = sorted((x for x in candidates if x["actionable"]), key=lambda x: (-x["production_readiness"], x["working_title"].lower()))
    research = sorted((x for x in candidates if not x["actionable"]), key=lambda x: (x["editorial_category"], x["working_title"].lower()))
    shortlist = [x for x in actionable if x["production_readiness"] >= 55][:min(limit, 10)]
    counts["shortlisted"], counts["research_only"] = len(shortlist), len(research)
    counts["filtered"] += max(0, len(actionable) - len(shortlist))
    report = {"version": 2, "generated_at": generated_at, "mode": "offline-fixture" if fixture else "live-public-feeds",
              "status": "fixture" if fixture else ("complete" if not failures else "incomplete"), "requested_limit": limit,
              "weights": weights, "source_failures": failures, "counts": counts, "proposals": shortlist,
              "research_material": research, "notice": "Research only. Demand is unknown without independent evidence; no demonstrations or approvals occurred."}
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    json_path, md_path = output_dir / f"scout-{stamp}.json", output_dir / f"scout-{stamp}.md"
    suffix = 1
    while json_path.exists() or md_path.exists():
        json_path, md_path = output_dir / f"scout-{stamp}-{suffix}.json", output_dir / f"scout-{stamp}-{suffix}.md"
        suffix += 1
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, md_path, report
