import copy
import json
import tempfile
import unittest
from pathlib import Path

from studio.quality import check
from studio.render import PRESETS, focal_zoom_filter, result_audio_filter
from studio.graphics import scene_panel
from studio.speech import narration_config
from studio.subtitles import (build_manifest, group_phrases, load_or_create_manifest,
                              validate_manifest, wrap_ass_text, write_ass)
from studio.utils import narr_hash, slugify

ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def test_long_subtitle_wraps_inside_production_safe_width(self):
        wrapped = wrap_ass_text(
            "A deliberately long phrase that must remain readable on narrow mobile screens",
            888, 58)
        self.assertIn(r"\N", wrapped)
        self.assertEqual(wrapped.replace(r"\N", " ").split(),
                         "A deliberately long phrase that must remain readable on narrow mobile screens".split())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            write_ass(path, [{"start": 0, "end": 2, "text": wrapped.replace(r"\N", " ")}],
                      1080, 1920)
            ass = path.read_text(encoding="utf-8-sig")
            self.assertIn("WrapStyle: 0", ass)
            self.assertIn(",96,96,184,", ass)
            self.assertIn(r"\N", ass)

    def test_focal_zoom_is_optional_and_targets_configured_region(self):
        self.assertEqual(focal_zoom_filter({}, 1000, 1200), "")
        value = focal_zoom_filter({"zoom": 1.3, "focus_x": 0.25, "focus_y": 0.4},
                                  1000, 1200)
        self.assertIn("z='1.300'", value)
        self.assertIn("iw*0.250", value)
        self.assertIn("ih*0.400", value)

    def test_long_focus_headline_moves_panel_below_text(self):
        short_top = scene_panel({"headline": "SHORT", "visual": {"layout": "audio_demo"}})[1]
        long_top = scene_panel({"headline": "NO HOSTED API REQUIRED",
                                "visual": {"layout": "audio_demo"}})[1]
        self.assertGreater(long_top, short_top)
        self.assertGreaterEqual(long_top, 175)

    def test_verified_result_audio_is_delayed_trimmed_and_mixed(self):
        value = result_audio_filter(2, 3, {"result_audio_start": 2.5,
                                           "result_audio_duration": 2.2,
                                           "result_audio_volume": 0.8})
        self.assertIn("atrim=0:2.200", value)
        self.assertIn("adelay=2500|2500", value)
        self.assertIn("volume=0.800", value)
        self.assertIn("amix=inputs=2", value)

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

    def test_nominal_manifest_is_not_silently_used_for_audio(self):
        import tempfile

        durations = [float(scene["duration"]) for scene in self.project["scenes"]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subtitles.json"
            load_or_create_manifest(path, self.project, durations, [False] * len(durations))
            with self.assertRaisesRegex(ValueError, "narration audio is now available"):
                load_or_create_manifest(path, self.project, durations, [True] * len(durations))

    def test_default_manifest_refreshes_when_measured_audio_arrives(self):
        import tempfile

        nominal = [float(scene["duration"]) for scene in self.project["scenes"]]
        measured = [duration - 1 for duration in nominal]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subtitles.json"
            load_or_create_manifest(path, self.project, nominal, [False] * len(nominal))
            refreshed = load_or_create_manifest(
                path, self.project, measured, [True] * len(measured), auto_refresh=True
            )
            self.assertTrue(all(
                scene["timing_source"] == "measured_audio" for scene in refreshed["scenes"]
            ))
            self.assertEqual(refreshed["scenes"][0]["duration"], measured[0])

    def test_task_02_project_remains_valid_after_real_capture_upgrade(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        errors, warnings = check(project)
        self.assertFalse(errors)
        self.assertTrue(all(scene["visual"]["layout"] == "focus"
                            for scene in project["scenes"]))
        self.assertTrue(any("capture" in warning.lower() for warning in warnings))

    def test_project_narration_configuration_and_cli_override(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        config = narration_config(project)
        self.assertEqual(config["engine"], "piper")
        self.assertEqual(config["voice"], "en_US-lessac-medium")
        self.assertEqual(narration_config(project, engine="espeak", speed=145)["engine"], "espeak")

    def test_caption_emphasis_is_selective(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        durations = [float(scene["duration"]) for scene in project["scenes"]]
        manifest = build_manifest(project, durations, [False] * len(durations))
        emphasized = [cue for scene in manifest["scenes"] for cue in scene["cues"]
                      if cue.get("emphasis")]
        plain = [cue for scene in manifest["scenes"] for cue in scene["cues"]
                 if not cue.get("emphasis")]
        self.assertTrue(emphasized)
        self.assertTrue(plain)


if __name__ == "__main__":
    unittest.main()
