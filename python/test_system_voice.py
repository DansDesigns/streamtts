"""Unit tests for the OS voice backend using a small fake pyttsx3 engine."""
from __future__ import annotations

import sys
import types
import unittest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from system_voice import SystemVoiceTTS  # noqa: E402


class FakeVoice:
    id = "fake-system-voice"
    name = "Fake Voice"


class FakeEngine:
    def __init__(self):
        self.spoken = []
        self.properties = {"voices": [FakeVoice()], "rate": 180, "voice": FakeVoice.id}

    def getProperty(self, name):
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def say(self, text):
        self.spoken.append(text)

    def runAndWait(self):
        pass

    def stop(self):
        pass


class SystemVoiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        fake_module = types.ModuleType("pyttsx3")
        fake_module.init = lambda driverName=None: self.engine
        self.old_module = sys.modules.get("pyttsx3")
        sys.modules["pyttsx3"] = fake_module

    def tearDown(self):
        if self.old_module is None:
            sys.modules.pop("pyttsx3", None)
        else:
            sys.modules["pyttsx3"] = self.old_module

    def test_incremental_text_and_flush(self):
        tts = SystemVoiceTTS("fake-system-voice", mode="balanced")
        try:
            tts.push_text("hello there ")
            tts.wait_until_idle()
            self.assertEqual(self.engine.spoken, ["hello there"])
            tts.push_text("last word")
            tts.flush()
            tts.wait_until_idle()
            self.assertEqual(self.engine.spoken[-1], "last word")
        finally:
            tts.close()

    def test_rate_update_is_applied(self):
        tts = SystemVoiceTTS("fake-system-voice")
        try:
            tts.set_speed(1.5)
            tts.wait_until_idle()
            self.assertEqual(self.engine.properties["rate"], 270)
            self.assertFalse(tts.supports_pitch)
        finally:
            tts.close()


if __name__ == "__main__":
    unittest.main()
