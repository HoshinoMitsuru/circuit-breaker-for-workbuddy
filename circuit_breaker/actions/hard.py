"""硬熔断动作（100%）：写 TRIP 状态 + 通知 + 停止当前生成 + 经 locator 关闭任务窗口。

安全红线：绝不关闭 WorkBuddy 主窗口。关闭只针对『任务会话』控件，且必须有 close_locator
配置；未配置时仅停止生成 + 通知（遵循用户『破坏性操作先确认』的工程习惯）。
"""

import json
import time

import uiautomation as auto

from .. import errors
from ..ui import dfs_walk, find_workbuddy_window
from .notify import notify


def _write_state(config, verdict, action: str):
    path = config.state_file(verdict.workspace or "_", verdict.task_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**verdict.to_dict(), "action": action, "ts": time.time()},
                      f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _stop_generating(config):
    """best-effort：找到名称含『停止/stop』的按钮并 Invoke，打断当前生成。"""
    win, _ = find_workbuddy_window(config.reader.get("exe", "WorkBuddy.exe"),
                                   config.reader.get("title", "WorkBuddy"))
    if win is None:
        return
    ctrl = auto.ControlFromHandle(win["hwnd"])
    target = None
    for c, _d in dfs_walk(ctrl):
        try:
            tn = c.ControlTypeName
        except Exception:
            tn = ""
        try:
            nm = c.Name or ""
        except Exception:
            nm = ""
        if tn == "ButtonControl" and ("停止" in nm or "stop" in nm.lower()):
            target = c
            break
    if target is None:
        return
    pat = target.GetPattern(10000)  # UIA_InvokePatternId
    if pat is not None:
        pat.Invoke()
    else:
        try:
            target.Click()
        except Exception:
            pass


def _is_system_close(button) -> bool:
    """判断『关闭』按钮是否位于标题栏（与 最小化/最大化 同排），即关整个应用的系统按钮。"""
    try:
        parent = button.GetParent()
    except Exception:
        return False
    if parent is None:
        return False
    try:
        sibs = parent.GetChildren()
    except Exception:
        sibs = []
    for s in sibs:
        try:
            tn = s.ControlTypeName
        except Exception:
            tn = ""
        try:
            nm = s.Name or ""
        except Exception:
            nm = ""
        if tn == "ButtonControl" and ("最小化" in nm or "最大化" in nm):
            return True
    return False


def _close_task(config):
    loc = config.hard.get("close_locator")
    if not loc:
        raise RuntimeError(errors.emit("E-ACT-006"))
    win, _ = find_workbuddy_window(config.reader.get("exe", "WorkBuddy.exe"),
                                   config.reader.get("title", "WorkBuddy"))
    if win is None:
        return
    ctrl = auto.ControlFromHandle(win["hwnd"])
    name_contains = loc.get("name_contains", "关闭")
    candidates = []
    for c, _d in dfs_walk(ctrl):
        try:
            tn = c.ControlTypeName
        except Exception:
            tn = ""
        try:
            nm = c.Name or ""
        except Exception:
            nm = ""
        if tn == "ButtonControl" and name_contains in nm:
            if _is_system_close(c):
                continue  # 绝不关整个应用
            candidates.append(c)
    if not candidates:
        raise RuntimeError("未找到『任务会话』关闭控件（已排除系统关闭）；"
                           "close_locator=%s" % name_contains)
    if len(candidates) > 1:
        # 多候选时不开盲盒，避免关错会话
        names = [ (c.Name or "") for c in candidates ]
        raise RuntimeError("存在多个非系统『关闭』候选，无法唯一确定任务会话关闭：%s" % names)
    target = candidates[0]
    pat = target.GetPattern(10000)
    if pat is not None:
        pat.Invoke()
    else:
        try:
            target.Click()
        except Exception:
            pass


def hard_fuse(verdict, config) -> str:
    _write_state(config, verdict, "hard")
    if config.hard.get("notify", True):
        notify(config.hard.get("notify_text", ""), "积分熔断")
    try:
        _stop_generating(config)
    except Exception:
        pass
    if config.hard.get("close_task_window", True):
        try:
            _close_task(config)
        except Exception as e:
            # 未配置 locator：只停止生成 + 通知，不关窗口（安全）
            print(errors.emit("E-ACT-006", detail=str(e),
                              extra={"workspace": verdict.workspace}))
    return "hard"
