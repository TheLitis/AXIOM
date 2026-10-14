// Software-only fault checks execute the production observer implementation.
// Win32 window/input APIs and Geode window/clock functions are fake. The real
// matjson library serializes snapshots. No GD process, real HWND, raw packet,
// keyboard action, device origin or live input qualification is involved.
#include "stubs/Windows.h"
#include <atomic>
#include <condition_variable>
#include <cstring>
#include <functional>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>

struct FakeWindow {
    bool valid = true;
    DWORD thread = 11, process = 33;
    WNDPROC procedure = nullptr;
};

#include "../../src/WindowsInputObserver.cpp"

namespace fake {
using Json = matjson::Value;
namespace observer = axiom::windowsinput;
thread_local DWORD thread = 11, lastError = 0;
std::mutex apiMutex;
FakeWindow mainWindow, rawWindow;
HWND foreground = &mainWindow;
alignas(void*) std::array<std::byte, 0x378> glfw{};
cocos2d::CCEGLView view;
std::atomic<double> timestamp = 10;
std::atomic<size_t> forwards = 0, rawReads = 0, scopeEnters = 0, scopeLeaves = 0;
std::atomic<WPARAM> observedWparam = 0;
std::atomic<LPARAM> observedLparam = 0;
std::atomic<DWORD> predecessorIncomingError = 0;
size_t setCalls = 0;
enum class SetFault { Fail, ChangedReturn, ZeroSuccess };
std::map<size_t, SetFault> setFaults;
bool moduleMismatch = false, readFailure = false, truncated = false, nestedFocus = false;
bool noRawWindow = false, releaseAtDetach = false;
std::mutex gateMutex;
std::condition_variable gate;
bool blockForward = false, forwarding = false, releaseForward = false;
constexpr LRESULT returned = -0x123456789LL;
constexpr DWORD returnedError = 19;
size_t totalChecks = 0;

void require(bool condition, char const* text) {
    ++totalChecks;
    if (!condition) throw std::runtime_error(text);
}
LRESULT other(HWND, UINT, WPARAM, LPARAM) { return 7; }
LRESULT original(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    ++forwards;
    observedWparam = wparam; observedLparam = lparam;
    predecessorIncomingError = lastError;
    if (window == &rawWindow && message == WM_INPUT) {
        geode::utils::getInputTimestamp();
        std::unique_lock lock(gateMutex);
        if (blockForward) {
            forwarding = true; gate.notify_all();
            gate.wait(lock, [] { return releaseForward; });
        }
    }
    if (nestedFocus && window == &mainWindow && message == WM_SETFOCUS)
        window->procedure(window, WM_KILLFOCUS, 0, 0);
    if (message == WM_NCDESTROY) {
        std::lock_guard lock(apiMutex);
        window->valid = false;
    }
    lastError = returnedError;
    return returned;
}
void reset() {
    // All test worker threads have joined before fixtures are reset.
    std::atomic_store(&observer::current, observer::SessionPtr{});
    observer::hooks.clear();
    observer::mainHookWindow = observer::rawHookWindow = nullptr;
    observer::mainPrevious = observer::rawPrevious = nullptr;
    observer::setMainScopes([] { ++scopeEnters; }, [] { ++scopeLeaves; });
    mainWindow = {true, 11, 33, original};
    rawWindow = {true, 22, 33, original};
    foreground = &mainWindow;
    HWND main = &mainWindow;
    std::memcpy(glfw.data() + 0x370, &main, sizeof(main));
    view.m_pMainWindow = glfw.data();
    timestamp = 10; forwards = 0; rawReads = 0; scopeEnters = scopeLeaves = 0;
    observedWparam = 0; observedLparam = 0; predecessorIncomingError = 0;
    setCalls = 0; setFaults.clear();
    moduleMismatch = readFailure = truncated = nestedFocus = noRawWindow = releaseAtDetach = false;
    blockForward = forwarding = releaseForward = false;
    thread = 11; lastError = 0;
}
observer::SessionPtr begin() {
    auto session = observer::begin(std::chrono::steady_clock::now());
    require(session->accepting.load(), "fixture failed to attach before fault injection");
    return session;
}
Json snapshot(observer::SessionPtr const& session) { return observer::snapshot(session, Json::array()); }
bool errors(Json const& value) { return value["integrity"]["errors"].size() != 0; }
bool errorContains(Json const& value, std::string const& fragment) {
    for (auto const& row : value["integrity"]["errors"])
        if (row.asString().unwrap().find(fragment) != std::string::npos) return true;
    return false;
}
void declaredAttachments(Json const& value) {
    require(value["windows"].size() == 2, "lost main/raw declarations");
    require(value["windows"][0]["installed"].asBool().unwrap(), "successful main attachment history changed");
    require(value["windows"][1]["installed"].asBool().unwrap(), "successful raw attachment history changed");
}
RAWINPUT keyboard() {
    RAWINPUT packet{};
    packet.header.dwType = RIM_TYPEKEYBOARD; packet.header.dwSize = sizeof(packet);
    packet.data.keyboard.VKey = 32; packet.data.keyboard.MakeCode = 57;
    packet.data.keyboard.Message = 256;
    return packet;
}
LRESULT dispatchRaw(RAWINPUT& packet, WPARAM wparam = 0) {
    thread = 22;
    return rawWindow.procedure(&rawWindow, WM_INPUT, wparam, reinterpret_cast<LPARAM>(&packet));
}

void normalForwarding() {
    auto session = begin(); auto packet = keyboard();
    lastError = 77;
    WPARAM wparam = std::numeric_limits<WPARAM>::max();
    auto result = dispatchRaw(packet, wparam);
    require(result == returned && forwards == 1, "predecessor return or exact single call changed");
    require(observedWparam == wparam && observedLparam == reinterpret_cast<LPARAM>(&packet), "message arguments changed");
    require(predecessorIncomingError == 77 && lastError == returnedError, "predecessor LastError behavior changed");
    auto value = snapshot(session);
    declaredAttachments(value);
    require(!errors(value) && value["messages"].size() == 1, "normal observation incomplete");
    require(value["messages"][0]["native_return"].asInt().unwrap() == returned, "snapshot lost signed native return");
    require(value["messages"][0]["raw_input"]["vkey"].asUInt().unwrap() == 32, "snapshot lost raw key namespace");
    require(rawWindow.procedure == original && mainWindow.procedure == original, "normal snapshot failed to restore procedures");
    require(!session->accepting.load() && !observer::onMainThread(), "snapshot left session active");
}
void rawDestruction() {
    auto session = begin(); thread = 22;
    auto result = rawWindow.procedure(&rawWindow, WM_NCDESTROY, 0, -1);
    require(result == returned && forwards == 1, "destroy predecessor behavior changed");
    auto value = snapshot(session);
    declaredAttachments(value);
    require(errors(value), "active raw-window destruction did not invalidate coverage");
    require(errorContains(value, "destroyed"), "destruction reason missing");
    require(value["messages"].size() == 0, "raw destruction invented a schema-7 WM_INPUT row");
    require(value["integrity"]["pending_callbacks_at_snapshot"].asUInt().unwrap() == 0, "raw lifecycle callback barrier leaked");
}
void mainDestruction() {
    auto session = begin();
    mainWindow.procedure(&mainWindow, WM_NCDESTROY, 0, 0);
    auto value = snapshot(session);
    require(errors(value) && errorContains(value, "destroyed"), "active main-window destruction did not invalidate coverage");
    require(value["messages"].size() == 1 && value["messages"][0]["message"].asUInt().unwrap() == WM_NCDESTROY,
        "main lifecycle row not preserved");
    require(scopeEnters == 1 && scopeLeaves == 1, "main lifecycle export scope unbalanced");
    declaredAttachments(value);
}
void missingWindow() {
    auto session = begin(); rawWindow.valid = false;
    auto value = snapshot(session);
    require(errors(value), "missing raw HWND at snapshot did not invalidate coverage");
    declaredAttachments(value);
}
void missingRegistry() {
    auto session = begin(); observer::hooks.erase(&rawWindow);
    auto value = snapshot(session);
    require(errors(value), "missing retained hook at snapshot did not invalidate coverage");
    declaredAttachments(value);
}
void uninstalledRegistry() {
    auto session = begin(); observer::hooks.at(&rawWindow).installed = false;
    auto value = snapshot(session);
    require(errors(value), "lost retained installed state did not invalidate coverage");
    declaredAttachments(value);
}
void replacedHook() {
    auto session = begin(); rawWindow.procedure = other;
    auto value = snapshot(session);
    require(errors(value), "replacement above observer accepted as complete");
    require(rawWindow.procedure == other, "snapshot overwrote another procedure owner");
    declaredAttachments(value);
}
void retainedHookReuse() {
    auto previous = begin(); observer::stop(previous);
    auto settersBefore = setCalls;
    auto session = begin();
    require(setCalls == settersBefore, "retained valid observer was needlessly reattached");
    auto value = snapshot(session);
    require(!errors(value), "retained valid observer reuse rejected");
    declaredAttachments(value);
    require(mainWindow.procedure == original && rawWindow.procedure == original, "retained observer reuse lost restoration");
}
void invalidRetainedHook(bool lostInstalledState) {
    auto previous = begin(); observer::stop(previous);
    auto& hook = observer::hooks.at(&rawWindow);
    if (lostInstalledState) hook.installed = false;
    else hook.thread = 999;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "invalid retained observer ownership accepted");
    require(errorContains(value, "ownership"), "invalid retained ownership reason missing");
}
void failedAttach() {
    setFaults[2] = SetFault::Fail;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "failed attachment activated complete capture");
    require(mainWindow.procedure == original && rawWindow.procedure == original, "partial attachment not restored");
    require(!value["windows"][1]["installed"].asBool().unwrap(), "failed raw attachment declared successful");
}
void changedPredecessor() {
    setFaults[2] = SetFault::ChangedReturn;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "changed predecessor accepted");
    require(mainWindow.procedure == original && rawWindow.procedure == other, "rollback changed actual returned predecessor");
}
void rollbackFailure() {
    setFaults[2] = SetFault::ChangedReturn; setFaults[3] = SetFault::Fail;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "failed rollback accepted");
    require(errorContains(value, "rollback failed"), "failed rollback reason missing");
    require(mainWindow.procedure == original && rawWindow.procedure == other, "retained partial hook cleanup failed");
}
void anomalousZeroPredecessor() {
    setFaults[2] = SetFault::ZeroSuccess;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "anomalous zero predecessor accepted");
    require(mainWindow.procedure == original && rawWindow.procedure == original, "anomalous zero chain rollback failed");
}
void wrongRawModule() {
    moduleMismatch = true;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "unverified raw predecessor accepted");
    require(mainWindow.procedure == original && rawWindow.procedure == original, "module refusal changed window procedures");
}
void missingRawWindow() {
    noRawWindow = true;
    auto session = observer::begin(std::chrono::steady_clock::now());
    auto value = snapshot(session);
    require(!session->accepting.load() && errors(value), "missing process-owned raw window accepted");
    require(mainWindow.procedure == original, "main attachment remained after raw lookup failure");
}
void rawReadError() {
    auto session = begin(); auto packet = keyboard(); readFailure = true;
    lastError = 77; dispatchRaw(packet);
    require(forwards == 1 && predecessorIncomingError == 77 && lastError == returnedError, "packet-read error altered forwarding");
    auto value = snapshot(session);
    require(errors(value) && value["integrity"]["read_error_count"].asUInt().unwrap() == 1, "packet-read failure not retained");
    require(value["messages"].size() == 0, "failed raw read fabricated a packet row");
}
void truncatedPacket() {
    auto session = begin(); auto packet = keyboard(); truncated = true; dispatchRaw(packet);
    auto value = snapshot(session);
    require(forwards == 1 && errors(value) && value["integrity"]["read_error_count"].asUInt().unwrap() == 1,
        "truncated packet altered passthrough or was accepted");
}
void skippedScope() {
    auto session = begin(); auto packet = keyboard(); foreground = nullptr; dispatchRaw(packet);
    foreground = &mainWindow;
    packet.header.dwType = RIM_TYPEMOUSE; packet.data.mouse.usButtonFlags = 0; dispatchRaw(packet);
    packet.data.mouse.usButtonFlags = 0x400; dispatchRaw(packet);
    auto value = snapshot(session);
    require(!errors(value) && forwards == 3 && rawReads == 2, "scope exclusion changed native dispatch");
    require(value["messages"].size() == 0, "out-of-scope input retained as foreground packet");
    for (auto key : {"background_raw_count", "mouse_motion_count", "unsupported_raw_count"})
        require(value["skipped"][key].asUInt().unwrap() == 1, "scope exclusion not counted");
}
void nestedLifecycle() {
    auto session = begin(); nestedFocus = true;
    mainWindow.procedure(&mainWindow, WM_SETFOCUS, 0, 0);
    auto value = snapshot(session);
    require(!errors(value) && forwards == 2 && value["messages"].size() == 2, "nested lifecycle forwarding incomplete");
    require(value["messages"][1]["parent_sequence"].asUInt().unwrap() == 0, "per-thread parent lost");
    require(scopeEnters == 2 && scopeLeaves == 2, "nested main callback export scope unbalanced");
}
void boundedMessages() {
    auto session = begin(); auto packet = keyboard();
    for (size_t i = 0; i < observer::MaxMessages + 2; ++i) dispatchRaw(packet);
    auto value = snapshot(session);
    require(forwards == observer::MaxMessages + 2, "overflow consumed native messages");
    require(errors(value) && value["messages"].size() == observer::MaxMessages, "message bound silently truncated complete evidence");
    require(value["integrity"]["overflow_count"].asUInt().unwrap() == 2, "overflow count not exact");
}
void blockedDrain(bool finishesDuringDetach) {
    auto session = begin(); auto packet = keyboard(); blockForward = true;
    std::thread worker([&] { dispatchRaw(packet); });
    {
        std::unique_lock lock(gateMutex);
        if (!gate.wait_for(lock, std::chrono::seconds(2), [] { return forwarding; })) {
            releaseForward = true; gate.notify_all(); lock.unlock(); worker.join();
            throw std::runtime_error("fake callback did not reach predecessor gate");
        }
    }
    releaseAtDetach = finishesDuringDetach;
    auto value = snapshot(session);
    { std::lock_guard lock(gateMutex); releaseForward = true; gate.notify_all(); }
    worker.join();
    auto pending = value["integrity"]["pending_callbacks_at_snapshot"].asUInt().unwrap();
    if (finishesDuringDetach) {
        require(!errors(value) && pending == 0, "finished raw callback did not drain before snapshot");
        require(!value["messages"][0]["wall_exit_ns"].isNull(), "finished callback exit missing");
    } else {
        require(errors(value) && pending == 1, "bounded drain fabricated a completed raw callback");
        require(value["messages"][0]["wall_exit_ns"].isNull() && value["messages"][0]["native_return"].isNull(),
            "timed-out callback fabricated exit or native return");
        require(value["messages"][0]["wall_exit_ns"].isNull(), "later callback mutated the frozen snapshot");
    }
    require(forwards == 1 && session->inFlight == 0, "admitted raw callback barrier leaked after actual return");
    declaredAttachments(value);
}
}

cocos2d::CCEGLView* cocos2d::CCEGLView::get() { return &fake::view; }
double geode::utils::getInputTimestamp() { return fake::timestamp.fetch_add(0.01); }
DWORD GetLastError() { return fake::lastError; }
void SetLastError(DWORD error) { fake::lastError = error; }
DWORD GetCurrentProcessId() { return 33; }
DWORD GetCurrentThreadId() { return fake::thread; }
UINT GetRawInputData(HRAWINPUT handle, UINT, void* bytes, UINT* size, UINT) {
    ++fake::rawReads; fake::lastError = 500;
    if (fake::readFailure) return static_cast<UINT>(-1);
    auto length = fake::truncated ? sizeof(RAWINPUTHEADER) : sizeof(RAWINPUT);
    std::memcpy(bytes, handle, length); *size = static_cast<UINT>(length);
    return *size;
}
DWORD GetWindowThreadProcessId(HWND window, DWORD* process) {
    if (!window) { if (process) *process = 0; return 0; }
    if (process) *process = window->process;
    return window->thread;
}
bool IsWindow(HWND window) { std::lock_guard lock(fake::apiMutex); return window && window->valid; }
HWND GetForegroundWindow() { std::lock_guard lock(fake::apiMutex); return fake::foreground; }
LONG_PTR GetWindowLongPtrW(HWND window, int) { std::lock_guard lock(fake::apiMutex); return reinterpret_cast<LONG_PTR>(window->procedure); }
LONG_PTR SetWindowLongPtrW(HWND window, int, LONG_PTR procedure) {
    std::lock_guard lock(fake::apiMutex);
    auto call = ++fake::setCalls;
    auto previous = window->procedure;
    auto fault = fake::setFaults.find(call);
    if (fault != fake::setFaults.end() && fault->second == fake::SetFault::Fail) { fake::lastError = 5; return 0; }
    window->procedure = reinterpret_cast<WNDPROC>(procedure);
    if (fake::releaseAtDetach && previous == axiom::windowsinput::observer) {
        std::lock_guard gateLock(fake::gateMutex); fake::releaseForward = true; fake::gate.notify_all();
    }
    if (fault != fake::setFaults.end())
        return fault->second == fake::SetFault::ZeroSuccess ? 0 : reinterpret_cast<LONG_PTR>(fake::other);
    return reinterpret_cast<LONG_PTR>(previous);
}
LRESULT CallWindowProcW(WNDPROC previous, HWND window, UINT message, WPARAM wparam, LPARAM lparam) { return previous(window, message, wparam, lparam); }
LRESULT DefWindowProcW(HWND, UINT, WPARAM, LPARAM) { throw std::runtime_error("known predecessor unexpectedly lost"); }
HMODULE GetModuleHandleW(LPCWSTR) { return reinterpret_cast<HMODULE>(1); }
bool GetModuleHandleExW(DWORD, LPCWSTR, HMODULE* module) { *module = reinterpret_cast<HMODULE>(fake::moduleMismatch ? 2 : 1); return true; }
HWND FindWindowExW(HWND, HWND after, LPCWSTR, LPCWSTR) { return !after && !fake::noRawWindow ? &fake::rawWindow : nullptr; }

int main() {
    using namespace fake;
    auto results = Json::array(); size_t failed = 0;
    std::pair<char const*, std::function<void()>> cases[] = {
        {"single_predecessor_arguments_return_last_error", normalForwarding},
        {"raw_window_destruction_invalidates_coverage", rawDestruction},
        {"main_window_destruction_invalidates_coverage", mainDestruction},
        {"missing_window_at_snapshot_invalidates_coverage", missingWindow},
        {"missing_retained_hook_invalidates_coverage", missingRegistry},
        {"lost_installed_state_invalidates_coverage", uninstalledRegistry},
        {"replacement_above_observer_is_preserved", replacedHook},
        {"retained_valid_observer_reuse", retainedHookReuse},
        {"retained_observer_lost_installed_state_refusal", [] { invalidRetainedHook(true); }},
        {"retained_observer_changed_owner_refusal", [] { invalidRetainedHook(false); }},
        {"failed_partial_attachment_cleanup", failedAttach},
        {"changed_predecessor_rollback", changedPredecessor},
        {"failed_rollback_retains_cleanup_context", rollbackFailure},
        {"anomalous_zero_predecessor_rollback", anomalousZeroPredecessor},
        {"wrong_raw_predecessor_module_refusal", wrongRawModule},
        {"missing_raw_window_refusal", missingRawWindow},
        {"raw_packet_read_error_passthrough", rawReadError},
        {"truncated_raw_packet_rejection", truncatedPacket},
        {"foreground_motion_unsupported_scope", skippedScope},
        {"nested_main_lifecycle_scopes", nestedLifecycle},
        {"bounded_message_overflow_passthrough", boundedMessages},
        {"inflight_raw_callback_drains", [] { blockedDrain(true); }},
        {"inflight_raw_callback_timeout_stays_incomplete", [] { blockedDrain(false); }},
    };
    for (auto const& [name, run] : cases) {
        reset(); size_t before = totalChecks; std::string error;
        try { run(); }
        catch (std::exception const& exception) { error = exception.what(); ++failed; }
        results.push(matjson::makeObject({{"name", name}, {"passed", error.empty()},
            {"checks", static_cast<uint64_t>(totalChecks - before)}, {"error", error}}));
    }
    std::cout << matjson::makeObject({{"kind", "software_only_windows_observer_fault_checks"},
        {"scope", "actual_observer_source_with_fake_Win32_and_Geode_window_clock"},
        {"live_windows_qualification", "not_established"}, {"gd_launched", false},
        {"case_count", static_cast<uint64_t>(std::size(cases))}, {"failed_cases", static_cast<uint64_t>(failed)},
        {"check_count", static_cast<uint64_t>(totalChecks)}, {"cases", results}}).dump(2) << '\n';
    return failed ? 1 : 0;
}
