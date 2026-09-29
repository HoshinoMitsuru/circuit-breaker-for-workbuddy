"""配置层：路径解析唯一事实来源 + 两级预算 + 阈值 + reader/soft/hard 设置。

路径解析规则（遵循 windows-uia-automation 坑 11）：
  1. 环境变量 CB_HOME 显式指定；
  2. 否则若是 exe（frozen）取 exe 旁 data/；
  3. 否则取源码目录旁 data/；
  4. 以上均不可写时退回 %LOCALAPPDATA%/workbuddy-points-circuit-breaker。
相对路径一律按 home 解析，绝不看当前工作目录。
"""

import json
import os
import sys
from typing import Dict, Optional


def resolve_home() -> str:
    env = os.environ.get("CB_HOME")
    if env:
        return os.path.abspath(env)

    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    cand = os.path.join(base, "data")
    try:
        os.makedirs(cand, exist_ok=True)
        probe = os.path.join(cand, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return cand
    except OSError:
        pass

    local = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "workbuddy-points-circuit-breaker",
    )
    os.makedirs(local, exist_ok=True)
    return local


DEFAULT_CONFIG = {
    "default_budget": 0,                    # 默认预算：0=无上限（不熔断）；正整数=积分上限
    "thresholds": {"warn": 0.9, "trip": 1.0},
    "workspaces": {},                       # { ws_name: { "budget": int, "tasks": { task_id: {"budget": int} } } }
    "reader": {
        "mode": "uia",                      # uia | ocr | auto
        "exe": "WorkBuddy.exe",
        "title": "WorkBuddy",
        "keyword": "共消耗",                # WorkBuddy 每条 AI 回复页脚：共消耗 X Hy3
        "value_regex": r"共消耗\s*(\d[\d,]*)",
        "scope": "whole",                   # 页脚在对话滚动区，不在顶栏
        "cumulative": False,                # False=单轮消耗，按页脚指纹累计；True=页脚为会话累计
        "field": "used",                    # 页脚即已用，无需 remaining 换算
        "normalize_thousands": True,
        "ocr_lang": "chi_sim",
    },
    "soft": {
        "write_state_file": True,
        "notify": True,
        "inject_message": False,
        "inject_text": "【熔断警告】积分已用至 90% 上限，请立即收尾并输出摘要。",
        "notify_text": "积分熔断预警：已用至 90%，请尽快收尾。",
    },
    "hard": {
        "close_task_window": True,
        "close_locator": {"name_contains": "关闭"},  # 只关任务会话，resolver 排除系统关闭
        "notify_text": "积分熔断：已达 100% 上限，任务已停止。",
    },
    "poll_interval": 5,
    "window": {"exe": "WorkBuddy.exe", "title": "WorkBuddy"},
}


class Config:
    def __init__(self, path: Optional[str] = None):
        self.home = resolve_home()
        self.path = path or os.path.join(self.home, "config.json")
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = _deep_merge(DEFAULT_CONFIG, loaded)
                return merged
            except (json.JSONDecodeError, OSError):
                pass
        return _deep_merge({}, DEFAULT_CONFIG)

    def save(self):
        os.makedirs(self.home, exist_ok=True)
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            # 用错误码而不是静默失败（坑 13）
            raise RuntimeError(f"E-CFG-005|{e}")

    # ---- 工作空间 / 单任务预算 ----
    def workspace_budget(self, ws: str) -> int:
        ws_cfg = self.data["workspaces"].get(ws, {})
        if "budget" in ws_cfg:
            return int(ws_cfg["budget"])
        return int(self.data["default_budget"])

    def task_budget(self, ws: str, task_id: str) -> int:
        ws_cfg = self.data["workspaces"].get(ws, {})
        tasks = ws_cfg.get("tasks", {})
        if task_id in tasks and "budget" in tasks[task_id]:
            return int(tasks[task_id]["budget"])
        return self.workspace_budget(ws)

    def set_workspace_budget(self, ws: str, budget: int):
        self.data.setdefault("workspaces", {}).setdefault(ws, {})["budget"] = int(budget)
        self.save()

    def set_task_budget(self, ws: str, task_id: str, budget: int):
        self.data.setdefault("workspaces", {}).setdefault(ws, {}).setdefault("tasks", {})[task_id] = {"budget": int(budget)}
        self.save()

    # ---- 阈值 ----
    @property
    def warn_ratio(self) -> float:
        return float(self.data["thresholds"]["warn"])

    @property
    def trip_ratio(self) -> float:
        return float(self.data["thresholds"]["trip"])

    # ---- reader / soft / hard ----
    @property
    def reader(self) -> Dict:
        return self.data["reader"]

    @property
    def soft(self) -> Dict:
        return self.data["soft"]

    @property
    def hard(self) -> Dict:
        return self.data["hard"]

    # ---- 状态文件路径 ----
    def state_file(self, ws: str, task_id: Optional[str] = None) -> str:
        name = f".cb_state_{ws}.json" if not task_id else f".cb_state_{ws}_{task_id}.json"
        return os.path.join(self.home, name)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
