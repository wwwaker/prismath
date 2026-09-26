# -*- coding: utf-8 -*-
"""
模型列表入口页（桌面窗口的首页）
================================

``python main.py`` 不带参数时打开的就是这一页：把注册表里的模型按主题排成卡片，
点卡片（或卡片上的「打开」按钮）进入该模型的桌面视图；进入之后，窗口顶部的
「☰ 模型列表」按钮可以随时回到这里。

* 卡片内容**全部来自** :class:`~prismath.spec.ModelSpec`（图标 / 名称 / 简介 / 要点），
  因此新增模型不需要动这个文件；
* 「打开」按钮用该模型的 ``spec.accent`` 作强调色（与模型视图里的主按钮同色）；
* 没有专用桌面视图的模型会标出「通用视图」——进去后是「跑动作 + 看 JSON 结果」的兜底界面。

本页被外壳当成一个普通「视图」使用（同样提供 ``HINTS`` / ``on_key`` / ``shutdown``），
所以 ``DesktopShell`` 切换视图的那套机制一行都不用改。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from .kit import view_for
from .theme import (
    BG,
    DIM,
    FONT_BOLD,
    FONT_SM,
    FONT_TITLE,
    ScrollArea,
    make_accent_button,
)

__all__ = ["ModelPortal"]

#: 卡片列数（模型变多时按行换行，配合可滚动容器）
COLUMNS = 3


class ModelPortal:
    """模型列表入口页。"""

    HINTS = "点卡片打开模型    也可用顶部的「模型」下拉框直接切换"

    def __init__(self, root: tk.Tk, host: tk.Misc, models: Iterable, on_open: Callable,
                 on_quit: Optional[Callable] = None) -> None:
        self.root = root
        self.host = host
        self.models: List = list(models)
        self.on_open = on_open
        self.on_quit = on_quit
        self.host.configure(bg=BG)
        self.host.columnconfigure(0, weight=1)
        self.host.rowconfigure(1, weight=1)
        self._build()

    # ==================================================================
    # 构建
    # ==================================================================
    def _build(self) -> None:
        self._build_header()
        self._build_cards()
        self._build_footer()

    def _build_header(self) -> None:
        head = ttk.Frame(self.host, style="Panel.TFrame", padding=(20, 16, 20, 14))
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        head.columnconfigure(0, weight=1)

        ttk.Label(head, text="选择一个模型开始", style="Card.TLabel",
                  font=FONT_TITLE).grid(row=0, column=0, sticky="w")
        ttk.Label(
            head,
            text=f"共 {len(self.models)} 个模型 · 点击卡片进入它的桌面视图",
            style="CardDim.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        tips = ttk.Frame(head, style="Card.TFrame")
        tips.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Label(tips, text="网页界面：python main.py --ui web",
                  style="CardDim.TLabel", font=FONT_SM).pack(anchor="e")
        ttk.Label(tips, text="终端交互模式：python main.py --menu",
                  style="CardDim.TLabel", font=FONT_SM).pack(anchor="e", pady=(3, 0))

    def _build_cards(self) -> None:
        area = ScrollArea(self.host, width=None)          # 宽度自适应整页
        area.outer.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        body = area.inner
        for col in range(COLUMNS):
            body.columnconfigure(col, weight=1, uniform="card")

        row = 0
        for topic, specs in self._by_topic():
            ttk.Label(body, text=topic, style="Dim.TLabel",
                      font=FONT_BOLD).grid(row=row, column=0, columnspan=COLUMNS,
                                           sticky="w", pady=(10, 6))
            row += 1
            for i, spec in enumerate(specs):
                card = self._build_card(body, spec)
                card.grid(
                    row=row + i // COLUMNS, column=i % COLUMNS, sticky="nsew",
                    padx=(0 if i % COLUMNS == 0 else 10, 0), pady=(0, 10),
                )
            row += max(1, (len(specs) + COLUMNS - 1) // COLUMNS)

        if not self.models:
            ttk.Label(body, text="还没有注册任何模型。", style="Dim.TLabel").grid(
                row=0, column=0, sticky="w")
        area.bind_wheel()

    def _build_card(self, parent: tk.Misc, spec) -> ttk.LabelFrame:
        card = ttk.LabelFrame(parent, text=f" {spec.icon} {spec.name} ",
                              style="Card.TLabelframe", padding=(14, 10, 14, 12))
        card.columnconfigure(0, weight=1)

        line = 0
        ttk.Label(card, text=spec.summary, style="CardDim.TLabel",
                  wraplength=330, justify="left").grid(row=line, column=0, sticky="w")
        line += 1

        for item in tuple(getattr(spec, "highlights", ()))[:3]:
            ttk.Label(card, text=f"· {item}", style="CardDim.TLabel",
                      wraplength=330, justify="left", font=FONT_SM).grid(
                row=line, column=0, columnspan=2, sticky="w", pady=(3, 0))
            line += 1

        foot = ttk.Frame(card, style="Card.TFrame")
        foot.grid(row=line, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        foot.columnconfigure(0, weight=1)
        kind = "专用视图" if view_for(spec.view) else "通用视图（JSON）"
        ttk.Label(foot, text=f"视图：{kind}", style="CardDim.TLabel",
                  font=FONT_SM).grid(row=0, column=0, sticky="w")
        ttk.Button(foot, text="打开 ▸", style=make_accent_button(self.root, spec.accent),
                   command=lambda s=spec: self.on_open(s)).grid(row=0, column=1, sticky="e")

        self._bind_card_click(card, spec)
        return card

    def _bind_card_click(self, widget: tk.Misc, spec) -> None:
        """让整张卡片（含所有子控件）都可点击，并给出手型光标。"""

        def open_card(_event=None) -> None:
            self.on_open(spec)

        def walk(node: tk.Misc) -> None:
            if not isinstance(node, ttk.Button):      # 按钮自己已经有 command
                node.bind("<Button-1>", open_card, add="+")
                node.bind("<Enter>", lambda _e, n=node: self._set_cursor(n, "hand2"), add="+")
                node.bind("<Leave>", lambda _e, n=node: self._set_cursor(n, ""), add="+")
            for child in node.winfo_children():
                walk(child)

        walk(widget)

    @staticmethod
    def _set_cursor(widget: tk.Misc, cursor: str) -> None:
        try:
            widget.configure(cursor=cursor)
        except tk.TclError:       # 视图销毁过程中可能已被回收
            pass

    def _build_footer(self) -> None:
        foot = ttk.Frame(self.host, style="Panel.TFrame", padding=(20, 10))
        foot.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 12))
        ttk.Label(
            foot,
            text="进入模型后：空格 播放动画    R 重新生成    点画布可指定注水点",
            style="CardDim.TLabel", font=FONT_SM,
        ).pack(side="left")
        ttk.Button(foot, text="退出", width=8, command=self._quit).pack(side="right")

    def _quit(self) -> None:
        if self.on_quit is not None:
            self.on_quit()
        else:
            self.root.destroy()

    def _by_topic(self) -> Sequence[Tuple[str, List]]:
        """按 ``spec.topic`` 分组（顺序沿用注册表的排序，保证展示稳定）。"""
        groups: List[Tuple[str, List]] = []
        for spec in self.models:
            topic = getattr(spec, "topic", "") or "其它"
            if groups and groups[-1][0] == topic:
                groups[-1][1].append(spec)
            else:
                groups.append((topic, [spec]))
        return groups

    # ==================================================================
    # 视图接口（外壳会调用，这里都是一行）
    # ==================================================================
    def on_key(self, _key: str) -> None:
        """入口页不响应快捷键。"""

    def shutdown(self) -> None:
        """入口页没有后台任务与定时器，无需释放资源（宿主容器由外壳销毁）。"""
