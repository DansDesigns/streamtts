#!/usr/bin/env python3
"""Type directly into a terminal and hear speech begin before the sentence ends.

Windows CMD/Windows Terminal is supported without Visual Studio. On Windows,
characters are read with msvcrt; on POSIX, stdin is temporarily put in raw mode.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from streamtts_python import StreamingTTS  # noqa: E402


@contextmanager
def raw_terminal():
    if os.name == "nt":
        yield
        return
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_key() -> str:
    if os.name == "nt":
        import msvcrt
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            msvcrt.getwch()  # consume the extended-key code
            return ""
        return key
    return sys.stdin.read(1)


def main() -> int:
    model_dir = ROOT / "models" / "vits-piper-en_US-amy-low"
    if not (model_dir / "en_US-amy-low.onnx").exists():
        print("Voice model is not installed yet.")
        print("Run setup_windows.bat (Windows) or: python scripts/download_model.py")
        return 2

    print("Loading local voice model; first startup can take a few seconds...")
    try:
        tts = StreamingTTS(model_dir, mode="balanced", num_threads=2, speed=1.0)
    except Exception as exc:
        print(f"Could not start StreamTTS: {exc}")
        return 1

    print("\nStreamTTS interactive test — no Visual Studio required for this Python test")
    print("Type normally. Speech starts after word boundaries; you do not need to press Enter.")
    print("Backspace edits the current unsubmitted word. Enter flushes the line.")
    print("Ctrl+C exits. Voice: Piper en_US-amy-low.\n")
    print("> ", end="", flush=True)
    current_word = ""

    try:
        with raw_terminal():
            while True:
                ch = read_key()
                if ch == "":
                    continue
                if ch == "\x03":  # Ctrl+C in Windows console
                    break
                if ch == "\x04":  # Ctrl+D on POSIX
                    break
                if ch in ("\x08", "\x7f"):
                    if current_word:
                        current_word = current_word[:-1]
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    if current_word:
                        tts.push_text(current_word + "\n")
                        current_word = ""
                    else:
                        tts.push_text("\n")
                    tts.flush()
                    sys.stdout.write("> ")
                    sys.stdout.flush()
                    continue
                if ch == "\x1b":  # Escape
                    continue
                if ch.isprintable() and not ch.isspace():
                    sys.stdout.write(ch)
                    sys.stdout.flush()
                    current_word += ch
                    # Sentence-ending punctuation can be submitted immediately.
                    if ch in ".!?" and current_word:
                        tts.push_text(current_word)
                        current_word = ""
                    continue
                if ch.isspace():
                    sys.stdout.write(ch)
                    sys.stdout.flush()
                    if current_word:
                        tts.push_text(current_word + ch)
                        current_word = ""
                    else:
                        tts.push_text(ch)
    except KeyboardInterrupt:
        pass
    finally:
        # If the terminal reader exits mid-word, speak the unfinished word too.
        try:
            if current_word:
                tts.push_text(current_word)
            tts.flush()
            tts.wait_until_idle()
        except Exception as exc:
            print(f"\nWarning while draining audio: {exc}")
        try:
            tts.close()
        except Exception as exc:
            print(f"\nWarning while closing TTS: {exc}")
        print("\nStreamTTS closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
