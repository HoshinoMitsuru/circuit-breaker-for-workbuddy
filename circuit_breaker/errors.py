"""错误码目录：一个码只对应一个根因，fixes 给可执行动作。

设计遵循 windows-uia-automation 技能的坑 13：报错不得混多根因，否则会把人引向错误修复动作。
兜底码保持中性（只描述发生了什么，不断言原因）。
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ErrorSpec:
    code: str
    title: str
    severity: str = "ERROR"          # ERROR | WARN | INFO
    causes: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)


CATALOG = {
    "E-WIN-001": ErrorSpec(
        "E-WIN-001", "找不到 WorkBuddy 窗口",
        causes=[
            "WorkBuddy 进程未启动",
            "WorkBuddy 在跑但所有窗口都不可见（缩到托盘/最小化）",
            "WorkBuddy 不是从默认路径启动，exe 名不匹配",
        ],
        fixes=[
            "确认 WorkBuddy 已启动（任务管理器里有 WorkBuddy.exe）",
            "若只在托盘：点开主窗口让它可见，不要最小化",
            "若仍找不到：用 --exe 显式指定 exe 路径，或 --title 指定窗口标题",
        ],
    ),
    "E-UIA-002": ErrorSpec(
        "E-UIA-002", "WorkBuddy 无障碍树为空壳",
        causes=[
            "启动未带 --force-renderer-accessibility，Chromium 不构建无障碍树",
            "窗口最小化/被完全遮挡，renderer 节流",
        ],
        fixes=[
            "完全退出 WorkBuddy，带参重启：WorkBuddy.exe --force-renderer-accessibility "
            "--disable-features=CalculateNativeWinOcclusion --disable-backgrounding-occluded-windows "
            "--disable-renderer-backgrounding --disable-background-timer-throttling",
            "重启后保持窗口可见、不要最小化",
        ],
    ),
    "E-READ-003": ErrorSpec(
        "E-READ-003", "读不到积分数值",
        causes=[
            "locator 的 keyword/value_regex 与界面实际文本不匹配",
            "积分显示不在当前搜索域内（scope 设错）",
            "界面文本是图片而非文本（需走 OCR 兜底）",
        ],
        fixes=[
            "运行 circuit-breaker discover 重新定位积分元素",
            "若积分是图片：开启 OCR 兜底（pip install pytesseract pillow + 安装 tesseract）",
            "手动在 config.json 的 reader 里改 keyword / value_regex / scope",
        ],
    ),
    "E-READ-004": ErrorSpec(
        "E-READ-004", "读到的积分数值无法解析为非负整数",
        causes=["文本里混入了非数字字符", "value_regex 捕获组取到空"],
        fixes=[
            "检查 reader.value_regex 是否只捕获数字（含千分位逗号）",
            "确认 reader.field 是 remaining 还是 used，与界面一致",
        ],
    ),
    "E-CFG-005": ErrorSpec(
        "E-CFG-005", "配置写入失败（数据目录不可写）",
        causes=["程序被装进只读目录（如 Program Files）", "CB_HOME 指向只读路径"],
        fixes=[
            "用环境变量 CB_HOME 指向可写目录，例如 set CB_HOME=%LOCALAPPDATA%\\cb",
            "或以可写路径运行：python -m circuit_breaker.cli ...",
        ],
    ),
    "E-ACT-006": ErrorSpec(
        "E-ACT-006", "硬熔断关闭任务窗口未配置 locator",
        causes=["config.actions.hard.close_locator 为空", "discover 未捕获到关闭控件"],
        fixes=[
            "运行 circuit-breaker discover 捕获关闭控件并写入 close_locator",
            "或临时把 actions.hard.close_task_window 设为 false，仅停止生成 + 通知",
        ],
    ),
    "E-GEN-012": ErrorSpec(
        "E-GEN-012", "发生未分类异常",
        causes=["未知运行时错误"],
        fixes=[
            "看『详情』里的异常类型与消息——它通常已说明问题",
            "注意这条不代表界面/网络有问题；能确定的错误会各自报具体码",
        ],
    ),
}


def describe(code: str) -> ErrorSpec:
    return CATALOG.get(code, CATALOG["E-GEN-012"])


def emit(code: str, detail: str = "", extra: dict = None):
    """统一输出错误块（逐行，便于日志面板着色）。"""
    spec = describe(code)
    lines = [f"{spec.severity:<5} {spec.code} {spec.title}"]
    if detail:
        lines.append(f"{'':<5} 详情　　：{detail}")
    for c in spec.causes:
        lines.append(f"{'':<5} 可能原因：{c}")
    for f in spec.fixes:
        lines.append(f"{'':<5} 怎么办　：{f}")
    if extra:
        lines.append(f"{'':<5} 现场数据：{extra}")
    return "\n".join(lines)
