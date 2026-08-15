#!/usr/bin/env python3
"""Unit tests for Steam discovery and error isolation."""

import unittest
import tempfile
from pathlib import Path

from proton_runner_gui import scan_games_in_libraries, scan_proton_installations


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_scan_games_filtering(self):
        steamapps = self.base_path / "steamapps"
        steamapps.mkdir(parents=True)

        # Real game
        acf1 = steamapps / "appmanifest_3513350.acf"
        acf1.write_text('"AppState" { "appid" "3513350" "name" "Wuthering Waves" "LastPlayed" "1000" }')

        # Ignored tool (Proton Experimental)
        acf2 = steamapps / "appmanifest_1493710.acf"
        acf2.write_text('"AppState" { "appid" "1493710" "name" "Proton Experimental" "LastPlayed" "0" }')

        # Ignored tool (Steam Linux Runtime)
        acf3 = steamapps / "appmanifest_1628350.acf"
        acf3.write_text('"AppState" { "appid" "1628350" "name" "Steam Linux Runtime 3.0 (sniper)" "LastPlayed" "0" }')

        games = scan_games_in_libraries([self.base_path])
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["appid"], "3513350")
        self.assertEqual(games[0]["name"], "Wuthering Waves")

    def test_scan_games_missing_library_does_not_crash(self):
        missing_lib = self.base_path / "nonexistent"
        games = scan_games_in_libraries([missing_lib])
        self.assertEqual(games, [])

    def test_scan_proton_installations(self):
        compat_dir = self.base_path / "compatibilitytools.d" / "GE-Proton-Test"
        compat_dir.mkdir(parents=True)
        proton_bin = compat_dir / "proton"
        proton_bin.write_text("#!/bin/sh\nexit 0")
        proton_bin.chmod(0o755)

        protons = scan_proton_installations([self.base_path])
        self.assertTrue(any(p["name"] == "GE-Proton-Test" for p in protons))


if __name__ == "__main__":
    unittest.main()
