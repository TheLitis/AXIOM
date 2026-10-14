#include "WindowsInputObserver.hpp"
#include <Geode/Geode.hpp>
#include <Windows.h>
#include <array>
#include <atomic>
#include <condition_variable>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <vector>

using namespace geode::prelude;
namespace axiom::windowsinput {
namespace {
using Json = matjson::Value;
using Clock = std::chrono::steady_clock;
struct Packet {
    UINT kind = 0;
    USHORT vkey = 0, scan = 0, flags = 0;
    UINT keyboardMessage = 0;
    USHORT mouseButtons = 0;
};
struct Message {
    size_t sequence = 0;
    std::optional<size_t> parent;
    bool rawWindow = false;
    UINT message = 0;
    WPARAM wparam = 0;
    LPARAM lparam = 0;
    DWORD thread = 0;
    bool foregroundBefore = false, foregroundAfter = false;
    int64_t wallEnter = 0, wallExit = 0;
    double timestampEnter = 0, timestampExit = 0;
    LRESULT returned = 0;
    bool closed = false;
    std::optional<Packet> packet;
};
struct Hook {
    HWND window = nullptr;
    DWORD thread = 0, process = 0;
    bool rawWindow = false;
    WNDPROC previous = nullptr;
    bool installed = false;
};
// Contexts remain valid for the guarded process's lifetime, even when another
// owner subsequently places a procedure above ours. No Run or game pointer is
// reachable from this registry or from a raw-input callback.
std::recursive_mutex registryMutex;
std::map<HWND, Hook> hooks;
std::atomic<HWND> mainHookWindow = nullptr, rawHookWindow = nullptr;
std::atomic<WNDPROC> mainPrevious = nullptr, rawPrevious = nullptr;
std::shared_ptr<Session> current;
void (*enterMain)() = nullptr;
void (*leaveMain)() = nullptr;
LRESULT CALLBACK observer(HWND window, UINT message, WPARAM wparam, LPARAM lparam);

bool focusMessage(UINT message) {
    return message == WM_ACTIVATE || message == WM_SETFOCUS || message == WM_KILLFOCUS ||
        message == WM_ACTIVATEAPP || message == WM_NCDESTROY;
}
} // namespace

struct Session {
    Clock::time_point start;
    DWORD mainThread = 0;
    HWND mainWindow = nullptr;
    std::atomic<bool> accepting = false;
    std::mutex mutex;
    std::condition_variable condition;
    std::vector<Message> messages;
    std::map<DWORD, std::vector<size_t>> stacks;
    std::vector<Hook> declarations;
    size_t inFlight = 0, overflow = 0, readErrors = 0;
    uint64_t background = 0, motion = 0, unsupported = 0;
    std::vector<std::string> errors;
};

namespace {
int64_t elapsed(Session const& session) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - session.start).count();
}
void error(SessionPtr const& session, char const* message) noexcept {
    try {
        if (!session) return;
        std::lock_guard lock(session->mutex);
        if (session->errors.size() < 16) session->errors.push_back(message);
    } catch (...) {} // Observer diagnostics must not escape a Windows callback.
}
void skip(SessionPtr const& session, uint64_t Session::*counter) {
    std::lock_guard lock(session->mutex);
    ++(session.get()->*counter);
}
std::optional<Packet> packet(SessionPtr const& session, LPARAM lparam) {
    alignas(RAWINPUT) std::array<BYTE, sizeof(RAWINPUT)> bytes{};
    UINT size = bytes.size();
    auto length = GetRawInputData(reinterpret_cast<HRAWINPUT>(lparam), RID_INPUT,
        bytes.data(), &size, sizeof(RAWINPUTHEADER));
    if (length == static_cast<UINT>(-1) || length < sizeof(RAWINPUTHEADER) || size > bytes.size()) {
        std::lock_guard lock(session->mutex);
        ++session->readErrors;
        if (session->errors.size() < 16) session->errors.push_back("Foreground raw-input packet read failed or exceeded bound");
        return {};
    }
    auto const* raw = reinterpret_cast<RAWINPUT const*>(bytes.data());
    Packet result;
    result.kind = raw->header.dwType;
    // Device identifiers, HID payloads and movement coordinates are never retained.
    if (result.kind == RIM_TYPEKEYBOARD) {
        if (length < offsetof(RAWINPUT, data) + sizeof(RAWKEYBOARD)) {
            error(session, "Truncated foreground raw keyboard packet");
            std::lock_guard lock(session->mutex); ++session->readErrors;
            return {};
        }
        result.vkey = raw->data.keyboard.VKey;
        result.scan = raw->data.keyboard.MakeCode;
        result.flags = raw->data.keyboard.Flags;
        result.keyboardMessage = raw->data.keyboard.Message;
    } else if (result.kind == RIM_TYPEMOUSE) {
        if (length < offsetof(RAWINPUT, data) + sizeof(RAWMOUSE)) {
            error(session, "Truncated foreground raw mouse packet");
            std::lock_guard lock(session->mutex); ++session->readErrors;
            return {};
        }
        result.mouseButtons = raw->data.mouse.usButtonFlags;
        if (!result.mouseButtons) { skip(session, &Session::motion); return {}; }
        if (!(result.mouseButtons & 0x03ff)) { skip(session, &Session::unsupported); return {}; }
    } else { skip(session, &Session::unsupported); return {}; }
    return result;
}

LRESULT CALLBACK observer(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
    DWORD incomingError = GetLastError();
    Hook hook;
    hook.rawWindow = window == rawHookWindow.load();
    hook.previous = hook.rawWindow ? rawPrevious.load() : mainPrevious.load();
    SessionPtr session;
    bool admitted = false, inFlight = false;
    bool foreground = false;
    bool mainScope = false;
    std::optional<size_t> index;
    try {
        {
            std::lock_guard lock(registryMutex);
            auto found = hooks.find(window);
            if (found != hooks.end()) hook = found->second;
        }
        session = std::atomic_load(&current);
        bool selected = session &&
            ((hook.rawWindow && (message == WM_INPUT || message == WM_NCDESTROY)) ||
                (!hook.rawWindow && focusMessage(message)));
        if (selected) {
            std::lock_guard lock(session->mutex);
            if (session->accepting.load(std::memory_order_acquire)) {
                ++session->inFlight;
                inFlight = admitted = true;
            }
        }
        if (admitted && message == WM_NCDESTROY) {
            error(session, hook.rawWindow ? "Raw Windows input window destroyed during active capture" :
                "Main Windows input window destroyed during active capture");
            // The raw lifecycle participates in the callback barrier but is
            // not fabricated as a schema-7 foreground WM_INPUT packet. Main
            // lifecycle rows retain their existing paired/export-scope path.
            if (hook.rawWindow) admitted = false;
        }
        foreground = admitted && GetForegroundWindow() == session->mainWindow;
        if (admitted && hook.rawWindow && !foreground) {
            skip(session, &Session::background);
            admitted = false;
        }
        std::optional<Packet> decoded;
        if (admitted && hook.rawWindow) {
            decoded = packet(session, lparam);
            if (!decoded) admitted = false;
        }
        if (admitted) {
            if (!hook.rawWindow && GetCurrentThreadId() == session->mainThread && enterMain && leaveMain) {
                enterMain();
                mainScope = true;
            }
            std::lock_guard lock(session->mutex);
            if (session->accepting.load(std::memory_order_acquire)) {
                if (session->messages.size() >= MaxMessages) {
                    ++session->overflow;
                    if (session->errors.size() < 16) session->errors.push_back("Windows message buffer overflow");
                } else {
                    Message row;
                    row.sequence = session->messages.size();
                    row.rawWindow = hook.rawWindow;
                    row.message = message; row.wparam = wparam; row.lparam = lparam;
                    row.thread = GetCurrentThreadId();
                    auto& stack = session->stacks[row.thread];
                    if (!stack.empty()) row.parent = stack.back();
                    row.foregroundBefore = foreground;
                    row.wallEnter = elapsed(*session);
                    row.packet = decoded;
                    row.timestampEnter = geode::utils::getInputTimestamp();
                    index = row.sequence;
                    session->messages.push_back(row);
                    stack.push_back(*index);
                }
            }
        }
    } catch (...) {
        if (session) error(session, "Windows entry observation failed");
    }
    // Observation neither consumes nor generates input. Preserve the retained
    // predecessor's message, return and last-error behavior exactly once.
    SetLastError(incomingError);
    LRESULT returned = hook.previous ? CallWindowProcW(hook.previous, window, message, wparam, lparam) :
        DefWindowProcW(window, message, wparam, lparam);
    DWORD originalError = GetLastError();
    try {
        if (index) {
            auto stamp = geode::utils::getInputTimestamp();
            auto foregroundAfter = GetForegroundWindow() == session->mainWindow;
            std::lock_guard lock(session->mutex);
            auto& row = session->messages[*index];
            row.timestampExit = stamp;
            row.wallExit = elapsed(*session);
            row.foregroundAfter = foregroundAfter;
            row.returned = returned;
            row.closed = true;
            auto& stack = session->stacks[row.thread];
            if (!stack.empty() && stack.back() == *index) stack.pop_back();
            else if (session->errors.size() < 16) session->errors.push_back("Windows per-thread callback nesting mismatch");
        }
        if (message == WM_NCDESTROY) {
            std::lock_guard lock(registryMutex);
            auto found = hooks.find(window);
            if (found != hooks.end()) found->second.installed = false;
        }
    } catch (...) {
        if (session) error(session, "Windows exit observation failed");
    }
    if (inFlight) {
        try {
            std::lock_guard lock(session->mutex);
            --session->inFlight;
            session->condition.notify_all();
        } catch (...) { error(session, "Windows callback barrier release failed"); }
    }
    if (mainScope) {
        try { leaveMain(); }
        catch (...) { error(session, "Main Windows callback capture scope failed"); }
    }
    SetLastError(originalError);
    return returned;
}

Hook attach(SessionPtr const& session, HWND window, bool rawWindow) {
    Hook result;
    result.window = window; result.rawWindow = rawWindow;
    if (!window || !IsWindow(window)) throw std::runtime_error("Selected Windows input window unavailable");
    result.thread = GetWindowThreadProcessId(window, &result.process);
    if (!result.thread || result.process != GetCurrentProcessId())
        throw std::runtime_error("Selected Windows input window is not owned by this process");
    // Register ownership before a procedure replacement can succeed and before
    // returning to begin. Every partial attachment is therefore visible to its
    // failure cleanup, including a changed or anomalous returned predecessor.
    auto declaration = session->declarations.size();
    session->declarations.push_back(result);
    std::lock_guard lock(registryMutex);
    auto existing = hooks.find(window);
    auto previous = reinterpret_cast<WNDPROC>(GetWindowLongPtrW(window, GWLP_WNDPROC));
    if (previous == observer) {
        if (existing == hooks.end() || !existing->second.previous || !existing->second.installed ||
                existing->second.thread != result.thread || existing->second.process != result.process ||
                existing->second.rawWindow != rawWindow)
            throw std::runtime_error("Existing observer ownership or installed predecessor is unavailable");
        session->declarations[declaration] = existing->second;
        return existing->second;
    }
    if (!previous) throw std::runtime_error("Selected Windows input predecessor unavailable");
    if (existing != hooks.end() && existing->second.installed)
        throw std::runtime_error("Selected Windows procedure chain was replaced; observer will not overwrite it");
    if (rawWindow) {
        HMODULE owner = nullptr;
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                reinterpret_cast<LPCWSTR>(previous), &owner) || owner != GetModuleHandleW(L"Geode.dll"))
            throw std::runtime_error("Raw Windows predecessor is not the loaded Geode handler");
    }
    result.previous = previous;
    hooks[window] = result;
    auto& selectedWindow = rawWindow ? rawHookWindow : mainHookWindow;
    auto& selectedPrevious = rawWindow ? rawPrevious : mainPrevious;
    selectedPrevious.store(previous);
    selectedWindow.store(window);
    SetLastError(0);
    auto replaced = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(observer)));
    auto failure = GetLastError();
    if (!replaced && failure) throw std::runtime_error("Windows procedure attachment failed");
    // The registry lock prevents another thread entering our procedure before
    // the actual predecessor returned by Windows has been published.
    hooks[window].previous = replaced;
    // A zero previous value after a nonzero pre-check is anomalous. Retain the
    // known nonnull chain while rolling back rather than publishing a null
    // forwarder; the attempted observation is explicitly incomplete.
    if (!replaced) hooks[window].previous = previous;
    selectedPrevious.store(hooks[window].previous);
    hooks[window].installed = true;
    session->declarations[declaration] = hooks[window];
    if (!replaced || replaced != previous) {
        if (reinterpret_cast<WNDPROC>(GetWindowLongPtrW(window, GWLP_WNDPROC)) == observer) {
            SetLastError(0);
            auto removed = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(window, GWLP_WNDPROC,
                reinterpret_cast<LONG_PTR>(hooks[window].previous)));
            auto restoreError = GetLastError();
            if (removed == observer && !restoreError) hooks[window].installed = false;
            else error(session, "Changed-predecessor attachment rollback failed; context retained for cleanup");
        } else error(session, "Procedure replaced above partial attachment; context retained for cleanup");
        session->declarations[declaration] = hooks[window];
        throw std::runtime_error(!replaced ? "Windows attachment returned an anomalous zero predecessor" :
            "Windows predecessor changed during attachment; rollback attempted");
    }
    return hooks[window];
}

void detach(SessionPtr const& session) {
    std::lock_guard lock(registryMutex);
    for (auto const& declaration : session->declarations) {
        auto found = hooks.find(declaration.window);
        if (found == hooks.end()) {
            if (declaration.installed) error(session, "Installed Windows input hook missing from retained registry");
            continue;
        }
        if (!found->second.installed) {
            if (declaration.installed) error(session, "Declared Windows input hook no longer installed before snapshot");
            continue;
        }
        auto& hook = found->second;
        if (!IsWindow(hook.window)) {
            error(session, "Observed Windows input window unavailable before restoration");
            hook.installed = false;
            continue;
        }
        auto actual = reinterpret_cast<WNDPROC>(GetWindowLongPtrW(hook.window, GWLP_WNDPROC));
        if (actual != observer) {
            error(session, "Windows procedure replaced above observer; retained inert forwarding context");
            continue;
        }
        SetLastError(0);
        auto previous = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(hook.window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(hook.previous)));
        auto failure = GetLastError();
        if ((!previous && failure) || previous != observer) {
            error(session, "Windows procedure restoration failed or chain changed");
            continue;
        }
        hook.installed = false;
    }
}
} // namespace

void setMainScopes(void (*enter)(), void (*leave)()) { enterMain = enter; leaveMain = leave; }

SessionPtr begin(Clock::time_point start) {
    auto session = std::make_shared<Session>();
    session->start = start;
    session->mainThread = GetCurrentThreadId();
    session->messages.reserve(MaxMessages);
    try {
        auto view = CCEGLView::get();
        if (!view || !view->m_pMainWindow) throw std::runtime_error("Native GLFW game window unavailable");
        // Exact pinned Geode 5.8.2 input.cpp uses this GLFW 2.2081 layout.
        session->mainWindow = *reinterpret_cast<HWND*>(reinterpret_cast<uintptr_t>(view->m_pMainWindow) + 0x370);
        DWORD process = 0;
        if (GetWindowThreadProcessId(session->mainWindow, &process) != session->mainThread || process != GetCurrentProcessId())
            throw std::runtime_error("Native game window owner does not match capture thread/process");
        attach(session, session->mainWindow, false);
        HWND selected = nullptr, candidate = nullptr;
        size_t matches = 0;
        while ((candidate = FindWindowExW(nullptr, candidate, L"GD_RawInput", nullptr))) {
            DWORD owner = 0;
            GetWindowThreadProcessId(candidate, &owner);
            if (owner == GetCurrentProcessId()) { selected = candidate; ++matches; }
        }
        if (matches != 1) throw std::runtime_error("Exactly one process-owned GD_RawInput window is required");
        attach(session, selected, true);
        session->accepting.store(true, std::memory_order_release);
        std::atomic_store(&current, session);
    } catch (std::exception const& failure) {
        error(session, failure.what());
        detach(session);
    }
    return session;
}

void stop(SessionPtr const& session) {
    if (!session) return;
    session->accepting.store(false, std::memory_order_release);
    auto expected = session;
    std::atomic_compare_exchange_strong(&current, &expected, SessionPtr{});
}

bool onMainThread() {
    auto session = std::atomic_load(&current);
    return session && session->accepting.load(std::memory_order_acquire) && GetCurrentThreadId() == session->mainThread;
}

void sdkOverflow(SessionPtr const& session) {
    if (!session) return;
    std::lock_guard lock(session->mutex);
    ++session->overflow;
    if (session->errors.size() < 16) session->errors.push_back("Geode SDK event buffer overflow");
}

Json snapshot(SessionPtr const& session, Json const& sdkEvents) {
    stop(session);
    detach(session);
    std::unique_lock lock(session->mutex);
    if (!session->condition.wait_for(lock, std::chrono::milliseconds(25), [&] { return session->inFlight == 0; }))
        if (session->errors.size() < 16) session->errors.push_back("Windows callbacks still in flight at bounded snapshot");
    Json declarations = Json::array(), messages = Json::array(), errors = Json::array();
    for (auto const& window : session->declarations)
        declarations.push(matjson::makeObject({{"role", window.rawWindow ? "raw" : "main"},
            {"thread_id", window.thread}, {"process_id", window.process},
            {"hwnd", static_cast<uint64_t>(reinterpret_cast<uintptr_t>(window.window))}, {"installed", window.installed}}));
    for (auto const& row : session->messages) {
        Json raw = nullptr;
        if (row.packet) {
            auto const& packet = *row.packet;
            raw = packet.kind == RIM_TYPEKEYBOARD ? matjson::makeObject({{"kind", "keyboard"},
                {"vkey", packet.vkey}, {"scan_code", packet.scan}, {"flags", packet.flags}, {"keyboard_message", packet.keyboardMessage}}) :
                matjson::makeObject({{"kind", "mouse"}, {"button_flags", packet.mouseButtons}});
        }
        messages.push(matjson::makeObject({{"sequence", static_cast<uint64_t>(row.sequence)},
            {"parent_sequence", row.parent ? Json(static_cast<uint64_t>(*row.parent)) : Json(nullptr)},
            {"window_role", row.rawWindow ? "raw" : "main"}, {"message", row.message},
            {"wparam", static_cast<uint64_t>(row.wparam)}, {"lparam", static_cast<int64_t>(row.lparam)},
            {"thread_id", row.thread}, {"foreground_before", row.foregroundBefore}, {"foreground_after", row.foregroundAfter},
            {"wall_enter_ns", row.wallEnter}, {"wall_exit_ns", row.closed ? Json(row.wallExit) : Json(nullptr)},
            {"input_timestamp_enter", row.timestampEnter}, {"input_timestamp_exit", row.closed ? Json(row.timestampExit) : Json(nullptr)},
            {"native_return", row.closed ? Json(static_cast<int64_t>(row.returned)) : Json(nullptr)}, {"raw_input", raw}}));
    }
    for (auto const& message : session->errors) errors.push(message);
    return matjson::makeObject({{"enabled", true}, {"scope", "active-guarded-sandbox-attempt-foreground-raw-only"},
        {"main_thread_id", session->mainThread}, {"windows", declarations}, {"messages", messages}, {"sdk_events", sdkEvents},
        {"integrity", matjson::makeObject({{"overflow_count", static_cast<uint64_t>(session->overflow)},
            {"read_error_count", static_cast<uint64_t>(session->readErrors)}, {"pending_callbacks_at_snapshot", static_cast<uint64_t>(session->inFlight)}, {"errors", errors}})},
        {"skipped", matjson::makeObject({{"background_raw_count", session->background}, {"mouse_motion_count", session->motion}, {"unsupported_raw_count", session->unsupported}})},
        {"timestamp_unit", "Geode-getInputTimestamp-QPC-seconds"}, {"sdk_listener_phase", "public-global-listener-receipt"},
        {"sdk_listener_priority", std::numeric_limits<int>::min()}});
}
} // namespace axiom::windowsinput
