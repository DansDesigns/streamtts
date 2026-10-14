#include "streamtts/streaming_tts.h"
#include "text_segmenter.h"

#include "sherpa-onnx/csrc/offline-tts.h"

#include <algorithm>
#include <condition_variable>
#include <exception>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace streamtts {
namespace {
size_t MaxWords(const Options& options) {
  if (options.max_words_per_chunk != 0) return std::max<size_t>(1, options.max_words_per_chunk);
  switch (options.chunking) {
    case ChunkingMode::Immediate: return 1;
    case ChunkingMode::Balanced: return 3;
    case ChunkingMode::Natural: return 6;
  }
  return 3;
}
size_t FirstWords(const Options& options, size_t max_words) {
  switch (options.chunking) {
    case ChunkingMode::Immediate: return 1;
    case ChunkingMode::Balanced: return std::min<size_t>(2, max_words);
    case ChunkingMode::Natural: return std::min<size_t>(4, max_words);
  }
  return std::min<size_t>(2, max_words);
}
}  // namespace

struct StreamingTts::Impl {
  explicit Impl(Options opts)
      : options(std::move(opts)),
        segmenter(MaxWords(options), FirstWords(options, MaxWords(options))) {
    if (options.model_path.empty()) throw std::invalid_argument("model_path is required");
    if (options.tokens_path.empty()) throw std::invalid_argument("tokens_path is required");
    if (options.num_threads < 1) throw std::invalid_argument("num_threads must be >= 1");
    if (!(options.speed > 0.0f)) throw std::invalid_argument("speed must be > 0");

    sherpa_onnx::OfflineTtsConfig config;
    config.model.vits.model = options.model_path;
    config.model.vits.tokens = options.tokens_path;
    config.model.vits.data_dir = options.data_dir;
    config.model.num_threads = options.num_threads;
    config.model.provider = options.provider;
    config.model.debug = false;
    config.max_num_sentences = 1;
    config.silence_scale = 0.2f;

    if (!config.Validate()) {
      throw std::runtime_error("sherpa-onnx rejected the TTS model configuration; check model, tokens and data_dir paths");
    }
    tts = std::make_unique<sherpa_onnx::OfflineTts>(config);
    worker = std::thread([this] { workerLoop(); });
  }

  ~Impl() { stop(); }

  void enqueueText(std::vector<std::string>&& chunks) {
    if (chunks.empty()) return;
    {
      std::lock_guard<std::mutex> lock(queue_mutex);
      for (auto& chunk : chunks) text_queue.push(std::move(chunk));
    }
    queue_cv.notify_one();
  }

  void push(std::string_view fragment) {
    std::lock_guard<std::mutex> lock(input_mutex);
    if (!accepting) throw std::logic_error("StreamingTts is stopped; create a new instance to restart it");
    enqueueText(segmenter.push(std::string(fragment)));
  }

  void flushInput() {
    std::lock_guard<std::mutex> lock(input_mutex);
    if (!accepting) return;
    enqueueText(segmenter.flush());
  }

  void waitIdle() {
    std::unique_lock<std::mutex> lock(queue_mutex);
    idle_cv.wait(lock, [this] { return text_queue.empty() && !worker_busy; });
  }

  void stop() {
    {
      std::lock_guard<std::mutex> lock(input_mutex);
      if (!accepting) {
        // Another caller may already have begun shutdown; joining below is safe
        // only for one caller, so the public API documents single-owner stop.
      } else {
        enqueueText(segmenter.flush());
        accepting = false;
      }
    }
    {
      std::lock_guard<std::mutex> lock(queue_mutex);
      stopping = true;
    }
    queue_cv.notify_all();
    if (worker.joinable()) worker.join();
  }

  void reportError(const std::string& message) {
    ErrorCallback cb;
    {
      std::lock_guard<std::mutex> lock(callback_mutex);
      cb = error_callback;
    }
    if (cb) {
      try { cb(message); } catch (...) { /* don't unwind the worker */ }
    }
  }

  void workerLoop() {
    for (;;) {
      std::string text;
      {
        std::unique_lock<std::mutex> lock(queue_mutex);
        queue_cv.wait(lock, [this] { return stopping || !text_queue.empty(); });
        if (text_queue.empty()) {
          if (stopping) break;
          continue;
        }
        text = std::move(text_queue.front());
        text_queue.pop();
        worker_busy = true;
      }

      try {
        sherpa_onnx::GenerationConfig generation;
        generation.sid = options.speaker_id;
        generation.speed = options.speed;
        auto generated = tts->Generate(text, generation);
        if (!generated.samples.empty()) {
          AudioCallback cb;
          {
            std::lock_guard<std::mutex> lock(callback_mutex);
            cb = audio_callback;
          }
          if (cb) cb(generated.samples.data(), generated.samples.size(), generated.sample_rate);
        }
      } catch (const std::exception& e) {
        reportError(std::string("TTS synthesis failed for chunk '") + text + "': " + e.what());
      } catch (...) {
        reportError(std::string("TTS synthesis failed for chunk '") + text + "': unknown error");
      }

      {
        std::lock_guard<std::mutex> lock(queue_mutex);
        worker_busy = false;
        if (text_queue.empty()) idle_cv.notify_all();
      }
    }
    {
      std::lock_guard<std::mutex> lock(queue_mutex);
      worker_busy = false;
      idle_cv.notify_all();
    }
  }

  Options options;
  detail::TextSegmenter segmenter;
  std::unique_ptr<sherpa_onnx::OfflineTts> tts;
  std::thread worker;

  mutable std::mutex callback_mutex;
  AudioCallback audio_callback;
  ErrorCallback error_callback;

  std::mutex input_mutex;
  bool accepting = true;

  std::mutex queue_mutex;
  std::condition_variable queue_cv;
  std::condition_variable idle_cv;
  std::queue<std::string> text_queue;
  bool worker_busy = false;
  bool stopping = false;
};

StreamingTts::StreamingTts(Options options) : impl_(std::make_unique<Impl>(std::move(options))) {}
StreamingTts::~StreamingTts() = default;
void StreamingTts::setAudioCallback(AudioCallback callback) {
  std::lock_guard<std::mutex> lock(impl_->callback_mutex);
  impl_->audio_callback = std::move(callback);
}
void StreamingTts::setErrorCallback(ErrorCallback callback) {
  std::lock_guard<std::mutex> lock(impl_->callback_mutex);
  impl_->error_callback = std::move(callback);
}
void StreamingTts::pushText(std::string_view fragment) { impl_->push(fragment); }
void StreamingTts::flush() { impl_->flushInput(); }
void StreamingTts::waitUntilIdle() { impl_->waitIdle(); }
void StreamingTts::stop() { impl_->stop(); }
int32_t StreamingTts::sampleRate() const noexcept { return impl_->tts ? impl_->tts->SampleRate() : 0; }
int32_t StreamingTts::numSpeakers() const noexcept { return impl_->tts ? impl_->tts->NumSpeakers() : 0; }
}  // namespace streamtts
