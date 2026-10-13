#pragma once
#include <Geode/DefaultInclude.hpp>
#include <chrono>
#include <memory>

namespace axiom::windowsinput {
struct Session;
using SessionPtr = std::shared_ptr<Session>;
constexpr size_t MaxMessages = 2048;
constexpr size_t MaxSdkEvents = 2048;

// Main-window message scopes participate in the existing capture's deferred
// export. The separate raw-window thread never invokes these callbacks.
void setMainScopes(void (*enter)(), void (*leave)());
SessionPtr begin(std::chrono::steady_clock::time_point start);
void stop(SessionPtr const& session);
bool onMainThread();
void sdkOverflow(SessionPtr const& session);
matjson::Value snapshot(SessionPtr const& session, matjson::Value const& sdkEvents);
} // namespace axiom::windowsinput
