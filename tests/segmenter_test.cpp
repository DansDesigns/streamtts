#include "../src/text_segmenter.h"
#include <cassert>
#include <iostream>
#include <string>
#include <vector>

int main() {
  streamtts::detail::TextSegmenter s(3, 2);
  auto a = s.push("Hel");
  assert(a.empty());                 // incomplete token is held
  auto b = s.push("lo there ");
  assert(b.size() == 1 && b[0] == "Hello there");
  auto c = s.push("this is a test.");
  assert(c.size() == 2);
  assert(c[0] == "this is a");
  assert(c[1] == "test.");
  auto d = s.push("last word");
  assert(d.empty());
  auto e = s.flush();
  assert(e.size() == 1 && e[0] == "last word");
  std::cout << "TextSegmenter tests passed\n";
}
