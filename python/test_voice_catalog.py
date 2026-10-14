"""Sanity checks for the built-in Piper voice library."""
from __future__ import annotations
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voice_catalog import VOICE_CATALOG, VOICE_ITEMS  # noqa: E402

MODEL_ID_RE = re.compile(r"^vits-piper-[A-Za-z0-9][A-Za-z0-9_.-]{0,140}$")


class VoiceCatalogTests(unittest.TestCase):
    def test_catalog_has_many_profiles(self):
        self.assertGreaterEqual(len(VOICE_CATALOG), 60)
        self.assertEqual(len(VOICE_CATALOG), len(VOICE_ITEMS))

    def test_ids_are_valid_and_unique(self):
        model_ids = [model_id for model_id, _label in VOICE_ITEMS]
        self.assertEqual(len(model_ids), len(set(model_ids)))
        for model_id, label in VOICE_ITEMS:
            self.assertRegex(model_id, MODEL_ID_RE)
            self.assertTrue(label.strip())
            self.assertEqual(VOICE_CATALOG[model_id]["model_name"], model_id)

    def test_expected_english_and_international_voices_are_included(self):
        expected = (
            "vits-piper-en_GB-cori-high",
            "vits-piper-en_GB-jenny_dioco-medium",
            "vits-piper-en_US-ryan-high",
            "vits-piper-fr_FR-siwis-medium",
            "vits-piper-de_DE-thorsten-medium",
            "vits-piper-es_ES-davefx-medium",
            "vits-piper-it_IT-paola-medium",
            "vits-piper-pl_PL-gosia-medium",
        )
        for model_id in expected:
            self.assertIn(model_id, VOICE_CATALOG)


if __name__ == "__main__":
    unittest.main()
