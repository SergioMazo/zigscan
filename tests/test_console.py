from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import console  # noqa: E402
import capture  # noqa: E402


class CaptureDisplayNameTests(unittest.TestCase):
    def test_sweep_capture_includes_time(self) -> None:
        root = pathlib.Path("/tmp/zigscan/captures")
        path = root / "scan-20260815-173818" / "ch15.pcap"
        with mock.patch.object(console.paths, "CAPTURES", root):
            self.assertEqual(console.capture_display_name(path), "scan-173818 / ch15.pcap")

    def test_direct_capture_keeps_filename(self) -> None:
        root = pathlib.Path("/tmp/zigscan/captures")
        path = root / "console-20260815-173818.pcap"
        with mock.patch.object(console.paths, "CAPTURES", root):
            self.assertEqual(console.capture_display_name(path), path.name)


class ConsoleLanguageTests(unittest.TestCase):
    def test_capture_messages_have_english_and_spanish_variants(self) -> None:
        self.assertEqual(capture.msg("captured", lang="en", frames=5),
                         "5 frames captured.")
        self.assertEqual(capture.msg("captured", lang="es", frames=5),
                         "5 tramas capturadas.")

    def test_job_passes_selected_language_to_worker(self) -> None:
        job = console.Job("capture", ["worker"], ROOT, lang="en")
        self.assertEqual(job.env["ZIGSCAN_LANG"], "en")


if __name__ == "__main__":
    unittest.main()
