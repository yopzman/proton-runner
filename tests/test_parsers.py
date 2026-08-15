#!/usr/bin/env python3
"""Unit tests for Steam VDF and ACF metadata parsers."""

import unittest
import tempfile
from pathlib import Path

from proton_runner_gui import parse_vdf_paths, parse_acf_file


class TestParsers(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_parse_vdf_valid(self):
        lib1 = self.base_path / "lib1"
        lib2 = self.base_path / "lib2"
        lib1.mkdir()
        lib2.mkdir()

        vdf_content = f'''
"libraryfolders"
{{
    "0"
    {{
        "path"		"{lib1}"
        "label"		""
    }}
    "1"
    {{
        "path"		"{lib2}"
        "label"		"Games"
    }}
}}
'''
        vdf_file = self.base_path / "libraryfolders.vdf"
        vdf_file.write_text(vdf_content)

        paths = parse_vdf_paths(vdf_file)
        self.assertEqual(len(paths), 2)
        self.assertIn(lib1.resolve(), paths)
        self.assertIn(lib2.resolve(), paths)

    def test_parse_vdf_missing_file(self):
        non_existent = self.base_path / "does_not_exist.vdf"
        paths = parse_vdf_paths(non_existent)
        self.assertEqual(paths, [])

    def test_parse_vdf_unmounted_path(self):
        vdf_content = '''
"libraryfolders"
{
    "0"
    {
        "path"		"/nonexistent/unmounted/disk/steamapps"
    }
}
'''
        vdf_file = self.base_path / "libraryfolders.vdf"
        vdf_file.write_text(vdf_content)

        paths = parse_vdf_paths(vdf_file)
        self.assertEqual(paths, [])

    def test_parse_acf_valid(self):
        acf_content = '''
"AppState"
{
    "appid"		"3513350"
    "Universe"		"1"
    "name"		"Wuthering Waves"
    "StateFlags"		"4"
    "installdir"		"Wuthering Waves"
    "LastPlayed"		"1786718811"
}
'''
        acf_file = self.base_path / "appmanifest_3513350.acf"
        acf_file.write_text(acf_content)

        meta = parse_acf_file(acf_file)
        self.assertEqual(meta["appid"], "3513350")
        self.assertEqual(meta["name"], "Wuthering Waves")
        self.assertEqual(meta["last_played"], 1786718811)
        self.assertEqual(meta["installdir"], "Wuthering Waves")

    def test_parse_acf_malformed_syntax(self):
        acf_content = 'AppState { broken content syntax'
        acf_file = self.base_path / "appmanifest_999999.acf"
        acf_file.write_text(acf_content)

        meta = parse_acf_file(acf_file)
        self.assertEqual(meta["appid"], "999999")
        self.assertEqual(meta["name"], "AppID 999999")
        self.assertEqual(meta["last_played"], 0)


if __name__ == "__main__":
    unittest.main()
