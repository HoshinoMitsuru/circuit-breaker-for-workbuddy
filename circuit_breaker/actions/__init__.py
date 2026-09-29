"""熔断动作层入口。"""

from .hard import hard_fuse
from .soft import soft_fuse

__all__ = ["soft_fuse", "hard_fuse"]
