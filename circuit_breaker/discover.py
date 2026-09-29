"""discover：只读定位积分元素与停止/关闭候选控件，输出建议 locator 片段。

不改任何东西，仅读取 WorkBuddy 无障碍树。需要 WB 带 --force-renderer-accessibility 启动。
"""

import json
import re

import uiautomation as auto

from . import errors
from .ui import collect_block_text, dfs_walk, find_workbuddy_window

KEYWORDS = ["积分", "点", "额度", "余", "credit", "point", "配额", "token",
            "消耗", "可用", "剩余", "余额", "用量", "quota", "budget"]


def _parent_chain(ctrl, maxlen: int = 4):
    chain = []
    cur = ctrl
    for _ in range(maxlen):
        try:
            p = cur.GetParent()
        except Exception:
            break
        if p is None or p == cur:
            break
        try:
            tn = p.ControlTypeName
        except Exception:
            tn = ""
        try:
            cls = p.ClassName
        except Exception:
            cls = ""
        try:
            nm = p.Name or ""
        except Exception:
            nm = ""
        chain.append({"type": tn, "class": cls, "name": nm[:40]})
        cur = p
    return chain


def _guess_keyword(text: str) -> str:
    low = text.lower()
    for k in KEYWORDS:
        if k.lower() in low:
            return k
    return "积分"


def discover(config, apply: bool = False) -> dict:
    rc = config.reader
    win, status = find_workbuddy_window(rc.get("exe", "WorkBuddy.exe"),
                                        rc.get("title", "WorkBuddy"))
    if win is None or status == "no_process":
        print(errors.emit("E-WIN-001", extra={"exe": rc.get("exe")}))
        return None
    if status == "not_visible":
        print("[WARN] WorkBuddy 窗口不可见（缩在托盘/最小化）。先点开主窗口再 discover。")

    ctrl = auto.ControlFromHandle(win["hwnd"])
    nodes = list(dfs_walk(ctrl))
    if len(nodes) <= 1:
        print(errors.emit("E-UIA-002", extra={"hwnd": win["hwnd"], "nodes": len(nodes)}))
        return None

    print(f"主窗口 hwnd={win['hwnd']} 节点数={len(nodes)}")
    print("\n=== 命中积分类文本（keyword + 数值）===")
    hits = []
    for c, _d in nodes:
        block = collect_block_text(c)
        if not block:
            continue
        if any(k.lower() in block.lower() for k in KEYWORDS):
            m = re.search(r"(\d[\d,]*)", block)
            val = m.group(1) if m else None
            try:
                tn = c.ControlTypeName
            except Exception:
                tn = ""
            try:
                cls = c.ClassName
            except Exception:
                cls = ""
            try:
                rect = c.BoundingRectangle
            except Exception:
                rect = None
            top = rect.top if rect else -1
            info = {"type": tn, "class": cls, "text": block[:60],
                    "number": val, "top": top, "chain": _parent_chain(c)}
            hits.append(info)
            print(f"  [{tn}] cls={cls} top={top} text={block[:60]!r} num={val}")

    print("\n=== 候选按钮（停止/关闭/会话）===")
    buttons = []
    for c, _d in nodes:
        try:
            tn = c.ControlTypeName
        except Exception:
            tn = ""
        try:
            nm = c.Name or ""
        except Exception:
            nm = ""
        if tn == "ButtonControl" and nm:
            try:
                rect = c.BoundingRectangle
            except Exception:
                rect = None
            top = rect.top if rect else -1
            role = ""
            if any(x in nm for x in ("停止", "stop", "Stop")):
                role = "STOP"
            elif any(x in nm for x in ("关闭", "close", "Close")):
                role = "CLOSE"
            rec = {"text": nm, "top": top, "role": role}
            buttons.append(rec)
            print(f"  {role or '?':<6} top={top} text={nm!r}")

    suggestion = {}
    if hits:
        # 优先用『共消耗』页脚（WorkBuddy 真实消耗信号），否则退回到命中关键词
        ch = next((h for h in hits if "共消耗" in (h["text"] or "")), None)
        if ch:
            suggestion["reader"] = {
                "keyword": "共消耗",
                "value_regex": r"共消耗\s*(\d[\d,]*)",
                "scope": "whole",
                "cumulative": False,
                "field": "used",
            }
        else:
            num_hit = next((h for h in hits if h["number"]), hits[0])
            suggestion["reader"] = {
                "keyword": _guess_keyword(num_hit["text"]),
                "value_regex": r"(\d[\d,]*)",
                "scope": "top_bar" if (num_hit["top"] < 200) else "whole",
                "field": "remaining",
            }
    if buttons:
        close = next((b for b in buttons if b["role"] == "CLOSE"), None)
        if close:
            # 硬熔断只关任务会话：resolver 会自动排除标题栏系统关闭
            suggestion["hard"] = {"close_locator": {"name_contains": "关闭"}}

    print("\n=== 建议写入 config.json 的片段 ===")
    print(json.dumps(suggestion, ensure_ascii=False, indent=2))

    if apply and suggestion:
        if "reader" in suggestion:
            config.data.setdefault("reader", {}).update(suggestion["reader"])
        if "hard" in suggestion:
            config.data.setdefault("hard", {}).update(suggestion["hard"])
        try:
            config.save()
            print("[OK] 已写入 config.json：", json.dumps(suggestion, ensure_ascii=False))
        except Exception as e:
            print(errors.emit("E-CFG-005", detail=str(e)))

    return suggestion
