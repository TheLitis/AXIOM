#pragma once
// Deliberately fake API declarations, not a Windows SDK ABI qualification.
// No operating-system window, input receiver or input injection is created.
#include <cstddef>
#include <cstdint>

#define CALLBACK
using BYTE = unsigned char;
using USHORT = std::uint16_t;
using UINT = std::uint32_t;
using DWORD = std::uint32_t;
using WPARAM = std::uintptr_t;
using LPARAM = std::intptr_t;
using LRESULT = std::intptr_t;
using LONG_PTR = std::intptr_t;
using LPCWSTR = wchar_t const*;
struct FakeWindow;
using HWND = FakeWindow*;
using HRAWINPUT = void*;
using HMODULE = void*;
using WNDPROC = LRESULT (*)(HWND, UINT, WPARAM, LPARAM);

constexpr UINT WM_ACTIVATE = 6, WM_SETFOCUS = 7, WM_KILLFOCUS = 8;
constexpr UINT WM_ACTIVATEAPP = 28, WM_NCDESTROY = 130, WM_INPUT = 255;
constexpr UINT RIM_TYPEMOUSE = 0, RIM_TYPEKEYBOARD = 1, RIM_TYPEHID = 2;
constexpr UINT RID_INPUT = 0x10000003;
constexpr int GWLP_WNDPROC = -4;
constexpr DWORD GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS = 4;
constexpr DWORD GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT = 2;
struct RAWINPUTHEADER { DWORD dwType, dwSize; void* hDevice; WPARAM wParam; };
struct RAWKEYBOARD { USHORT MakeCode, Flags, Reserved, VKey; UINT Message; DWORD ExtraInformation; };
struct RAWMOUSE {
    USHORT usFlags;
    USHORT padding;
    USHORT usButtonFlags, usButtonData;
    std::uint32_t ulRawButtons;
    std::int32_t lLastX, lLastY;
    std::uint32_t ulExtraInformation;
};
struct RAWINPUT { RAWINPUTHEADER header; union { RAWMOUSE mouse; RAWKEYBOARD keyboard; } data; };

DWORD GetLastError();
void SetLastError(DWORD);
UINT GetRawInputData(HRAWINPUT, UINT, void*, UINT*, UINT);
DWORD GetWindowThreadProcessId(HWND, DWORD*);
DWORD GetCurrentProcessId();
DWORD GetCurrentThreadId();
bool IsWindow(HWND);
HWND GetForegroundWindow();
LONG_PTR GetWindowLongPtrW(HWND, int);
LONG_PTR SetWindowLongPtrW(HWND, int, LONG_PTR);
LRESULT CallWindowProcW(WNDPROC, HWND, UINT, WPARAM, LPARAM);
LRESULT DefWindowProcW(HWND, UINT, WPARAM, LPARAM);
bool GetModuleHandleExW(DWORD, LPCWSTR, HMODULE*);
HMODULE GetModuleHandleW(LPCWSTR);
HWND FindWindowExW(HWND, HWND, LPCWSTR, LPCWSTR);
