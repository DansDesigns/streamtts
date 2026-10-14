#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <string_view>
#include "streamtts/export.h"

namespace streamtts {

enum class ChunkingMode {
  // Emit short chunks aggressively; lowest text-buffering latency.
  Immediate,
  // Start after two completed words, then group up to three words unless
  // punctuation provides a better boundary.
  Balanced,
  // Use longer chunks for more context and usually smoother prosody.
  Natural,
};

struct Options {
  // Paths to a sherpa-onnx-compatible VITS/Piper model and its companion files.
  std::string model_path;
  std::string tokens_path;
  std::string data_dir;  // Commonly the model's espeak-ng-data directory.

  std::string provider = "cpu";
  int32_t num_threads = 2;
  int32_t speaker_id = 0;
  float speed = 1.0f;
  ChunkingMode chunking = ChunkingMode::Balanced;

  // Zero selects the mode's default. For Balanced, 3 is a sensible default.
  size_t max_words_per_chunk = 0;
};

// Called on the synthesis worker thread. Samples are mono float PCM [-1, 1]
// and are only valid for the duration of this callback; copy/enqueue them if
// they need to outlive the callback. `sample_rate` is supplied for every chunk.
using AudioCallback =
    std::function<void(const float* samples, size_t count, int32_t sample_rate)>;
using ErrorCallback = std::function<void(const std::string& message)>;

class STREAMTTS_API StreamingTts {
 public:
  explicit StreamingTts(Options options);
  ~StreamingTts();

  StreamingTts(const StreamingTts&) = delete;
  StreamingTts& operator=(const StreamingTts&) = delete;
  StreamingTts(StreamingTts&&) = delete;
  StreamingTts& operator=(StreamingTts&&) = delete;

  // Install callbacks before pushText(). Audio callbacks run on the one
  // synthesis thread, never from inside pushText().
  void setAudioCallback(AudioCallback callback);
  void setErrorCallback(ErrorCallback callback);

  // Feed arbitrary fragments. Fragments may split in the middle of a word;
  // the segmenter keeps the unfinished trailing token until a boundary arrives.
  // Thread-safe with respect to other pushText() calls and flush().
  void pushText(std::string_view fragment);

  // Emit any buffered trailing text, including a final word without a space.
  void flush();

  // Wait until all accepted text has been synthesized and handed to the audio
  // callback. This does not wait for a downstream audio device to finish playing.
  void waitUntilIdle();

  // Stop accepting text, flush pending text, finish queued synthesis, and join
  // the worker. Safe to call more than once.
  void stop();

  int32_t sampleRate() const noexcept;
  int32_t numSpeakers() const noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace streamtts
