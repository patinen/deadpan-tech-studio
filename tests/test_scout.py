import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from studio.scout import (DEFAULT_WEIGHTS, ScoutError, SourceSpec, build_candidate,
                          parse_feed, run_scout, score_candidate, url_key)


def item(title="Useful browser shortcut", url="https://example.test/item"):
    return {"title": title, "summary": "A browser shortcut saves a repetitive file task.",
            "url": url, "published_at": "2026-11-01T00:00:00+00:00",
            "source_name": "Test Docs", "source_kind": "official docs",
            "category": "Browser and productivity hacks", "source_confidence": 5}


class ScoutTests(unittest.TestCase):
    def test_feed_parser_accepts_rss_and_rejects_malformed_xml(self):
        source = SourceSpec("Official", "https://example.test/feed")
        payload = b"""<rss><channel><item><title>Browser shortcut</title>
        <link>https://example.test/shortcut</link><description>Save a repetitive task.</description>
        <pubDate>Sun, 01 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
        parsed = parse_feed(payload, source)
        self.assertEqual(parsed[0]["url"], "https://example.test/shortcut")
        self.assertTrue(parsed[0]["published_at"].startswith("2026-11-01"))
        with self.assertRaisesRegex(ScoutError, "Malformed feed"):
            parse_feed(b"<rss><broken>", source)

    def test_scoring_is_deterministic_and_penalizes_effort_and_risk(self):
        strong = {key: 5 for key in DEFAULT_WEIGHTS}
        strong["production_effort"] = strong["misleading_risk"] = 1
        risky = strong | {"production_effort": 5, "misleading_risk": 5}
        self.assertGreater(score_candidate(strong, DEFAULT_WEIGHTS),
                           score_candidate(risky, DEFAULT_WEIGHTS))
        self.assertEqual(score_candidate(strong, DEFAULT_WEIGHTS),
                         score_candidate(strong, DEFAULT_WEIGHTS))

    def test_roundups_and_developer_topics_do_not_outrank_concrete_hacks(self):
        now = "2026-11-09T00:00:00+00:00"
        concrete = build_candidate(item("Search browser tabs from the keyboard"),
                                   DEFAULT_WEIGHTS, fixture=False, discovered_at=now)
        roundup = build_candidate(item("60 biggest AI announcements weekly recap"),
                                  DEFAULT_WEIGHTS, fixture=False, discovered_at=now)
        developer = build_candidate(item("GitHub Actions developer workflow API"),
                                    DEFAULT_WEIGHTS, fixture=False, discovered_at=now)
        self.assertGreater(concrete["score"], roundup["score"])
        self.assertGreater(concrete["scores"]["audience_breadth"],
                           developer["scores"]["audience_breadth"])

    def test_candidates_preserve_uncertainty_and_never_claim_execution(self):
        proposal = build_candidate(item(), DEFAULT_WEIGHTS, fixture=False,
                                   discovered_at="2026-11-09T12:00:00+00:00")
        self.assertFalse(proposal["executed_demo"])
        self.assertTrue(proposal["uncertain_claims"])
        self.assertEqual(proposal["restrictions"]["licensing"], "unknown")
        self.assertEqual(proposal["evidence"][0]["url"], "https://example.test/item")

    def test_fixture_run_deduplicates_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.json"
            fixture.write_text(json.dumps({"items": [item(), item()]}), encoding="utf-8")
            sources = root / "sources.json"
            sources.write_text('{"sources": []}', encoding="utf-8")
            now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
            first_json, _, first = run_scout(limit=10, fixture_path=fixture,
                sources_path=sources, weights_path=None, output_dir=root / "out",
                include_known=True, now=now)
            second_json, _, second = run_scout(limit=10, fixture_path=fixture,
                sources_path=sources, weights_path=None, output_dir=root / "out",
                include_known=True, now=now)
            self.assertEqual(len(first["proposals"]), 1)
            self.assertEqual(first["status"], "fixture")
            self.assertNotEqual(first_json, second_json)
            self.assertTrue(second_json.name.endswith("-1.json"))
            self.assertEqual(len(second["proposals"]), 1)

    def test_partial_source_failure_is_reported_as_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "sources.json"
            sources.write_text(json.dumps({"sources": [
                {"name": "Working", "url": "https://example.test/one"},
                {"name": "Broken", "url": "https://example.test/two"}]}), encoding="utf-8")
            def fetcher(source):
                if source.name == "Broken":
                    raise ScoutError("HTTP 503")
                return [item()]
            _, _, report = run_scout(limit=10, fixture_path=None, sources_path=sources,
                weights_path=None, output_dir=root / "out", include_known=True,
                fetcher=fetcher, now=datetime(2026, 11, 9, tzinfo=timezone.utc))
            self.assertEqual(report["status"], "incomplete")
            self.assertIn("HTTP 503", report["source_failures"][0])

    def test_all_source_failures_do_not_fabricate_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "sources.json"
            sources.write_text('{"sources":[{"name":"Broken","url":"https://example.test"}]}',
                               encoding="utf-8")
            with self.assertRaisesRegex(ScoutError, "No research items"):
                run_scout(limit=10, fixture_path=None, sources_path=sources,
                    weights_path=None, output_dir=root / "out", include_known=True,
                    fetcher=lambda _source: (_ for _ in ()).throw(ScoutError("blocked")),
                    now=datetime(2026, 11, 9, tzinfo=timezone.utc))

    def test_malformed_fixture_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "bad.json"
            fixture.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(ScoutError, "Invalid scout fixture"):
                run_scout(limit=10, fixture_path=fixture, sources_path=root / "unused",
                          weights_path=None, output_dir=root / "out")

    def test_unsupported_urls_are_skipped_and_url_dedup_is_stable(self):
        self.assertEqual(url_key("HTTPS://EXAMPLE.TEST/item#details"),
                         url_key("https://example.test/item/"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.json"
            fixture.write_text(json.dumps({"items": [{
                "title": "Unsafe source", "url": "file:///private/data",
                "summary": "Do not load this", "source_confidence": 5,
            }]}), encoding="utf-8")
            _, _, report = run_scout(
                limit=10, fixture_path=fixture, sources_path=root / "unused",
                weights_path=None, output_dir=root / "out", include_known=True,
                now=datetime(2026, 11, 9, tzinfo=timezone.utc))
            self.assertEqual([], report["proposals"])
            self.assertIn("unsupported URL scheme", report["source_failures"][0])

    def test_same_topic_title_from_repeated_releases_appears_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.json"
            fixture.write_text(json.dumps({"items": [
                item("Stable Channel Update", "https://example.test/one"),
                item("stable-channel update", "https://example.test/two"),
            ]}), encoding="utf-8")
            _, _, report = run_scout(
                limit=10, fixture_path=fixture, sources_path=root / "unused",
                weights_path=None, output_dir=root / "out", include_known=True,
                now=datetime(2026, 11, 9, tzinfo=timezone.utc))
            self.assertEqual(1, len(report["proposals"]))


if __name__ == "__main__":
    unittest.main()
