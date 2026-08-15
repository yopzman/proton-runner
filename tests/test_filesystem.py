#!/usr/bin/env python3
"""Unit tests for filesystem detection and NTFS warning logic."""

import unittest
from proton_runner_gui import detect_filesystem_type, GameEnvironment


class TestFilesystem(unittest.TestCase):
    def test_detect_filesystem_nonexistent(self):
        fs = detect_filesystem_type("/nonexistent/path/xyz")
        self.assertEqual(fs, "unknown")

    def test_ntfs_warn_flag(self):
        env1 = GameEnvironment(appid="1", game_name="Test", game_fs="ntfs", pfx_fs="ext4", is_ntfs_warn=True)
        self.assertTrue(env1.is_ntfs_warn)

        env2 = GameEnvironment(appid="2", game_name="Test", game_fs="btrfs", pfx_fs="btrfs", is_ntfs_warn=False)
        self.assertFalse(env2.is_ntfs_warn)


if __name__ == "__main__":
    unittest.main()
