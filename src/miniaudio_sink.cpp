#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#include "streamtts/miniaudio_sink.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

namespace streamtts {
struct MiniaudioSink::Impl {
  explicit Impl(int rate, size_t capacity)
      : sample_rate(rate), ring_capacity(std::max<size_t>(capacity, 4096)), ring(ring_capacity, 0.0f) {
    if (sample_rate <= 0) throw std::invalid_argument("audio sample rate must be positive");
    ma_device_config config = ma_device_config_init(ma_device_type_playback);
    config.playback.format = ma_format_f32;
    config.playback.channels = 1;
    config.sampleRate = static_cast<ma_uint32>(sample_rate);
    config.dataCallback = &Impl::onAudio;
    config.pUserData = this;
    ma_result result = ma_device_init(nullptr, &config, &device);
    if (result != MA_SUCCESS) throw std::runtime_error("miniaudio device init failed: " + std::to_string(result));
    device_initialized = true;
    result = ma_device_start(&device);
    if (result != MA_SUCCESS) {
      ma_device_uninit(&device);
      device_initialized = false;
      throw std::runtime_error("miniaudio device start failed: " + std::to_string(result));
    }
    started = true;
  }

  ~Impl() { stop(); }

  static void onAudio(ma_device* device, void* output, const void*, ma_uint32 frames) {
    auto* self = static_cast<Impl*>(device->pUserData);
    auto* dst = static_cast<float*>(output);
    const size_t n = frames;  // configured mono float output
    std::fill(dst, dst + n, 0.0f);
    const uint64_t read = self->read_index.load(std::memory_order_relaxed);
    const uint64_t write = self->write_index.load(std::memory_order_acquire);
    const size_t available = static_cast<size_t>(write - read);
    const size_t take = std::min(n, available);
    for (size_t i = 0; i < take; ++i) dst[i] = self->ring[(read + i) % self->ring_capacity];
    self->read_index.store(read + take, std::memory_order_release);
    if (take != 0) self->drain_cv.notify_all();
  }

  void enqueue(const float* samples, size_t count) {
    if (!samples || count == 0) return;
    size_t offset = 0;
    while (offset < count && !stopped.load(std::memory_order_acquire)) {
      uint64_t w = write_index.load(std::memory_order_relaxed);
      const uint64_t r = read_index.load(std::memory_order_acquire);
      const size_t used = static_cast<size_t>(w - r);
      const size_t space = ring_capacity > used ? ring_capacity - used : 0;
      if (space == 0) {
        std::unique_lock<std::mutex> lock(drain_mutex);
        drain_cv.wait_for(lock, std::chrono::milliseconds(2));
        continue;
      }
      const size_t put = std::min(space, count - offset);
      for (size_t i = 0; i < put; ++i) ring[(w + i) % ring_capacity] = samples[offset + i];
      write_index.store(w + put, std::memory_order_release);
      offset += put;
    }
  }

  void waitUntilDrained() {
    while (!stopped.load(std::memory_order_acquire)) {
      const uint64_t r = read_index.load(std::memory_order_acquire);
      const uint64_t w = write_index.load(std::memory_order_acquire);
      if (r == w) return;
      std::unique_lock<std::mutex> lock(drain_mutex);
      drain_cv.wait_for(lock, std::chrono::milliseconds(10));
    }
  }

  void stop() {
    if (stopped.exchange(true, std::memory_order_acq_rel)) return;
    drain_cv.notify_all();
    if (device_initialized) {
      if (started) ma_device_stop(&device);
      ma_device_uninit(&device);
      device_initialized = false;
      started = false;
    }
  }

  int sample_rate;
  size_t ring_capacity;
  std::vector<float> ring;
  std::atomic<uint64_t> write_index{0};
  std::atomic<uint64_t> read_index{0};
  std::atomic<bool> stopped{false};
  ma_device device{};
  bool device_initialized = false;
  bool started = false;
  mutable std::mutex error_mutex;
  std::string error;
  std::mutex drain_mutex;
  std::condition_variable drain_cv;
};

MiniaudioSink::MiniaudioSink(int sample_rate, size_t ring_capacity_frames)
    : impl_(std::make_unique<Impl>(sample_rate, ring_capacity_frames)) {}
MiniaudioSink::~MiniaudioSink() = default;
void MiniaudioSink::enqueue(const float* samples, size_t count) { impl_->enqueue(samples, count); }
void MiniaudioSink::waitUntilDrained() { impl_->waitUntilDrained(); }
void MiniaudioSink::stop() { impl_->stop(); }
std::string MiniaudioSink::lastError() const {
  std::lock_guard<std::mutex> lock(impl_->error_mutex);
  return impl_->error;
}
}  // namespace streamtts
