#!/usr/bin/env python3
"""Unit tests for SmartCache management and mtime invalidation."""

import unittest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import proton_runner_gui
from proton_runner_gui import SmartCache


class TestSmartCache(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)
        self.cache_file = self.base_path / "cache.json"
        self.patcher = patch.object(proton_runner_gui, "CACHE_FILE", self.cache_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp_dir.cleanup()

    def test_save_and_load_cache(self):
        lib = self.base_path / "steam_lib"
        steamapps = lib / "steamapps"
        steamapps.mkdir(parents=True)
        vdf = steamapps / "libraryfolders.vdf"
        vdf.write_text('"libraryfolders" {}')

        sample_games = [
            {"appid": "3513350", "name": "Wuthering Waves", "last_played": 100}
        ]

        SmartCache.save(sample_games, [lib])
        self.assertTrue(self.cache_file.is_file())

        loaded = SmartCache.load()
        self.assertIsNotNone(loaded)
        games = loaded.get("games", [])
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["appid"], "3513350")

    def test_cache_invalidation_on_mtime_change(self):
        lib = self.base_path / "steam_lib"
        steamapps = lib / "steamapps"
        steamapps.mkdir(parents=True)
        vdf = steamapps / "libraryfolders.vdf"
        vdf.write_text('"libraryfolders" {}')

        sample_games = [{"appid": "100", "name": "Game"}]
        SmartCache.save(sample_games, [lib])

        # Modify file timestamp
        time.sleep(0.05)
        vdf.write_text('"libraryfolders" { "1" { "path" "/new" } }')

        loaded = SmartCache.load()
        # Should detect mtime invalidation and return None
        self.assertIsNone(loaded)

    def test_cache_load_missing(self):
        self.assertIsNone(SmartCache.load())


if __name__ == "__main__":
    unittest.main()
