from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import census  # noqa: E402
import console  # noqa: E402
import pcap_convert  # noqa: E402
import pcap_summary  # noqa: E402

SAMPLE = ROOT / "samples" / "demo-synthetic-join.pcap"


class SyntheticDemoTests(unittest.TestCase):
    def test_analysis_has_join_commands_addresses_and_rssi(self) -> None:
        rows = console.decode_pcap(SAMPLE, limit=100)["rows"]
        self.assertEqual(len(rows), 18)
        self.assertIn("Association Request", {row["detail"] for row in rows})
        self.assertIn("Association Response", {row["detail"] for row in rows})
        self.assertTrue(all(row["rssi"] is not None for row in rows))
        self.assertGreaterEqual(sum(bool(row["secured"]) for row in rows), 2)

    def test_census_finds_one_open_synthetic_pan(self) -> None:
        networks = census.census([SAMPLE])
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]["channel"], 15)
        self.assertTrue(networks[0]["zigbee"])
        self.assertTrue(networks[0]["permit_join"])

    def test_cli_decoders_locate_long_address_mac_commands(self) -> None:
        frames = [item[0] for item in pcap_summary.records(SAMPLE.read_bytes())]
        labels = {pcap_summary.classify(item) for item in frames}
        descriptions = {pcap_convert.describe(item) for item in frames}
        self.assertIn("MAC-Command: Association Request", labels)
        self.assertIn("MAC-Command: Association Response", labels)
        self.assertTrue(any("Data Request" in item for item in descriptions))


if __name__ == "__main__":
    unittest.main()
