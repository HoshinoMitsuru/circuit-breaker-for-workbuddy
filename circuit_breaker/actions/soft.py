"""软熔断动作（90%）：写状态文件 + 弹通知 + 可选注入聊天消息。

『提示 agent 尽快收尾』由外部 CLI 直接注入 LLM 上下文做不到，故采用组合：
  - 状态文件 .cb_state_<ws>.json：agent 若约定每轮读取即可自行收尾；
  - Windows 通知：用户可见；
  - 可选注入消息：往当前对话输入框写一条警告并发送（默认关闭，实验性）。
"""

import json
import time

import uiautomation as auto

from .. import errors
from ..ui import dfs_walk, find_workbuddy_window
from .notify import notify


def _write_state(config, verdict, action: str):
    if not config.soft.get("write_state_file", True):
        return
    path = config.state_file(verdict.workspace or "_", verdict.task_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**verdict.to_dict(), "action": action, "ts": time.time()},
                      f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _inject(text: str, reader_cfg: dict):
    """实验性：往对话输入框注入提示并发送。需 WorkBuddy 窗口可见。"""
    try:
        win, _ = find_workbuddy_window(reader_cfg.get("exe", "WorkBuddy.exe"),
                                       reader_cfg.get("title", "WorkBuddy"))
        if win is None:
            return
        ctrl = auto.ControlFromHandle(win["hwnd"])
        editor = None
        for c, _d in dfs_walk(ctrl):
            try:
                tn = c.ControlTypeName
            except Exception:
                tn = ""
            try:
                cls = c.ClassName
            except Exception:
                cls = ""
            if "ProseMirror" in cls or tn in ("EditControl", "DocumentControl"):
                editor = c
        if editor is None:
            return
        editor.SetFocus()
        auto.SendKeys(text, waitTime=0.01)
        auto.SendKeys("{Enter}", waitTime=0.01)
    except Exception:
        pass


def soft_fuse(verdict, config) -> str:
    _write_state(config, verdict, "soft")
    if config.soft.get("notify", True):
        notify(config.soft.get("notify_text", ""), "积分熔断预警")
    if config.soft.get("inject_message", False):
        _inject(config.soft.get("inject_text", ""), config.reader)
    return "soft"
