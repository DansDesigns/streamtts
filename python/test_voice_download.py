"""Tests voice archive loading for catalog and user-added Piper model IDs."""
from __future__ import annotations

import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gui_app  # noqa: E402


def build_archive(model_id: str) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:bz2") as archive:
        for name, content in (
            (f"{model_id}/fake-voice.onnx", b"mock onnx"),
            (f"{model_id}/tokens.txt", b"mock tokens\n"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


class VoiceDownloadTests(unittest.TestCase):
    def test_non_catalogued_model_id_can_download(self):
        model_id = "vits-piper-en_GB-cori-high"
        with tempfile.TemporaryDirectory() as temp:
            original_models = gui_app.MODELS_DIR
            gui_app.MODELS_DIR = Path(temp)
            try:
                archive_bytes = build_archive(model_id)
                with patch.object(gui_app, "urlopen", return_value=io.BytesIO(archive_bytes)):
                    path = gui_app.download_voice(model_id)
                self.assertEqual(path.name, model_id)
                self.assertTrue((path / "fake-voice.onnx").is_file())
                self.assertTrue((path / "tokens.txt").is_file())
            finally:
                gui_app.MODELS_DIR = original_models

    def test_invalid_system_voice_id_is_not_treated_as_model(self):
        with self.assertRaises(ValueError):
            gui_app.download_voice("system::not-a-model")


if __name__ == "__main__":
    unittest.main()
