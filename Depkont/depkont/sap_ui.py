from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes

import win32con
import win32gui
import win32process

LVIF_TEXT = 0x0001
LVM_GETITEMCOUNT = 0x1004
LVM_ENSUREVISIBLE = 0x1013
LVM_SETITEMSTATE = 0x102B
LVM_GETITEMTEXTW = 0x1073
LVIS_FOCUSED = 0x0001
LVIS_SELECTED = 0x0002
TCM_GETITEMCOUNT = 0x1304
TCM_GETITEMW = 0x133C
TCM_SETCURSEL = 0x130C
TCIF_TEXT = 0x0001
_PROCESS_RIGHTS = 0x0010 | 0x0020 | 0x0008 | 0x0400
_MEM_COMMIT = 0x1000
_MEM_RESERVE = 0x2000
_MEM_RELEASE = 0x8000
_PAGE_READWRITE = 0x04

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.VirtualAllocEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
    wintypes.DWORD,
]
kernel32.VirtualAllocEx.restype = ctypes.c_void_p
kernel32.VirtualFreeEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
]
kernel32.VirtualFreeEx.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
kernel32.IsWow64Process.restype = wintypes.BOOL
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t


def pack_lvitem_text(pointer_size: int, text_address: int, subitem: int) -> bytes:
    if pointer_size == 4:
        return struct.pack("<IiiIIII", LVIF_TEXT, 0, subitem, 0, 0, text_address, 260)
    return struct.pack("<IiiII4xQi", LVIF_TEXT, 0, subitem, 0, 0, text_address, 260)


def pack_lvitem_state(state: int, state_mask: int) -> bytes:
    return struct.pack("<IiiII", 0, 0, 0, state, state_mask)


def button_label(text: str) -> str:
    return text.replace("&", "").strip().casefold()


def find_top_window(prefix: str) -> int:
    found = 0
    folded = prefix.casefold()

    def visit(hwnd: int, _extra: object) -> bool:
        nonlocal found
        if found or not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.GetWindowText(hwnd).casefold().startswith(folded):
            found = hwnd
        return True

    win32gui.EnumWindows(visit, None)
    return found


def child_windows(parent: int, class_name: str) -> list[int]:
    hits: list[int] = []

    def visit(hwnd: int, _extra: object) -> bool:
        if win32gui.GetClassName(hwnd) == class_name:
            hits.append(hwnd)
        return True

    win32gui.EnumChildWindows(parent, visit, None)
    return hits


def find_button(parent: int, label: str) -> int:
    wanted = button_label(label)
    found = 0

    def visit(hwnd: int, _extra: object) -> bool:
        nonlocal found
        if found or win32gui.GetClassName(hwnd) != "Button":
            return True
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if button_label(win32gui.GetWindowText(hwnd)) == wanted:
            found = hwnd
        return True

    win32gui.EnumChildWindows(parent, visit, None)
    return found


def click_button(button: int) -> None:
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(
        button,
        win32con.BM_CLICK,
        0,
        0,
        win32con.SMTO_NORMAL,
        3000,
        ctypes.byref(result),
    )


class RemoteList:
    """Reads a ListView that belongs to another process."""

    def __init__(self, hwnd: int) -> None:
        _thread, pid = win32process.GetWindowThreadProcessId(hwnd)
        self.hwnd = hwnd
        self.process = kernel32.OpenProcess(_PROCESS_RIGHTS, False, pid)
        if not self.process:
            raise OSError(ctypes.get_last_error())
        wow64 = wintypes.BOOL()
        kernel32.IsWow64Process(self.process, ctypes.byref(wow64))
        self.pointer_size = 4 if wow64.value or ctypes.sizeof(ctypes.c_void_p) == 4 else 8
        self.remote = kernel32.VirtualAllocEx(
            self.process,
            None,
            8192,
            _MEM_COMMIT | _MEM_RESERVE,
            _PAGE_READWRITE,
        )
        if not self.remote:
            kernel32.CloseHandle(self.process)
            raise OSError(ctypes.get_last_error())
        self.text_address = self.remote + 1024
        self._written = ctypes.c_size_t()

    def close(self) -> None:
        if self.remote:
            kernel32.VirtualFreeEx(self.process, self.remote, 0, _MEM_RELEASE)
            self.remote = 0
        if self.process:
            kernel32.CloseHandle(self.process)
            self.process = 0

    def __enter__(self) -> RemoteList:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def item_count(self) -> int:
        return int(user32.SendMessageW(self.hwnd, LVM_GETITEMCOUNT, 0, 0))

    def rows(self, columns: int = 8) -> list[list[str]]:
        result: list[list[str]] = []
        for index in range(self.item_count()):
            cells = [self.cell(index, column) for column in range(columns)]
            result.append(cells)
        return result

    def cell(self, index: int, column: int) -> str:
        self._write(pack_lvitem_text(self.pointer_size, self.text_address, column))
        length = int(user32.SendMessageW(self.hwnd, LVM_GETITEMTEXTW, index, self.remote))
        if length <= 0:
            return ""
        return self._read_text()

    def select(self, index: int) -> None:
        clear = pack_lvitem_state(0, LVIS_SELECTED | LVIS_FOCUSED)
        self._write(clear)
        user32.SendMessageW(self.hwnd, LVM_SETITEMSTATE, wintypes.WPARAM(-1).value, self.remote)
        selected = pack_lvitem_state(LVIS_SELECTED | LVIS_FOCUSED, LVIS_SELECTED | LVIS_FOCUSED)
        self._write(selected)
        user32.SendMessageW(self.hwnd, LVM_SETITEMSTATE, index, self.remote)
        user32.SendMessageW(self.hwnd, LVM_ENSUREVISIBLE, index, 0)

    def _write(self, data: bytes) -> None:
        buffer = ctypes.create_string_buffer(data)
        ok = kernel32.WriteProcessMemory(
            self.process,
            self.remote,
            buffer,
            len(data),
            ctypes.byref(self._written),
        )
        if not ok:
            raise OSError(ctypes.get_last_error())

    def _read_text(self) -> str:
        raw = ctypes.create_string_buffer(520)
        kernel32.ReadProcessMemory(
            self.process,
            self.text_address,
            raw,
            len(raw),
            ctypes.byref(self._written),
        )
        return raw.raw.decode("utf-16le", errors="ignore").split("\x00", 1)[0]


def tab_labels(tab: int, reader: RemoteList) -> list[str]:
    count = int(user32.SendMessageW(tab, TCM_GETITEMCOUNT, 0, 0))
    labels: list[str] = []
    for index in range(count):
        if reader.pointer_size == 4:
            data = struct.pack("<IIIIiII", TCIF_TEXT, 0, 0, reader.text_address, 260, 0, 0)
        else:
            data = struct.pack("<III4xQiII", TCIF_TEXT, 0, 0, reader.text_address, 260, 0, 0)
        reader._write(data)
        user32.SendMessageW(tab, TCM_GETITEMW, index, reader.remote)
        labels.append(reader._read_text().strip())
    return labels


def select_tab(tab: int, index: int) -> None:
    user32.SendMessageW(tab, TCM_SETCURSEL, index, 0)
