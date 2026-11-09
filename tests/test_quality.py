import copy
import json
import unittest
from pathlib import Path

from studio.quality import check
from studio.render import PRESETS
from studio.subtitles import build_manifest, group_phrases, validate_manifest
from studio.utils import narr_hash, slugify

ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads((ROOT / "content" / "001-stop-copy-pasting.json").read_text())

    def test_sample_is_valid_draft(self):
        errors, warnings = check(self.project)
        self.assertFalse(errors)
        self.assertTrue(warnings)

    def test_publication_requires_review(self):
        errors, warnings = check(self.project, require_approval=True)
        self.assertTrue(any("Publication blocked" in x for x in errors))
        approved = copy.deepcopy(self.project)
        approved["review"] = {"facts_checked": True, "assets_licensed": True, "final_approved": True}
        errors, warnings = check(approved, require_approval=True)
        self.assertFalse(errors)

    def test_missing_narration_is_error(self):
        project = copy.deepcopy(self.project)
        project["scenes"][0]["narration"] = ""
        errors, _ = check(project)
        self.assertTrue(any("narration" in x for x in errors))

    def test_hash_changes_when_narration_changes(self):
        self.assertNotEqual(narr_hash("A"), narr_hash("B"))

    def test_slug(self):
        self.assertEqual(slugify("AI & Tech Hacks!"), "ai-tech-hacks")

    def test_output_presets_are_vertical_and_production_is_full_hd(self):
        self.assertEqual((PRESETS["draft"]["width"], PRESETS["draft"]["height"]), (540, 960))
        self.assertEqual((PRESETS["production"]["width"], PRESETS["production"]["height"]), (1080, 1920))

    def test_phrase_grouping_is_short_and_lossless(self):
        narration = self.project["scenes"][1]["narration"]
        phrases = group_phrases(narration)
        self.assertEqual(" ".join(phrases), narration)
        self.assertTrue(all(len(phrase.split()) <= 6 for phrase in phrases))

    def test_subtitle_manifest_is_ordered_and_within_scene_duration(self):
        durations = [float(scene["duration"]) for scene in self.project["scenes"]]
        manifest = build_manifest(self.project, durations, [False] * len(durations))
        validate_manifest(manifest, self.project, durations)
        for scene, duration in zip(manifest["scenes"], durations):
            self.assertEqual(scene["timing_source"], "nominal_scene_duration")
            self.assertLessEqual(scene["cues"][-1]["end"], duration)

    def test_subtitle_manifest_rejects_changed_narration(self):
        durations = [float(scene["duration"]) for scene in self.project["scenes"]]
        manifest = build_manifest(self.project, durations, [True] * len(durations))
        changed = copy.deepcopy(self.project)
        changed["scenes"][0]["narration"] += " Changed."
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_manifest(manifest, changed, durations)


if __name__ == "__main__":
    unittest.main()
