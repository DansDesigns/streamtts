#include "text_segmenter.h"

#include <cctype>
#include <utility>

namespace streamtts::detail {
namespace {
bool IsSpace(unsigned char c) { return std::isspace(c) != 0; }
bool IsHardPunctuation(char c) { return c == '.' || c == '!' || c == '?'; }
bool IsClausePunctuation(char c) { return c == ',' || c == ';' || c == ':'; }
std::string Trim(std::string s) {
  size_t begin = 0;
  while (begin < s.size() && IsSpace(static_cast<unsigned char>(s[begin]))) ++begin;
  size_t end = s.size();
  while (end > begin && IsSpace(static_cast<unsigned char>(s[end - 1]))) --end;
  return s.substr(begin, end - begin);
}
}  // namespace

TextSegmenter::TextSegmenter(size_t max_words, size_t first_chunk_words)
    : max_words_(max_words ? max_words : 3),
      first_chunk_words_(first_chunk_words ? first_chunk_words : 2) {
  if (first_chunk_words_ > max_words_) first_chunk_words_ = max_words_;
}

std::vector<std::string> TextSegmenter::push(const std::string& fragment) {
  pending_.append(fragment);
  return drain(false);
}

std::vector<std::string> TextSegmenter::flush() { return drain(true); }

bool TextSegmenter::empty() const noexcept { return pending_.empty(); }

std::vector<std::string> TextSegmenter::drain(bool final) {
  std::vector<std::string> ready;
  while (!pending_.empty()) {
    const size_t target = emitted_first_ ? max_words_ : first_chunk_words_;
    size_t chunk_end = std::string::npos;
    size_t consume_end = std::string::npos;
    size_t words = 0;
    bool in_word = false;

    for (size_t i = 0; i < pending_.size(); ++i) {
      const unsigned char uc = static_cast<unsigned char>(pending_[i]);
      const char c = pending_[i];
      if (IsSpace(uc)) {
        if (in_word) {
          ++words;
          in_word = false;
        }
        if (words >= target) {
          chunk_end = i;
          consume_end = i + 1;
          break;
        }
      } else if (IsHardPunctuation(c) || IsClausePunctuation(c)) {
        if (in_word) {
          ++words;
          in_word = false;
        }
        // Sentence punctuation flushes immediately. Comma/semicolon/colon
        // flush only once the chunk has at least two words.
        if (IsHardPunctuation(c) || (IsClausePunctuation(c) && words >= 2)) {
          chunk_end = i + 1;
          consume_end = i + 1;
          break;
        }
      } else {
        in_word = true;
      }
    }

    if (chunk_end == std::string::npos && final) {
      chunk_end = pending_.size();
      consume_end = pending_.size();
    }
    if (chunk_end == std::string::npos) break;  // trailing token may be partial

    std::string chunk = Trim(pending_.substr(0, chunk_end));
    pending_.erase(0, consume_end);
    if (!chunk.empty()) {
      ready.emplace_back(std::move(chunk));
      emitted_first_ = true;
    }
  }
  return ready;
}
}  // namespace streamtts::detail
