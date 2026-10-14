#include "streamtts/streaming_tts.h"
#include "streamtts/miniaudio_sink.h"

#include <iostream>
#include <memory>
#include <string>

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "Usage: streamtts_cli <model-dir> [max-words-per-chunk]\n"
              << "Expected files in <model-dir>: en_US-amy-low.onnx, tokens.txt, espeak-ng-data/\n"
              << "Type lines to speak. Enter /quit to exit.\n";
    return 2;
  }

  try {
    streamtts::Options options;
    const std::string dir = argv[1];
    options.model_path = dir + "/en_US-amy-low.onnx";
    options.tokens_path = dir + "/tokens.txt";
    options.data_dir = dir + "/espeak-ng-data";
    if (argc >= 3) options.max_words_per_chunk = static_cast<size_t>(std::stoul(argv[2]));
    options.chunking = streamtts::ChunkingMode::Balanced;

    // Construct in this order so the TTS worker is destroyed before the sink.
    streamtts::StreamingTts tts(options);
    streamtts::MiniaudioSink sink(tts.sampleRate());
    tts.setAudioCallback([&sink](const float* audio, size_t count, int32_t) {
      sink.enqueue(audio, count);
    });
    tts.setErrorCallback([](const std::string& message) { std::cerr << "[TTS] " << message << '\n'; });

    std::cout << "Ready (" << tts.sampleRate() << " Hz, " << tts.numSpeakers()
              << " speakers). Enter text, /flush, or /quit.\n> " << std::flush;
    std::string line;
    while (std::getline(std::cin, line)) {
      if (line == "/quit") break;
      if (line == "/flush") {
        tts.flush();
        tts.waitUntilIdle();
        std::cout << "> " << std::flush;
        continue;
      }
      tts.pushText(line + "\n");
      tts.flush();  // a submitted line is a complete user input in this demo
      std::cout << "> " << std::flush;
    }
    tts.flush();
    tts.waitUntilIdle();
    sink.waitUntilDrained();
    tts.stop();
    sink.stop();
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "Fatal: " << e.what() << '\n';
    return 1;
  }
}
