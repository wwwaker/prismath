# -*- coding: utf-8 -*-
"""
界面后端注册表
===============

同一个数学模型可以挂载到不同的界面实现上，模型本身完全不需要知道界面长什么样：

========  ==========================================  ==============================
key       说明                                         依赖
========  ==========================================  ==============================
``web``   现代网页界面（Canvas 动画 + 玻璃拟态配色）     Python 标准库（可选 pywebview）
``tk``    桌面窗口（Tkinter，顶部下拉框切换模型）        tkinter（可选 matplotlib）
``cli``   终端统计模式，适合批量化出数                  无
========  ==========================================  ==============================

新增界面后端时，只需在 :data:`UI_BACKENDS` 中登记一个入口函数。
入口函数签名为 ``entry(spec, args) -> int``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence, Tuple

from ..spec import ModelSpec

__all__ = ["UIBackend", "UI_BACKENDS", "get_ui", "list_uis"]


@dataclass(frozen=True)
class UIBackend:
    key: str
    name: str
    summary: str
    entry: Callable[[ModelSpec, Any], int]
    requires: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "summary": self.summary,
            "requires": list(self.requires),
        }


# ----------------------------------------------------------------------
# 各后端的入口（内部延迟导入，避免没用到 tkinter 时也去加载它）
# ----------------------------------------------------------------------
def _run_web(spec: ModelSpec, args) -> int:
    from .web.server import serve

    return serve(
        spec,
        host=getattr(args, "host", "127.0.0.1"),
        port=getattr(args, "port", 8765),
        open_browser=not getattr(args, "no_browser", False),
        desktop=getattr(args, "desktop", False),
    )


def _run_tk(spec: ModelSpec, args) -> int:
    from .tk.shell import launch

    return launch(spec)


def _run_cli(spec: ModelSpec, args) -> int:
    if spec.cli is None:
        raise RuntimeError(f"模型 {spec.key} 未提供终端模式入口")
    return spec.cli(args)


UI_BACKENDS: Dict[str, UIBackend] = {
    "web": UIBackend(
        key="web",
        name="现代网页界面",
        summary="浏览器中运行，Canvas 逐层动画 + 实时曲线，配色与交互最完整（推荐）",
        entry=_run_web,
        requires=("无（可选 pywebview 以获得独立窗口）",),
    ),
    "tk": UIBackend(
        key="tk",
        name="桌面窗口",
        summary="Tkinter 实现的单窗口程序：顶部下拉框可切换模型，含逐层动画、批量统计与曲线",
        entry=_run_tk,
        requires=("tkinter（Python 自带）", "matplotlib（可选，用于曲线）"),
    ),
    "cli": UIBackend(
        key="cli",
        name="终端统计模式",
        summary="不开窗口，直接在命令行输出渗流概率与扫描表格",
        entry=_run_cli,
    ),
}


def get_ui(key: str) -> UIBackend:
    """按 key 取界面后端；也支持用名称模糊匹配。"""
    text = str(key).strip().lower()
    if text in UI_BACKENDS:
        return UI_BACKENDS[text]
    for backend in UI_BACKENDS.values():
        if text in backend.key.lower() or text in backend.name.lower():
            return backend
    raise KeyError(f"未找到界面后端：{key}（可选：{'、'.join(UI_BACKENDS)}）")


def list_uis() -> List[UIBackend]:
    """返回所有界面后端（顺序即推荐展示顺序）。"""
    return list(UI_BACKENDS.values())
