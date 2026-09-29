"""熔断状态机：NORMAL -> WARN(>=90%) -> TRIP(>=100%)。

两种消耗口径：
  - 工作空间总量：consumed = 当前已用积分（由 reader 直接给出）。
  - 单任务：consumed = 基线剩余 - 当前剩余（基线在任务开始时记录）。
两种都归一成『已消耗积分』喂给本状态机，逻辑与范围无关。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BreakerState(str, Enum):
    NORMAL = "NORMAL"
    WARN = "WARN"          # 软熔断：提示收尾
    TRIP = "TRIP"          # 硬熔断：停止任务


@dataclass
class Verdict:
    state: BreakerState
    consumed: int
    budget: int
    ratio: float
    message: str
    task_id: Optional[str] = None
    workspace: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "consumed": self.consumed,
            "budget": self.budget,
            "ratio": round(self.ratio, 4),
            "percent": round(self.ratio * 100, 1),
            "message": self.message,
            "task_id": self.task_id,
            "workspace": self.workspace,
        }


class Breaker:
    def __init__(self, budget: int, warn_ratio: float = 0.9, trip_ratio: float = 1.0):
        # budget <= 0 视为无上限（默认置空）：永不触发熔断
        self.budget = int(budget)
        self.warn_ratio = warn_ratio
        self.trip_ratio = trip_ratio

    def evaluate(self, consumed: int, workspace: Optional[str] = None,
                 task_id: Optional[str] = None) -> Verdict:
        consumed = max(0, int(consumed))
        if self.budget <= 0:  # 无上限：永远 NORMAL
            return Verdict(state=BreakerState.NORMAL, consumed=consumed, budget=self.budget,
                           ratio=0.0, message=f"无上限（消耗 {consumed}，未设预算）",
                           task_id=task_id, workspace=workspace)
        ratio = consumed / self.budget
        if ratio >= self.trip_ratio:
            state = BreakerState.TRIP
            message = (f"已达熔断上限 {int(self.trip_ratio*100)}%"
                       f"（消耗 {consumed}/{self.budget}），任务必须停止。")
        elif ratio >= self.warn_ratio:
            state = BreakerState.WARN
            message = (f"已达软熔断线 {int(self.warn_ratio*100)}%"
                       f"（消耗 {consumed}/{self.budget}），请尽快收尾。")
        else:
            state = BreakerState.NORMAL
            message = f"正常（消耗 {consumed}/{self.budget}，{ratio*100:.1f}%）"
        return Verdict(state=state, consumed=consumed, budget=self.budget,
                       ratio=ratio, message=message, task_id=task_id, workspace=workspace)


def evaluate(consumed: int, budget: int, warn_ratio: float = 0.9,
             trip_ratio: float = 1.0, workspace: Optional[str] = None,
             task_id: Optional[str] = None) -> Verdict:
    return Breaker(budget, warn_ratio, trip_ratio).evaluate(consumed, workspace, task_id)
