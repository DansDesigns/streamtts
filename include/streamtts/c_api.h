#pragma once
#include <stddef.h>
#include <stdint.h>
#include "streamtts/export.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void* StreamTtsHandle;

typedef struct StreamTtsConfig {
  const char* model_path;
  const char* tokens_path;
  const char* data_dir;
  const char* provider;       /* defaults to "cpu" when null/empty */
  int32_t num_threads;        /* defaults to 2 when <= 0 */
  int32_t speaker_id;
  float speed;                /* defaults to 1.0 when <= 0 */
  int32_t chunking_mode;      /* 0=immediate, 1=balanced, 2=natural */
  size_t max_words_per_chunk; /* 0 selects mode default */
} StreamTtsConfig;

typedef void (*StreamTtsAudioCallback)(const float* samples, size_t count,
                                       int32_t sample_rate, void* user_data);
typedef void (*StreamTtsErrorCallback)(const char* message, void* user_data);

typedef struct StreamTtsCallbacks {
  StreamTtsAudioCallback audio;
  StreamTtsErrorCallback error;
  void* user_data;
} StreamTtsCallbacks;

/* Creates the model and starts the background synthesis worker. On failure,
   returns NULL and writes a message into error_buffer when provided. */
STREAMTTS_API StreamTtsHandle streamtts_create(
    const StreamTtsConfig* config, const StreamTtsCallbacks* callbacks,
    char* error_buffer, size_t error_buffer_capacity);

/* Feeds any UTF-8 fragment; pass its byte count, not strlen(), if the fragment
   is not NUL-terminated. Returns 0 on success, -1 on error. */
STREAMTTS_API int streamtts_push_text(StreamTtsHandle handle,
                                      const char* utf8, size_t byte_count);
STREAMTTS_API int streamtts_flush(StreamTtsHandle handle);
STREAMTTS_API int streamtts_wait_until_idle(StreamTtsHandle handle);
STREAMTTS_API int32_t streamtts_sample_rate(StreamTtsHandle handle);
STREAMTTS_API int32_t streamtts_num_speakers(StreamTtsHandle handle);
STREAMTTS_API const char* streamtts_last_error(StreamTtsHandle handle);
STREAMTTS_API void streamtts_destroy(StreamTtsHandle handle);

#ifdef __cplusplus
}
#endif
