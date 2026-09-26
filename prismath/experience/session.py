"""引导会话状态机。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from .spec import ExperienceSpec, GuideStep

__all__ = ["GuideSession"]


@dataclass
class GuideSession:
    """持有一次模型体验的模式、当前步骤和完成事件。

    会话不执行模型计算，也不直接触碰 UI。交互层只需在发生有意义的动作时调用
    :meth:`emit`，例如 ``emit("point_inspected")`` 或 ``emit("zoomed")``。
    """

    experience: ExperienceSpec
    mode: Optional[str] = None
    step_index: int = 0
    completed_steps: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.mode is None:
            self.mode = self.experience.default_mode
        if self.mode not in self.experience.modes:
            raise ValueError(f"模式 {self.mode!r} 不在体验配置中")
        self.step_index = max(0, min(int(self.step_index), len(self.experience.guide)))
        self._normalize()

    @property
    def current_step(self) -> Optional[GuideStep]:
        if self.mode != "guided" or self.step_index >= len(self.experience.guide):
            return None
        return self.experience.guide[self.step_index]

    @property
    def guide_complete(self) -> bool:
        return self.step_index >= len(self.experience.guide)

    def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """发出一个交互事件，返回本次是否完成了当前步骤。

        ``payload`` 当前只用于未来扩展和记录调用形状；步骤的基础完成条件是事件名匹配。
        具体模型若需要阈值判断，可以在 UI/体验适配器中先把原始动作归一化成事件。
        """
        del payload
        step = self.current_step
        if step is None or event != step.completion_event:
            return False
        self.completed_steps.add(step.key)
        self.step_index += 1
        self._normalize()
        return True

    def skip(self) -> None:
        """跳过剩余引导，进入自由探索。"""
        self.step_index = len(self.experience.guide)
        self.mode = "explore" if "explore" in self.experience.modes else self.mode

    def enter_mode(self, mode: str) -> None:
        if mode not in self.experience.modes:
            raise ValueError(f"模式 {mode!r} 不在体验配置中")
        self.mode = mode

    def reset(self) -> None:
        self.mode = self.experience.default_mode
        self.step_index = 0
        self.completed_steps.clear()
        self._normalize()

    def to_dict(self) -> Dict[str, Any]:
        step = self.current_step
        return {
            "mode": self.mode,
            "stepIndex": self.step_index,
            "guideComplete": self.guide_complete,
            "completedSteps": sorted(self.completed_steps),
            "currentStep": step.to_dict() if step is not None else None,
        }

    def _normalize(self) -> None:
        if self.mode == "guided" and self.guide_complete:
            self.mode = "explore" if "explore" in self.experience.modes else self.mode
