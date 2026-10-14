#include "streamtts/streaming_tts.h"
#include "streamtts/miniaudio_sink.h"

#include <jni.h>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

namespace {
std::mutex g_mutex;
std::unique_ptr<streamtts::StreamingTts> g_tts;
std::unique_ptr<streamtts::MiniaudioSink> g_sink;

std::string FromJString(JNIEnv* env, jstring value) {
  if (!value) return {};
  const char* chars = env->GetStringUTFChars(value, nullptr);
  if (!chars) throw std::runtime_error("Could not read Java string");
  std::string out(chars);
  env->ReleaseStringUTFChars(value, chars);
  return out;
}
void ThrowJava(JNIEnv* env, const char* message) {
  jclass cls = env->FindClass("java/lang/IllegalStateException");
  if (cls) env->ThrowNew(cls, message);
}
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_example_streamtts_NativeTts_nativeInit(JNIEnv* env, jclass,
                                                 jstring modelPath,
                                                 jstring tokensPath,
                                                 jstring dataDir) {
  try {
    const std::string model = FromJString(env, modelPath);
    const std::string tokens = FromJString(env, tokensPath);
    const std::string data = FromJString(env, dataDir);
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_tts) g_tts->stop();
    g_tts.reset();
    if (g_sink) g_sink->stop();
    g_sink.reset();

    streamtts::Options options;
    options.model_path = model;
    options.tokens_path = tokens;
    options.data_dir = data;
    options.num_threads = 2;
    options.chunking = streamtts::ChunkingMode::Balanced;
    auto tts = std::make_unique<streamtts::StreamingTts>(options);
    auto sink = std::make_unique<streamtts::MiniaudioSink>(tts->sampleRate());
    streamtts::MiniaudioSink* sinkPtr = sink.get();
    tts->setAudioCallback([sinkPtr](const float* samples, size_t count, int32_t) {
      sinkPtr->enqueue(samples, count);
    });
    tts->setErrorCallback([](const std::string& message) {
      // Production apps should forward this to their logging/UI layer.
      (void)message;
    });
    g_tts = std::move(tts);
    g_sink = std::move(sink);
    return JNI_TRUE;
  } catch (const std::exception& e) {
    ThrowJava(env, e.what());
    return JNI_FALSE;
  }
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_streamtts_NativeTts_nativePushText(JNIEnv* env, jclass, jstring text) {
  try {
    const std::string fragment = FromJString(env, text);
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_tts) throw std::runtime_error("Call NativeTts.init() before pushText()");
    g_tts->pushText(fragment);
  } catch (const std::exception& e) { ThrowJava(env, e.what()); }
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_streamtts_NativeTts_nativeFlush(JNIEnv* env, jclass) {
  try {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (!g_tts) throw std::runtime_error("TTS is not initialized");
    g_tts->flush();
  } catch (const std::exception& e) { ThrowJava(env, e.what()); }
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_streamtts_NativeTts_nativeWaitUntilIdle(JNIEnv* env, jclass) {
  try {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_tts) g_tts->waitUntilIdle();
  } catch (const std::exception& e) { ThrowJava(env, e.what()); }
}

extern "C" JNIEXPORT void JNICALL
Java_com_example_streamtts_NativeTts_nativeShutdown(JNIEnv*, jclass) {
  std::lock_guard<std::mutex> lock(g_mutex);
  if (g_tts) g_tts->stop();
  g_tts.reset();
  if (g_sink) {
    g_sink->waitUntilDrained();
    g_sink->stop();
  }
  g_sink.reset();
}
