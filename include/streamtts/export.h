#pragma once
#if defined(_WIN32) && defined(STREAMTTS_SHARED)
  #if defined(STREAMTTS_BUILDING_LIBRARY)
    #define STREAMTTS_API __declspec(dllexport)
  #else
    #define STREAMTTS_API __declspec(dllimport)
  #endif
#elif defined(__GNUC__) && defined(STREAMTTS_SHARED)
  #define STREAMTTS_API __attribute__((visibility("default")))
#else
  #define STREAMTTS_API
#endif
