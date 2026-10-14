The optional desktop/Android audio example uses miniaudio. To obtain the pinned
single-header dependency, run `python scripts/download_miniaudio.py`. It is
excluded from the source archive because it is a third-party dependency; its
license notice is included at the top of the downloaded header. The core
`streamtts` library itself does not include or require miniaudio.
