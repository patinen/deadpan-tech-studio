import json
import copy
import tempfile
import unittest
from pathlib import Path

from studio.capture import HOST, PORT, demo_command, prepare_demo_site
from studio.quality import check

ROOT = Path(__file__).resolve().parents[1]


class CaptureTests(unittest.TestCase):
    def test_http_server_command_is_localhost_only(self):
        command = demo_command(Path("safe-fixture"))
        self.assertIn("--bind", command)
        self.assertEqual(command[command.index("--bind") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("http.server") + 1], str(PORT))
        self.assertEqual(HOST, "127.0.0.1")

    def test_fixture_contains_only_generated_harmless_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = prepare_demo_site(Path(directory))
            self.assertEqual({path.name for path in paths},
                             {"index.html", "style.css", "demo.js", "readme.txt"})
            html = (Path(directory) / "index.html").read_text(encoding="utf-8")
            self.assertIn("LOCALHOST-ONLY DEMO", html)
            self.assertIn("--bind 127.0.0.1", html)

    def test_task_03_project_uses_real_capture_assets_and_focus_layout(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        self.assertEqual(project["production"]["capture"], "http_server")
        self.assertTrue(all(scene["asset"].endswith(".mp4") for scene in project["scenes"]))
        self.assertTrue(all(scene["visual"]["layout"] == "focus" for scene in project["scenes"]))
        errors, warnings = check(project)
        self.assertFalse(errors)
        self.assertTrue(any("capture" in warning.lower() for warning in warnings))

    def test_callouts_must_fit_inside_scene(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        invalid = copy.deepcopy(project)
        invalid["scenes"][0]["edit"]["callouts"][0]["end"] = 99
        errors, _ = check(invalid)
        self.assertTrue(any("callout timing" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
