// An explicit, isolated engine smoke test. Inert in the normal game executable.
#include <Geode/Geode.hpp>
#include <Geode/cocos/platform/win32/CCFileUtilsWin32.h>
#include <Geode/modify/CCFileUtilsWin32.hpp>
#include <Geode/modify/MenuLayer.hpp>
#include <Geode/utils/file.hpp>
#include <Windows.h>
#include <fstream>
#include <stdexcept>

using namespace geode::prelude;

namespace {
bool sandboxEnabled() {
    wchar_t buffer[32768]{};
    auto length = GetModuleFileNameW(nullptr, buffer, 32768);
    if (!length || length >= 32768) return false;
    return std::filesystem::path(buffer).filename() == L"AXIOMSandbox.exe" &&
        Loader::get()->getLaunchFlag("axiom-sandbox");
}

gd::string sandboxWritablePath() {
    auto gameDir = dirs::getGameDir();
    auto path = gameDir / "sandbox-saves";
    for (auto const& candidate : {gameDir, path}) {
        auto attributes = GetFileAttributesW(candidate.c_str());
        if (attributes != INVALID_FILE_ATTRIBUTES &&
            ((attributes & FILE_ATTRIBUTE_REPARSE_POINT) || !(attributes & FILE_ATTRIBUTE_DIRECTORY))) {
            throw std::runtime_error("AXIOM sandbox save directory is redirected or is a file");
        }
    }
    std::filesystem::create_directories(path);
    return (path.generic_string() + "/").c_str();
}
}

class $modify(AxiomSandboxFiles, CCFileUtilsWin32) {
    gd::string getWritablePath() {
        if (sandboxEnabled()) return sandboxWritablePath();
        return CCFileUtilsWin32::getWritablePath();
    }
    gd::string getWritablePath2() {
        if (sandboxEnabled()) return sandboxWritablePath();
        return CCFileUtilsWin32::getWritablePath2();
    }
};

class $modify(AxiomSandboxMenu, MenuLayer) {
    bool init() {
        if (!MenuLayer::init()) return false;
        static bool started = false;
        if (!sandboxEnabled() || started) return true;
        started = true;
        auto actual = CCFileUtils::sharedFileUtils()->getWritablePath();
        if (std::filesystem::weakly_canonical(actual.c_str()) !=
            std::filesystem::weakly_canonical(dirs::getGameDir() / "sandbox-saves")) {
            log::error("AXIOM sandbox writable-path isolation failed; fixture not started");
            return true;
        }
        log::info("AXIOM sandbox isolated writable path: {}", actual);
        // The fixture is supplied locally, never downloaded or added to saved levels.
        auto fixturePath = dirs::getGameDir() / "fixture-level.txt";
        std::ifstream stream(fixturePath, std::ios::binary);
        std::string raw(1048577, '\0');
        stream.read(raw.data(), raw.size());
        raw.resize(stream.gcount());
        if (!stream.eof() || raw.empty() || raw.size() > 1048576) {
            log::error("AXIOM sandbox requires a nonempty fixture-level.txt <= 1 MiB");
            return true;
        }
        Mod::get()->setSettingValue("capture-enabled", true);
        // The isolated fixture's effective replay mode comes only from the launch
        // flag, so a saved toggle cannot silently turn the baseline into replay.
        Mod::get()->setSettingValue("replay-enabled", false);
        queueInMainThread([raw]() {
            auto level = GJGameLevel::create();
            level->m_levelName = "AXIOM instrument fixture";
            level->m_levelString = raw.c_str();
            level->m_levelType = GJLevelType::Editor;
            level->m_audioTrack = 0;
            auto scene = PlayLayer::scene(level, false, false);
            if (!scene) {
                log::error("AXIOM sandbox fixture scene creation failed");
                return;
            }
            CCDirector::sharedDirector()->replaceScene(scene);
            log::info("AXIOM sandbox fixture launched; no human or rating evidence");
        });
        return true;
    }
};
