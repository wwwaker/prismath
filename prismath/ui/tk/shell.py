# -*- coding: utf-8 -*-
"""
桌面窗口外壳：一个窗口装下所有模型
====================================

窗口自上而下分两层：

* **顶部标题栏**：项目名 + 「模型」下拉框（列出注册表里的全部模型，切换即换视图）
  + 「☰ 模型列表」按钮（回到入口页）；
* **视图区**：首屏是**模型列表入口页**（:class:`~prismath.ui.tk.portal.ModelPortal`，
  点卡片进入某个模型），之后由 ``spec.view`` 决定用哪个视图（见
  :mod:`prismath.ui.tk.kit` 的注册表），没有专用视图的模型自动落到
  :class:`FallbackView`（跑动作 + 看 JSON 结果）。

新增模型时**不必改这里**：在模型自己的包里写 ``views/tk.py``，用
:func:`~prismath.ui.tk.kit.register_view` 装饰视图类（并把 ``spec.view`` 取成同一个
名字）即可被自动发现；没有专用视图的模型自动获得一个可用的兜底界面。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Type

from ..._deps import exit_if_missing
from ...registry import load_models
from ...spec import ModelSpec
from .theme import (
    ACCENT,
    BG,
    BORDER,
    DIM,
    FAINT,
    FONT_SM,
    FONT_TITLE,
    enable_windows_dpi_awareness,
    install_theme,
    polish_comboboxes,
)
from .kit import ModelViewBase, view_for
from .portal import ModelPortal

__all__ = ["DesktopShell", "FallbackView", "launch"]


class FallbackView(ModelViewBase):
    """通用兜底视图：继承万能骨架 :class:`~prismath.ui.tk.kit.base.ModelViewBase`。

    没有专用渲染器的模型也能在桌面里跑动作、看结果：参数表单由 ``spec.params`` 自动生成，
    按钮由 ``spec.actions`` 生成，结果以 JSON 显示。

    想给某个模型定制界面时，按需选一个骨架写 ``views/tk.py``：**通用图表骨架**
    :class:`~prismath.ui.tk.kit.chart.ChartViewBase`（声明式图表 + 动画，多数非渗流模型用它）、
    **万能骨架** :class:`ModelViewBase`（中央 / 右侧自己画），或**渗流特化骨架**
    :class:`~prismath.ui.tk.kit.base.PercolationViewBase`。
    """

    HINTS = "该模型暂无专用桌面视图，可用左侧参数与动作运行"
    INTRO_STATUS = "就绪：可调参数、运行动作，结果以 JSON 显示。"


class DesktopShell:
    """桌面窗口：顶部模型下拉框 + 中部当前模型的视图（首屏是模型列表入口页）。"""

    def __init__(self, root: tk.Tk, spec: Optional[ModelSpec] = None) -> None:
        self.root = root
        # force=True：确保 models/ 下的所有模型包都被导入过，
        # 否则若某个模型包已先被导入，load_models() 会直接返回而漏掉其它模型。
        self.models: List[ModelSpec] = load_models(force=True)
        self.view = None
        self.host: Optional[tk.Frame] = None

        root.title("数学模型可视化工具箱 · 桌面窗口")
        root.geometry("1460x900")
        root.minsize(1220, 800)

        self._build_chrome()

        # 指定了模型就直接进它的视图；否则先停在「模型列表」入口页
        if spec is not None:
            self.show(spec)
        elif self.models:
            self.show_portal()
        else:
            self._show_message("还没有注册任何模型。")

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        # 所有按键都转给当前视图，由视图自己决定认哪些（约定：空格播放、R 重来、
        # 数字键 1..9 触发第 n 个动作；具体模型还可以有别的键，例如 Mandelbrot 的
        # ``I`` 切布局 / ``BackSpace`` 退回上一步）。**不在这里写死键名**：视图加自己的
        # 快捷键不该反过来改外壳；未知键对既有视图是无害的（它们的 on_key 只认自己那几个）。
        root.bind("<Key>", self._on_key_event)

    # ==================================================================
    # 顶部标题栏
    # ==================================================================
    def _build_chrome(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, sticky="ew")

        inner = tk.Frame(header, bg=BG)
        inner.pack(fill="x", padx=16, pady=(12, 10))

        tk.Label(inner, text="数学模型可视化", bg=BG, fg=ACCENT,
                 font=FONT_TITLE).pack(side="left")
        tk.Label(inner, text="桌面窗口", bg=BG, fg=FAINT,
                 font=FONT_SM).pack(side="left", padx=(10, 0), pady=(6, 0))

        self.hint_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=self.hint_var, bg=BG, fg=FAINT,
                 font=FONT_SM).pack(side="right")

        tk.Label(inner, text="模型", bg=BG, fg=DIM, font=FONT_SM).pack(side="left", padx=(28, 6))
        self.model_var = tk.StringVar(value="")
        self.combo = ttk.Combobox(
            inner, width=24, state="readonly",
            textvariable=self.model_var,
            values=[self._label(m) for m in self.models],
        )
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        ttk.Button(inner, text="☰ 模型列表", command=self.show_portal).pack(
            side="left", padx=(10, 0))
        polish_comboboxes(header)     # 让弹出列表也沿用浅色主题

        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")

    @staticmethod
    def _label(spec: ModelSpec) -> str:
        return f"{spec.icon} {spec.name}"

    def _on_model_selected(self, _event=None) -> None:
        index = self.combo.current()
        if 0 <= index < len(self.models):
            self.show(self.models[index])

    # ==================================================================
    # 视图切换
    # ==================================================================
    def _reset_host(self) -> tk.Frame:
        """释放旧视图并换一个新的宿主容器（切模型与回入口页共用），返回新容器。"""
        if self.view is not None:
            self.view.shutdown()
            self.view = None
        if self.host is not None:
            self.host.destroy()

        host = tk.Frame(self.root, bg=BG)
        host.grid(row=1, column=0, sticky="nsew")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        self.host = host
        return host

    def show_portal(self) -> None:
        """回到「模型列表」入口页：把注册表里的模型排成卡片，点一下进对应视图。"""
        host = self._reset_host()
        self.view = ModelPortal(
            self.root, host, self.models,
            on_open=self.show, on_quit=self._on_close,
        )
        self.model_var.set("")
        self.combo.set("")
        self.hint_var.set(getattr(self.view, "HINTS", ""))
        self.root.title("数学模型可视化工具箱 · 桌面窗口")

    def show(self, spec: ModelSpec) -> None:
        """切换到指定模型的视图（先释放旧视图，再新建宿主容器）。"""
        host = self._reset_host()

        view_cls: Type = view_for(spec.view) or FallbackView
        self.view = view_cls(self.root, host, spec)

        self.model_var.set(self._label(spec))
        self.combo.set(self._label(spec))
        self.hint_var.set(getattr(self.view, "HINTS", ""))
        self.root.title(f"{spec.name} · 数学模型可视化（桌面窗口）")

    def _show_message(self, text: str) -> None:
        self.host = tk.Frame(self.root, bg=BG)
        self.host.grid(row=1, column=0, sticky="nsew")
        ttk.Label(self.host, text=text, style="Dim.TLabel").pack(pady=40)

    # ==================================================================
    # 快捷键与关闭
    # ==================================================================
    @staticmethod
    def _key_text(event) -> str:
        """把按键事件转成视图认的键名：单字符给小写字符，特殊键给 keysym（如 ``BackSpace``）。"""
        keysym = str(getattr(event, "keysym", "") or "")
        return keysym.lower() if len(keysym) == 1 else keysym

    def _on_key_event(self, event) -> None:
        """把按键转发给当前视图（真正的过滤在 :meth:`_dispatch_key` 里）。"""
        self._dispatch_key(self._key_text(event))

    def _dispatch_key(self, key: str) -> None:
        """把快捷键转发给当前视图；正在输入框里打字时不触发。"""
        try:
            focus = self.root.focus_get()
        except KeyError:
            # ttk 下拉框弹出列表（popdown）不在父窗口的 children 里，focus_get() 会抛
            # KeyError —— 按普通键处理即可（只读下拉框里也没有文本可输入）。
            focus = None
        if isinstance(focus, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox)):
            return
        if self.view is not None:
            self.view.on_key(key)

    def _on_close(self) -> None:
        if self.view is not None:
            self.view.shutdown()
        self.root.destroy()


def launch(spec: Optional[ModelSpec] = None, **_kwargs) -> int:
    """启动桌面窗口。

    ``spec`` 由 :mod:`prismath.launcher` 传入：给了就直接进那个模型的视图
    （``--model xxx``）；省略则先显示**模型列表入口页**，由用户挑一个模型进去。
    进入之后，顶部的下拉框与「☰ 模型列表」按钮都可以随时切换。
    """
    # 依赖自检：`python -m prismath.ui.tk` 不经过 launcher，得在这里自己拦一次
    # （依赖齐全时是一次零输出的轻量探测）。
    exit_if_missing()
    # 必须在创建 Tk 根窗口之前设置 DPI 感知，否则 Windows 会把整个界面
    # 位图缩放，文字和画布都会显得发糊。
    enable_windows_dpi_awareness()
    root = tk.Tk()
    install_theme(root)
    DesktopShell(root, spec)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(launch())
