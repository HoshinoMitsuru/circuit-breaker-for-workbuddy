"""读取层：把『界面上的积分数值』变成整数。

UIA 读取依赖 WorkBuddy 带 --force-renderer-accessibility 启动；OCR 为截图兜底（可选依赖）。
两者都归一成『界面显示的整数』，field 口径（remaining/used）由上层决定如何换算成消耗。
"""

from .uia_reader import UIAReader, ReaderError
from .ocr_reader import OCRReader

__all__ = ["UIAReader", "OCRReader", "ReaderError"]
