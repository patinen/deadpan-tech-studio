import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio.production_bridge import (BridgeError, convert_brief, evaluate_editorial,
                                      intake_recording, save_project)
from studio.graphics import build_frame
from studio.quality import check, is_publication_approved, publication_readiness
from studio.render import render


SOURCE = "https://example.test/official-feature"


def brief():
    return {
        "id": "pilot", "title": "Edit a useful file", "status": "editorial-draft",
        "sources": [SOURCE],
        "viewer_pain_point": "Rough meeting notes require copying into a second editor before they become an action plan.",
        "proposed_benefit": "The viewer ends with an edited action-plan file while avoiding one copy-and-paste step.",
        "script": ["Turn these rough notes into an editable action plan without opening another editor.",
                   "Upload harmless notes, generate the file, then correct the due date in the real preview.",
                   "Highlight one paragraph, shorten it, and compare the original notes with the finished file."],
        "shots": [
            {"seconds": 5, "narration": "Turn these rough notes into an editable action plan without opening another editor.",
             "shot": "Open on the finished real action plan beside the harmless source notes."},
            {"seconds": 8, "narration": "Upload harmless notes, generate the file, then correct the due date in the real preview.",
             "shot": "Upload meeting-notes.txt, type the action-plan prompt, and edit the due date."},
            {"seconds": 7, "narration": "Highlight one paragraph, shorten it, and compare the original notes with the finished file.",
             "shot": "Highlight the paragraph, request a shorter version, and reveal the final result."},
        ],
        "required_real_demonstrations": ["Upload harmless notes, edit a due date, shorten a paragraph, and show the final file."],
        "claims": [{"text": "The feature edits supported files.", "evidence_urls": [SOURCE], "confidence": "high"}],
        "availability": {"status": "available", "restrictions": ["web only"]},
        "editorial_warnings": [],
        "publication_blockers": ["Real demonstration is not verified."],
        "review": {"facts_checked": False, "demo_verified": False, "assets_licensed": False,
                   "script_approved": False, "final_approved": False},
    }


def media_probe(duration=12):
    return {"format": {"duration": str(duration), "size": "100"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920}]}


class ProductionBridgeTests(unittest.TestCase):
    def test_editorial_gate_separates_creative_and_evidence_quality(self):
        value = brief()
        value["script"][0] = "See how this feature works."
        value["viewer_pain_point"] = "Switching apps causes friction."
        result = evaluate_editorial(value)
        self.assertEqual("pass", result["evidence_integrity"]["status"])
        self.assertEqual("human_review_required", result["factual_validity"]["status"])
        self.assertIsNone(result["factual_validity"]["score"])
        self.assertEqual("blocked", result["production_readiness"]["status"])
        self.assertEqual("human_review_required", result["creative_quality"]["status"])
        self.assertTrue(result["revision_suggestions"])
        self.assertFalse(any("word" in reason.lower() for reason in result["creative_quality"]["reasons"]))

    def test_editorial_gate_handles_malformed_claims_and_shots_without_raw_errors(self):
        value = brief()
        value["claims"] = ["not-an-object", {"text": "Missing evidence", "evidence_urls": None}]
        value["shots"][0]["seconds"] = "eventually"
        result = evaluate_editorial(value)
        self.assertEqual("blocked", result["evidence_integrity"]["status"])
        self.assertIn("invalid duration", " ".join(result["production_readiness"]["reasons"]))

    def test_conversion_preserves_claims_sources_and_blocks_all_reviews(self):
        project = convert_brief(brief(), project_id="006-pilot", source_brief="editorial/pilot.json")
        self.assertEqual([SOURCE], project["sources"])
        self.assertEqual(brief()["claims"], project["claims"])
        self.assertEqual(3, len(project["scenes"]))
        self.assertTrue(all(scene["asset"] is None for scene in project["scenes"]))
        self.assertTrue(all(value is False for value in project["review"].values()))
        self.assertTrue(project["editorial"]["publication_blocked"])
        errors, warnings = check(project, require_approval=True)
        self.assertTrue(any("script_approved" in error for error in errors))
        self.assertTrue(any("Authentic editorial footage missing" in error for error in errors))
        self.assertTrue(any("placeholder draft" in warning for warning in warnings))

    def test_final_approval_alone_cannot_publish_editorial_project(self):
        project = convert_brief(brief())
        project["review"]["final_approved"] = True
        self.assertFalse(is_publication_approved(project))
        for key in project["review"]:
            project["review"][key] = True
        self.assertFalse(is_publication_approved(project))

    def _attach_footage(self, project, root, shot_ids):
        for shot_id in shot_ids:
            path = root / f"{shot_id}.mp4"
            path.write_bytes(f"real-{shot_id}".encode())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            scene = next(scene for scene in project["scenes"] if scene["id"] == shot_id)
            scene["asset"] = str(path)
            project["editorial"]["demo_intake"][shot_id] = {
                "imported_asset": str(path), "sha256": digest,
                "operator_owned": True, "verified_by_human": False,
            }

    def _approve_reviews(self, project):
        for key in project["review"]:
            project["review"][key] = True

    def test_publication_readiness_requires_every_clip_evidence_and_demo_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = convert_brief(brief())
            self._approve_reviews(project)
            self.assertFalse(publication_readiness(project)["ready"])

            self._attach_footage(project, root, ["shot-01"])
            self.assertFalse(publication_readiness(project)["ready"])

            self._attach_footage(project, root, ["shot-02", "shot-03"])
            project["review"]["demo_verified"] = False
            project["editorial"]["publication_blocked"] = False
            project["editorial"]["publication_blockers"] = []
            self.assertFalse(publication_readiness(project)["ready"])

            project["review"]["demo_verified"] = True
            readiness = publication_readiness(project)
            self.assertTrue(readiness["ready"])
            self.assertEqual("approved", readiness["status"])

            Path(project["scenes"][0]["asset"]).write_bytes(b"tampered-after-intake")
            readiness = publication_readiness(project)
            self.assertFalse(readiness["ready"])
            self.assertTrue(any("hash does not match" in item for item in readiness["blockers"]))

    def test_explicit_editorial_blocker_cannot_silently_approve(self):
        with tempfile.TemporaryDirectory() as directory:
            project = convert_brief(brief())
            self._attach_footage(project, Path(directory), ["shot-01", "shot-02", "shot-03"])
            self._approve_reviews(project)
            project["editorial"]["publication_blockers"] = []
            project["editorial"]["publication_blocked"] = True
            readiness = publication_readiness(project)
            self.assertFalse(readiness["ready"])
            self.assertTrue(any("publication_blocked" in item for item in readiness["blockers"]))

    def test_renderer_keeps_draft_watermark_and_report_when_clips_are_missing(self):
        project = convert_brief(brief())
        self._approve_reviews(project)
        project["editorial"]["publication_blockers"] = []
        project["editorial"]["publication_blocked"] = False
        original_build = build_frame
        draft_values = []

        def observed_build(*args, **kwargs):
            draft_values.append(kwargs["draft"])
            return original_build(*args, **kwargs)

        def fake_run(command):
            target = Path(command[-1])
            if target.suffix.lower() in {".mp4", ".jpg"}:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"render-fixture")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            voice = root / "voice.wav"; voice.write_bytes(b"voice")
            output = root / "draft.mp4"
            with (mock.patch("studio.render.assert_tool"),
                  mock.patch("studio.render.locate_voice", return_value=voice),
                  mock.patch("studio.render.duration_seconds", return_value=3.0),
                  mock.patch("studio.render.run", side_effect=fake_run),
                  mock.patch("studio.render.probe_media", return_value=media_probe(20)),
                  mock.patch("studio.render.build_frame", side_effect=observed_build)):
                render(project, project_path, output=output)
            report = json.loads((root / "pilot.quality.json").read_text(encoding="utf-8"))
            self.assertTrue(all(draft_values))
            self.assertEqual("draft", report["status"])
            self.assertFalse(report["publication_ready"])
            self.assertTrue(any("footage missing" in item.lower() for item in report["blockers"]))

    def test_focus_placeholder_is_visibly_distinct_from_real_footage_frame(self):
        scene = convert_brief(brief())["scenes"][0]
        placeholder = build_frame(scene, 1, 3, draft=True, has_video=False)
        recorded = build_frame(scene, 1, 3, draft=True, has_video=True)
        self.assertNotEqual(placeholder.tobytes(), recorded.tobytes())

    def test_save_project_rejects_repeated_runs_and_duplicate_sources(self):
        project = convert_brief(brief())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(project, root / "one.json")
            with self.assertRaisesRegex(BridgeError, "overwrite"):
                save_project(project, root / "one.json")
            duplicate = project | {"id": "different"}
            with self.assertRaisesRegex(BridgeError, "Duplicate project"):
                save_project(duplicate, root / "two.json")

    def test_intake_copies_original_and_maps_trim_reframe_with_traceability(self):
        project = convert_brief(brief())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path, media = root / "project.json", root / "owned.mp4"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            media.write_bytes(b"operator-owned-video")
            evidence = intake_recording(project_path, "shot-01", media, start=1, duration=5,
                                        zoom=1.2, focus_x=0.4, focus_y=0.6,
                                        asset_root=root / "imports", probe=lambda _path: media_probe())
            updated = json.loads(project_path.read_text(encoding="utf-8"))
            self.assertEqual(b"operator-owned-video", media.read_bytes())
            self.assertTrue(Path(evidence["imported_asset"]).is_file())
            self.assertEqual(1.0, updated["scenes"][0]["edit"]["asset_start"])
            self.assertEqual(1.2, updated["scenes"][0]["edit"]["zoom"])
            self.assertFalse(updated["review"]["demo_verified"])
            self.assertFalse(evidence["verified_by_human"])
            with self.assertRaisesRegex(BridgeError, "already exists"):
                intake_recording(project_path, "shot-01", media, asset_root=root / "imports",
                                 probe=lambda _path: media_probe())

    def test_intake_rejects_missing_wrong_media_and_invalid_trim(self):
        project = convert_brief(brief())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            with self.assertRaisesRegex(BridgeError, "existing MP4"):
                intake_recording(project_path, "shot-01", root / "missing.mp4")
            wrong = root / "still.png"; wrong.write_bytes(b"png")
            with self.assertRaisesRegex(BridgeError, "existing MP4"):
                intake_recording(project_path, "shot-01", wrong)
            video = root / "owned.mp4"; video.write_bytes(b"video")
            with self.assertRaisesRegex(BridgeError, "ffprobe"):
                intake_recording(project_path, "shot-01", video, asset_root=root / "imports",
                                 probe=lambda _path: (_ for _ in ()).throw(OSError("bad media")))
            with self.assertRaisesRegex(BridgeError, "remain inside"):
                intake_recording(project_path, "shot-01", video, start=10, duration=5,
                                 asset_root=root / "imports", probe=lambda _path: media_probe(12))
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.assertRaisesRegex(BridgeError, "finite"):
                    intake_recording(project_path, "shot-01", video, start=value, duration=5,
                                     asset_root=root / "imports", probe=lambda _path: media_probe(12))
                with self.assertRaisesRegex(BridgeError, "finite"):
                    intake_recording(project_path, "shot-01", video, start=0, duration=value,
                                     asset_root=root / "imports", probe=lambda _path: media_probe(12))
                with self.assertRaisesRegex(BridgeError, "finite"):
                    intake_recording(project_path, "shot-01", video, start=0, duration=5,
                                     asset_root=root / "imports",
                                     probe=lambda _path, v=value: media_probe(v))


if __name__ == "__main__":
    unittest.main()
