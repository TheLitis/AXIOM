cmake_minimum_required(VERSION 3.25)
project(axiom_windows_observer_fault_tests LANGUAGES CXX)

foreach(dependency AXIOM_JSON_SOURCE_DIR AXIOM_RESULT_SOURCE_DIR)
    if(NOT EXISTS "${${dependency}}/CMakeLists.txt")
        message(FATAL_ERROR "${dependency} must identify the existing native build dependency source")
    endif()
endforeach()
# Build the real JSON library. Only the Win32 and small Geode window/clock
# surfaces are fake; the observer source itself is included without rewriting.
add_subdirectory("${AXIOM_RESULT_SOURCE_DIR}" result)
add_subdirectory("${AXIOM_JSON_SOURCE_DIR}" json)
add_executable(axiom_windows_observer_fault_tests WindowsInputObserverTests.cpp)
target_compile_features(axiom_windows_observer_fault_tests PRIVATE cxx_std_23)
target_include_directories(axiom_windows_observer_fault_tests PRIVATE stubs)
target_link_libraries(axiom_windows_observer_fault_tests PRIVATE mat-json)
if(MSVC)
    target_compile_options(axiom_windows_observer_fault_tests PRIVATE /W4 /permissive-)
endif()
