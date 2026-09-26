"""模型体验协议。

该模块只描述模型的视觉能力和教学流程，不依赖任何具体 UI 后端。Web、Tk
以及测试都可以消费同一份声明。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

__all__ = ["ExperienceSpec", "GuideStep", "RenderCapabilities"]

_VISUAL_KINDS = {"field", "grid", "particles", "geometry", "chart"}
_MODES = {"guided", "explore", "lab"}


@dataclass(frozen=True)
class RenderCapabilities:
    """模型可视化能力，而不是某个 UI 的布局配置。"""

    visual_kind: str
    interactions: Tuple[str, ...] = ()
    supports_play: bool = False
    supports_editing: bool = False
    supports_gpu_preview: bool = False
    default_mode: str = "explore"
    advanced_controls: bool = True

    def __post_init__(self) -> None:
        if self.visual_kind not in _VISUAL_KINDS:
            choices = ", ".join(sorted(_VISUAL_KINDS))
            raise ValueError(f"未知视觉范式：{self.visual_kind!r}（可选：{choices}）")
        if self.default_mode not in _MODES:
            raise ValueError(f"未知默认模式：{self.default_mode!r}")
        if len(set(self.interactions)) != len(self.interactions):
            raise ValueError("interactions 不能包含重复项")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "visualKind": self.visual_kind,
            "interactions": list(self.interactions),
            "supportsPlay": self.supports_play,
            "supportsEditing": self.supports_editing,
            "supportsGpuPreview": self.supports_gpu_preview,
            "defaultMode": self.default_mode,
            "advancedControls": self.advanced_controls,
        }


@dataclass(frozen=True)
class GuideStep:
    """一个可由交互事件完成的引导步骤。"""

    key: str
    title: str
    prompt: str
    explanation: str = ""
    completion_event: str = ""
    allowed_actions: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("引导步骤必须有 key")
        if not self.title.strip() or not self.prompt.strip():
            raise ValueError("引导步骤必须有 title 和 prompt")
        if not self.completion_event.strip():
            raise ValueError(f"引导步骤 {self.key!r} 必须声明 completion_event")
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError(f"引导步骤 {self.key!r} 的 allowed_actions 不能重复")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "prompt": self.prompt,
            "explanation": self.explanation,
            "completionEvent": self.completion_event,
            "allowedActions": list(self.allowed_actions),
        }


@dataclass(frozen=True)
class ExperienceSpec:
    """模型的体验配置：默认模式和可选的引导步骤。"""

    default_mode: str = "explore"
    modes: Tuple[str, ...] = ("guided", "explore", "lab")
    guide: Tuple[GuideStep, ...] = ()

    def __post_init__(self) -> None:
        if self.default_mode not in _MODES:
            raise ValueError(f"未知默认模式：{self.default_mode!r}")
        if not self.modes:
            raise ValueError("ExperienceSpec 至少需要一种模式")
        if any(mode not in _MODES for mode in self.modes):
            raise ValueError(f"modes 只能使用：{', '.join(sorted(_MODES))}")
        if self.default_mode not in self.modes:
            raise ValueError("default_mode 必须包含在 modes 中")
        keys = [step.key for step in self.guide]
        if len(set(keys)) != len(keys):
            raise ValueError("引导步骤 key 不能重复")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defaultMode": self.default_mode,
            "modes": list(self.modes),
            "guide": [step.to_dict() for step in self.guide],
        }
