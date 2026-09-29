"""守护 / 单次检测：把读取层、状态机、动作层串起来。

消耗口径（用户确认：页脚=单轮消耗）：
  WorkBuddy 每条 AI 回复页脚显示『共消耗 X Hy3』。监控用『页脚文本指纹』检测新回复，
  每条新页脚把其 X 累加进消耗：
    - cumulative=False（默认，单轮）：每条新页脚 delta = X；
    - cumulative=True（页脚为会话累计）：delta = X - 上次X。
  单任务消耗 = 该任务累计；工作空间总 = 监控本地累计（界面不显示总量，近似）。

错误抑制：轮询间隔小，持续性故障会刷屏，故同码 60s 内只完整输出一次。
"""

import json
import os
import time

from . import errors
from .actions import hard_fuse, soft_fuse
from .breaker import Breaker, BreakerState
from .config import Config
from .reader import OCRReader, UIAReader


def _build_reader(cfg: dict):
    mode = cfg.get("mode", "uia")
    if mode == "ocr":
        return OCRReader(cfg)
    if mode == "auto":
        return ("auto", UIAReader(cfg), OCRReader(cfg))
    return UIAReader(cfg)


def _read_latest(reader):
    if isinstance(reader, tuple) and reader[0] == "auto":
        _, uia, ocr = reader
        try:
            return uia.read_latest()
        except Exception as e:
            print("[INFO] UIA 读取失败，尝试 OCR 兜底：", e)
            return ocr.read_latest()
    return reader.read_latest()


def _task_path(config: Config, ws: str, task_id: str) -> str:
    return os.path.join(config.home, f".cb_task_{ws}_{task_id}.json")


def _ws_path(config: Config, ws: str) -> str:
    return os.path.join(config.home, f".cb_ws_{ws}.json")


def _load_state(path: str) -> dict:
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"total": 0, "last_footer": "", "last_value": 0}


def _accumulate(state: dict, value: int, text: str, cumulative: bool) -> int:
    if text != state.get("last_footer"):
        if cumulative:
            delta = max(0, value - state.get("last_value", 0))
        else:
            delta = value
        state["total"] = state.get("total", 0) + delta
        state["last_footer"] = text
        state["last_value"] = value
    return state["total"]


def check_once(config: Config, ws: str, task_id: str = None, act: bool = True):
    """单次检测。返回 (verdict, raw_value)。act=True 时按状态触发软/硬熔断。"""
    reader = _build_reader(config.reader)
    value, text = _read_latest(reader)
    cumulative = bool(config.reader.get("cumulative", False))

    if task_id:
        tstate = _load_state(_task_path(config, ws, task_id))
        consumed = _accumulate(tstate, value, text, cumulative)
        with open(_task_path(config, ws, task_id), "w", encoding="utf-8") as f:
            json.dump(tstate, f)
        wstate = _load_state(_ws_path(config, ws))
        _accumulate(wstate, value, text, cumulative)
        with open(_ws_path(config, ws), "w", encoding="utf-8") as f:
            json.dump(wstate, f)
        budget = config.task_budget(ws, task_id)
    else:
        wstate = _load_state(_ws_path(config, ws))
        consumed = _accumulate(wstate, value, text, cumulative)
        with open(_ws_path(config, ws), "w", encoding="utf-8") as f:
            json.dump(wstate, f)
        budget = config.workspace_budget(ws)

    verdict = Breaker(budget, config.warn_ratio, config.trip_ratio).evaluate(
        consumed, workspace=ws, task_id=task_id)

    if act:
        if verdict.state == BreakerState.WARN:
            soft_fuse(verdict, config)
        elif verdict.state == BreakerState.TRIP:
            hard_fuse(verdict, config)
    return verdict, value


def _write_light_state(config: Config, verdict, action: str):
    path = config.state_file(verdict.workspace or "_", verdict.task_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**verdict.to_dict(), "action": action, "ts": time.time()},
                      f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def run(config: Config, ws: str, task_id: str = None, poll_interval: int = None,
        once: bool = False):
    poll = poll_interval or config.data.get("poll_interval", 5)
    reader = _build_reader(config.reader)
    cumulative = bool(config.reader.get("cumulative", False))
    last_err = 0
    last_soft = 0
    tripped = False

    def loop_body():
        nonlocal last_err, last_soft, tripped
        try:
            value, text = _read_latest(reader)
        except Exception as e:
            now = time.time()
            if now - last_err > 60:
                print(errors.emit("E-READ-003", detail=str(e)))
                last_err = now
            else:
                print(f"[SUPPRESSED] 读取失败：{e}")
            return

        if task_id:
            tstate = _load_state(_task_path(config, ws, task_id))
            consumed = _accumulate(tstate, value, text, cumulative)
            with open(_task_path(config, ws, task_id), "w", encoding="utf-8") as f:
                json.dump(tstate, f)
            wstate = _load_state(_ws_path(config, ws))
            _accumulate(wstate, value, text, cumulative)
            with open(_ws_path(config, ws), "w", encoding="utf-8") as f:
                json.dump(wstate, f)
            budget = config.task_budget(ws, task_id)
        else:
            wstate = _load_state(_ws_path(config, ws))
            consumed = _accumulate(wstate, value, text, cumulative)
            with open(_ws_path(config, ws), "w", encoding="utf-8") as f:
                json.dump(wstate, f)
            budget = config.workspace_budget(ws)

        verdict = Breaker(budget, config.warn_ratio, config.trip_ratio).evaluate(
            consumed, workspace=ws, task_id=task_id)
        _write_light_state(config, verdict, "none")

        if verdict.state == BreakerState.TRIP:
            hard_fuse(verdict, config)
            tripped = True
            print(f"[TRIP] {verdict.message} → 已执行硬熔断（停止任务）")
            return
        if verdict.state == BreakerState.WARN:
            now = time.time()
            if now - last_soft > 60:
                soft_fuse(verdict, config)
                last_soft = now
                print(f"[WARN] {verdict.message} → 已执行软熔断（提示收尾）")
            else:
                print(f"[WARN] {verdict.message}（抑制，60s 内已提示）")
        else:
            print(f"[OK] {verdict.message}  最新页脚={text[:40]!r}")

    if once:
        loop_body()
        return

    print(f"守护启动：工作空间={ws} 任务={task_id or '总'} 间隔={poll}s "
          f"cumulative={cumulative}")
    try:
        while not tripped:
            loop_body()
            if tripped:
                break
            time.sleep(poll)
    except KeyboardInterrupt:
        print("\n守护已停止（Ctrl+C）")
