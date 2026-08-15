#!/usr/bin/env python3
"""Integration tests for proton-runner CLI subcommands."""

import unittest
import subprocess
from pathlib import Path

CLI_PATH = Path(__file__).resolve().parent.parent / "proton-runner"


class TestCLI(unittest.TestCase):
    def test_version_output(self):
        p = subprocess.run([str(CLI_PATH), "--version"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("proton-runner 0.3.0", p.stdout)

    def test_help_output(self):
        p = subprocess.run([str(CLI_PATH), "--help"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("Usage:", p.stdout)
        self.assertIn("proton-runner", p.stdout)

    def test_list_command(self):
        p = subprocess.run([str(CLI_PATH), "list"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("Running Steam games:", p.stdout)

    def test_doctor_command(self):
        p = subprocess.run([str(CLI_PATH), "doctor"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("Proton Runner Diagnostic Report", p.stdout)

    def test_invalid_command(self):
        p = subprocess.run([str(CLI_PATH), "invalid_command_xyz"], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("Error:", p.stderr)


if __name__ == "__main__":
    unittest.main()
