#include <Geode/Geode.hpp>
#include <Geode/modify/GJBaseGameLayer.hpp>
#include <Geode/modify/PlayLayer.hpp>
#include <Geode/modify/PlayerObject.hpp>
#include <Geode/modify/CCScheduler.hpp>
#include <Windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <fstream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>

using namespace geode::prelude;
namespace axiom {
using Json = matjson::Value;
using Clock = std::chrono::steady_clock;
constexpr size_t MaxBytes = 16 * 1024 * 1024;
constexpr size_t MaxCommands = 20000;
constexpr size_t MaxInputs = 12000;
constexpr char Policy[] = "process-commands-pre-hook-owned-input-v1";
enum class ClockPolicy { Native, FixedBase60, FixedScheduler240 };
ClockPolicy clockPolicy = ClockPolicy::Native;
std::string clockSelectionError;
size_t updateDepth = 0;
size_t schedulerDepth = 0;
size_t phaseDepth = 0;
std::filesystem::path executablePath();

void selectClockPolicy() {
    auto choice = Mod::get()->getLaunchArgument("clock-policy").value_or("native");
    if (choice == "native") return;
    if (choice != "fixed-base-60" && choice != "fixed-scheduler-240") {
        clockSelectionError = "Unsupported clock-policy launch argument";
        return;
    }
    // Clock interventions are an explicitly selected isolated-process experiment.
    // They never activate in the ordinary game, even if settings enable capture.
    if (_wcsicmp(executablePath().filename().c_str(), L"AXIOMSandbox.exe") != 0 ||
            !Loader::get()->getLaunchFlag("axiom-sandbox")) {
        clockSelectionError = "Fixed clock requires AXIOMSandbox.exe and axiom-sandbox launch guard";
        return;
    }
    clockPolicy = choice == "fixed-base-60" ? ClockPolicy::FixedBase60 : ClockPolicy::FixedScheduler240;
}

// Environment documents contain no floating point values. Sorting keys recursively
// matches Python's compact, sorted, ensure_ascii=False JSON for these documents.
std::string canonical(Json const& value) {
    if (value.isObject()) {
        std::map<std::string, Json const*> entries;
        for (auto const& entry : value) entries.emplace(entry.getKey().value(), &entry);
        std::string result = "{";
        bool first = true;
        for (auto const& [key, entry] : entries) {
            if (!first) result += ',';
            first = false;
            result += Json(key).dump(0) + ':' + canonical(*entry);
        }
        return result + '}';
    }
    if (value.isArray()) {
        std::string result = "[";
        bool first = true;
        for (auto const& entry : value) {
            if (!first) result += ',';
            first = false;
            result += canonical(entry);
        }
        return result + ']';
    }
    return value.dump(0);
}

class Sha256 {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
public:
    Sha256() {
        if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0)
            throw std::runtime_error("SHA256 provider unavailable");
        if (BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) < 0) {
            BCryptCloseAlgorithmProvider(algorithm, 0);
            algorithm = nullptr;
            throw std::runtime_error("SHA256 hash unavailable");
        }
    }
    ~Sha256() {
        if (hash) BCryptDestroyHash(hash);
        if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    }
    void update(char const* data, size_t size) {
        if (size > ULONG_MAX || BCryptHashData(hash, reinterpret_cast<PUCHAR>(const_cast<char*>(data)),
                static_cast<ULONG>(size), 0) < 0) throw std::runtime_error("SHA256 update failed");
    }
    std::string finish() {
        std::array<UCHAR, 32> digest{};
        if (BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) < 0)
            throw std::runtime_error("SHA256 finish failed");
        char const* hex = "0123456789abcdef";
        std::string result;
        for (auto byte : digest) { result += hex[byte >> 4]; result += hex[byte & 15]; }
        return result;
    }
};
std::string sha(std::string const& text) { Sha256 hash; hash.update(text.data(), text.size()); return hash.finish(); }
std::string fileSha(std::filesystem::path const& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("Cannot hash runtime binary");
    Sha256 hash;
    std::array<char, 65536> bytes{};
    while (stream) { stream.read(bytes.data(), bytes.size()); hash.update(bytes.data(), stream.gcount()); }
    if (!stream.eof()) throw std::runtime_error("Runtime binary read failed");
    return hash.finish();
}
std::filesystem::path executablePath() {
    std::array<wchar_t, 32768> buffer{};
    auto length = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    if (!length || length >= buffer.size()) throw std::runtime_error("Executable identity unavailable");
    return std::filesystem::path(std::wstring(buffer.data(), length));
}
Json environment() {
    if (!clockSelectionError.empty()) throw std::runtime_error(clockSelectionError);
    std::vector<Mod*> mods;
    for (auto mod : Loader::get()->getAllMods()) if (mod->isLoaded()) mods.push_back(mod);
    std::sort(mods.begin(), mods.end(), [](auto a, auto b) { return std::string(a->getID()) < std::string(b->getID()); });
    Json manifest = Json::array();
    for (auto mod : mods) {
        auto binary = mod->getBinaryPath();
        // The loader's internal Mod has no separate mod DLL. Hash its real loader DLL.
        if (mod->isInternal()) binary = executablePath().parent_path() / "Geode.dll";
        manifest.push(matjson::makeObject({{"id", std::string(mod->getID())},
            {"version", mod->getVersion().toNonVString()}, {"binary_sha256", fileSha(binary)}}));
    }
    return matjson::makeObject({
        {"game_executable_sha256", fileSha(executablePath())}, {"game_version", "2.2081"},
        {"geode_version", Loader::get()->getVersion().toNonVString()},
        {"adapter_binary_sha256", fileSha(Mod::get()->getBinaryPath())},
        {"platform", "windows-x64"}, {"mods", manifest}, {"configuration_complete", false},
        {"input_policy", Policy}, {"clocks", matjson::makeObject({
            {"unit", "processCommands_call_index"}, {"dt_unit", "seconds_as_passed_to_hook"},
            {"hardware_arrival", "unknown"}, {"render_cadence", "not_captured"},
            {"clock_policy", clockPolicy == ClockPolicy::Native ? "native" : clockPolicy == ClockPolicy::FixedBase60 ? "fixed-base-60" : "fixed-scheduler-240"},
            {"intervention_hook", clockPolicy == ClockPolicy::Native ? "none" : clockPolicy == ClockPolicy::FixedBase60 ? "GJBaseGameLayer::update" : "CCScheduler::update"},
            {"step_numerator", clockPolicy == ClockPolicy::Native ? 0 : 1},
            {"step_denominator", clockPolicy == ClockPolicy::FixedBase60 ? 60 : clockPolicy == ClockPolicy::FixedScheduler240 ? 240 : 1},
            {"intervention_scope", "guarded-sandbox-process"},
            {"update_unit", "GJBaseGameLayer::update_call_index"},
            {"scheduler_unit", "CCScheduler::update_call_index"}})}});
}
double checked(double value) {
    if (!std::isfinite(value)) throw std::runtime_error("Nonfinite selected engine state");
    return value;
}
Json playerState(PlayerObject* player) {
    if (!player) return nullptr;
    auto position = player->getPosition();
    char const* mode = player->m_isShip ? "ship" : player->m_isBird ? "ufo" : player->m_isBall ? "ball" :
        player->m_isDart ? "wave" : player->m_isRobot ? "robot" : player->m_isSpider ? "spider" :
        player->m_isSwing ? "swing" : "cube";
    return matjson::makeObject({{"x", checked(position.x)}, {"y", checked(position.y)},
        {"y_velocity", checked(player->m_yVelocity)}, {"rotation", checked(player->getRotation())},
        {"is_dead", player->m_isDead}, {"mode", mode}});
}
Json state(GJBaseGameLayer* layer) {
    return matjson::makeObject({{"player1", playerState(layer->m_player1)}, {"player2", playerState(layer->m_player2)}});
}
Json phase(GJBaseGameLayer* layer) {
    // Runs are owned only by PlayLayer. These are raw fields, not a gameplay/
    // collision or animation-completion classification inferred from position.
    auto play = static_cast<PlayLayer*>(layer);
    return matjson::makeObject({{"level_end_animation_started", layer->m_levelEndAnimationStarted},
        {"has_completed_level", play->m_hasCompletedLevel}});
}
Json membership(std::vector<size_t> const& stack) {
    return stack.empty() ? Json(nullptr) : Json(static_cast<uint64_t>(stack.back()));
}
struct ReplayEvent { uint64_t command; int player; int button; bool pressed; };
uint64_t integer(Json const& value, uint64_t minimum, uint64_t maximum) {
    if (!value.isExactlyInt() && !value.isExactlyUInt()) throw std::runtime_error("Replay integer required");
    auto result = value.asUInt();
    if (!result || result.unwrap() < minimum || result.unwrap() > maximum) throw std::runtime_error("Replay integer out of range");
    return result.unwrap();
}
std::string string(Json const& value) {
    if (!value.isString()) throw std::runtime_error("Replay string required");
    return value.asString().unwrap();
}
bool digest(std::string const& text) {
    return text.size() == 64 && std::all_of(text.begin(), text.end(), [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); });
}
// Bound parser recursion before calling the SDK parser, and reject duplicate
// object keys instead of allowing ambiguous replay plans to overwrite values.
void checkJsonSafety(std::string const& raw) {
    struct Container { bool object; bool expectsKey; std::set<std::string> keys; };
    std::vector<Container> stack;
    size_t tokens = 0;
    for (size_t i = 0; i < raw.size(); ++i) {
        char c = raw[i];
        if (c == '"') {
            if (++tokens > 50000) throw std::runtime_error("Replay JSON token budget exceeded");
            auto start = i++;
            for (; i < raw.size(); ++i) {
                if (raw[i] == '\\') { if (++i == raw.size()) throw std::runtime_error("Truncated JSON escape"); }
                else if (raw[i] == '"') break;
            }
            if (i == raw.size()) throw std::runtime_error("Unterminated JSON string");
            if (!stack.empty() && stack.back().object && stack.back().expectsKey) {
                auto parsed = Json::parse(std::string_view(raw).substr(start, i - start + 1));
                if (!parsed || !parsed.unwrap().isString()) throw std::runtime_error("Invalid JSON key");
                auto key = parsed.unwrap().asString().unwrap();
                if (!stack.back().keys.insert(key).second) throw std::runtime_error("Duplicate JSON object key");
                stack.back().expectsKey = false;
            }
        } else if (c == '{' || c == '[') {
            if (++tokens > 50000) throw std::runtime_error("Replay JSON token budget exceeded");
            if (stack.size() >= 64) throw std::runtime_error("Replay JSON nesting exceeds 64");
            stack.push_back({c == '{', c == '{', {}});
        } else if (c == '}' || c == ']') {
            if (stack.empty() || stack.back().object != (c == '}')) throw std::runtime_error("Unbalanced replay JSON");
            stack.pop_back();
        } else if (c == ',' && !stack.empty() && stack.back().object) stack.back().expectsKey = true;
        else if ((c >= '0' && c <= '9') || c == '-' || c == 't' || c == 'f' || c == 'n') {
            if (++tokens > 50000) throw std::runtime_error("Replay JSON token budget exceeded");
            while (i + 1 < raw.size() && raw[i + 1] != ',' && raw[i + 1] != '}' && raw[i + 1] != ']' &&
                raw[i + 1] != ' ' && raw[i + 1] != '\t' && raw[i + 1] != '\r' && raw[i + 1] != '\n') ++i;
        }
    }
    if (!stack.empty()) throw std::runtime_error("Unclosed replay JSON container");
}
void onlyKeys(Json const& value, std::set<std::string> const& keys) {
    if (!value.isObject()) throw std::runtime_error("Replay object required");
    for (auto const& entry : value) if (!keys.contains(entry.getKey().value())) throw std::runtime_error("Unknown replay field");
    if (value.size() != keys.size()) throw std::runtime_error("Missing replay field");
}
struct Run {
    GJBaseGameLayer* layer;
    Json document;
    uint64_t command = 0;
    uint64_t sequence = 0;
    uint64_t blockedSequence = 0;
    uint64_t dropped = 0;
    bool inCommand = false;
    bool injecting = false;
    bool replay = false;
    bool terminal = false;
    bool complete = true;
    Clock::time_point start = Clock::now();
    std::vector<size_t> updates;
    std::vector<size_t> schedulers;
    std::vector<ReplayEvent> planned;
    size_t next = 0;
    explicit Run(GJBaseGameLayer* owner) : layer(owner) { layer->retain(); }
    ~Run() { layer->release(); }
    Json& attempt() { return document["attempt"]; }
    void error(std::string const& message) {
        complete = false;
        document["integrity"]["errors"].push(message);
    }
    int64_t wallTime() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    }
    size_t enterUpdate(char const* stream, float original, float delivered, std::vector<size_t>& stack) {
        checked(original); checked(delivered);
        if (original < 0 || original > 60 || delivered < 0 || delivered > 60)
            throw std::runtime_error("Update dt outside 0..60 seconds");
        auto& records = attempt()[stream];
        if (records.size() >= MaxCommands) { ++dropped; throw std::runtime_error("Update trace limit reached"); }
        auto index = records.size();
        auto record = matjson::makeObject({{"sequence", static_cast<uint64_t>(index)},
            {"parent_sequence", membership(stack)}, {"original_dt_seconds", checked(original)},
            {"delivered_dt_seconds", checked(delivered)}, {"command_index_before", command},
            {"command_index_after", nullptr}, {"phase_before", phase(layer)}, {"phase_after", nullptr},
            {"wall_enter_ns", wallTime()}, {"wall_exit_ns", nullptr}});
        if (std::string_view(stream) == "updates") record["scheduler_sequence"] = membership(schedulers);
        records.push(record);
        stack.push_back(index);
        return index;
    }
    void exitUpdate(char const* stream, size_t index, std::vector<size_t>& stack) {
        auto& record = attempt()[stream][index];
        record["command_index_after"] = command;
        record["phase_after"] = phase(layer);
        record["wall_exit_ns"] = wallTime();
        if (stack.empty() || stack.back() != index) throw std::runtime_error("Update nesting mismatch");
        stack.pop_back();
    }
    size_t enterPhaseEvent() {
        auto& records = attempt()["phase_events"];
        if (records.size() >= 256) { ++dropped; throw std::runtime_error("Finish phase event limit reached"); }
        auto index = records.size();
        records.push(matjson::makeObject({{"sequence", static_cast<uint64_t>(index)},
            {"event", "PlayLayer::playEndAnimationToPos"}, {"command_index", command},
            {"update_sequence", membership(updates)}, {"scheduler_sequence", membership(schedulers)},
            {"phase_before", phase(layer)}, {"phase_after", nullptr},
            {"wall_enter_ns", wallTime()}, {"wall_exit_ns", nullptr}}));
        return index;
    }
    void exitPhaseEvent(size_t index) {
        auto& record = attempt()["phase_events"][index];
        record["phase_after"] = phase(layer);
        record["wall_exit_ns"] = wallTime();
    }
    void trace(float dt, bool half, bool last) {
        if (attempt()["trace"].size() >= MaxCommands + 1) { ++dropped; throw std::runtime_error("Command trace limit reached"); }
        attempt()["trace"].push(matjson::makeObject({{"command_index", command}, {"dt_seconds", checked(dt)},
            {"is_half_tick", half}, {"is_last_tick", last}, {"state", state(layer)},
            {"phase", phase(layer)}, {"update_sequence", membership(updates)},
            {"scheduler_sequence", membership(schedulers)}}));
    }
    void input(int button, int player, bool pressed, char const* phase, Json returned = nullptr) {
        if (terminal) return;
        if (button < 1 || button > 3) throw std::runtime_error("Unsupported native button");
        if (attempt()["inputs"].size() + attempt()["blocked_inputs"].size() >= MaxInputs) {
            ++dropped; throw std::runtime_error("Combined input trace limit reached");
        }
        auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
        attempt()["inputs"].push(matjson::makeObject({{"sequence", sequence++}, {"command_index", command},
            {"player", player}, {"button", button}, {"pressed", pressed}, {"phase", phase},
            {"source", replay ? "replay" : "observed"}, {"native_return", returned}, {"wall_time_ns", elapsed}}));
    }
    void blockedInput(int button, int player, bool pressed) {
        if (terminal) return;
        if (attempt()["inputs"].size() + attempt()["blocked_inputs"].size() >= MaxInputs) {
            ++dropped; throw std::runtime_error("Combined input trace limit reached");
        }
        auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
        // Keep raw button values: a suppressed native request is diagnostic data,
        // not one of the validated, forwarded replay plan events.
        attempt()["blocked_inputs"].push(matjson::makeObject({{"sequence", blockedSequence++},
            {"command_index", command}, {"player", player}, {"button", button}, {"pressed", pressed},
            {"source", "unknown"}, {"wall_time_ns", elapsed}}));
    }
    void finish(char const* outcome, char const* event) {
        if (terminal) return;
        terminal = true;
        attempt()["terminal"] = matjson::makeObject({{"outcome", outcome}, {"event", event},
            {"command_index", command}, {"wall_elapsed_seconds", std::chrono::duration<double>(Clock::now() - start).count()},
            {"state", state(layer)}, {"phase", phase(layer)}, {"update_sequence", membership(updates)},
            {"scheduler_sequence", membership(schedulers)}});
    }
    void loadReplay(std::string const& levelHash, std::string const& envHash) {
        std::ifstream stream(Mod::get()->getSaveDir() / "replay.json", std::ios::binary);
        if (!stream) throw std::runtime_error("Cannot read replay.json");
        std::string raw(MaxBytes + 1, '\0');
        stream.read(raw.data(), raw.size());
        raw.resize(stream.gcount());
        if (raw.size() > MaxBytes || (!stream.eof() && !stream)) throw std::runtime_error("Replay exceeds limit or read failed");
        checkJsonSafety(raw);
        auto parsed = Json::parse(raw);
        if (!parsed) throw std::runtime_error("Invalid replay JSON");
        auto data = parsed.unwrap();
        onlyKeys(data, {"schema_version", "kind", "clock", "level_sha256", "environment_sha256", "inputs"});
        if (!data.isObject() || integer(data["schema_version"], 1, 1) != 1 || string(data["kind"]) != "native_replay" ||
            string(data["clock"]) != "processCommands_call_index") throw std::runtime_error("Unsupported replay format/clock");
        auto target = string(data["level_sha256"]);
        if (!digest(target) || target != levelHash) throw std::runtime_error("Replay level hash mismatch");
        auto expectedEnvironment = string(data["environment_sha256"]);
        if (!digest(expectedEnvironment) || expectedEnvironment != envHash) throw std::runtime_error("Replay environment hash mismatch");
        if (!data["inputs"].isArray() || data["inputs"].size() > 4000) throw std::runtime_error("Replay event limit or invalid inputs");
        uint64_t previous = 0;
        for (auto const& entry : data["inputs"]) {
            onlyKeys(entry, {"command_index", "player", "button", "pressed"});
            if (!entry.isObject() || !entry["pressed"].isBool()) throw std::runtime_error("Invalid replay event");
            auto commandIndex = integer(entry["command_index"], 1, MaxCommands);
            if (commandIndex < previous) throw std::runtime_error("Replay events must be ordered");
            previous = commandIndex;
            planned.push_back({commandIndex, static_cast<int>(integer(entry["player"], 1, 2)),
                static_cast<int>(integer(entry["button"], 1, 3)), entry["pressed"].asBool().unwrap()});
        }
        attempt()["replay_sha256"] = sha(raw);
        attempt()["planned_inputs"] = data["inputs"];
    }
};
std::unique_ptr<Run> active;
GJBaseGameLayer* initializing = nullptr;
bool initCommandSeen = false;
GJBaseGameLayer* resetting = nullptr;
bool resetCommandSeen = false;
PlayLayer* pendingStart = nullptr;
bool pendingStartUncertain = false;
uint64_t runId = 0;
bool option(char const* setting, char const* flag) { return Mod::get()->getSettingValue<bool>(setting) || Mod::get()->getLaunchFlag(flag); }

void exportRun() {
    if (!active || !active->terminal || active->inCommand || updateDepth || schedulerDepth || phaseDepth) return;
    auto run = std::move(active);
    if (auto indicator = run->layer->getChildByID("axiom-capture-indicator")) indicator->removeFromParent();
    run->document["integrity"]["recording_complete"] = run->complete;
    run->document["integrity"]["dropped_records"] = run->dropped;
    try {
        auto text = run->document.dump(2);
        if (text.size() > MaxBytes) throw std::runtime_error("Capture export exceeds 16 MiB");
        auto folder = Mod::get()->getSaveDir() / "captures";
        std::filesystem::create_directories(folder);
        auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
        auto filename = folder / (std::to_string(now) + "-" + std::to_string(runId) + ".json");
        auto temporary = filename; temporary += ".tmp";
        std::ofstream stream(temporary, std::ios::binary | std::ios::trunc);
        if (!stream) throw std::runtime_error("Capture output could not be opened");
        stream.write(text.data(), text.size()); stream.close();
        if (!stream) throw std::runtime_error("Capture output write failed");
        std::filesystem::rename(temporary, filename);
        log::info("AXIOM native capture exported locally: {}", filename.string());
    } catch (std::exception const& error) { log::error("AXIOM capture export failed; no complete artifact: {}", error.what()); }
}
void fail(std::string const& message) {
    log::error("AXIOM capture error: {}", message);
    if (!active) return;
    active->error(message);
    try { active->finish("error", "AXIOM::error"); }
    catch (...) { active.reset(); return; }
    exportRun();
}
void stop(char const* outcome, char const* event) {
    if (!active) return;
    try { active->finish(outcome, event); exportRun(); } catch (std::exception const& error) { fail(error.what()); }
}
void begin(PlayLayer* layer, bool uncertainStart = false) {
    if (active && (active->inCommand || updateDepth || schedulerDepth || phaseDepth)) {
        stop("aborted", "PlayLayer::resetLevel");
        pendingStart = layer;
        pendingStartUncertain = true;
        return;
    }
    if (active) stop("aborted", "PlayLayer::resetLevel");
    if (!option("capture-enabled", "capture") && !option("replay-enabled", "replay")) return;
    if (Loader::get()->getVersion() != VersionInfo(5, 8, 2)) { log::error("AXIOM capture requires Geode 5.8.2"); return; }
    try {
        auto env = environment();
        auto envHash = sha(canonical(env));
        auto levelRaw = std::string(layer->m_level->m_levelString);
        if (levelRaw.empty() || levelRaw.size() > MaxBytes) throw std::runtime_error("Raw native level string missing or oversized");
        auto levelHash = sha(levelRaw);
        auto startKind = uncertainStart ? "unknown" : layer->m_isPracticeMode ? "practice" : layer->m_startPosObject ? "start_position" : "level_start";
        active = std::make_unique<Run>(layer);
        active->replay = option("replay-enabled", "replay");
        active->document = matjson::makeObject({
            {"schema_version", 2}, {"kind", "native_capture"},
            {"provenance", matjson::makeObject({{"origin", "native-engine-capture"}, {"independently_verified", false}, {"state_completeness", "selected_fields_only"}})},
            {"collector", matjson::makeObject({{"id", "axiom.native-capture"}, {"version", "0.1.0"},
                {"source_commit", AXIOM_SOURCE_COMMIT}, {"source_tree_sha256", AXIOM_SOURCE_TREE_SHA256},
                {"sdk_commit", AXIOM_SDK_COMMIT}, {"bindings_commit", AXIOM_BINDINGS_COMMIT}})},
            {"environment", env}, {"environment_sha256", envHash},
            {"challenge", matjson::makeObject({{"id", "native-" + levelHash.substr(0, 16)}, {"level_sha256", levelHash},
                {"game_version", "2.2081"}, {"physics_version", "native-2.2081-uncharacterized"},
                {"input_policy", Policy}, {"environment_id", envHash}})},
            {"state_fields", Json(std::vector<Json>{"x", "y", "y_velocity", "rotation", "is_dead", "mode"})},
            {"integrity", matjson::makeObject({{"recording_complete", true}, {"dropped_records", 0}, {"errors", Json::array()}})},
            {"attempt", matjson::makeObject({{"id", std::to_string(std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count()) + "-" + std::to_string(GetCurrentProcessId()) + "-" + std::to_string(++runId)}, {"start_kind", startKind},
                {"input_source", active->replay ? "replay" : "unknown"}, {"replay_sha256", nullptr},
                {"planned_inputs", Json::array()}, {"inputs", Json::array()}, {"blocked_inputs", Json::array()},
                {"trace", Json::array()}, {"updates", Json::array()}, {"scheduler_updates", Json::array()},
                {"phase_events", Json::array()}, {"terminal", nullptr}})},
            {"limitations", Json(std::vector<Json>{"Selected state is not a complete resumable snapshot.",
                "The processCommands call clock is not a demonstrated physics or hardware input clock.",
                "Mod settings and all game configuration are not yet exhaustively captured.",
                "No physical input provenance or human difficulty calibration is established.",
                "Replay suppresses non-injector handleButton requests of unknown origin and retains blocked_inputs diagnostics.",
                "Direct PlayerObject push/release calls bypassing handleButton are not controlled by replay channel ownership.",
                "The update and scheduler hooks are not render callbacks or a complete engine clock.",
                "A callback already running at capture start has no invented paired row; its membership is null.",
                "Fixed clocks are isolated-process interventions; equivalence to ordinary gameplay is unverified.",
                "Original update dt and wall timing are cadence diagnostics; delivered dt and call grouping are retained."})}});
        active->trace(0, false, false);
        if (layer->m_isPlatformer) throw std::runtime_error("M1 supports classic levels only");
        if (active->replay) {
            if (std::string(startKind) != "level_start") throw std::runtime_error("Replay requires a true full start");
            active->loadReplay(levelHash, envHash);
        }
        log::info("AXIOM local {} active; command-call clock, selected-state only", active->replay ? "replay" : "capture");
        if (auto previous = layer->getChildByID("axiom-capture-indicator")) previous->removeFromParent();
        auto indicator = CCLabelBMFont::create(active->replay ? "AXIOM REPLAY" : "AXIOM CAPTURE", "bigFont.fnt");
        if (indicator) { indicator->setScale(0.25f); indicator->setPosition({80, 20}); indicator->setID("axiom-capture-indicator"); layer->addChild(indicator, 10000); }
    } catch (std::exception const& error) { fail(error.what()); }
}
void flushPending() {
    exportRun();
    if (pendingStart && !updateDepth && !schedulerDepth && !phaseDepth && (!active || !active->inCommand)) {
        auto layer = pendingStart;
        auto uncertain = pendingStartUncertain;
        pendingStart = nullptr;
        begin(layer, uncertain);
    }
}
} // namespace axiom

class $modify(AxiomPlayLayer, PlayLayer) {
    bool init(GJGameLevel* level, bool useReplay, bool dontCreateObjects) {
        axiom::initializing = this; axiom::initCommandSeen = false;
        auto result = PlayLayer::init(level, useReplay, dontCreateObjects);
        axiom::initializing = nullptr;
        if (result) axiom::begin(this, axiom::initCommandSeen || useReplay || dontCreateObjects);
        return result;
    }
    void resetLevel() {
        if (axiom::active && axiom::active->layer == this) axiom::stop("aborted", "PlayLayer::resetLevel");
        axiom::resetting = this; axiom::resetCommandSeen = false;
        PlayLayer::resetLevel();
        axiom::resetting = nullptr;
        if (axiom::initializing != this) {
            if (axiom::active && (axiom::active->inCommand || axiom::updateDepth || axiom::schedulerDepth || axiom::phaseDepth)) {
                axiom::pendingStart = this;
                // The enclosing command can continue updating after reset.
                axiom::pendingStartUncertain = true;
            } else axiom::begin(this, axiom::resetCommandSeen);
        }
    }
    void playEndAnimationToPos(CCPoint position) {
        ++axiom::phaseDepth;
        auto run = axiom::active.get();
        std::optional<size_t> row;
        if (run && run->layer == this && !run->terminal) {
            try { row = run->enterPhaseEvent(); }
            catch (std::exception const& error) { axiom::fail(error.what()); }
        }
        PlayLayer::playEndAnimationToPos(position);
        if (row && axiom::active.get() == run) {
            try { run->exitPhaseEvent(*row); }
            catch (std::exception const& error) { axiom::fail(error.what()); }
        }
        --axiom::phaseDepth;
        axiom::flushPending();
    }
    void destroyPlayer(PlayerObject* player, GameObject* object) {
        PlayLayer::destroyPlayer(player, object);
        if (axiom::active && axiom::active->layer == this && player && player->m_isDead)
            axiom::stop("died", "PlayLayer::destroyPlayer");
    }
    void levelComplete() {
        PlayLayer::levelComplete();
        if (axiom::active && axiom::active->layer == this) axiom::stop("completed", "PlayLayer::levelComplete");
    }
    void pauseGame(bool unfocused) {
        if (axiom::active && axiom::active->layer == this) axiom::stop("aborted", "PlayLayer::pauseGame");
        PlayLayer::pauseGame(unfocused);
    }
    void onQuit() {
        if (axiom::active && axiom::active->layer == this) axiom::stop("aborted", "PlayLayer::onQuit");
        PlayLayer::onQuit();
    }
};
class $modify(AxiomBaseLayer, GJBaseGameLayer) {
    void update(float dt) {
        ++axiom::updateDepth;
        auto run = axiom::active.get();
        std::optional<size_t> row;
        float delivered = dt;
        // PlayLayer inherits this native update in 2.2081. Do not alter editor
        // updates, and do not replace getModifiedDelta or expected-tick logic.
        if (axiom::clockPolicy == axiom::ClockPolicy::FixedBase60 &&
                (static_cast<GJBaseGameLayer*>(PlayLayer::get()) == this || axiom::initializing == this))
            delivered = 1.0f / 60.0f;
        if (run && run->layer == this && !run->terminal) {
            try { row = run->enterUpdate("updates", dt, delivered, run->updates); }
            catch (std::exception const& error) { axiom::fail(error.what()); }
        }
        GJBaseGameLayer::update(delivered);
        if (row && axiom::active.get() == run) {
            try { run->exitUpdate("updates", *row, run->updates); }
            catch (std::exception const& error) {
                if (!run->updates.empty() && run->updates.back() == *row) run->updates.pop_back();
                axiom::fail(error.what());
            }
        }
        --axiom::updateDepth;
        axiom::flushPending();
    }
    void handleButton(bool down, int button, bool isPlayer1) {
        auto run = axiom::active.get();
        if (run && run->layer == this && !run->terminal) {
            if (run->replay) {
                // A one-shot permit admits only the scheduled wrapper entry.
                // Native calls nested inside the original handler cannot reuse it.
                bool scheduled = run->injecting;
                run->injecting = false;
                if (!scheduled) {
                    try { run->blockedInput(button, isPlayer1 ? 1 : 2, down); }
                    catch (std::exception const& error) { axiom::fail(error.what()); }
                    return; // Deliberately do not forward any non-injector request.
                }
            }
            try { run->input(button, isPlayer1 ? 1 : 2, down, "requested"); }
            catch (std::exception const& error) { axiom::fail(error.what()); }
        }
        GJBaseGameLayer::handleButton(down, button, isPlayer1);
    }
    void processCommands(float dt, bool isHalfTick, bool isLastTick) {
        if (axiom::initializing == this) axiom::initCommandSeen = true;
        if (axiom::resetting == this) axiom::resetCommandSeen = true;
        auto run = axiom::active.get();
        if (!run || run->layer != this || run->terminal) { GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick); return; }
        if ((run->replay && !axiom::option("replay-enabled", "replay")) ||
            (!run->replay && !axiom::option("capture-enabled", "capture"))) {
            axiom::stop("aborted", "AXIOM::disabled");
            GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
            return;
        }
        run->inCommand = true;
        ++run->command;
        try {
            if (run->command > axiom::MaxCommands) throw std::runtime_error("Command trace limit reached");
            axiom::checked(dt);
            if (dt < 0 || dt > 60) throw std::runtime_error("Command dt outside 0..60 seconds");
            if (run->replay) {
                while (run->next < run->planned.size() && run->planned[run->next].command == run->command) {
                    auto event = run->planned[run->next++];
                    run->injecting = true;
                    // Enter through the native binding, so Geode establishes the
                    // handleButton hook context before our one-shot permit is
                    // consumed. Calling this->handleButton invokes the modified
                    // wrapper directly; its base call then re-enters that hook.
                    GJBaseGameLayer::handleButton(event.pressed, event.button, event.player == 1);
                    run->injecting = false;
                }
            }
        } catch (std::exception const& error) { axiom::fail(error.what()); }
        GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
        if (axiom::active.get() == run) {
            try { run->trace(dt, isHalfTick, isLastTick); }
            catch (std::exception const& error) { axiom::fail(error.what()); }
            if (axiom::active.get() == run) { run->inCommand = false; axiom::exportRun(); }
        }
        axiom::flushPending();
    }
};
class $modify(AxiomScheduler, CCScheduler) {
    void update(float dt) {
        ++axiom::schedulerDepth;
        auto run = axiom::active.get();
        std::optional<size_t> row;
        auto delivered = axiom::clockPolicy == axiom::ClockPolicy::FixedScheduler240 ? 1.0f / 240.0f : dt;
        if (run && !run->terminal) {
            try { row = run->enterUpdate("scheduler_updates", dt, delivered, run->schedulers); }
            catch (std::exception const& error) { axiom::fail(error.what()); }
        }
        // Exactly one original call per actual scheduler callback. Cocos may
        // scale its argument internally; we neither change its time scale nor
        // separately advance actions, repeat frames or add a timestep carry.
        CCScheduler::update(delivered);
        if (row && axiom::active.get() == run) {
            try { run->exitUpdate("scheduler_updates", *row, run->schedulers); }
            catch (std::exception const& error) {
                if (!run->schedulers.empty() && run->schedulers.back() == *row) run->schedulers.pop_back();
                axiom::fail(error.what());
            }
        }
        --axiom::schedulerDepth;
        axiom::flushPending();
    }
};
class $modify(AxiomPlayer, PlayerObject) {
    bool pushButton(PlayerButton button) {
        auto result = PlayerObject::pushButton(button);
        record(button, true, "push", result);
        return result;
    }
    bool releaseButton(PlayerButton button) {
        auto result = PlayerObject::releaseButton(button);
        record(button, false, "release", result);
        return result;
    }
    void record(PlayerButton button, bool pressed, char const* phase, bool result) {
        auto run = axiom::active.get();
        if (!run || run->terminal) return;
        int player = this == run->layer->m_player1 ? 1 : this == run->layer->m_player2 ? 2 : 0;
        if (!player) return;
        try { run->input(static_cast<int>(button), player, pressed, phase, result); }
        catch (std::exception const& error) { axiom::fail(error.what()); }
    }
};
$on_mod(Loaded) {
    try { axiom::selectClockPolicy(); }
    catch (std::exception const& error) { axiom::clockSelectionError = error.what(); }
    if (!axiom::clockSelectionError.empty()) log::error("AXIOM clock experiment refused: {}", axiom::clockSelectionError);
    log::info("AXIOM M1 adapter loaded; local capture/replay disabled by default; selected-state only; SDK {} bindings {}", AXIOM_SDK_COMMIT, AXIOM_BINDINGS_COMMIT);
}
