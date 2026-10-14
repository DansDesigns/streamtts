#!/usr/bin/env python3
"""Download the pinned, single-header miniaudio backend dependency."""
from pathlib import Path
from urllib.request import urlopen

URL = "https://raw.githubusercontent.com/mackron/miniaudio/0.11.22/miniaudio.h"
DEST = Path(__file__).resolve().parents[1] / "third_party" / "miniaudio.h"


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading miniaudio header to {DEST}")
    with urlopen(URL, timeout=60) as response:
        data = response.read()
    if len(data) < 100_000 or b"miniaudio_h" not in data[:20_000].lower():
        raise RuntimeError("Downloaded file does not look like miniaudio.h")
    DEST.write_bytes(data)
    print(f"Downloaded {len(data):,} bytes")


if __name__ == "__main__":
    main()
