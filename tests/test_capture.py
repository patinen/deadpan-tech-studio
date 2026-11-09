import json
import copy
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest import mock
import tempfile
import unittest
from pathlib import Path

from studio.capture import (HOST, PORT, _stop_process, _wait_for_server,
                            assert_port_available, demo_command, prepare_demo_site,
                            stop_transcript)
from studio.quality import check
from studio.visual_qa import sample_timestamps

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
            self.assertIn("[hidden]{display:none!important}",
                          (Path(directory) / "style.css").read_text(encoding="utf-8"))

    def test_playwright_result_is_hidden_until_click(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("Playwright is not installed")
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            prepare_demo_site(site)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto((site / "index.html").as_uri())
                result = page.locator("#result")
                self.assertTrue(result.is_hidden())
                page.locator("#inspect").click()
                self.assertTrue(result.is_visible())
                browser.close()

    def test_port_conflict_is_rejected_before_capture(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((HOST, 0))
            port = listener.getsockname()[1]
            listener.listen(1)
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                assert_port_available(HOST, port)
            self.assertEqual(listener.getsockname()[1], port)
        finally:
            listener.close()

    def test_readiness_rejects_unrelated_server(self):
        class UnrelatedHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"unrelated local service"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer((HOST, 0), UnrelatedHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        process = mock.Mock()
        process.poll.return_value = None
        try:
            with self.assertRaisesRegex(RuntimeError, "unrelated content"):
                _wait_for_server(f"http://{HOST}:{server.server_port}/", "our-marker",
                                 process, timeout=1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_cleanup_kills_process_after_interrupt_timeout(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("demo", 4), 9]
        process.returncode = -9
        exit_code, forced = _stop_process(process)
        self.assertTrue(forced)
        self.assertEqual(exit_code, -9)
        process.kill.assert_called_once()

    def test_stop_transcript_hides_platform_specific_exit_code(self):
        self.assertEqual(stop_transcript(3221225786, False),
                         "Process stopped by Control C")
        self.assertIn("timed out", stop_transcript(-9, True))

    def test_contact_sheet_timestamps_cover_video_without_edges(self):
        timestamps = sample_timestamps(40.0, 8)
        self.assertEqual(len(timestamps), 8)
        self.assertGreaterEqual(timestamps[0], 0)
        self.assertLess(timestamps[-1], 40.0)
        self.assertEqual(timestamps, sorted(timestamps))

    def test_task_03_project_uses_real_capture_assets_and_focus_layout(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        self.assertEqual(project["production"]["capture"], "http_server")
        self.assertTrue(all(scene["asset"].endswith(".mp4") for scene in project["scenes"]))
        self.assertTrue(all(scene["visual"]["layout"] == "focus" for scene in project["scenes"]))
        errors, warnings = check(project)
        self.assertFalse(errors)
        self.assertTrue(any("capture" in warning.lower() for warning in warnings))

    def test_sample_is_audience_first_and_result_led(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        self.assertGreaterEqual(sum(scene["duration"] for scene in project["scenes"]), 20)
        self.assertLessEqual(sum(scene["duration"] for scene in project["scenes"]), 28)
        hook = project["scenes"][0]
        self.assertTrue(hook["asset"].endswith("browser-real.mp4"))
        self.assertGreaterEqual(hook["edit"]["asset_start"], 2.0)
        self.assertGreater(hook["edit"]["zoom"], 1.0)

    def test_callouts_must_fit_inside_scene(self):
        project = json.loads((ROOT / "content" / "002-instant-local-file-server.json").read_text())
        invalid = copy.deepcopy(project)
        invalid["scenes"][0]["edit"]["callouts"][0]["end"] = 99
        errors, _ = check(invalid)
        self.assertTrue(any("callout timing" in error for error in errors))

    def test_task_05_projects_use_reusable_verified_recipes(self):
        projects = [json.loads((ROOT / "content" / name).read_text(encoding="utf-8")) for name in (
            "003-paste-without-formatting.json", "004-local-ai-voice.json",
            "005-batch-rename-files.json")]
        self.assertEqual({project["production"]["capture_plan"]["type"] for project in projects},
                         {"browser", "command"})
        for project in projects:
            self.assertEqual(project["production"]["capture"], "recipe")
            self.assertTrue(project["sources"])
            self.assertTrue(20 <= sum(scene["duration"] for scene in project["scenes"]) <= 30)
            self.assertFalse(any(project["review"].values()))
            self.assertGreater(len({scene.get("visual", {}).get("layout", "inset")
                                    for scene in project["scenes"]}), 1)

    def test_browser_recipe_requires_plain_text_result(self):
        project = json.loads((ROOT / "content" / "003-paste-without-formatting.json").read_text())
        assertion = project["production"]["capture_plan"]["assertions"][0]
        self.assertTrue(assertion["plain_text"])
        self.assertEqual(assertion["text"], "Quarterly plan \u2014 review Friday")


if __name__ == "__main__":
    unittest.main()
