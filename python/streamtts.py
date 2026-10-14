"""Thin ctypes wrapper for the StreamTTS native library (no pip dependencies).

Build the C++ project with -DBUILD_SHARED_LIBS=ON, then load libstreamtts.so
(Linux) or streamtts.dll (Windows). Audio is delivered through a callback on a
native worker thread; copy the samples during the callback if retaining them.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Callable, Optional


AudioCallback = Callable[[ctypes.POINTER(ctypes.c_float), int, int], None]
ErrorCallback = Callable[[str], None]


class _Config(ctypes.Structure):
    _fields_ = [
        ("model_path", ctypes.c_char_p),
        ("tokens_path", ctypes.c_char_p),
        ("data_dir", ctypes.c_char_p),
        ("provider", ctypes.c_char_p),
        ("num_threads", ctypes.c_int32),
        ("speaker_id", ctypes.c_int32),
        ("speed", ctypes.c_float),
        ("chunking_mode", ctypes.c_int32),
        ("max_words_per_chunk", ctypes.c_size_t),
    ]


_AUDIO_CFUNC = ctypes.CFUNCTYPE(
    None, ctypes.POINTER(ctypes.c_float), ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p
)
_ERROR_CFUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_void_p)


class _Callbacks(ctypes.Structure):
    _fields_ = [("audio", _AUDIO_CFUNC), ("error", _ERROR_CFUNC), ("user_data", ctypes.c_void_p)]


class StreamTTS:
    """Native TTS wrapper exposing ``push_text`` and ``flush``."""

    def __init__(
        self,
        library: os.PathLike | str,
        model_path: os.PathLike | str,
        tokens_path: os.PathLike | str,
        data_dir: os.PathLike | str = "",
        *,
        audio_callback: Optional[AudioCallback] = None,
        error_callback: Optional[ErrorCallback] = None,
        mode: str = "balanced",
        num_threads: int = 2,
        speaker_id: int = 0,
        speed: float = 1.0,
        max_words_per_chunk: int = 0,
    ) -> None:
        self._lib = ctypes.CDLL(str(Path(library).resolve()))
        self._last_error = ""
        self._audio_user_callback = audio_callback
        self._error_user_callback = error_callback
        self._audio_c_callback = _AUDIO_CFUNC(self._on_audio)
        self._error_c_callback = _ERROR_CFUNC(self._on_error)
        self._configure_functions()

        mode_map = {"immediate": 0, "balanced": 1, "natural": 2}
        if mode not in mode_map:
            raise ValueError("mode must be 'immediate', 'balanced' or 'natural'")
        self._encoded_paths = [
            os.fsencode(model_path),
            os.fsencode(tokens_path),
            os.fsencode(data_dir) if data_dir else b"",
            b"cpu",
        ]  # Keep c_char_p backing buffers alive for the native call.
        config = _Config(
            self._encoded_paths[0], self._encoded_paths[1], self._encoded_paths[2], self._encoded_paths[3],
            int(num_threads), int(speaker_id), float(speed), mode_map[mode], int(max_words_per_chunk),
        )
        callbacks = _Callbacks(self._audio_c_callback, self._error_c_callback, None)
        error_buffer = ctypes.create_string_buffer(2048)
        self._handle = self._lib.streamtts_create(
            ctypes.byref(config), ctypes.byref(callbacks), error_buffer, ctypes.sizeof(error_buffer)
        )
        if not self._handle:
            detail = error_buffer.value.decode("utf-8", errors="replace") or "unknown native error"
            raise RuntimeError(detail)

    def _configure_functions(self) -> None:
        lib = self._lib
        lib.streamtts_create.argtypes = [ctypes.POINTER(_Config), ctypes.POINTER(_Callbacks), ctypes.c_char_p, ctypes.c_size_t]
        lib.streamtts_create.restype = ctypes.c_void_p
        lib.streamtts_push_text.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        lib.streamtts_push_text.restype = ctypes.c_int
        lib.streamtts_flush.argtypes = [ctypes.c_void_p]
        lib.streamtts_flush.restype = ctypes.c_int
        lib.streamtts_wait_until_idle.argtypes = [ctypes.c_void_p]
        lib.streamtts_wait_until_idle.restype = ctypes.c_int
        lib.streamtts_sample_rate.argtypes = [ctypes.c_void_p]
        lib.streamtts_sample_rate.restype = ctypes.c_int32
        lib.streamtts_num_speakers.argtypes = [ctypes.c_void_p]
        lib.streamtts_num_speakers.restype = ctypes.c_int32
        lib.streamtts_last_error.argtypes = [ctypes.c_void_p]
        lib.streamtts_last_error.restype = ctypes.c_char_p
        lib.streamtts_destroy.argtypes = [ctypes.c_void_p]
        lib.streamtts_destroy.restype = None

    def _on_audio(self, samples, count: int, sample_rate: int, _user_data) -> None:
        callback = self._audio_user_callback
        if callback is not None:
            try:
                callback(samples, int(count), int(sample_rate))
            except Exception as exc:  # exceptions must not cross the C callback boundary
                self._last_error = f"audio callback failed: {exc}"

    def _on_error(self, message, _user_data) -> None:
        self._last_error = message.decode("utf-8", errors="replace") if message else "native TTS error"
        if self._error_user_callback is not None:
            try:
                self._error_user_callback(self._last_error)
            except Exception:
                pass

    @property
    def sample_rate(self) -> int:
        return int(self._lib.streamtts_sample_rate(self._handle))

    @property
    def num_speakers(self) -> int:
        return int(self._lib.streamtts_num_speakers(self._handle))

    @property
    def last_error(self) -> str:
        if self._last_error:
            return self._last_error
        raw = self._lib.streamtts_last_error(self._handle)
        return raw.decode("utf-8", errors="replace") if raw else ""

    def push_text(self, fragment: str) -> None:
        """Push any text fragment; fragments may split inside words."""
        data = fragment.encode("utf-8")
        buffer = ctypes.create_string_buffer(data, len(data) + 1)
        if self._lib.streamtts_push_text(self._handle, buffer, len(data)) != 0:
            raise RuntimeError(self.last_error or "push_text failed")

    def flush(self) -> None:
        if self._lib.streamtts_flush(self._handle) != 0:
            raise RuntimeError(self.last_error or "flush failed")

    def wait_until_idle(self) -> None:
        if self._lib.streamtts_wait_until_idle(self._handle) != 0:
            raise RuntimeError(self.last_error or "wait_until_idle failed")

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle:
            self._lib.streamtts_destroy(handle)
            self._handle = None

    def __enter__(self) -> "StreamTTS":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
