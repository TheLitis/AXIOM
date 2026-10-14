// An explicit, isolated engine smoke test. Inert in the normal game executable.
#include <Geode/Geode.hpp>
#include <Geode/cocos/platform/win32/CCFileUtilsWin32.h>
#include <Geode/modify/AppDelegate.hpp>
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

void launchSandboxFixture(std::string const& raw) {
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
        log::info("AXIOM sandbox fixture launched; input authorship is not authenticated by the collector");
    });
}
}

class $modify(AxiomSandboxApp, AppDelegate) {
    bool applicationDidFinishLaunching() {
        bool scoped = sandboxEnabled();
        if (scoped) log::info("AXIOM sandbox app init entered");
        bool result = AppDelegate::applicationDidFinishLaunching();
        if (scoped) log::info("AXIOM sandbox app init returned: {}", result ? "true" : "false");
        return result;
    }
};

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
    struct Fields {
        std::string fixtureRaw;
        bool manualStarted = false;
    };
    void onAxiomManualStart(CCObject*) {
        if (!sandboxEnabled() || m_fields->manualStarted || m_fields->fixtureRaw.empty()) return;
        m_fields->manualStarted = true;
        launchSandboxFixture(m_fields->fixtureRaw);
    }
    bool init() {
        bool scoped = sandboxEnabled();
        if (scoped) log::info("AXIOM sandbox menu init entered");
        bool initialized = MenuLayer::init();
        if (scoped) log::info("AXIOM sandbox menu init returned: {}", initialized ? "true" : "false");
        if (!initialized) return false;
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
        if (Loader::get()->getLaunchFlag("axiom-sandbox-manual")) {
            // Only the explicitly guarded sandbox gets this user-operated
            // start control. No OS keyboard/mouse input is synthesized here.
            m_fields->fixtureRaw = raw;
            auto size = CCDirector::sharedDirector()->getWinSize();
            auto menu = CCMenu::create();
            menu->setPosition({size.width / 2.f, size.height - 95.f});
            auto button = CCMenuItemSpriteExtra::create(ButtonSprite::create("Start AXIOM Test"), this,
                menu_selector(AxiomSandboxMenu::onAxiomManualStart));
            menu->addChild(button);
            this->addChild(menu, 100);
            auto label = CCLabelBMFont::create("SPACE W UP A D LEFT RIGHT + click after starting", "bigFont.fnt");
            label->setScale(0.25f);
            label->setPosition({size.width / 2.f, size.height - 60.f});
            this->addChild(label, 100);
            log::info("AXIOM sandbox manual test ready; waiting for the user's Start AXIOM Test button");
        } else launchSandboxFixture(raw);
        return true;
    }
};
