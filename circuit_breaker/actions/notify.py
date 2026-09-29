"""Windows 通知：线程内弹 MessageBoxTimeoutW（带超时、置顶、系统模态）。

放在独立线程里，避免阻塞守护主循环。不引第三方库。
"""

import ctypes
import threading
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.MessageBoxTimeoutW.argtypes = [
    wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
    wintypes.UINT, wintypes.WORD, wintypes.DWORD,
]
_user32.MessageBoxTimeoutW.restype = ctypes.c_int

MB_OK = 0x0
MB_ICONWARNING = 0x30
MB_TOPMOST = 0x40000
MB_SYSTEMMODAL = 0x1000


def notify(text: str, title: str = "积分熔断"):
    def _run():
        try:
            _user32.MessageBoxTimeoutW(
                0, text, title,
                MB_OK | MB_ICONWARNING | MB_TOPMOST | MB_SYSTEMMODAL,
                0, 8000,
            )
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
