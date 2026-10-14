#pragma once
#include <cstddef>
#include <string>
#include <vector>

namespace streamtts::detail {
class TextSegmenter {
 public:
  TextSegmenter(size_t max_words, size_t first_chunk_words);
  std::vector<std::string> push(const std::string& fragment);
  std::vector<std::string> flush();
  bool empty() const noexcept;
 private:
  std::vector<std::string> drain(bool final);
  size_t max_words_;
  size_t first_chunk_words_;
  bool emitted_first_ = false;
  std::string pending_;
};
}  // namespace streamtts::detail
