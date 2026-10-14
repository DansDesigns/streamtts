"""Offline unit tests for GitHub update/version handling."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater  # noqa: E402


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit=-1):
        return self.data


class UpdaterTests(unittest.TestCase):
    def test_versions_compare_numerically_not_lexically(self):
        self.assertTrue(updater.is_newer_version("0.1.10", "0.1.9"))
        self.assertFalse(updater.is_newer_version("0.1.4", "0.1.5"))
        self.assertFalse(updater.is_newer_version("v0.1.5", "0.1.5"))

    def test_release_is_newer_than_matching_prerelease(self):
        self.assertTrue(updater.is_newer_version("0.1.5", "0.1.5-beta"))

    def test_invalid_version_rejected(self):
        with self.assertRaises(ValueError):
            updater.parse_version("not a version")

    def test_main_branch_version_is_read(self):
        with patch.object(updater, "urlopen", return_value=FakeResponse(b"0.1.6\n")):
            self.assertEqual(updater.fetch_latest_version(), ("0.1.6", "main"))

    def test_falls_back_to_master_when_main_file_is_missing(self):
        def fake_urlopen(request, timeout=0):
            if "/main/" in request.full_url:
                raise HTTPError(request.full_url, 404, "not found", {}, None)
            return FakeResponse(b"v0.1.7\r\n")

        with patch.object(updater, "urlopen", side_effect=fake_urlopen):
            self.assertEqual(updater.fetch_latest_version(), ("0.1.7", "master"))

    def test_invalid_remote_content_is_reported(self):
        with patch.object(updater, "urlopen", return_value=FakeResponse(b"hello world")):
            with self.assertRaises(updater.UpdateCheckError):
                updater.fetch_latest_version()


if __name__ == "__main__":
    unittest.main()
