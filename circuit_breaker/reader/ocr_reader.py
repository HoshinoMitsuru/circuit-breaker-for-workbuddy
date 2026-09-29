"""OCR 读取器：截图 WorkBuddy 窗口 → tesseract 识别 → 同规则提取积分。

可选依赖（pip install pytesseract pillow + 安装 tesseract 二进制）。未安装时静默降级报错，
不阻塞主流程（遵循技能：OCR 依赖标可选）。
"""

import os
import re
import tempfile

import uiautomation as auto

from .. import errors
from ..ui import find_workbuddy_window, parse_int
from .uia_reader import ReaderError


class OCRReader:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.exe = cfg.get("exe", "WorkBuddy.exe")
        self.title = cfg.get("title", "WorkBuddy")
        self.keyword = cfg.get("keyword", "积分")
        self.value_regex = re.compile(cfg.get("value_regex", r"(\d[\d,]*)"))
        self.scope = cfg.get("scope", "top_bar")
        self.lang = cfg.get("ocr_lang", "chi_sim")
        self.normalize_thousands = bool(cfg.get("normalize_thousands", True))
        self.last_text = None

    def read(self) -> int:
        win, status = find_workbuddy_window(self.exe, self.title)
        if win is None or status == "no_process":
            raise ReaderError(errors.emit("E-WIN-001", extra={"exe": self.exe}))

        ctrl = auto.ControlFromHandle(win["hwnd"])
        try:
            bmp = auto.Bitmap.FromControl(ctrl)
        except Exception as e:
            raise ReaderError(errors.emit("E-UIA-002", detail=f"截图失败: {e}"))
        path = os.path.join(tempfile.gettempdir(), "cb_ocr.png")
        bmp.ToFile(path)

        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            raise ReaderError(
                "OCR 依赖未安装：pip install pytesseract pillow，并安装 tesseract 二进制"
            )

        img = Image.open(path)
        if self.scope == "top_bar":
            img = img.crop((0, 0, img.width, int(img.height * 0.3)))
        data = pytesseract.image_to_data(
            img, lang=self.lang, output_type=pytesseract.Output.DICT
        )
        rows = {}
        for i in range(len(data["text"])):
            t = (data["text"][i] or "").strip()
            if not t:
                continue
            rows.setdefault(data["top"][i] // 20, []).append(t)
        block = " ".join(" ".join(v) for v in rows.values())

        if self.keyword and self.keyword in block:
            search_in = block
        else:
            search_in = block  # 关键词可能被 OCR 误识别，仍对整个块试正则
        m = self.value_regex.search(search_in)
        if m:
            try:
                val = parse_int(m.group(1), self.normalize_thousands)
            except ValueError as e:
                raise ReaderError(errors.emit("E-READ-004", detail=str(e)))
            self.last_text = block
            return val, block
        raise ReaderError(errors.emit("E-READ-003",
                                      extra={"keyword": self.keyword, "ocr_block": block[:120]}))

    def read(self) -> int:
        value, _ = self.read_latest()
        return value
