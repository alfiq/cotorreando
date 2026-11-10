"""Windows keyboard plumbing: a global hotkey, typing detection and text injection.

No keyboard hook, on purpose: this process never receives what is being typed.
The hotkey is found by asking only about its own keys, and while the Settings field
records a new one it asks about the keys a hotkey can use (down_keys), still with no hook.
Typing is inferred from the time of the last input (which says nothing about the key): input that neither the
mouse hook nor our own injection explains came from the keyboard. Moving the mouse
while typing can hide keystrokes, a price accepted to stay out of the key stream.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_MOUSE_LL = 14
MOUSE_DOWN = {0x201, 0x204, 0x207}  # left, right and middle button
WM_QUIT = 0x12
POLL_S = 0.01
SETTLE_MS = 20  # the mouse hook may report an event just after it shows up as input
SAME_EVENT_MS = 30  # input this close to a mouse event or our own typing is explained by it
HOTKEY_GRACE_S = 0.1  # releasing the hotkey is input too, and it is not typing
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x2, 0x4
VK_BACK, VK_RETURN, VK_UNASSIGNED = 0x08, 0x0D, 0xE8

MODIFIERS = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "shift": {0x10, 0xA0, 0xA1},
    "alt": {0x12, 0xA4, 0xA5},
    "win": {0x5B, 0x5C},
}
NAMED = {
    "space": 0x20,
    "tab": 0x09,
    "esc": 0x1B,
    "capslock": 0x14,
    "pause": 0x13,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
}
VK_ESCAPE = 0x1B
LONE_KEYS = {f"f{i}" for i in range(1, 25)} | {"pause"}  # allowed without a modifier
_ORDER = ["ctrl", "alt", "shift", "win"]
_NAME_OF = {vk: name for name, vk in NAMED.items()}
WIN_VKS = MODIFIERS["win"]
HOTKEY_VKS = (
    set().union(*MODIFIERS.values())
    | set(NAMED.values())
    | set(range(ord("A"), ord("Z") + 1))
    | set(range(ord("0"), ord("9") + 1))
)

# While set, the monitor ignores the hotkey (the Settings field is recording a new one).
hotkey_paused = threading.Event()


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


def hotkey_from_vks(vks) -> str:
    """The hotkey text for a set of pressed keys: ctrl, alt, shift, win, then one key.

    Left and right modifiers are the same, keys a hotkey cannot use are ignored and,
    if several plain keys are down, the lowest virtual-key code stays.
    """
    parts = [name for name in _ORDER if MODIFIERS[name] & set(vks)]
    keys = sorted(vk for vk in vks if vk in HOTKEY_VKS and not any(vk in g for g in MODIFIERS.values()))
    if keys:
        vk = keys[0]
        parts.append(_NAME_OF.get(vk) or chr(vk).lower())
    return "+".join(parts)


def hotkey_label(text: str) -> str:
    """'ctrl+win' -> 'Ctrl+Win', 'f5' -> 'F5'. Text that is not a hotkey is shown as it is."""
    try:
        parse_hotkey(text)
    except ValueError:
        return text
    parts = text.lower().replace(" ", "").split("+")
    return "+".join(p.upper() if len(p) == 1 or p in LONE_KEYS and p != "pause" else p.capitalize() for p in parts)


def hotkey_valid(text: str) -> bool:
    """A lone key only if it is an F key or Pause; otherwise Ctrl, Alt or Win plus something else."""
    try:
        parse_hotkey(text)
    except ValueError:
        return False
    parts = text.lower().replace(" ", "").split("+")
    if len(parts) == 1:
        return parts[0] in LONE_KEYS
    return any(p in ("ctrl", "alt", "win") for p in parts)


def down_keys() -> set[int]:
    """Which of the keys a hotkey can use are down. The only place that polls all of them."""
    return {vk for vk in HOTKEY_VKS if _is_down(vk)}


def cancel_start_menu() -> None:
    """Stops a lone Win release from opening the Start menu."""
    _tap(VK_UNASSIGNED)


class HotkeyRecorder:
    """Turns successive snapshots of the pressed keys into one hotkey (pure logic).

    Recording starts once nothing is down, so keys held on arrival are not part of it.
    The most keys seen at once wins (the first on a tie) and the hotkey ends when all
    are released. Esc cancels. feed() answers: "idle", "live" (see ``text``), "done"
    (see ``result``), "invalid" (released with something unusable; it listens again)
    or "cancel".
    """

    def __init__(self):
        self.armed = False
        self.peak: set[int] = set()
        self.text = ""
        self.result = ""

    def feed(self, down) -> str:
        down = set(down) & HOTKEY_VKS
        if not self.armed:
            self.armed = not down
            return "idle"
        if VK_ESCAPE in down:
            return "cancel"
        if down:
            self.text = hotkey_from_vks(down)
            if self.text.count("+") > hotkey_from_vks(self.peak).count("+") or not self.peak:
                self.peak = down
            return "live"
        if not self.peak:
            return "idle"
        text, self.peak = hotkey_from_vks(self.peak), set()
        if hotkey_valid(text):
            self.result = text
            return "done"
        return "invalid"


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


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
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetLastInputInfo.argtypes = (ctypes.POINTER(LASTINPUTINFO),)
kernel32.GetTickCount.restype = wintypes.DWORD
user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.CloseDesktop.argtypes = (wintypes.HANDLE,)

_injected_at = 0  # GetTickCount of our last SendInput


def _is_down(vk: int) -> bool:
    return user32.GetAsyncKeyState(vk) < 0


def _last_input() -> int:
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    user32.GetLastInputInfo(ctypes.byref(info))
    return info.dwTime


def idle_ms() -> int:
    """How long since the last key press or mouse move, anywhere in the session."""
    return _ms_apart(kernel32.GetTickCount(), _last_input())


def session_locked() -> bool:
    """True while Windows shows the lock screen: the input desktop is then out of reach."""
    desktop = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not desktop:
        return True
    user32.CloseDesktop(desktop)
    return False


def _ms_apart(a: int, b: int) -> int:
    """Distance between two GetTickCount values, which wrap around every 49 days."""
    delta = (a - b) & 0xFFFFFFFF
    return min(delta, 0x100000000 - delta)


class KeyboardMonitor:
    """Watches the hotkey and input activity on its own threads and reports events."""

    def __init__(self, hotkey: str, on_hotkey_down, on_hotkey_up):
        self.groups = parse_hotkey(hotkey)
        self.on_down, self.on_up = on_hotkey_down, on_hotkey_up
        self.last_typed = 0.0
        self.last_click = 0.0
        self._active = False
        self._rearm = False  # keys already held when the hotkey comes back must be released first
        self._thread_id = 0
        self._stopped = threading.Event()
        self._hotkey_seen = 0.0
        self._input_seen = _last_input()
        self._mouse_at = 0
        self._mouse_proc = HOOKPROC(self._mouse_hook)  # keep a reference alive

    def set_hotkey(self, hotkey: str) -> None:
        self.groups = parse_hotkey(hotkey)
        self._rearm = True

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="mouse").start()
        threading.Thread(target=self._poll, daemon=True, name="keyboard").start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(mouse_hook)

    def _mouse_hook(self, code, wparam, lparam):
        if code >= 0:
            self._mouse_at = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents.time
            if wparam in MOUSE_DOWN:  # the caret may have moved
                self.last_click = time.monotonic()
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _poll(self) -> None:
        while not self._stopped.wait(POLL_S):
            self._check_hotkey()
            self._check_typing()

    def _check_hotkey(self) -> None:
        if hotkey_paused.is_set():
            self._rearm = True
            if self._active:
                self._active = False
                self.on_up()
            return
        states = [[_is_down(vk) for vk in group] for group in self.groups]
        if any(map(any, states)):
            self._hotkey_seen = time.monotonic()
        combo = all(map(any, states))
        if self._rearm:
            if combo:
                return
            self._rearm = False
        if combo and not self._active:
            self._active = True
            cancel_start_menu()
            self.on_down()
        elif not combo and self._active:
            self._active = False
            self.on_up()

    def _check_typing(self) -> None:
        tick = _last_input()
        if tick == self._input_seen or _ms_apart(kernel32.GetTickCount(), tick) < SETTLE_MS:
            return
        self._input_seen = tick
        if time.monotonic() - self._hotkey_seen < HOTKEY_GRACE_S:
            return
        if _ms_apart(tick, self._mouse_at) > SAME_EVENT_MS and _ms_apart(tick, _injected_at) > SAME_EVENT_MS:
            self.last_typed = time.monotonic()


def _tap(vk: int) -> None:
    send([_key(vk, 0, 0), _key(vk, 0, KEYEVENTF_KEYUP)])


def _key(vk: int, scan: int, flags: int) -> INPUT:
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def send(inputs: list[INPUT]) -> None:
    global _injected_at
    array = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    _injected_at = kernel32.GetTickCount()


def foreground() -> int:
    return user32.GetForegroundWindow()


def ours_in_front() -> bool:
    """One of our own windows has the keyboard: dictation must not land in it."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == kernel32.GetCurrentProcessId()


def _chars(text: str) -> list[INPUT]:
    inputs = []
    for ch in text:
        if ch == "\n":
            inputs += [_key(VK_RETURN, 0, 0), _key(VK_RETURN, 0, KEYEVENTF_KEYUP)]
        else:
            data = ch.encode("utf-16-le")
            units = [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]
            inputs += [_key(0, u, KEYEVENTF_UNICODE | f) for f in (0, KEYEVENTF_KEYUP) for u in units]
    return inputs


def replace_text(old: str, new: str) -> None:
    """Swap ``old``, just typed before the caret, for ``new`` in one single SendInput.

    Only what differs is touched, so text that was already in the field is never at risk.
    """
    same = 0
    while same < min(len(old), len(new)) and old[same] == new[same]:
        same += 1
    removed = len(old[same:].encode("utf-16-le")) // 2
    back = [_key(VK_BACK, 0, f) for _ in range(removed) for f in (0, KEYEVENTF_KEYUP)]
    inputs = back + _chars(new[same:])
    if inputs:
        send(inputs)


def type_text(text: str, delay: float = 0.004) -> None:
    """Type Unicode text into whatever window has focus."""
    for ch in text:
        if ch == "\n":
            send([_key(VK_RETURN, 0, 0), _key(VK_RETURN, 0, KEYEVENTF_KEYUP)])
        else:
            data = ch.encode("utf-16-le")
            units = [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]
            send([_key(0, u, KEYEVENTF_UNICODE | f) for f in (0, KEYEVENTF_KEYUP) for u in units])
        time.sleep(delay)
