cmake_minimum_required(VERSION 3.24)
project(streamtts VERSION 0.1.0 LANGUAGES C CXX)

option(STREAMTTS_BUILD_DEMO "Build the interactive desktop demo (uses miniaudio)" ON)
option(STREAMTTS_BUILD_TESTS "Build text segmenter tests" ON)
set(SHERPA_ONNX_SOURCE_DIR "" CACHE PATH "Optional path to an existing sherpa-onnx source checkout")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build only the native inference pieces needed by this project. This project
# does not enable or invoke any Rust toolchain or Rust bindings.
set(SHERPA_ONNX_ENABLE_TTS ON CACHE BOOL "" FORCE)
set(SHERPA_ONNX_ENABLE_C_API ON CACHE BOOL "" FORCE)
set(SHERPA_ONNX_ENABLE_BINARY OFF CACHE BOOL "" FORCE)
set(SHERPA_ONNX_ENABLE_PORTAUDIO OFF CACHE BOOL "" FORCE)
set(SHERPA_ONNX_ENABLE_WEBSOCKET OFF CACHE BOOL "" FORCE)
set(SHERPA_ONNX_ENABLE_SPEAKER_DIARIZATION OFF CACHE BOOL "" FORCE)
set(SHERPA_ONNX_ENABLE_TESTS OFF CACHE BOOL "" FORCE)
set(SHERPA_ONNX_BUILD_C_API_EXAMPLES OFF CACHE BOOL "" FORCE)

if(SHERPA_ONNX_SOURCE_DIR)
  if(NOT EXISTS "${SHERPA_ONNX_SOURCE_DIR}/CMakeLists.txt")
    message(FATAL_ERROR "SHERPA_ONNX_SOURCE_DIR does not point to a sherpa-onnx checkout")
  endif()
  set(_streamtts_sherpa_root "${SHERPA_ONNX_SOURCE_DIR}")
  add_subdirectory("${SHERPA_ONNX_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/sherpa-onnx" EXCLUDE_FROM_ALL)
else()
  include(FetchContent)
  FetchContent_Declare(
    sherpa_onnx
    GIT_REPOSITORY https://github.com/k2-fsa/sherpa-onnx.git
    GIT_TAG v1.13.8
    GIT_SHALLOW TRUE
  )
  FetchContent_MakeAvailable(sherpa_onnx)
  set(_streamtts_sherpa_root "${sherpa_onnx_SOURCE_DIR}")
endif()

if(NOT TARGET sherpa-onnx-cxx-api)
  message(FATAL_ERROR "Expected target sherpa-onnx-cxx-api was not created by sherpa-onnx. Check that the selected sherpa-onnx checkout includes its C++ API.")
endif()

find_package(Threads REQUIRED)

add_library(streamtts
  src/streaming_tts.cpp
  src/text_segmenter.cpp
  src/c_api.cpp
)
target_include_directories(streamtts
  PUBLIC "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
         "$<INSTALL_INTERFACE:include>"
  PRIVATE "${_streamtts_sherpa_root}" "${CMAKE_CURRENT_SOURCE_DIR}/src"
)
target_link_libraries(streamtts PUBLIC sherpa-onnx-cxx-api Threads::Threads)
target_compile_definitions(streamtts PRIVATE STREAMTTS_BUILDING_LIBRARY)
if(BUILD_SHARED_LIBS)
  target_compile_definitions(streamtts PUBLIC STREAMTTS_SHARED)
endif()
set_target_properties(streamtts PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  target_compile_options(streamtts PRIVATE /W4 /permissive- /utf-8)
else()
  target_compile_options(streamtts PRIVATE -Wall -Wextra -Wpedantic)
endif()

# The output device is a replaceable adapter. This reference implementation
# uses miniaudio; host applications may instead supply CoreAudio/WASAPI/AAudio/etc.
if(ANDROID OR STREAMTTS_BUILD_DEMO)
  set(_miniaudio_header "${CMAKE_CURRENT_SOURCE_DIR}/third_party/miniaudio.h")
  if(NOT EXISTS "${_miniaudio_header}")
    file(DOWNLOAD
      "https://raw.githubusercontent.com/mackron/miniaudio/0.11.22/miniaudio.h"
      "${_miniaudio_header}"
      TLS_VERIFY ON
      STATUS _miniaudio_download_status
      SHOW_PROGRESS
    )
    list(GET _miniaudio_download_status 0 _miniaudio_status_code)
    if(NOT _miniaudio_status_code EQUAL 0)
      file(REMOVE "${_miniaudio_header}")
      message(FATAL_ERROR "Could not download miniaudio.h. Run: python scripts/download_miniaudio.py, then reconfigure. Details: ${_miniaudio_download_status}")
    endif()
    file(SIZE "${_miniaudio_header}" _miniaudio_size)
    if(_miniaudio_size LESS 100000)
      file(REMOVE "${_miniaudio_header}")
      message(FATAL_ERROR "Downloaded miniaudio.h is unexpectedly small. Run python scripts/download_miniaudio.py and retry.")
    endif()
  endif()

  add_library(streamtts_audio STATIC src/miniaudio_sink.cpp)
  target_include_directories(streamtts_audio PUBLIC include PRIVATE third_party)
  target_link_libraries(streamtts_audio PUBLIC streamtts)
  set_target_properties(streamtts_audio PROPERTIES POSITION_INDEPENDENT_CODE ON)
endif()

if(ANDROID)
  add_library(streamtts_jni SHARED android/app/src/main/cpp/native_bridge.cpp)
  target_include_directories(streamtts_jni PRIVATE include)
  target_link_libraries(streamtts_jni PRIVATE streamtts streamtts_audio log android aaudio OpenSLES)
  set_target_properties(streamtts_jni PROPERTIES OUTPUT_NAME streamtts_jni)
elseif(STREAMTTS_BUILD_DEMO)
  add_executable(streamtts_cli examples/streamtts_cli.cpp)
  target_link_libraries(streamtts_cli PRIVATE streamtts streamtts_audio)
endif()

if(STREAMTTS_BUILD_TESTS)
  enable_testing()
  add_executable(streamtts_segmenter_test tests/segmenter_test.cpp src/text_segmenter.cpp)
  target_include_directories(streamtts_segmenter_test PRIVATE src)
  add_test(NAME streamtts_segmenter COMMAND streamtts_segmenter_test)
endif()

include(GNUInstallDirs)
install(TARGETS streamtts EXPORT streamttsTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
