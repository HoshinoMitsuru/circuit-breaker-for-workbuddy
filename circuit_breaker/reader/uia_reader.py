"""UIA 读取器：遍历 WorkBuddy 无障碍树，按 keyword + value_regex 提取积分数值。"""

import re

import uiautomation as auto

from .. import errors
from ..ui import (
    collect_block_text,
    dfs_walk,
    find_workbuddy_window,
    parse_int,
)


class ReaderError(RuntimeError):
    pass


class UIAReader:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.exe = cfg.get("exe", "WorkBuddy.exe")
        self.title = cfg.get("title", "WorkBuddy")
        self.keyword = cfg.get("keyword", "积分")
        self.value_regex = re.compile(cfg.get("value_regex", r"(\d[\d,]*)"))
        self.scope = cfg.get("scope", "top_bar")
        self.normalize_thousands = bool(cfg.get("normalize_thousands", True))
        self.last_text = None

    def read_latest(self):
        """返回 (value:int, text:str)。收集所有命中页脚，取文档顺序最后一条（最新 AI 回复）。"""
        win, status = find_workbuddy_window(self.exe, self.title)
        if win is None:
            raise ReaderError(errors.emit("E-WIN-001", extra={"exe": self.exe}))
        if status == "no_process":
            raise ReaderError(errors.emit("E-WIN-001", extra={"exe": self.exe}))

        ctrl = auto.ControlFromHandle(win["hwnd"])
        try:
            rect = ctrl.BoundingRectangle
        except Exception:
            rect = None
        h = (rect.bottom - rect.top if rect else 0) or 0
        top_limit = (rect.top + h * 0.3) if h else (rect.top + 200 if rect else 200)

        hits = []
        seen = 0
        for c, _d in dfs_walk(ctrl):
            seen += 1
            try:
                r = c.BoundingRectangle
            except Exception:
                r = None
            if self.scope == "top_bar" and r and r.top > top_limit:
                continue
            block = collect_block_text(c)
            if not block:
                continue
            if self.keyword and self.keyword not in block:
                continue
            m = self.value_regex.search(block)
            if m:
                try:
                    val = parse_int(m.group(1), self.normalize_thousands)
                except ValueError as e:
                    raise ReaderError(errors.emit("E-READ-004", detail=str(e),
                                                  extra={"block": block[:80]}))
                hits.append((val, block))
        if not hits:
            if seen <= 1:
                raise ReaderError(errors.emit("E-UIA-002",
                                              extra={"hwnd": win["hwnd"], "nodes": seen}))
            raise ReaderError(errors.emit("E-READ-003",
                                          extra={"keyword": self.keyword, "scope": self.scope}))
        value, text = hits[-1]  # 最新一条
        self.last_text = text
        return value, text

    def read(self) -> int:
        value, _ = self.read_latest()
        return value
