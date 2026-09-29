"""WorkBuddy 积分熔断工具。

两级熔断：
  - WARN (>= 90% 默认)：软熔断。写状态文件 + 弹通知，可选注入聊天消息提示 agent 收尾。
  - TRIP (>= 100% 默认)：硬熔断。停止当前生成 + 经配置 locator 关闭任务窗口（绝不关主窗口）。

数据源：UIA 读取 WorkBuddy 界面上的积分数值（需 WB 带 --force-renderer-accessibility 等
启动参数），OCR 截图兜底。工具是独立 Python 包 + CLI，不直接注入 LLM 上下文。
"""

__version__ = "0.1.0"

from .breaker import Breaker, BreakerState, evaluate  # noqa: F401
from .config import Config, resolve_home            # noqa: F401
