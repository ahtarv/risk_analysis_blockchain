cmake_minimum_required(VERSION 3.20)
project(orderbook_engine CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Find Python & pybind11 ────────────────────────────────────────────────────
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

# pybind11 via pip: python -m pip install pybind11
execute_process(
    COMMAND ${Python3_EXECUTABLE} -m pybind11 --cmakedir
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
find_package(pybind11 CONFIG REQUIRED HINTS "${pybind11_DIR}")

# ── Build the Python extension module ─────────────────────────────────────────
pybind11_add_module(orderbook_engine
    engine/bindings.cpp
)

target_include_directories(orderbook_engine PRIVATE engine/)

target_compile_options(orderbook_engine PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /O2 /arch:AVX2>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -O3 -march=native>
)

# ── Standalone test executable (no Python needed) ────────────────────────────
add_executable(test_engine tests/test_engine.cpp)
target_include_directories(test_engine PRIVATE engine/)
set_target_properties(test_engine PROPERTIES CXX_STANDARD 20)
target_compile_options(test_engine PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/W4 /O2>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -O2>
)
