#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include "streamtts/export.h"

namespace streamtts {

// Optional reference audio output implemented with miniaudio. The core library
// itself has no audio-backend dependency; apps can wire AudioCallback to any
// native playback engine instead.
class STREAMTTS_API MiniaudioSink {
 public:
  explicit MiniaudioSink(int sample_rate, size_t ring_capacity_frames = 262144);
  ~MiniaudioSink();
  MiniaudioSink(const MiniaudioSink&) = delete;
  MiniaudioSink& operator=(const MiniaudioSink&) = delete;

  // May be called from the synthesis thread. Blocks briefly if the playback
  // ring is full; it does not allocate or take a mutex from the audio callback.
  void enqueue(const float* samples, size_t count);
  void waitUntilDrained();
  void stop();
  std::string lastError() const;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace streamtts
