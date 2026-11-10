import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import requests

from studio.editorial import (EditorialError, build_production_brief, fetch_article,
                              gemini_analyze, load_fixture, replay_model_response,
                              save_brief, select_candidate, validate_analysis)
from studio.utils import ROOT


SOURCE = "https://example.test/article"


def analysis(**updates):
    value = {
        "classification": "ui feature", "accepted": True, "rejection_reason": "",
        "actual_feature": "The product edits a supported text file in its real web interface.",
        "viewer_problem": "Moving a draft between tools adds avoidable copying and correction work.",
        "realistic_benefit": "A first editing pass can remain in one supported interface.",
        "target_audience": "People who prepare short work documents with the product.",
        "visual_demonstration": "Capture a harmless text file, one real edit, and the resulting downloaded file.",
        "opening_hook": "Fix this draft without opening a second editor.",
        "availability": {"status": "available", "platforms": ["web"],
                         "accounts_or_plans": ["eligible accounts"], "rollout": "available",
                         "restrictions": []},
        "claims": [{"text": "The web interface can edit the supported file.",
                    "evidence_urls": [SOURCE], "confidence": "high"}],
        "uncertainties": ["The interaction has not been reproduced."], "sources": [SOURCE],
        "script": ["Fix this draft without opening a second editor.",
                   "Upload harmless notes, create a text file, and edit the real preview in the web app.",
                   "Then highlight one paragraph and request a shorter version, keeping the full result visible.",
                   "One fewer copy-paste ritual. Software has discovered staying in one tab."],
        "shot_plan": [{"seconds": 4, "shot": "Real completed result."},
                      {"seconds": 7, "shot": "Real upload and create action."},
                      {"seconds": 8, "shot": "Real edit and resulting text."},
                      {"seconds": 5, "shot": "Before/after and restrictions."}],
    }
    value.update(updates)
    return value


class _Response:
    status_code = 200
    content = b"x" * 500
    text = """<html><head><link rel='canonical' href='https://example.test/article?utm_source=feed'></head>
    <body><nav>Menu words are not article evidence.</nav><article><h1>Real feature</h1>
    <p>This is actual article content describing a supported file-editing feature in detail.</p>
    <p>It explains account availability, web restrictions, and the observable result.</p>
    <p>The remaining text makes this a sufficiently substantial article for deterministic testing.</p></article></body></html>"""
    headers = {"Content-Type": "text/html; charset=utf-8"}
    def raise_for_status(self): pass


class _Session:
    @staticmethod
    def get(*_args, **_kwargs): return _Response()


class EditorialTests(unittest.TestCase):
    def test_article_fetch_extracts_content_and_canonical_url(self):
        result = fetch_article(SOURCE, session=_Session)
        self.assertEqual(SOURCE, result["url"])
        self.assertIn("actual article content", result["text"])
        self.assertNotIn("Menu words", result["text"])

    def test_scout_http_workspace_candidate_upgrades_to_verified_https(self):
        http_url = "http://workspaceupdates.googleblog.com/2026/10/create-preview-and-edit-files-directly-in-the-Gemini-app.html"
        https_url = http_url.replace("http://", "https://")
        report = {"proposals": [{"id": "gemini-files", "working_title": "Create files",
                                  "evidence": [{"url": http_url}]}]}
        candidate = select_candidate(report, http_url)
        class RecordingSession:
            urls = []
            @classmethod
            def get(cls, url, **_kwargs):
                cls.urls.append(url)
                response = _Response()
                response.text = response.text.replace("https://example.test/article?utm_source=feed", https_url)
                return response
        article = fetch_article(candidate["evidence"][0]["url"], session=RecordingSession)
        self.assertEqual(https_url, RecordingSession.urls[0])
        self.assertEqual(https_url, article["url"])
        checked_data = analysis()
        checked_data["sources"] = [https_url]
        checked_data["claims"][0]["evidence_urls"] = [https_url]
        checked = validate_analysis(checked_data, [article["url"]])
        brief = build_production_brief(candidate, checked, analysis_mode="gemini")
        self.assertTrue(brief["publication_blocked"])

    def test_article_fetch_rejects_cross_host_redirect(self):
        class Redirect:
            status_code = 302
            headers = {"Location": "https://evil.test/article"}
            content = b""
            text = ""
            def raise_for_status(self): pass
        class RedirectSession:
            @staticmethod
            def get(*_args, **_kwargs): return Redirect()
        with self.assertRaisesRegex(EditorialError, "unverified host"):
            fetch_article(SOURCE, session=RedirectSession)

    def test_article_fetch_rejects_cross_host_canonical(self):
        class CanonicalSession:
            @staticmethod
            def get(*_args, **_kwargs):
                response = _Response()
                response.text = response.text.replace("https://example.test/article?utm_source=feed",
                                                      "https://evil.test/copied-article")
                return response
        with self.assertRaisesRegex(EditorialError, "canonical URL crossed"):
            fetch_article(SOURCE, session=CanonicalSession)

    def test_malformed_model_response_is_rejected(self):
        with self.assertRaisesRegex(EditorialError, "missing fields"):
            validate_analysis({"classification": "tool demo"}, [SOURCE])

    def test_trivial_null_representations_are_safely_normalized(self):
        value = analysis(rejection_reason=None)
        value["availability"]["restrictions"] = None
        checked = validate_analysis(value, [SOURCE])
        self.assertEqual("", checked["rejection_reason"])
        self.assertEqual([], checked["availability"]["restrictions"])

    def test_missing_or_object_restrictions_remain_invalid(self):
        missing = analysis()
        del missing["availability"]["restrictions"]
        with self.assertRaisesRegex(EditorialError, "restrictions must be a string list"):
            validate_analysis(missing, [SOURCE])
        object_value = analysis()
        object_value["availability"]["restrictions"] = {"platform": "web"}
        with self.assertRaisesRegex(EditorialError, "restrictions must be a string list"):
            validate_analysis(object_value, [SOURCE])

    def test_non_object_and_malformed_nested_model_values_are_controlled(self):
        for root in (None, [], "json", 7):
            with self.subTest(root=root), self.assertRaisesRegex(EditorialError, "root must be"):
                validate_analysis(root, [SOURCE])
        malformed = [
            analysis(classification=["tool demo"]),
            analysis(sources=[7]),
            analysis(claims=[{"text": "Claim", "confidence": "high", "evidence_urls": [7]}]),
            analysis(claims=[{"text": "Claim", "confidence": ["high"], "evidence_urls": [SOURCE]}]),
            analysis(availability={"status": ["available"], "platforms": [],
                                   "accounts_or_plans": [], "rollout": "now", "restrictions": []}),
            analysis(availability={"status": "available", "platforms": "web",
                                   "accounts_or_plans": [], "rollout": "now", "restrictions": []}),
            analysis(uncertainties=[{"not": "text"}]),
            analysis(shot_plan=[{"seconds": -1, "shot": "x"}] * 4),
            analysis(shot_plan=[{"seconds": float("nan"), "shot": "x"}] * 4),
            analysis(shot_plan=[{"seconds": True, "shot": "x"}] * 4),
        ]
        for value in malformed:
            with self.subTest(value=value), self.assertRaises(EditorialError):
                validate_analysis(value, [SOURCE])

    def test_fabricated_citations_and_unsupported_claims_are_rejected(self):
        bad_source = analysis(sources=["https://invented.test/source"])
        with self.assertRaisesRegex(EditorialError, "not supplied"):
            validate_analysis(bad_source, [SOURCE])
        unsupported = analysis(claims=[{"text": "It is popular", "evidence_urls": [], "confidence": "high"}])
        with self.assertRaisesRegex(EditorialError, "Every factual claim"):
            validate_analysis(unsupported, [SOURCE])

    def test_unavailable_features_cannot_be_accepted(self):
        value = analysis()
        value["availability"]["status"] = "unavailable"
        with self.assertRaisesRegex(EditorialError, "cannot be accepted"):
            validate_analysis(value, [SOURCE])

    def test_missing_provider_credentials_fail_clearly(self):
        candidate = {"id": "test", "working_title": "Test"}
        article = {"url": SOURCE, "text": "Evidence text"}
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(EditorialError, "GEMINI_API_KEY"):
                gemini_analyze(candidate, article)

    def test_valid_structured_response_uses_complete_schema(self):
        captured = {}
        class Response:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": json.dumps(analysis())}]}}]}
        def requester(_url, **kwargs):
            captured.update(kwargs)
            return Response()
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "secret-key"}):
            checked = gemini_analyze({"id": "x"}, {"url": SOURCE, "text": "article"}, requester=requester)
        schema = captured["json"]["generationConfig"]["responseJsonSchema"]
        self.assertEqual("object", schema["type"])
        self.assertEqual("array", schema["properties"]["availability"]["properties"]["restrictions"]["type"])
        self.assertEqual("number", schema["properties"]["shot_plan"]["items"]["properties"]["seconds"]["type"])
        self.assertEqual("ui feature", checked["classification"])

    def test_invalid_model_output_writes_redacted_diagnostic_and_replays_offline(self):
        class Response:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"candidates": [{"content": {"parts": [{"text": "{bad json"}]}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "secret-key"}):
                with self.assertRaisesRegex(EditorialError, "saved diagnostic"):
                    gemini_analyze({"id": "x"}, {"url": SOURCE, "text": "article"},
                                   requester=lambda *_args, **_kwargs: Response(), diagnostic_dir=root)
            diagnostic = next(root.glob("*.json"))
            self.assertNotIn("secret-key", diagnostic.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(EditorialError, "malformed JSON"):
                replay_model_response(diagnostic, [SOURCE])

            valid_path = root / "valid.json"
            valid_path.write_text(json.dumps({"raw_model_output": json.dumps(analysis())}), encoding="utf-8")
            self.assertEqual("ui feature", replay_model_response(valid_path, [SOURCE])["classification"])

    def test_transient_errors_retry_with_bounded_backoff(self):
        calls, sleeps = [], []
        class Response:
            def __init__(self, status): self.status_code = status
            def raise_for_status(self):
                if self.status_code >= 400:
                    response = requests.Response()
                    response.status_code = self.status_code
                    raise requests.HTTPError(f"HTTP {self.status_code}", response=response)
            def json(self): return {"candidates": [{"content": {"parts": [{"text": json.dumps(analysis())}]}}]}
        statuses = iter([429, 503, 200])
        def requester(*_args, **_kwargs):
            status = next(statuses); calls.append(status); return Response(status)
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "secret-key"}):
            gemini_analyze({"id": "x"}, {"url": SOURCE, "text": "article"}, requester=requester,
                           sleep_fn=sleeps.append)
        self.assertEqual([429, 503, 200], calls)
        self.assertEqual([1, 2], sleeps)

    def test_schema_failure_is_not_retried(self):
        calls = []
        class Response:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"candidates": [{"content": {"parts": [{"text": json.dumps({"accepted": True})}]}}]}
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict("os.environ", {"GEMINI_API_KEY": "secret-key"}):
            with self.assertRaisesRegex(EditorialError, "schema error"):
                gemini_analyze({"id": "x"}, {"url": SOURCE, "text": "article"},
                               requester=lambda *_args, **_kwargs: calls.append(1) or Response(),
                               diagnostic_dir=Path(directory), sleep_fn=lambda _seconds: None)
        self.assertEqual([1], calls)

    def test_editorial_rejection_is_explicit(self):
        value = analysis(classification="security advisory", accepted=False,
                         rejection_reason="Useful warning, but not a safe product demonstration.")
        checked = validate_analysis(value, [SOURCE])
        brief = build_production_brief({"id": "security", "working_title": "Patch now"}, checked,
                                       analysis_mode="fixture")
        self.assertTrue(brief["publication_blocked"])
        self.assertTrue(any("not a safe product" in blocker for blocker in brief["publication_blockers"]))

    def test_duplicate_topic_is_not_written_twice(self):
        checked = validate_analysis(analysis(), [SOURCE])
        brief = build_production_brief({"id": "one", "working_title": "One"}, checked,
                                       analysis_mode="fixture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_brief(brief, root / "one.json")
            with self.assertRaisesRegex(EditorialError, "Duplicate editorial topic"):
                save_brief(brief | {"id": "two"}, root / "two.json")

    def test_explicit_promotion_archives_fixture_and_resets_approval(self):
        checked = validate_analysis(analysis(), [SOURCE])
        fixture_brief = build_production_brief({"id": "one", "working_title": "One"}, checked,
                                               analysis_mode="offline-fixture")
        fixture_brief["review"]["facts_checked"] = True
        live_brief = build_production_brief({"id": "one", "working_title": "One"}, checked,
                                            analysis_mode="gemini", demo_verified=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "one.json"
            save_brief(fixture_brief, output)
            save_brief(live_brief, output, promote=True)
            promoted = json.loads(output.read_text(encoding="utf-8"))
            archived = json.loads((root / "history" / "one.v1.json").read_text(encoding="utf-8"))
            self.assertTrue(archived["review"]["facts_checked"])
            self.assertTrue(promoted["promotion"]["previous_review"]["facts_checked"])
            self.assertFalse(any(promoted["review"].values()))
            self.assertTrue(promoted["publication_blocked"])
            self.assertEqual(2, promoted["revision"])

    def test_promotion_rejects_unrelated_or_fixture_replacement(self):
        checked = validate_analysis(analysis(), [SOURCE])
        current = build_production_brief({"id": "one", "working_title": "One"}, checked,
                                         analysis_mode="offline-fixture")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "one.json"
            save_brief(current, output)
            unrelated = current | {"sources": ["https://example.test/other"], "analysis_mode": "gemini"}
            with self.assertRaisesRegex(EditorialError, "source mismatch"):
                save_brief(unrelated, output, promote=True)
            with self.assertRaisesRegex(EditorialError, "non-fixture"):
                save_brief(current, output, promote=True)

    def test_promotion_happens_only_after_successful_validation(self):
        checked = validate_analysis(analysis(), [SOURCE])
        current = build_production_brief({"id": "one", "working_title": "One"}, checked,
                                         analysis_mode="offline-fixture")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "one.json"
            save_brief(current, output)
            before = output.read_text(encoding="utf-8")
            invalid = analysis()
            invalid["availability"]["restrictions"] = {"bad": "shape"}
            with self.assertRaises(EditorialError):
                validate_analysis(invalid, [SOURCE])
            self.assertEqual(before, output.read_text(encoding="utf-8"))
            self.assertFalse((Path(directory) / "history").exists())

    def test_pilot_fixture_is_valid_and_blocked_without_real_demo(self):
        fixture = ROOT / "fixtures" / "editorial" / "gemini-file-editing.json"
        candidate, _article, checked = load_fixture(fixture)
        brief = build_production_brief(candidate, checked, analysis_mode="offline-fixture")
        self.assertTrue(brief["publication_blocked"])
        self.assertFalse(brief["review"]["demo_verified"])
        self.assertEqual(25, brief["script_target_seconds"])
        self.assertTrue(all(claim["evidence_urls"] for claim in brief["claims"]))


if __name__ == "__main__":
    unittest.main()
