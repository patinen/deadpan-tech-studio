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
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from .utils import ROOT, slugify

DEFAULT_WEIGHTS = {
    "problem_strength": 1.4, "audience_breadth": 1.5, "visual_hook": 1.2,
    "practical_usefulness": 1.5, "current_relevance": 0.8,
    "demo_feasibility": 1.3, "source_confidence": 1.2,
    "production_effort": 0.8, "misleading_risk": 1.3,
}
POSITIVE = tuple(key for key in DEFAULT_WEIGHTS if key not in {"production_effort", "misleading_risk"})
TAG_RE = re.compile(r"<[^>]+>")


class ScoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    kind: str = "official"
    category: str = "Useful software features"
    confidence: int = 5


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


def parse_feed(payload: bytes, source: SourceSpec) -> list[dict]:
    """Parse RSS or Atom without accepting scripts or executing feed content."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ScoutError(f"Malformed feed from {source.name}: {exc}") from exc
    items = root.findall(".//item")
    atom = False
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        atom = True
    output = []
    for item in items:
        if atom:
            title = item.findtext("{http://www.w3.org/2005/Atom}title")
            summary = (item.findtext("{http://www.w3.org/2005/Atom}summary") or
                       item.findtext("{http://www.w3.org/2005/Atom}content"))
            published = (item.findtext("{http://www.w3.org/2005/Atom}published") or
                         item.findtext("{http://www.w3.org/2005/Atom}updated"))
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
            link = link_node.get("href") if link_node is not None else None
        else:
            title, summary = item.findtext("title"), (item.findtext("description") or "")
            published, link = item.findtext("pubDate"), item.findtext("link")
        if _text(title) and link and urlparse(link.strip()).scheme in {"http", "https"}:
            output.append({"title": _text(title), "summary": _text(summary),
                           "url": link.strip(), "published_at": _iso_date(published),
                           "source_name": source.name, "source_kind": source.kind,
                           "category": source.category, "source_confidence": source.confidence})
    if not output:
        raise ScoutError(f"No usable RSS/Atom entries from {source.name}")
    return output


def fetch_feed(source: SourceSpec, timeout: float = 15) -> list[dict]:
    response = requests.get(source.url, timeout=timeout, headers={
        "User-Agent": "DeadpanTechStudio/1.0 (editorial research; one request per configured feed)"
    })
    response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ScoutError(f"Feed from {source.name} exceeds the 5 MB safety limit")
    return parse_feed(response.content, source)


def _category(item: dict) -> str:
    haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    if any(word in haystack for word in (" ai ", "artificial intelligence", "copilot", "model", "voice")):
        return "Practical AI tools"
    if any(word in haystack for word in ("browser", "chrome", "firefox", "tab", "paste")):
        return "Browser and productivity hacks"
    if any(word in haystack for word in ("automat", "workflow", "shortcut", "batch")):
        return "Everyday workflow automations"
    return item.get("category") or "Useful software features"


def _heuristic_scores(item: dict, now: datetime) -> tuple[dict, dict]:
    text = f"{item['title']} {item.get('summary', '')}".lower()
    practical = any(word in text for word in ("how to", "shortcut", "workflow", "save", "edit", "search",
                                               "export", "local", "privacy", "accessibility", "automat"))
    broad = any(word in text for word in ("browser", "email", "document", "file", "photo", "password",
                                           "meeting", "search", "phone", "windows", "android", "ios"))
    visual = any(word in text for word in ("before", "after", "click", "drag", "image", "video", "tab",
                                            "file", "voice", "screen", "browser"))
    account_risk = any(word in text for word in ("enterprise", "admin", "api", "developer preview", "beta"))
    roundup = any(word in item["title"].lower() for word in ("weekly recap", "announcements", "roundup"))
    developer_niche = any(word in text for word in ("github actions", " sdk ", " api ", "command line", "developer"))
    published = item.get("published_at")
    relevance = 2
    relevance_reason = "Publication date unavailable; current relevance is uncertain."
    if published:
        try:
            age = max(0, (now - datetime.fromisoformat(published)).days)
            relevance = 5 if age <= 14 else 4 if age <= 45 else 3 if age <= 120 else 2
            relevance_reason = f"Published {age} days before this research run."
        except ValueError:
            pass
    scores = {
        "problem_strength": 4 if practical else 3,
        "audience_breadth": 5 if broad else 3,
        "visual_hook": 5 if visual else 3,
        "practical_usefulness": 5 if practical else 3,
        "current_relevance": relevance,
        "demo_feasibility": 3 if account_risk else 4,
        "source_confidence": max(1, min(5, int(item.get("source_confidence", 3)))),
        "production_effort": 4 if account_risk else 2,
        "misleading_risk": 4 if account_risk else 2,
    }
    if roundup:
        scores.update(problem_strength=2, visual_hook=2, practical_usefulness=2,
                      demo_feasibility=2, production_effort=3, misleading_risk=3)
    if developer_niche:
        scores["audience_breadth"] = min(scores["audience_breadth"], 2)
    reasons = {
        "problem_strength": "Source language describes an actionable task." if practical else "Pain point must be confirmed with users.",
        "audience_breadth": "Everyday software keywords indicate broad relevance." if broad else "Audience breadth is not established by the source.",
        "visual_hook": "The result can plausibly be shown on screen." if visual else "A strong visual before/after still needs design.",
        "practical_usefulness": "The item describes a practical operation." if practical else "Practical payoff needs independent verification.",
        "current_relevance": relevance_reason,
        "demo_feasibility": "Likely reproducible with local/browser capture." if not account_risk else "May require an account, preview access, or admin setup.",
        "source_confidence": f"Configured source confidence: {scores['source_confidence']}/5 ({item.get('source_kind', 'unknown')}).",
        "production_effort": "Low-to-moderate capture effort." if not account_risk else "Higher setup and access effort.",
        "misleading_risk": "Claims remain bounded to source metadata." if not account_risk else "Preview/access wording raises claim risk.",
    }
    if roundup:
        for key in ("problem_strength", "visual_hook", "practical_usefulness", "demo_feasibility"):
            reasons[key] = "A release roundup is not yet one concrete, demonstrable viewer payoff."
    if developer_niche:
        reasons["audience_breadth"] = "Developer-specific language limits broad audience relevance."
    return scores, reasons


def score_candidate(scores: dict, weights: dict) -> float:
    unknown = set(weights) - set(DEFAULT_WEIGHTS)
    if unknown or any(not isinstance(value, (int, float)) or value < 0 for value in weights.values()):
        raise ValueError(f"Invalid score weights: {sorted(unknown) or 'weights must be non-negative numbers'}")
    numerator = 0.0
    denominator = 0.0
    for key, weight in weights.items():
        raw = float(scores[key])
        contribution = raw if key in POSITIVE else 6 - raw
        numerator += contribution * float(weight)
        denominator += 5 * float(weight)
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def candidate_key(item: dict) -> str:
    title = title_key(item.get("title", ""))
    url = item.get("url", "").split("#", 1)[0].rstrip("/")
    return hashlib.sha256(f"{title}|{url}".encode()).hexdigest()[:16]


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def url_key(url: str) -> str:
    normalized = url.split("#", 1)[0].rstrip("/").lower()
    return "url:" + hashlib.sha256(normalized.encode()).hexdigest()[:16]


def build_candidate(item: dict, weights: dict, *, fixture: bool, discovered_at: str) -> dict:
    now = datetime.fromisoformat(discovered_at)
    scores, reasons = _heuristic_scores(item, now)
    category = _category(item)
    browser = category == "Browser and productivity hacks"
    title = item["title"]
    summary = item.get("summary") or "The source provides a title but no usable description."
    capture = "browser recipe" if browser else "existing browser/command recipe if access permits"
    pain_by_category = {
        "Browser and productivity hacks": "A common browser task takes more clicks or attention than it should.",
        "Practical AI tools": "The viewer needs a useful result without trusting a vague AI promise.",
        "Everyday workflow automations": "A repeatable manual step wastes time and invites mistakes.",
        "Useful software features": "A useful feature is easy to miss or difficult to evaluate from release notes.",
    }
    demo_by_category = {
        "Browser and productivity hacks": "Record the browser state before and after the exact interaction using harmless test data.",
        "Practical AI tools": "Run one bounded input through the real tool, capture its output, and state account, plan, and model limits.",
        "Everyday workflow automations": "Capture the manual baseline, execute the verified automation in an isolated fixture, then compare results.",
        "Useful software features": "Open the supported product version, perform the documented action, and capture the visible result.",
    }
    return {
        "id": slugify(title), "dedup_key": candidate_key(item), "working_title": title,
        "category": category,
        "viewer_pain_point": (pain_by_category[category] if scores["audience_breadth"] >= 4 else
                              "The concrete user frustration still needs community validation."),
        "hook_suggestion": f"Show the useful result first: {title}.",
        "proposed_payoff": "A verified before/after with the limitation stated on screen.",
        "what_it_does": summary[:500],
        "evidence": [{"url": item["url"], "source_name": item.get("source_name"),
                      "source_kind": item.get("source_kind"),
                      "published_at": item.get("published_at"), "discovered_at": discovered_at}],
        "verified_claims": ["The linked source published this title and description."],
        "uncertain_claims": ["Actual availability, exact behavior, platform/version support, price, licensing, and user demand require independent verification."],
        "restrictions": {"version": "unknown", "platform": "unknown", "licensing": "unknown"},
        "research_confidence": "fixture-only" if fixture else ("high-source / untested-product" if scores["source_confidence"] >= 4 else "needs corroboration"),
        "demonstration": {
            "screen_action": demo_by_category[category],
            "capture_compatibility": capture, "external_requirements": "Unknown until editorial verification; do not assume free access.",
            "claims_to_verify": ["Feature exists in the current version", "Result matches source description", "Account/plan/platform requirements"],
            "rights_privacy_safety": "Use an isolated fixture and owned data; avoid personal accounts or third-party media."
        },
        "production_complexity": "high" if scores["production_effort"] >= 4 else "medium" if scores["production_effort"] == 3 else "low",
        "scores": scores, "score_reasons": reasons,
        "score": score_candidate(scores, weights), "fixture_data": fixture,
        "executed_demo": False,
    }


def load_sources(path: Path) -> list[SourceSpec]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sources = [SourceSpec(**{key: value for key, value in item.items() if key != "enabled"})
                   for item in data["sources"] if item.get("enabled", True)]
        if not sources:
            raise ScoutError(f"No enabled sources in {path}")
        return sources
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ScoutError(f"Invalid source configuration {path}: {exc}") from exc


def load_weights(path: Path | None) -> dict:
    if path is None:
        return DEFAULT_WEIGHTS.copy()
    try:
        weights = json.loads(path.read_text(encoding="utf-8"))["weights"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ScoutError(f"Invalid weight configuration {path}: {exc}") from exc
    score_candidate({key: 3 for key in DEFAULT_WEIGHTS}, weights)
    return weights


def known_keys(output_dir: Path) -> set[str]:
    keys: set[str] = set()
    for path in (ROOT / "content").glob("*.json"):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            for url in project.get("sources", []):
                keys.add(candidate_key({"title": project.get("title", ""), "url": url}))
                keys.add(url_key(url))
            keys.add("id:" + slugify(project.get("title", "")))
        except (OSError, json.JSONDecodeError):
            continue
    for path in output_dir.glob("scout-*.json"):
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            for item in prior.get("proposals", []):
                keys.add(item["dedup_key"])
                for evidence in item.get("evidence", []):
                    keys.add(url_key(evidence.get("url", "")))
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    return keys


def _markdown(report: dict) -> str:
    lines = [f"# Deadpan Tech Scout — {report['generated_at']}", "",
             f"**Status:** {report['status']}  ",
             f"**Mode:** {report['mode']}  ",
             f"**Proposals:** {len(report['proposals'])}", ""]
    if report["source_failures"]:
        lines += ["## Source failures", ""] + [f"- {failure}" for failure in report["source_failures"]] + [""]
    lines += ["## Ranked proposals", ""]
    for rank, item in enumerate(report["proposals"], 1):
        lines += [f"### {rank}. {item['working_title']} — {item['score']}/100", "",
                  f"- **Category:** {item['category']}",
                  f"- **Viewer pain:** {item['viewer_pain_point']}",
                  f"- **Hook:** {item['hook_suggestion']}",
                  f"- **Payoff:** {item['proposed_payoff']}",
                  f"- **Confidence:** {item['research_confidence']}",
                  f"- **Demo:** {item['demonstration']['screen_action']}",
                  f"- **Capture:** {item['demonstration']['capture_compatibility']}",
                  f"- **Complexity:** {item['production_complexity']}",
                  f"- **Evidence:** {', '.join(e['url'] for e in item['evidence'])}",
                  f"- **Why this score:** " + "; ".join(item["score_reasons"].values()), ""]
    lines += ["## Editorial gate", "",
              "No demonstration was executed. Select a proposal manually, verify every product claim and restriction, then create a separate content project.", ""]
    return "\n".join(lines)


def run_scout(*, limit: int, fixture_path: Path | None, sources_path: Path,
              weights_path: Path | None, output_dir: Path, include_known: bool = False,
              fetcher=fetch_feed, now: datetime | None = None) -> tuple[Path, Path, dict]:
    if not 1 <= limit <= 50:
        raise ValueError("Scout limit must be between 1 and 50")
    now = now or datetime.now(timezone.utc)
    generated_at = now.isoformat()
    weights = load_weights(weights_path)
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
            except Exception as exc:  # isolate public-source availability failures
                failures.append(f"{source.name}: {exc}")
    if not raw:
        raise ScoutError("No research items were available; no trend report was fabricated")
    known = set() if include_known else known_keys(output_dir)
    unique: dict[str, dict] = {}
    seen_titles: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not item.get("title") or not item.get("url"):
            failures.append("Skipped malformed item without title or URL")
            continue
        if urlparse(item["url"]).scheme not in {"http", "https"}:
            failures.append(f"Skipped item with unsupported URL scheme: {item['title']}")
            continue
        key = candidate_key(item)
        if key in known or url_key(item["url"]) in known or "id:" + slugify(item["title"]) in known:
            continue
        normalized_title = title_key(item["title"])
        if normalized_title in seen_titles:
            continue
        candidate = build_candidate(item, weights, fixture=fixture, discovered_at=generated_at)
        unique.setdefault(key, candidate)
        seen_titles.add(normalized_title)
    ranked = sorted(unique.values(), key=lambda item: (-item["score"], item["working_title"].lower()))[:limit]
    status = "fixture" if fixture else ("complete" if len(ranked) >= limit and not failures else "incomplete")
    report = {"version": 1, "generated_at": generated_at, "mode": "offline-fixture" if fixture else "live-public-feeds",
              "status": status, "requested_limit": limit, "weights": weights,
              "source_failures": failures, "proposals": ranked,
              "notice": "Research proposals only. No demonstrations executed and no claims approved."}
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
