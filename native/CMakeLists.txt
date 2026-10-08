cmake_minimum_required(VERSION 3.25)
project(axiom_native_capture VERSION 0.1.0 LANGUAGES CXX)

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "M1 supports Windows x64 only")
endif()
if(NOT GEODE_SDK)
    set(GEODE_SDK "$ENV{GEODE_SDK}")
endif()
if(NOT EXISTS "${GEODE_SDK}/CMakeLists.txt")
    message(FATAL_ERROR "Pass -DGEODE_SDK=<pinned Geode 5.8.2 checkout>")
endif()
set(AXIOM_SDK_COMMIT "2a5fd87433da47d6bf07221774f0cbb25535ae08" CACHE STRING "Geode SDK source identity")
set(AXIOM_BINDINGS_COMMIT "2a8b5c489ce8b49e7061b0543aa2bc5b22570063" CACHE STRING "Bindings source identity")
foreach(identity AXIOM_SDK_COMMIT AXIOM_BINDINGS_COMMIT)
    string(LENGTH "${${identity}}" identity_length)
    if(NOT identity_length EQUAL 40 OR NOT "${${identity}}" MATCHES "^[a-f0-9]+$")
        message(FATAL_ERROR "${identity} must be an exact lowercase Git commit")
    endif()
endforeach()
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${GEODE_SDK}"
    OUTPUT_VARIABLE actual_sdk_commit OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
if(NOT actual_sdk_commit STREQUAL AXIOM_SDK_COMMIT)
    message(FATAL_ERROR "Geode checkout does not match AXIOM_SDK_COMMIT")
endif()
if(NOT GEODE_BINDINGS_REPO_PATH)
    message(FATAL_ERROR "Pass -DGEODE_BINDINGS_REPO_PATH=<pinned bindings checkout>; floating bindings are unsupported")
endif()
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${GEODE_BINDINGS_REPO_PATH}"
    OUTPUT_VARIABLE actual_bindings_commit OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
if(NOT actual_bindings_commit STREQUAL AXIOM_BINDINGS_COMMIT)
    message(FATAL_ERROR "Bindings checkout does not match AXIOM_BINDINGS_COMMIT")
endif()
execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    OUTPUT_VARIABLE AXIOM_SOURCE_COMMIT OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
file(GLOB_RECURSE AXIOM_SOURCES CONFIGURE_DEPENDS "src/*.cpp" "src/*.hpp")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${AXIOM_SOURCES} "${CMAKE_CURRENT_SOURCE_DIR}/mod.json")
set(source_identity "")
foreach(source ${AXIOM_SOURCES} "${CMAKE_CURRENT_SOURCE_DIR}/CMakeLists.txt" "${CMAKE_CURRENT_SOURCE_DIR}/mod.json")
    file(SHA256 "${source}" source_sha)
    file(RELATIVE_PATH source_relative "${CMAKE_CURRENT_SOURCE_DIR}" "${source}")
    string(APPEND source_identity "${source_relative}:${source_sha}\n")
endforeach()
string(SHA256 AXIOM_SOURCE_TREE_SHA256 "${source_identity}")
add_subdirectory("${GEODE_SDK}" geode-sdk)
add_library(${PROJECT_NAME} SHARED ${AXIOM_SOURCES})
target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_23)
target_compile_definitions(${PROJECT_NAME} PRIVATE
    AXIOM_SOURCE_COMMIT="${AXIOM_SOURCE_COMMIT}"
    AXIOM_SOURCE_TREE_SHA256="${AXIOM_SOURCE_TREE_SHA256}"
    AXIOM_SDK_COMMIT="${AXIOM_SDK_COMMIT}"
    AXIOM_BINDINGS_COMMIT="${AXIOM_BINDINGS_COMMIT}")
target_link_libraries(${PROJECT_NAME} bcrypt)
# Pinned SDK 5.8.2 declares this virtual method public, while its win64 cocos
# import library exports the otherwise identical protected method. The sandbox
# subclass needs the vtable reference. Access is the sole verified ABI difference;
# do not alter the SDK or apply this alias to another signature/platform.
if(MSVC)
    set(cocos_public "?getPathForFilename@CCFileUtilsWin32@cocos2d@@UEAA?AV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@AEBV34@00@Z")
    set(cocos_protected "?getPathForFilename@CCFileUtilsWin32@cocos2d@@MEAA?AV?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@std@@AEBV34@00@Z")
    target_link_options(${PROJECT_NAME} PRIVATE
        "/alternatename:${cocos_public}=${cocos_protected}"
        "/alternatename:__imp_${cocos_public}=__imp_${cocos_protected}")
endif()
setup_geode_mod(${PROJECT_NAME} DONT_INSTALL)
