#!/usr/bin/env python3
"""Unit tests for Proton Provider classification."""

import unittest
from proton_runner_gui import classify_proton_provider


class TestProtonProviders(unittest.TestCase):
    def test_ge_proton_classification(self):
        self.assertEqual(
            classify_proton_provider("GE-Proton11-3", "/home/user/.steam/compatibilitytools.d/GE-Proton11-3/proton"),
            "GE-Proton (GloriousEggroll)"
        )

    def test_experimental_classification(self):
        self.assertEqual(
            classify_proton_provider("Proton Experimental", "/steamapps/common/Proton Experimental/proton"),
            "Valve Proton (Experimental)"
        )

    def test_hotfix_classification(self):
        self.assertEqual(
            classify_proton_provider("Proton Hotfix", "/steamapps/common/Proton Hotfix/proton"),
            "Valve Proton (Hotfix)"
        )

    def test_official_valve_classification(self):
        self.assertEqual(
            classify_proton_provider("Proton 9.0", "/steamapps/common/Proton 9.0/proton"),
            "Valve Official Proton"
        )
        self.assertEqual(
            classify_proton_provider("Proton 8.0", "/steamapps/common/Proton 8.0/proton"),
            "Valve Official Proton"
        )

    def test_custom_cachyos_classification(self):
        self.assertEqual(
            classify_proton_provider("proton-cachyos", "/home/user/.steam/compatibilitytools.d/proton-cachyos/proton"),
            "Custom / Community Build"
        )


if __name__ == "__main__":
    unittest.main()
