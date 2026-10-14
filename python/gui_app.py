#!/usr/bin/env python3
"""StreamTTS desktop GUI for live typing, voice selection, rate, pitch and chunking."""
from __future__ import annotations

import json
import queue
import re
import shutil
import tarfile
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODELS_DIR = ROOT / "models"
SETTINGS_PATH = ROOT / "settings.json"

import sys
sys.path.insert(0, str(HERE))
from streamtts_python import StreamingTTS  # noqa: E402
from system_voice import SystemVoiceTTS  # noqa: E402

# Curated built-in catalog of official sherpa-onnx Piper/VITS profiles.
# Catalog metadata ships with StreamTTS; large ONNX archives download on first use.
from voice_catalog import VOICE_CATALOG  # noqa: E402
from updater import (  # noqa: E402
    DOWNLOAD_URL_TEMPLATE, REPOSITORY_URL, UpdateCheckError,
    fetch_latest_version, is_newer_version, read_current_version,
)
VOICE_RELEASE_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models"
SYSTEM_PREFIX = "system::"
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,140}$")


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    base = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError(f"Unsafe path in voice archive: {member.name}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Refusing link in voice archive: {member.name}")
    archive.extractall(destination)


def find_model_dir(model_id: str) -> Path | None:
    candidate = MODELS_DIR / model_id
    if candidate.is_dir() and list(candidate.glob("*.onnx")) and (candidate / "tokens.txt").is_file():
        return candidate
    # Keep support for packages that were extracted with a different root name.
    if MODELS_DIR.exists():
        for model_file in MODELS_DIR.rglob("*.onnx"):
            folder = model_file.parent
            if (folder / "tokens.txt").is_file() and folder.name == model_id:
                return folder
    return None


def installed_voice_dirs() -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not MODELS_DIR.exists():
        return found
    for model_file in MODELS_DIR.rglob("*.onnx"):
        folder = model_file.parent
        if (folder / "tokens.txt").is_file():
            found[folder.name] = folder
    return found


def download_voice(model_id: str, status_callback=None) -> Path:
    # Catalogued voices and arbitrary official sherpa-onnx release model IDs
    # share the same archive format. Validate the ID before constructing a URL.
    if not MODEL_ID_RE.fullmatch(model_id) or model_id.startswith("system"):
        raise ValueError(f"Invalid sherpa-onnx model ID: {model_id!r}")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    existing = find_model_dir(model_id)
    if existing:
        return existing

    archive_name = f"{model_id}.tar.bz2"
    archive_path = MODELS_DIR / archive_name
    url = f"{VOICE_RELEASE_BASE}/{archive_name}"
    temp_path = archive_path.with_suffix(archive_path.suffix + ".part")
    label = VOICE_CATALOG.get(model_id, {}).get("label", model_id)
    try:
        if status_callback:
            status_callback(f"Downloading {label}…")
        with urlopen(url, timeout=180) as response, temp_path.open("wb") as out:
            shutil.copyfileobj(response, out, length=1024 * 1024)
        temp_path.replace(archive_path)
        if status_callback:
            status_callback(f"Installing {label}…")
        with tarfile.open(archive_path, "r:bz2") as archive:
            _safe_extract(archive, MODELS_DIR)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    model_dir = find_model_dir(model_id)
    if not model_dir:
        raise RuntimeError(
            f"The downloaded archive did not contain an ONNX model and tokens.txt in a '{model_id}' folder. "
            "Inspect the models directory before retrying."
        )
    return model_dir


def read_settings() -> dict:
    defaults = {"voice_id": "vits-piper-en_US-amy-low", "speed": 1.0, "pitch": 0.0, "mode": "balanced"}
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        defaults.update({k: saved[k] for k in defaults if k in saved})
    except (OSError, ValueError, TypeError):
        pass
    if not isinstance(defaults["voice_id"], str) or not defaults["voice_id"]:
        defaults["voice_id"] = "vits-piper-en_US-amy-low"
    if defaults["mode"] not in ("immediate", "balanced", "natural"):
        defaults["mode"] = "balanced"
    try:
        defaults["speed"] = max(0.5, min(2.0, float(defaults["speed"])))
        defaults["pitch"] = max(-6.0, min(6.0, float(defaults["pitch"])))
    except (ValueError, TypeError):
        defaults.update(speed=1.0, pitch=0.0)
    return defaults


class StreamTTSGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("StreamTTS — Live Speech Settings")
        self.root.geometry("1000x760")
        self.root.minsize(820, 650)
        self.settings = read_settings()
        self.tts: StreamingTTS | None = None
        self._reconfiguring = False
        self._closing = False
        self._ui_events: queue.Queue = queue.Queue()
        self._pending_fragments: list[str] = []
        self._flush_after_pending = False
        # Text already handed to the speech pipeline, aligned to the visible
        # text widget. Only the editable tail after this prefix remains unsent.
        self._committed_visible_text = ""
        self._unsent_text = ""
        self._error_displayed = ""

        # Keep the internal model/voice ID separate from the human-readable
        # combobox text. Sharing a StringVar here caused every selection to be
        # replaced by its label and triggered "Unknown voice profile" for all.
        self.voice_var = tk.StringVar(value=self.settings["voice_id"])
        self.voice_display_var = tk.StringVar()
        self._system_voices: dict[str, dict[str, str]] = {}
        self._extra_model_ids: set[str] = set()
        saved_voice = self.settings["voice_id"]
        if (saved_voice not in VOICE_CATALOG and not saved_voice.startswith(SYSTEM_PREFIX)
                and MODEL_ID_RE.fullmatch(saved_voice)):
            self._extra_model_ids.add(saved_voice)
        self.speed_var = tk.DoubleVar(value=self.settings["speed"])
        self.pitch_var = tk.DoubleVar(value=self.settings["pitch"])
        self.mode_var = tk.StringVar(value=self.settings["mode"])
        self.status_var = tk.StringVar(value="Starting…")
        self.rate_readout = tk.StringVar()
        self.pitch_readout = tk.StringVar()
        self.current_version = read_current_version()
        self.latest_version: str | None = None
        self.latest_branch = "main"
        self._update_checking = False
        self.current_version_var = tk.StringVar(value=f"Installed version: v{self.current_version}")
        self.update_status_var = tk.StringVar(value="Not checked yet")

        self._build_ui()
        self._refresh_voice_choices()
        self._update_rate_label()
        self._update_pitch_label()
        self._update_pitch_availability()
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self.root.after(100, self._poll_events)
        self._load_initial_voice()
        # Update check runs on a background thread and never blocks speech/UI.
        self.root.after(1200, self.check_for_updates)

    def _build_ui(self) -> None:
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        heading = ttk.Frame(outer)
        heading.pack(fill="x", pady=(0, 10))
        ttk.Label(heading, text="StreamTTS", font=("Segoe UI", 19, "bold")).pack(side="left")
        ttk.Label(heading, text="Low-latency local speech · no Rust", foreground="#666666").pack(side="left", padx=(12, 0), pady=(7, 0))

        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        settings_frame = ttk.LabelFrame(main, text="Speech settings", padding=12)
        settings_frame.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        settings_frame.columnconfigure(0, weight=1)

        ttk.Label(settings_frame, text="Voice (neural or system)").grid(row=0, column=0, sticky="w")
        self.voice_combo = ttk.Combobox(settings_frame, textvariable=self.voice_display_var, state="readonly", width=31)
        self.voice_combo.grid(row=1, column=0, sticky="ew", pady=(4, 6))
        ttk.Button(settings_frame, text="Apply selected voice", command=self.apply_voice).grid(row=2, column=0, sticky="ew", pady=(0, 5))
        voice_tools = ttk.Frame(settings_frame)
        voice_tools.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(voice_tools, text="Download other…", command=self.download_other_voice).pack(side="left", fill="x", expand=True)
        ttk.Button(voice_tools, text="Import folder…", command=self.import_voice_folder).pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Label(settings_frame, text="Speech rate").grid(row=4, column=0, sticky="w")
        ttk.Label(settings_frame, textvariable=self.rate_readout).grid(row=4, column=1, sticky="e")
        ttk.Scale(settings_frame, from_=0.5, to=2.0, variable=self.speed_var, command=self._rate_changed).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 15))
        ttk.Label(settings_frame, text="Pitch shift").grid(row=6, column=0, sticky="w")
        ttk.Label(settings_frame, textvariable=self.pitch_readout).grid(row=6, column=1, sticky="e")
        self.pitch_scale = ttk.Scale(settings_frame, from_=-6.0, to=6.0, variable=self.pitch_var, command=self._pitch_changed)
        self.pitch_scale.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(2, 5))
        ttk.Label(settings_frame, text="-6 lower  ·  0 original  ·  +6 higher", foreground="#666666", wraplength=230).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 15))
        ttk.Label(settings_frame, text="Streaming mode").grid(row=9, column=0, sticky="w")
        self.mode_combo = ttk.Combobox(settings_frame, textvariable=self.mode_var, state="readonly", values=("immediate", "balanced", "natural"), width=20)
        self.mode_combo.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(4, 5))
        self.mode_combo.bind("<<ComboboxSelected>>", self._mode_changed)
        ttk.Label(settings_frame, text="Immediate: shortest chunks\nBalanced: responsive + natural\nNatural: longer chunks", foreground="#666666", justify="left").grid(row=11, column=0, columnspan=2, sticky="w", pady=(0, 16))
        ttk.Button(settings_frame, text="Test selected voice", command=self.test_voice).grid(row=12, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        ttk.Button(settings_frame, text="Save settings", command=self.save_settings).grid(row=13, column=0, columnspan=2, sticky="ew")

        typing = ttk.LabelFrame(main, text="Live typing area", padding=10)
        typing.grid(row=0, column=1, sticky="nsew")
        typing.rowconfigure(0, weight=1)
        typing.columnconfigure(0, weight=1)
        self.text_box = tk.Text(typing, wrap="word", undo=True, font=("Consolas", 12), padx=8, pady=8)
        self.text_box.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(typing, orient="vertical", command=self.text_box.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_box.configure(yscrollcommand=scrollbar.set)
        self.text_box.bind("<KeyRelease>", self._text_changed)
        self.text_box.bind("<Control-Return>", self._flush_pending_event)
        self.text_box.bind("<Control-BackSpace>", self._text_changed)

        buttons = ttk.Frame(typing)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Flush pending words  (Ctrl+Enter)", command=self.flush_pending).pack(side="left")
        ttk.Button(buttons, text="Clear text", command=self.clear_text).pack(side="left", padx=(8, 0))
        ttk.Label(typing, text="Completed words stream at spaces and punctuation. Previously spoken text cannot be taken back.", foreground="#666666", wraplength=560).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        update_frame = ttk.LabelFrame(outer, text="Updates", padding=(10, 7))
        update_frame.pack(fill="x", pady=(10, 0))
        update_frame.columnconfigure(1, weight=1)
        ttk.Label(update_frame, textvariable=self.current_version_var).grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(update_frame, textvariable=self.update_status_var, wraplength=400).grid(row=0, column=1, sticky="ew", padx=(0, 10))
        update_buttons = ttk.Frame(update_frame)
        update_buttons.grid(row=0, column=2, sticky="e")
        self.check_update_button = ttk.Button(update_buttons, text="Check now", command=self.check_for_updates)
        self.check_update_button.pack(side="left")
        self.download_update_button = ttk.Button(update_buttons, text="Download ZIP", command=self.open_latest_download, state="disabled")
        self.download_update_button.pack(side="left", padx=(5, 0))
        ttk.Button(update_buttons, text="GitHub", command=self.open_repository).pack(side="left", padx=(5, 0))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(7, 0))
        ttk.Label(footer, textvariable=self.status_var, wraplength=850).pack(side="left", fill="x", expand=True)

    def check_for_updates(self) -> None:
        """Check GitHub version.txt asynchronously, keeping the GUI responsive."""
        if self._closing or self._update_checking:
            return
        self._update_checking = True
        self.check_update_button.configure(state="disabled")
        self.download_update_button.configure(state="disabled")
        self.update_status_var.set("Checking GitHub…")

        def worker() -> None:
            try:
                latest, branch = fetch_latest_version()
                self._ui_events.put(("update_check_done", latest, branch))
            except Exception as exc:
                self._ui_events.put(("update_check_failed", str(exc)))

        threading.Thread(target=worker, name="StreamTTSUpdateCheck", daemon=True).start()

    def open_repository(self) -> None:
        try:
            webbrowser.open(REPOSITORY_URL, new=2)
        except Exception as exc:
            self.update_status_var.set(f"Could not open GitHub: {exc}")

    def open_latest_download(self) -> None:
        if not self.latest_version:
            return
        url = DOWNLOAD_URL_TEMPLATE.format(branch=self.latest_branch)
        try:
            webbrowser.open(url, new=2)
            self.update_status_var.set("Opened the latest source ZIP in your browser. Back up settings.json and models before replacing files.")
        except Exception as exc:
            self.update_status_var.set(f"Could not open the download: {exc}")

    def _discover_system_voices(self) -> dict[str, dict[str, str]]:
        """Return system voice IDs and names without failing the whole GUI."""
        found: dict[str, dict[str, str]] = {}
        try:
            import pyttsx3
            import platform
            driver = "sapi5" if platform.system() == "Windows" else None
            engine = pyttsx3.init(driverName=driver)
            try:
                for voice in engine.getProperty("voices") or []:
                    voice_id = str(getattr(voice, "id", "") or "")
                    if not voice_id:
                        continue
                    name = str(getattr(voice, "name", voice_id) or voice_id)
                    languages = getattr(voice, "languages", []) or []
                    lang = ""
                    if languages:
                        first = languages[0]
                        if isinstance(first, bytes):
                            first = first.decode("utf-8", errors="ignore")
                        lang = str(first).strip("\x00")
                    key = SYSTEM_PREFIX + voice_id
                    found[key] = {"id": voice_id, "name": name, "language": lang}
            finally:
                try:
                    engine.stop()
                except Exception:
                    pass
        except Exception as exc:
            self._system_voice_error = str(exc)
        else:
            self._system_voice_error = ""
        return found

    def _display_label(self, voice_id: str, installed: dict[str, Path] | None = None) -> str:
        if voice_id.startswith(SYSTEM_PREFIX):
            voice = self._system_voices.get(voice_id, {})
            name = voice.get("name", voice_id[len(SYSTEM_PREFIX):])
            lang = voice.get("language", "")
            lang_text = f" · {lang}" if lang else ""
            return f"System voice — {name}{lang_text}"
        if voice_id in VOICE_CATALOG:
            label = VOICE_CATALOG[voice_id]["label"]
        else:
            label = voice_id
        if installed is None:
            installed = installed_voice_dirs()
        if voice_id in installed:
            label += "  ✓ installed"
        else:
            label += "  (download)"
        return label

    def _refresh_voice_choices(self, rediscover_system: bool = False) -> None:
        installed = installed_voice_dirs()
        if rediscover_system or not self._system_voices:
            self._system_voices = self._discover_system_voices()
        ids = list(VOICE_CATALOG)
        for model_id in sorted(set(installed) | self._extra_model_ids):
            if model_id not in ids:
                ids.append(model_id)
        for system_id in self._system_voices:
            if system_id not in ids:
                ids.append(system_id)
        self._voice_ids = ids
        self._label_to_id = {}
        labels = []
        for voice_id in ids:
            label = self._display_label(voice_id, installed)
            # Avoid collisions if two installed voices have the same display name.
            if label in self._label_to_id:
                label += f" [{voice_id[-24:]}]"
            self._label_to_id[label] = voice_id
            labels.append(label)
        self._id_to_label = {voice_id: label for label, voice_id in self._label_to_id.items()}
        self.voice_combo.configure(values=labels)
        selected = self.voice_var.get()
        if selected not in ids:
            selected = "vits-piper-en_US-amy-low"
            self.voice_var.set(selected)
        self.voice_display_var.set(self._id_to_label.get(selected, labels[0] if labels else ""))
        self.voice_combo.bind("<<ComboboxSelected>>", self._voice_selected)
        self._update_pitch_availability()

    def _voice_selected(self, _event=None) -> None:
        label = self.voice_display_var.get()
        voice_id = self._label_to_id.get(label)
        if voice_id:
            self.voice_var.set(voice_id)
            self._update_pitch_availability()

    def _update_pitch_availability(self) -> None:
        is_system = self.voice_var.get().startswith(SYSTEM_PREFIX)
        try:
            self.pitch_scale.configure(state="disabled" if is_system else "normal")
        except (AttributeError, tk.TclError):
            pass
        if is_system:
            self.pitch_readout.set("not supported")
        else:
            self._update_pitch_label()

    def download_other_voice(self) -> None:
        model_id = simpledialog.askstring(
            "Download another voice model",
            "Enter a compatible sherpa-onnx Piper/VITS model ID. Examples:\n"
            "vits-piper-en_GB-cori-high\n"
            "vits-piper-en_US-lessac-medium\n\n"
            "The model archive is downloaded from the official sherpa-onnx tts-models release.",
            parent=self.root,
        )
        if not model_id:
            return
        model_id = model_id.strip()
        if (not MODEL_ID_RE.fullmatch(model_id) or model_id.startswith("system")
                or not model_id.startswith("vits-piper-")):
            messagebox.showerror(
                "Invalid model ID",
                "This GUI currently supports sherpa-onnx Piper/VITS release IDs beginning with 'vits-piper-'.",
                parent=self.root,
            )
            return
        self._extra_model_ids.add(model_id)
        self.voice_var.set(model_id)
        self._refresh_voice_choices()
        self.apply_voice()

    def import_voice_folder(self) -> None:
        folder_str = filedialog.askdirectory(title="Choose a TTS model folder (must contain .onnx and tokens.txt)", parent=self.root)
        if not folder_str:
            return
        source = Path(folder_str)
        if not list(source.glob("*.onnx")) or not (source / "tokens.txt").is_file():
            messagebox.showerror("Invalid voice folder", "The selected folder must contain at least one .onnx model and tokens.txt directly inside it.", parent=self.root)
            return
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", source.name).strip(".-_") or "voice"
        slug = "local-" + slug
        destination = MODELS_DIR / slug
        suffix = 2
        while destination.exists() and destination.resolve() != source.resolve():
            destination = MODELS_DIR / f"{slug}-{suffix}"
            suffix += 1
        if destination.resolve() != source.resolve():
            try:
                shutil.copytree(source, destination)
            except Exception as exc:
                messagebox.showerror("Import voice", f"Could not copy voice folder:\n{exc}", parent=self.root)
                return
        self._extra_model_ids.add(destination.name)
        self.voice_var.set(destination.name)
        self._refresh_voice_choices()
        self.status_var.set(f"Imported voice model: {destination.name}")
        self.apply_voice()

    def _load_initial_voice(self) -> None:
        model_id = self.voice_var.get()
        if model_id.startswith(SYSTEM_PREFIX):
            if model_id in self._system_voices:
                self._replace_voice(model_id, model_dir=None, download_if_missing=False)
                return
            self.status_var.set("Saved system voice is not available; choose another voice and apply it.")
            return
        model_dir = find_model_dir(model_id)
        if not model_dir:
            self.status_var.set("No installed voice found. Choose a voice and click ‘Apply selected voice’.")
            return
        self._replace_voice(model_id, model_dir=model_dir, download_if_missing=False)

    def apply_voice(self) -> None:
        voice_id = self.voice_var.get()
        if not voice_id:
            return
        if voice_id.startswith(SYSTEM_PREFIX):
            self._replace_voice(voice_id, model_dir=None, download_if_missing=False)
            return
        model_dir = find_model_dir(voice_id)
        self._replace_voice(voice_id, model_dir=model_dir, download_if_missing=True)

    def _replace_voice(self, model_id: str, model_dir: Path | None, download_if_missing: bool) -> None:
        if self._reconfiguring:
            self.status_var.set("Voice change is already in progress.")
            return
        self._reconfiguring = True
        old_tts = self.tts
        self.tts = None
        speed = float(self.speed_var.get())
        pitch = float(self.pitch_var.get())
        mode = self.mode_var.get()
        self.status_var.set("Preparing voice; any queued speech will finish before switching…")
        self.voice_combo.configure(state="disabled")
        threading.Thread(
            target=self._replace_voice_worker,
            args=(old_tts, model_id, model_dir, download_if_missing, speed, pitch, mode),
            daemon=True,
            name="StreamTTS-VoiceSetup",
        ).start()

    def _replace_voice_worker(self, old_tts, model_id, model_dir, download_if_missing, speed, pitch, mode) -> None:
        old_closed = False
        try:
            if old_tts is not None:
                old_tts.close()
                old_closed = True
            if model_id.startswith(SYSTEM_PREFIX):
                self._ui_events.put(("status", f"Loading system voice {self._display_label(model_id)}…"))
                new_tts = SystemVoiceTTS(
                    model_id[len(SYSTEM_PREFIX):], mode=mode, speed=speed, pitch_semitones=pitch
                )
                self._ui_events.put(("voice_ready", model_id, None, new_tts))
                return
            if model_dir is None:
                if not download_if_missing:
                    self._ui_events.put(("not_installed", model_id, old_tts))
                    return
                model_dir = download_voice(model_id, lambda msg: self._ui_events.put(("status", msg)))
            self._ui_events.put(("status", f"Loading {VOICE_CATALOG.get(model_id, {}).get('label', model_id)}…"))
            new_tts = StreamingTTS(
                model_dir,
                mode=mode,
                num_threads=2,
                speed=speed,
                pitch_semitones=pitch,
            )
            self._ui_events.put(("voice_ready", model_id, model_dir, new_tts))
        except Exception as exc:
            self._ui_events.put(("voice_failed", model_id, str(exc), None if old_closed else old_tts))

    def _rate_changed(self, _value=None) -> None:
        self._update_rate_label()
        if self.tts is not None:
            try:
                self.tts.set_speed(float(self.speed_var.get()))
            except Exception as exc:
                self.status_var.set(str(exc))

    def _pitch_changed(self, _value=None) -> None:
        if self.voice_var.get().startswith(SYSTEM_PREFIX):
            self.pitch_readout.set("not supported")
            self.status_var.set("The selected operating-system voice does not expose pitch control; choose a neural model for pitch shifting.")
            return
        self._update_pitch_label()
        if self.tts is not None:
            try:
                self.tts.set_pitch(float(self.pitch_var.get()))
                if abs(float(self.pitch_var.get())) >= 0.01:
                    self.status_var.set("Pitch shift uses extra processing; first use may be slower.")
            except Exception as exc:
                self.status_var.set(str(exc))

    def _update_rate_label(self) -> None:
        self.rate_readout.set(f"{float(self.speed_var.get()):.2f}×")

    def _update_pitch_label(self) -> None:
        value = float(self.pitch_var.get())
        self.pitch_readout.set(f"{value:+.1f} semitones")

    def _mode_changed(self, _event=None) -> None:
        if self.tts is not None:
            try:
                self.tts.set_mode(self.mode_var.get())
            except Exception as exc:
                self.status_var.set(str(exc))
        self.status_var.set(f"Streaming mode set to {self.mode_var.get()}.")

    def _submit_fragment(self, fragment: str) -> None:
        if not fragment:
            return
        if self._reconfiguring:
            self._pending_fragments.append(fragment)
        elif self.tts is not None:
            try:
                self.tts.push_text(fragment)
            except Exception as exc:
                self.status_var.set(f"Could not queue text: {exc}")
        else:
            self._pending_fragments.append(fragment)
            self.status_var.set("Text buffered until a voice is loaded. Choose a voice and click Apply selected voice.")

    def _text_changed(self, _event=None) -> None:
        current = self.text_box.get("1.0", "end-1c")
        if current.startswith(self._committed_visible_text):
            # Recompute the tail from the widget. This means backspace/editing
            # within the unfinished word works without sending corrections to TTS.
            self._unsent_text = current[len(self._committed_visible_text):]
            # A complete boundary commits text. Do not send an unfinished word,
            # so it stays editable until a space or punctuation is typed.
            safe_ends = [i + 1 for i, ch in enumerate(self._unsent_text) if ch.isspace() or ch in ".!?"]
            if safe_ends:
                safe_end = safe_ends[-1]
                to_send = self._unsent_text[:safe_end]
                self._committed_visible_text += to_send
                self._unsent_text = current[len(self._committed_visible_text):]
                self._submit_fragment(to_send)
                if self.tts is not None and not self._reconfiguring:
                    self.status_var.set("Streaming text to the speech engine…")
        else:
            # Editing/deleting an already-committed prefix cannot retract audio
            # already synthesized or queued, so rebase without re-speaking history.
            self._committed_visible_text = current
            self._unsent_text = ""
            self.status_var.set("Previously submitted text was edited. Its speech cannot be retracted; new text will stream normally.")

    def _flush_pending_event(self, _event=None):
        self.flush_pending()
        return "break"

    def flush_pending(self) -> None:
        current = self.text_box.get("1.0", "end-1c")
        if self._unsent_text:
            fragment = self._unsent_text
            self._unsent_text = ""
            self._submit_fragment(fragment)
        if self._reconfiguring or self.tts is None:
            self._flush_after_pending = True
        elif self.tts is not None:
            try:
                self.tts.flush()
                self.status_var.set("Flushed pending words to speech.")
            except Exception as exc:
                self.status_var.set(f"Flush failed: {exc}")
        self._committed_visible_text = current

    def test_voice(self) -> None:
        if self.tts is None and not self._reconfiguring:
            self.status_var.set("Load a voice before testing it.")
            return
        self._submit_fragment("Hello. This is a test of the selected voice. ")
        if self._reconfiguring:
            self._flush_after_pending = True
        elif self.tts is not None:
            self.tts.flush()

    def clear_text(self) -> None:
        if self._unsent_text:
            self._submit_fragment(self._unsent_text)
            self._unsent_text = ""
        # Also flush the segmenter's short buffered tail so it is not left waiting
        # for future words after the visible text has been cleared.
        if self._reconfiguring or self.tts is None:
            self._flush_after_pending = True
        elif self.tts is not None:
            self.tts.flush()
        self.text_box.delete("1.0", "end")
        # Text already handed to the speech pipeline, aligned to the visible
        # text widget. Only the editable tail after this prefix remains unsent.
        self._committed_visible_text = ""
        self._unsent_text = ""
        self.text_box.focus_set()

    def save_settings(self) -> None:
        data = {
            "voice_id": self.voice_var.get(),
            "speed": round(float(self.speed_var.get()), 3),
            "pitch": round(float(self.pitch_var.get()), 2),
            "mode": self.mode_var.get(),
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            self.status_var.set(f"Settings saved to {SETTINGS_PATH.name}.")
        except OSError as exc:
            messagebox.showerror("Save settings", str(exc), parent=self.root)

    def _poll_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                event = self._ui_events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self.status_var.set(event[1])
                elif kind == "update_check_done":
                    _, latest, branch = event
                    self._update_checking = False
                    self.check_update_button.configure(state="normal")
                    self.latest_version = latest
                    self.latest_branch = branch
                    try:
                        if is_newer_version(latest, self.current_version):
                            self.update_status_var.set(f"Update available: v{latest}")
                            self.download_update_button.configure(state="normal")
                        elif is_newer_version(self.current_version, latest):
                            self.update_status_var.set(f"Installed v{self.current_version} is newer than GitHub v{latest}.")
                            self.download_update_button.configure(state="disabled")
                        else:
                            self.update_status_var.set(f"You're up to date (v{latest}).")
                            self.download_update_button.configure(state="disabled")
                    except ValueError as exc:
                        self.latest_version = None
                        self.update_status_var.set(f"Invalid version returned by GitHub: {exc}")
                        self.download_update_button.configure(state="disabled")
                elif kind == "update_check_failed":
                    _, detail = event
                    self._update_checking = False
                    self.check_update_button.configure(state="normal")
                    self.latest_version = None
                    self.download_update_button.configure(state="disabled")
                    self.update_status_var.set(f"Update check failed — {detail}")
                elif kind == "voice_ready":
                    _, model_id, _model_dir, new_tts = event
                    if self._closing:
                        threading.Thread(target=new_tts.close, daemon=True).start()
                        continue
                    self.tts = new_tts
                    # Apply the latest slider values, including any changes made
                    # while an on-demand voice download was running.
                    self.tts.set_speed(float(self.speed_var.get()))
                    self.tts.set_pitch(float(self.pitch_var.get()))
                    self.tts.set_mode(self.mode_var.get())
                    self.voice_var.set(model_id)
                    self._reconfiguring = False
                    self.voice_combo.configure(state="readonly")
                    if model_id not in VOICE_CATALOG and not model_id.startswith(SYSTEM_PREFIX):
                        self._extra_model_ids.add(model_id)
                    self._refresh_voice_choices()
                    for fragment in self._pending_fragments:
                        self.tts.push_text(fragment)
                    self._pending_fragments.clear()
                    if self._flush_after_pending:
                        self.tts.flush()
                        self._flush_after_pending = False
                    self.status_var.set(f"Ready — {self._display_label(model_id)}. Start typing; spaces and punctuation stream text.")
                elif kind == "voice_failed":
                    _, model_id, message, old_tts = event
                    self.tts = old_tts
                    self._reconfiguring = False
                    self.voice_combo.configure(state="readonly")
                    if self.tts is not None and self._pending_fragments:
                        for fragment in self._pending_fragments:
                            self.tts.push_text(fragment)
                        self._pending_fragments.clear()
                        if self._flush_after_pending:
                            self.tts.flush()
                            self._flush_after_pending = False
                    self.status_var.set(f"Could not load voice: {message}")
                    messagebox.showerror("StreamTTS voice error", message, parent=self.root)
                elif kind == "not_installed":
                    _, model_id, old_tts = event
                    self.tts = old_tts
                    self._reconfiguring = False
                    self.voice_combo.configure(state="readonly")
                    self.status_var.set(f"Voice {model_id} is not installed.")
                elif kind == "unused":
                    pass
        except queue.Empty:
            pass
        if self.tts is not None:
            error = self.tts.last_error
            if error and error != self._error_displayed:
                self._error_displayed = error
                self.status_var.set(f"Speech engine: {error}")
        self.root.after(100, self._poll_events)

    def close_window(self) -> None:
        if self._closing:
            return
        self.save_settings()
        self._closing = True
        tts = self.tts
        self.tts = None
        if tts is not None:
            threading.Thread(target=self._close_engine, args=(tts,), daemon=True).start()
        self.root.destroy()

    @staticmethod
    def _close_engine(tts) -> None:
        try:
            tts.close()
        except Exception:
            pass


def main() -> int:
    root = tk.Tk()
    StreamTTSGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
