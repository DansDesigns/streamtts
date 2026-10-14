#include "streamtts/c_api.h"
#include "streamtts/streaming_tts.h"

#include <algorithm>
#include <cstring>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <string_view>
#include <string>

namespace {
struct Handle {
  std::unique_ptr<streamtts::StreamingTts> tts;
  StreamTtsCallbacks callbacks{};
  std::mutex error_mutex;
  std::string last_error;
};
void CopyError(char* dst, size_t capacity, const std::string& message) {
  if (!dst || capacity == 0) return;
  const size_t n = std::min(capacity - 1, message.size());
  std::memcpy(dst, message.data(), n);
  dst[n] = '\0';
}
Handle* Get(StreamTtsHandle h) { return static_cast<Handle*>(h); }
}

extern "C" {
StreamTtsHandle streamtts_create(const StreamTtsConfig* c,
                                 const StreamTtsCallbacks* callbacks,
                                 char* error_buffer, size_t error_buffer_capacity) {
  try {
    if (!c) throw std::invalid_argument("config must not be null");
    if (!c->model_path || !c->tokens_path) throw std::invalid_argument("model_path and tokens_path are required");
    auto h = std::make_unique<Handle>();
    if (callbacks) h->callbacks = *callbacks;
    streamtts::Options o;
    o.model_path = c->model_path;
    o.tokens_path = c->tokens_path;
    if (c->data_dir) o.data_dir = c->data_dir;
    o.provider = (c->provider && *c->provider) ? c->provider : "cpu";
    o.num_threads = c->num_threads > 0 ? c->num_threads : 2;
    o.speaker_id = c->speaker_id;
    o.speed = c->speed > 0.0f ? c->speed : 1.0f;
    o.max_words_per_chunk = c->max_words_per_chunk;
    switch (c->chunking_mode) {
      case 0: o.chunking = streamtts::ChunkingMode::Immediate; break;
      case 2: o.chunking = streamtts::ChunkingMode::Natural; break;
      default: o.chunking = streamtts::ChunkingMode::Balanced; break;
    }
    h->tts = std::make_unique<streamtts::StreamingTts>(std::move(o));
    Handle* raw = h.get();
    h->tts->setAudioCallback([raw](const float* samples, size_t count, int32_t rate) {
      if (raw->callbacks.audio) raw->callbacks.audio(samples, count, rate, raw->callbacks.user_data);
    });
    h->tts->setErrorCallback([raw](const std::string& message) {
      {
        std::lock_guard<std::mutex> lock(raw->error_mutex);
        raw->last_error = message;
      }
      if (raw->callbacks.error) raw->callbacks.error(message.c_str(), raw->callbacks.user_data);
    });
    CopyError(error_buffer, error_buffer_capacity, "");
    return h.release();
  } catch (const std::exception& e) {
    CopyError(error_buffer, error_buffer_capacity, e.what());
    return nullptr;
  } catch (...) {
    CopyError(error_buffer, error_buffer_capacity, "Unknown native error");
    return nullptr;
  }
}

int streamtts_push_text(StreamTtsHandle handle, const char* utf8, size_t byte_count) {
  try {
    if (!handle || (!utf8 && byte_count != 0)) return -1;
    Get(handle)->tts->pushText(std::string_view(utf8 ? utf8 : "", byte_count));
    return 0;
  } catch (const std::exception& e) {
    Handle* h = Get(handle);
    std::lock_guard<std::mutex> lock(h->error_mutex);
    h->last_error = e.what();
    return -1;
  } catch (...) { return -1; }
}
int streamtts_flush(StreamTtsHandle handle) {
  try { if (!handle) return -1; Get(handle)->tts->flush(); return 0; }
  catch (const std::exception& e) { Handle* h = Get(handle); std::lock_guard<std::mutex> lock(h->error_mutex); h->last_error = e.what(); return -1; }
  catch (...) { return -1; }
}
int streamtts_wait_until_idle(StreamTtsHandle handle) {
  try { if (!handle) return -1; Get(handle)->tts->waitUntilIdle(); return 0; }
  catch (const std::exception& e) { Handle* h = Get(handle); std::lock_guard<std::mutex> lock(h->error_mutex); h->last_error = e.what(); return -1; }
  catch (...) { return -1; }
}
int32_t streamtts_sample_rate(StreamTtsHandle handle) { return handle ? Get(handle)->tts->sampleRate() : 0; }
int32_t streamtts_num_speakers(StreamTtsHandle handle) { return handle ? Get(handle)->tts->numSpeakers() : 0; }
const char* streamtts_last_error(StreamTtsHandle handle) {
  if (!handle) return "invalid handle";
  // Keep the returned pointer valid after releasing the handle mutex. Its
  // contents remain valid on this thread until the next call to this function.
  thread_local std::string snapshot;
  Handle* h = Get(handle);
  {
    std::lock_guard<std::mutex> lock(h->error_mutex);
    snapshot = h->last_error;
  }
  return snapshot.c_str();
}
void streamtts_destroy(StreamTtsHandle handle) {
  if (!handle) return;
  std::unique_ptr<Handle> h(Get(handle));
  if (h->tts) h->tts->stop();
}
}
