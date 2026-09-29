"""UIA 助手：定位 WorkBuddy 窗口 + 遍历控件树。

遵循 windows-uia-automation 技能：
  - 用 EnumWindows（含隐藏窗口）找 WB，避免托盘窗口漏检（坑 1）；
  - 区分『进程没跑 / 窗口不可见 / 无障碍树空壳』三种根因（坑 13）；
  - DFS 文档顺序遍历（坑 5）；读取层免前台即可（最小化也能读，坑 2 更正）。
"""

import ctypes
import re
from ctypes import wintypes

import uiautomation as auto

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.IsWindowVisible.argtypes = [wintypes.HWND]
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _process_path(pid: int) -> str:
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        b = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, b, ctypes.byref(n)):
            return b.value
        return ""
    finally:
        k32.CloseHandle(h)


def enum_top_windows():
    rows = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lp):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        n = u32.GetWindowTextLengthW(hwnd)
        t = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, t, n + 1)
        c = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, c, 256)
        rows.append({
            "hwnd": int(hwnd), "pid": pid.value,
            "visible": bool(u32.IsWindowVisible(hwnd)),
            "class": c.value, "title": t.value,
            "exe": _process_path(pid.value),
        })
        return True

    u32.EnumWindows(cb, 0)
    return rows


def find_workbuddy_window(exe: str = "WorkBuddy.exe", title: str = "WorkBuddy"):
    """返回 (window_dict, status)。status: ok | no_process | not_visible。"""
    wins = enum_top_windows()
    wb = [w for w in wins if w["exe"] and exe.lower() in w["exe"].lower()]
    if not wb:
        return None, "no_process"
    visible = [w for w in wb if w["visible"]]
    if not visible:
        return wb[0], "not_visible"
    title_match = [w for w in visible if title.lower() in w["title"].lower()]
    return (title_match[0] if title_match else visible[0]), "ok"


def dfs_walk(root, maxdepth: int = 16, limit: int = 6000):
    """文档顺序 DFS（栈 + 子节点 reversed）。"""
    stack = [(root, 0)]
    n = 0
    while stack and n < limit:
        ctrl, d = stack.pop()
        if d > maxdepth:
            continue
        n += 1
        yield ctrl, d
        try:
            children = ctrl.GetChildren()
        except Exception:
            children = []
        for ch in reversed(children):
            stack.append((ch, d + 1))


def collect_block_text(ctrl, child_depth: int = 1) -> str:
    """收集节点自身 Name + 限定深度子节点 Name，用于『标签+值』不在同一节点时仍能命中。"""
    parts = []

    def _gather(c, depth):
        try:
            name = c.Name or ""
        except Exception:
            name = ""
        if name:
            parts.append(name)
        if depth < child_depth:
            try:
                for ch in c.GetChildren():
                    _gather(ch, depth + 1)
            except Exception:
                pass

    _gather(ctrl, 0)
    return " ".join(parts)


def parse_int(raw: str, normalize_thousands: bool = True) -> int:
    s = (raw or "").strip()
    if normalize_thousands:
        s = s.replace(",", "").replace("，", "")
    s = re.sub(r"\s+", "", s)
    if not re.fullmatch(r"\d+", s):
        raise ValueError(f"无法解析为非负整数: {raw!r}")
    return int(s)
