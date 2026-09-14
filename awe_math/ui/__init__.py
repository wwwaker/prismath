# -*- coding: utf-8 -*-
"""
界面后端注册表
===============

同一个数学模型可以挂载到不同的界面实现上，模型本身完全不需要知道界面长什么样：

========  ==========================================  ==============================
key       说明                                         依赖
========  ==========================================  ==============================
``tk``    桌面窗口（Tkinter）：模型列表入口页 + 逐层动画    tkinter（可选 matplotlib）
``cli``   终端统计模式，适合批量化出数                  无
``web``   现代网页界面（Canvas 动画 + 玻璃拟态配色）     Python 标准库（可选 pywebview）
========  ==========================================  ==============================

**暂时弃用**：``web`` 后端目前不再出现在入口页与终端菜单里，只能通过
``python main.py --ui web`` 显式进入（详见该后端的 ``note``）；默认入口是 ``tk`` 的
模型列表页。代码保留，随时可以恢复。

新增界面后端时，只需在 :data:`UI_BACKENDS` 中登记一个入口函数。
入口函数签名为 ``entry(spec, args) -> int``（``spec`` 可以是 ``None``，表示"先让用户挑模型"）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..spec import ModelSpec

__all__ = ["UIBackend", "UI_BACKENDS", "get_ui", "list_uis"]


@dataclass(frozen=True)
class UIBackend:
    key: str
    name: str
    summary: str
    #: 入口函数；``spec`` 可以是 ``None``，表示"先让用户挑模型"（桌面窗口的入口页就是这种）
    entry: Callable[[Optional[ModelSpec], Any], int]
    requires: Tuple[str, ...] = ()
    #: 暂时弃用：不出现在入口页 / 终端菜单里，仅 ``--ui <key>`` 可显式进入
    deprecated: bool = False
    #: 弃用或其他需要提醒用户的一句话
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "summary": self.summary,
            "requires": list(self.requires),
            "deprecated": self.deprecated,
            "note": self.note,
        }


# ----------------------------------------------------------------------
# 各后端的入口（内部延迟导入，避免没用到 tkinter 时也去加载它）
# ----------------------------------------------------------------------
def _run_web(spec: Optional[ModelSpec], args) -> int:
    if spec is None:
        raise RuntimeError("网页界面需要指定一个模型（用 --model 选择）")
    from .web.server import serve

    return serve(
        spec,
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 8765),
        open_browser=not getattr(args, "no_browser", False),
        desktop=getattr(args, "desktop", False),
    )


def _run_tk(spec: Optional[ModelSpec], args) -> int:
    """桌面窗口。``spec`` 为空时先显示「模型列表」入口页。"""
    from .tk.shell import launch

    return launch(spec)


def _run_cli(spec: Optional[ModelSpec], args) -> int:
    if spec is None or spec.cli is None:
        raise RuntimeError("终端模式需要指定一个提供了 cli 入口的模型（用 --model 选择）")
    return spec.cli(args)


UI_BACKENDS: Dict[str, UIBackend] = {
    "tk": UIBackend(
        key="tk",
        name="桌面窗口",
        summary="默认入口：先显示模型列表，点卡片进入逐层动画、批量统计与曲线",
        entry=_run_tk,
        requires=("tkinter（Python 自带）", "matplotlib（可选，用于曲线）"),
    ),
    "cli": UIBackend(
        key="cli",
        name="终端统计模式",
        summary="不开窗口，直接在命令行输出概率统计与扫描表格",
        entry=_run_cli,
    ),
    "web": UIBackend(
        key="web",
        name="现代网页界面",
        summary="浏览器中运行，Canvas 逐层动画 + 实时曲线，配色与交互最完整",
        entry=_run_web,
        requires=("无（可选 pywebview 以获得独立窗口）",),
        deprecated=True,
        note="暂时弃用：不再出现在入口页与终端菜单里，仅可用 --ui web 显式进入",
    ),
}


def get_ui(key: str) -> UIBackend:
    """按 key 取界面后端；也支持用名称模糊匹配。

    暂时弃用的后端（如 ``web``）同样可以取到——这正是"只能显式进入"的实现方式。
    """
    text = str(key).strip().lower()
    if text in UI_BACKENDS:
        return UI_BACKENDS[text]
    for backend in UI_BACKENDS.values():
        if text in backend.key.lower() or text in backend.name.lower():
            return backend
    raise KeyError(f"未找到界面后端：{key}（可选：{'、'.join(UI_BACKENDS)}）")


def list_uis(include_deprecated: bool = False) -> List[UIBackend]:
    """返回界面后端（顺序即推荐展示顺序）。

    ``include_deprecated=False``（默认）时只返回仍然推荐的后端，供入口页与终端菜单使用；
    需要展示"暂时弃用"的项（例如 ``--list``）时传 ``True``。
    """
    backends = list(UI_BACKENDS.values())
    if include_deprecated:
        return backends
    return [backend for backend in backends if not backend.deprecated]
