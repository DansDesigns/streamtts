# Android sample

This is a small Java/JNI host for the shared C++ engine. It does not bundle the
neural voice model in the APK. Copy a compatible sherpa-onnx model directory to
`<app filesDir>/models/` with `en_US-amy-low.onnx`, `tokens.txt`, and (for this
voice) `espeak-ng-data/`, then tap **Load local voice**.

Open the `android/` directory in Android Studio, install a recent Android SDK,
NDK and CMake 3.22.1, then build/run the app. The root CMake downloads the pinned
sherpa-onnx source and the miniaudio header unless `SHERPA_ONNX_SOURCE_DIR` points
to a local checkout. Build dependencies require network access on the first run.

The JNI methods are in `NativeTts.java`: `init(...)`, `pushText(fragment)`,
`flush()`, and `shutdown()`. A production host should feed `pushText()` from its
background/network callback and never block the UI thread waiting for synthesis.
