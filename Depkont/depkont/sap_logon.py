from __future__ import annotations

import ctypes
import os
import subprocess
import time
import winreg
from collections.abc import Callable, Iterable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

SAPLOGON_PATH = Path(r"C:\Program Files (x86)\SAP\FrontEnd\SAPgui\saplogon.exe")
SAPLOGON_CANDIDATES = (
    SAPLOGON_PATH,
    Path(r"C:\Program Files\SAP\FrontEnd\SAPgui\saplogon.exe"),
)
SAPLOGON_PROCESS_NAMES = frozenset({"saplogon.exe", "saplgpad.exe"})
SAP_WINDOW_CLASS = "SAP_FRONTEND_SESSION"
LAUNCH_TIMEOUT_SECONDS = 15.0
_APP_PATH_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\saplogon.exe",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\saplogon.exe",
)
_TH32CS_SNAPPROCESS = 0x00000002


class SapLogonError(RuntimeError):
    pass


@dataclass(frozen=True)
class SapStatus:
    already_open: bool
    executable: Path | None
    message: str


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def is_sap_window(title: str, class_name: str) -> bool:
    if class_name == SAP_WINDOW_CLASS:
        return True
    folded = title.casefold()
    return "sap logon" in folded or "sap easy access" in folded


def find_saplogon_executable(
    candidates: Iterable[Path] = SAPLOGON_CANDIDATES,
    *,
    search_registry: bool = True,
) -> Path | None:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if search_registry:
        registered = saplogon_from_registry()
        if registered is not None and registered.is_file():
            return registered
    return None


def saplogon_from_registry() -> Path | None:
    if os.name != "nt":
        return None
    for subkey in _APP_PATH_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                value, _kind = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        if value:
            return Path(str(value))
    return None


def sap_is_open() -> bool:
    if os.name != "nt":
        raise SapLogonError("SAP kontrolü yalnızca Windows'ta kullanılabilir.")
    return sap_process_is_running() or sap_window_is_open()


def sap_process_is_running() -> bool:
    return bool(SAPLOGON_PROCESS_NAMES & running_process_names())


def running_process_names() -> set[str]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise SapLogonError("Çalışan süreçler okunamadı.")

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    names: set[str] = set()
    try:
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return names
        while True:
            names.add(entry.szExeFile.casefold())
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def sap_window_is_open() -> bool:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int

    found = False

    def visit(hwnd: int, _lparam: int) -> bool:
        nonlocal found
        if found or not user32.IsWindowVisible(hwnd):
            return True
        if is_sap_window(_window_text(user32, hwnd), _class_name(user32, hwnd)):
            found = True
        return True

    callback = enum_proc(visit)
    if not user32.EnumWindows(callback, 0) and not found:
        error_code = ctypes.get_last_error()
        if error_code:
            raise SapLogonError(f"SAP pencereleri okunamadı ({error_code}).")
    return found


def start_saplogon(executable: Path) -> None:
    try:
        subprocess.Popen([str(executable)], cwd=str(executable.parent))
    except OSError as exc:
        raise SapLogonError(f"SAP Logon başlatılamadı: {exc}") from exc


def ensure_sap_open(
    *,
    finder: Callable[[], Path | None] | None = None,
    is_open: Callable[[], bool] | None = None,
    starter: Callable[[Path], None] | None = None,
    clock: Callable[[], float] | None = None,
    pause: Callable[[float], None] | None = None,
    timeout_seconds: float = LAUNCH_TIMEOUT_SECONDS,
) -> SapStatus:
    locate = finder or find_saplogon_executable
    probe = is_open or sap_is_open
    launch = starter or start_saplogon
    now = clock or time.monotonic
    wait = pause or time.sleep

    if probe():
        return SapStatus(True, None, "SAP zaten açık.")

    executable = locate()
    if executable is None:
        raise SapLogonError(
            "SAP Logon bulunamadı. Beklenen konum: "
            f"{SAPLOGON_PATH}"
        )

    launch(executable)
    deadline = now() + timeout_seconds
    while now() < deadline:
        if probe():
            return SapStatus(
                False,
                executable,
                f"SAP kapalıydı. SAP Logon açıldı: {executable}",
            )
        wait(0.25)
    raise SapLogonError(f"SAP Logon başlatıldı ancak açılmadı: {executable}")


def _window_text(user32: ctypes.WinDLL, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _class_name(user32: ctypes.WinDLL, hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    if user32.GetClassNameW(hwnd, buffer, len(buffer)) <= 0:
        return ""
    return buffer.value
