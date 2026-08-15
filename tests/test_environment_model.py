#!/usr/bin/env python3
"""Unit tests for GameEnvironment model and credential sanitization."""

import unittest
from proton_runner_gui import GameEnvironment, sanitize_env_vars


class TestEnvironmentModel(unittest.TestCase):
    def test_model_defaults_and_serialization(self):
        env = GameEnvironment(
            appid="3513350",
            game_name="Wuthering Waves",
            proton_provider="GE-Proton (GloriousEggroll)",
            wineprefix="/home/user/pfx"
        )
        d = env.to_dict()
        self.assertEqual(d["appid"], "3513350")
        self.assertEqual(d["game_name"], "Wuthering Waves")
        self.assertEqual(d["proton_provider"], "GE-Proton (GloriousEggroll)")
        self.assertFalse(d["is_ntfs_warn"])

    def test_sanitize_env_vars(self):
        raw_env = {
            "STEAM_COMPAT_APP_ID": "3513350",
            "USER_PASSWORD": "supersecretpassword",
            "AUTH_TOKEN": "12345abcdef",
            "SESSION_COOKIE": "xyz987",
            "PATH": "/usr/bin:/bin"
        }
        sanitized = sanitize_env_vars(raw_env)
        self.assertEqual(sanitized["STEAM_COMPAT_APP_ID"], "3513350")
        self.assertEqual(sanitized["PATH"], "/usr/bin:/bin")
        self.assertEqual(sanitized["USER_PASSWORD"], "[REDACTED]")
        self.assertEqual(sanitized["AUTH_TOKEN"], "[REDACTED]")
        self.assertEqual(sanitized["SESSION_COOKIE"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
