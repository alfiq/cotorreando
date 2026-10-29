"""Windows keyboard plumbing: a global hotkey, typing detection and text injection.

A single low-level keyboard hook (WH_KEYBOARD_LL) tells us when the hotkey is
held and when the user is typing. Keys we inject ourselves carry the
LLKHF_INJECTED flag and are ignored, so our own typing never pauses dictation.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_QUIT = 0x12
LLKHF_INJECTED = 0x10
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x2, 0x4
VK_RETURN, VK_UNASSIGNED = 0x0D, 0xE8

MODIFIERS = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "shift": {0x10, 0xA0, 0xA1},
    "alt": {0x12, 0xA4, 0xA5},
    "win": {0x5B, 0x5C},
}
NAMED = {"space": 0x20, "tab": 0x09, "esc": 0x1B, "capslock": 0x14, "pause": 0x13,
         **{f"f{i}": 0x6F + i for i in range(1, 25)}}


def parse_hotkey(text: str) -> list[set[int]]:
    """'ctrl+win' -> [{ctrl vks}, {win vks}]. Each group must have one key down."""
    groups = []
    for part in text.lower().replace(" ", "").split("+"):
        if part in MODIFIERS:
            groups.append(MODIFIERS[part])
        elif part in NAMED:
            groups.append({NAMED[part]})
        elif len(part) == 1 and part.isalnum():
            groups.append({ord(part.upper())})
        else:
            raise ValueError(f"Unknown key: {part}")
    return groups


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        # MOUSEINPUT is the largest member; pad so sizeof(INPUT) matches Windows.
        _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class KeyboardMonitor:
    """Runs the hook on its own thread and reports hotkey and typing events."""

    def __init__(self, hotkey: str, on_hotkey_down, on_hotkey_up):
        self.groups = parse_hotkey(hotkey)
        self.on_down, self.on_up = on_hotkey_down, on_hotkey_up
        self.last_typed = 0.0
        self._pressed: set[int] = set()
        self._active = False
        self._thread_id = 0
        self._proc = HOOKPROC(self._hook)  # keep a reference alive

    def set_hotkey(self, hotkey: str) -> None:
        self.groups = parse_hotkey(hotkey)

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="keyboard").start()

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(hook)

    def _hook(self, code, wparam, lparam):
        if code >= 0:
            info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not info.flags & LLKHF_INJECTED:
                self._handle(info.vkCode, wparam in (WM_KEYDOWN, WM_SYSKEYDOWN))
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _handle(self, vk: int, down: bool) -> None:
        if down:
            self._pressed.add(vk)
        else:
            self._pressed.discard(vk)
        combo = all(self._pressed & g for g in self.groups)
        in_hotkey = any(vk in g for g in self.groups)
        if combo and not self._active:
            self._active = True
            # Stops a lone Win release from opening the Start menu.
            _tap(VK_UNASSIGNED)
            self.on_down()
        elif not combo and self._active:
            self._active = False
            self.on_up()
        elif down and not in_hotkey and not self._active:
            self.last_typed = time.monotonic()


def _tap(vk: int) -> None:
    send([_key(vk, 0, 0), _key(vk, 0, KEYEVENTF_KEYUP)])


def _key(vk: int, scan: int, flags: int) -> INPUT:
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def send(inputs: list[INPUT]) -> None:
    array = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))


def type_text(text: str, delay: float = 0.004) -> None:
    """Type Unicode text into whatever window has focus."""
    for ch in text:
        if ch == "\n":
            send([_key(VK_RETURN, 0, 0), _key(VK_RETURN, 0, KEYEVENTF_KEYUP)])
        else:
            data = ch.encode("utf-16-le")
            units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
            send([_key(0, u, KEYEVENTF_UNICODE | f) for f in (0, KEYEVENTF_KEYUP) for u in units])
        time.sleep(delay)
