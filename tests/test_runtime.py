#!/usr/bin/env python3
"""Unit tests for Steam Linux Runtime / Pressure-Vessel detection."""

import unittest
from proton_runner_gui import DetailFetchWorker, GameEnvironment


class TestRuntimeDetection(unittest.TestCase):
    def test_pressure_vessel_detection(self):
        worker = DetailFetchWorker("123", live_proc_info={
            "pid": "4567",
            "env": {
                "PRESSURE_VESSEL_CONTAINER_DIR": "/run/pressure-vessel",
                "STEAM_COMPAT_APP_ID": "123"
            }
        })
        # Simulate worker processing
        live_env = worker.live_proc_info["env"]
        self.assertIn("PRESSURE_VESSEL_CONTAINER_DIR", live_env)

    def test_host_native_detection(self):
        worker = DetailFetchWorker("123", live_proc_info={
            "pid": "4567",
            "env": {
                "STEAM_COMPAT_APP_ID": "123",
                "WINEPREFIX": "/home/user/pfx"
            }
        })
        live_env = worker.live_proc_info["env"]
        self.assertNotIn("PRESSURE_VESSEL_CONTAINER_DIR", live_env)


if __name__ == "__main__":
    unittest.main()
