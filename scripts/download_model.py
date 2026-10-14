#!/usr/bin/env python3
"""Download and safely unpack the small English Piper voice used by the demo."""
from pathlib import Path
import tarfile
from urllib.request import urlopen

URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-amy-low.tar.bz2"
ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
ARCHIVE = MODELS / "vits-piper-en_US-amy-low.tar.bz2"
EXPECTED_DIR = MODELS / "vits-piper-en_US-amy-low"


def safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    base = destination.resolve()
    for member in tar.getmembers():
        target = (destination / member.name).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError(f"Unsafe archive path: {member.name}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Refusing archive link: {member.name}")
    tar.extractall(destination)


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE.exists():
        print(f"Downloading {URL}")
        with urlopen(URL, timeout=120) as response, ARCHIVE.open("wb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
    print(f"Extracting {ARCHIVE}")
    with tarfile.open(ARCHIVE, "r:bz2") as tar:
        safe_extract(tar, MODELS)

    model_dir = EXPECTED_DIR
    model = model_dir / "en_US-amy-low.onnx"
    tokens = model_dir / "tokens.txt"
    data_dir = model_dir / "espeak-ng-data"
    if not model.exists():
        # Archive layouts can change; locate the named model file instead of
        # silently inventing paths.
        found = list(MODELS.rglob("en_US-amy-low.onnx"))
        if found:
            model = found[0]
            model_dir = model.parent
            tokens = model_dir / "tokens.txt"
            data_dir = model_dir / "espeak-ng-data"
    print("\nModel setup complete. Pass these paths to StreamTts:")
    print(f"  model_path = {model}")
    print(f"  tokens_path = {tokens}")
    print(f"  data_dir = {data_dir if data_dir.exists() else '(empty if this model does not require it)'}")
    if not model.exists() or not tokens.exists():
        raise SystemExit("The archive layout was unexpected; inspect the extracted directory and update the paths.")


if __name__ == "__main__":
    main()
