# -*- coding: utf-8 -*-
"""
桌面窗口外壳：一个窗口装下所有模型
====================================

窗口自上而下分两层：

* **顶部标题栏**：项目名 + 「模型」下拉框（列出注册表里的全部模型，切换即换视图）；
* **视图区**：由 ``spec.view`` 决定用哪个视图（见 :func:`_view_classes`），
  没有专用视图的模型自动落到 :class:`FallbackView`（跑动作 + 看 JSON 结果）。

新增模型时不必改这里：只要在 :func:`_view_classes` 里登记一行 ``view 名 -> 视图类``，
其余模型自动获得一个可用的兜底界面。
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Type

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
    PANEL_2,
    TEXT,
    install_theme,
    polish_comboboxes,
)

__all__ = ["DesktopShell", "FallbackView", "launch"]


def _view_classes() -> dict:
    """桌面视图注册表（延迟导入，避免一次性加载全部视图与 matplotlib）。"""
    from .app import PercolationApp
    from .site import SitePercolationApp

    return {
        "percolation": PercolationApp,          # 边渗流（边随机连通）
        "site_percolation": SitePercolationApp,  # 点渗流（格子随机占据）
    }


class FallbackView:
    """通用兜底视图：没有专用渲染器的模型也能在桌面里跑动作、看 JSON 结果。"""

    HINTS = "该模型暂无专用桌面视图，可在下方运行动作查看结果"

    def __init__(self, root: tk.Tk, host: tk.Misc, spec: ModelSpec) -> None:
        self.root = root
        self.host = host
        self.spec = spec
        self.actions = tuple(getattr(spec, "actions", ()))
        self._build()

    def _build(self) -> None:
        self.host.columnconfigure(0, weight=1)
        self.host.rowconfigure(1, weight=1)

        head = ttk.Frame(self.host, style="Panel.TFrame", padding=16)
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        ttk.Label(head, text=self.spec.name, style="Card.TLabel", font=FONT_TITLE).pack(anchor="w")
        ttk.Label(
            head, text=self.spec.summary, style="CardDim.TLabel",
            wraplength=980, justify="left",
        ).pack(anchor="w", pady=(6, 0))
        if self.spec.description:
            ttk.Label(
                head, text=self.spec.description, style="CardDim.TLabel",
                wraplength=980, justify="left", font=FONT_SM,
            ).pack(anchor="w", pady=(8, 0))

        body = ttk.Frame(self.host, style="Panel.TFrame", padding=16)
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(8, 12))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        bar = ttk.Frame(body, style="Card.TFrame")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for action in self.actions:
            ttk.Button(
                bar, text=action.label,
                command=lambda key=action.key: self.run_action(key),
            ).pack(side="left", padx=(0, 8))
        if not self.actions:
            ttk.Label(bar, text="该模型没有声明可执行动作。",
                      style="CardDim.TLabel").pack(side="left")

        self.output = tk.Text(
            body, bg=PANEL_2, fg=TEXT, insertbackground=TEXT, relief="flat",
            wrap="none", padx=10, pady=8, height=18,
        )
        self.output.grid(row=1, column=0, sticky="nsew")
        self._write("点击上方按钮，用默认参数运行动作；结果以 JSON 显示。")

    def _write(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def run_action(self, key: str) -> None:
        """用参数默认值运行一次动作，把结果（或错误）显示在下方。"""
        try:
            result = self.spec.run(key, {})
        except Exception as exc:      # 把模型异常直接展示出来，方便排查
            self._write(f"× 运行失败：{type(exc).__name__}: {exc}")
            return
        self._write(json.dumps(result, ensure_ascii=False, indent=2))

    def on_key(self, key: str) -> None:
        """兜底视图不响应快捷键。"""

    def shutdown(self) -> None:
        """兜底视图没有后台任务，无需释放资源。"""


class DesktopShell:
    """桌面窗口：顶部模型下拉框 + 中部当前模型的可视化视图。"""

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

        target = spec if spec is not None else (self.models[0] if self.models else None)
        if target is not None:
            self.show(target)
        else:
            self._show_message("还没有注册任何模型。")

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<space>", lambda _e: self._dispatch_key(" "))
        root.bind("<Key-r>", lambda _e: self._dispatch_key("r"))

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
        polish_comboboxes(header)     # 让弹出列表也是暗色（否则会露出系统白底）

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
    def show(self, spec: ModelSpec) -> None:
        """切换到指定模型的视图（先释放旧视图，再新建宿主容器）。"""
        if self.view is not None:
            self.view.shutdown()
            self.view = None
        if self.host is not None:
            self.host.destroy()

        self.host = tk.Frame(self.root, bg=BG)
        self.host.grid(row=1, column=0, sticky="nsew")
        self.host.columnconfigure(0, weight=1)
        self.host.rowconfigure(0, weight=1)

        view_cls: Type = _view_classes().get(spec.view, FallbackView)
        self.view = view_cls(self.root, self.host, spec)

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
    def _dispatch_key(self, key: str) -> None:
        """把快捷键转发给当前视图；正在输入框里打字时不触发。"""
        focus = self.root.focus_get()
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

    ``spec`` 由 :mod:`awe_math.launcher` 传入，决定打开时先显示哪个模型；
    省略时默认显示注册表里的第一个模型。下拉框里始终可以切换到其它模型。
    """
    root = tk.Tk()
    install_theme(root)
    DesktopShell(root, spec)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(launch())
