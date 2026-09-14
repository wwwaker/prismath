# -*- coding: utf-8 -*-
"""
桌面界面的主题（配色 / 字体 / ttk 样式）
==========================================

深色扁平风：近黑底 + 细边框 + 单一强调色。所有 ttk 控件都从这里取色，
各视图（渗流、森林火灾）共用同一套调色板，只在「模型强调色」上有所区别。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

__all__ = [
    "BG",
    "PANEL",
    "PANEL_2",
    "BORDER",
    "BORDER_2",
    "TEXT",
    "DIM",
    "FAINT",
    "ACCENT",
    "ACCENT_TEXT",
    "SEL_BG",
    "BTN_HOVER",
    "BTN_ACTIVE",
    "OK",
    "WARN",
    "DANGER",
    "FONT",
    "FONT_SM",
    "FONT_BOLD",
    "FONT_TITLE",
    "FONT_BADGE",
    "FONT_MONO",
    "FONT_MONO_B",
    "lerp_color",
    "install_theme",
    "make_accent_button",
    "polish_comboboxes",
    "ScrollArea",
    "bind_mousewheel",
]

# ----------------------------------------------------------------------
# 调色板
# ----------------------------------------------------------------------
BG = "#0f141b"          # 窗口底色
PANEL = "#151c26"       # 卡片 / 面板底
PANEL_2 = "#1d2634"     # 输入框 / 按钮底
BORDER = "#26313f"      # 细边框
BORDER_2 = "#35455c"    # 悬停边框
TEXT = "#e6edf6"        # 主文字
DIM = "#93a1b5"         # 次要文字
FAINT = "#66748f"       # 弱化文字
ACCENT = "#38bdf8"      # 默认强调色
ACCENT_TEXT = "#06283a"  # 强调色按钮上的深色文字
SEL_BG = "#1d3a52"      # 列表 / 表格选中行
BTN_HOVER = "#273242"
BTN_ACTIVE = "#2f3c50"
OK = "#34d399"
WARN = "#fbbf24"
DANGER = "#fb7185"

# ----------------------------------------------------------------------
# 字体
# ----------------------------------------------------------------------
FONT = ("Microsoft YaHei UI", 10)
FONT_SM = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 14, "bold")
FONT_BADGE = ("Microsoft YaHei UI", 12, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_B = ("Consolas", 10, "bold")


def lerp_color(start: Tuple[int, int, int], end: Tuple[int, int, int], t: float) -> str:
    """在两个 RGB 颜色之间线性插值，返回 ``#rrggbb``。"""
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    r = int(start[0] + (end[0] - start[0]) * t)
    g = int(start[1] + (end[1] - start[1]) * t)
    b = int(start[2] + (end[2] - start[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def install_theme(root: tk.Tk) -> None:
    """在 clam 主题上定制一套深色扁平样式（所有控件共用同一调色板）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG)
    root.option_add("*TCombobox*Listbox.background", PANEL_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SEL_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    def cfg(name: str, **kw) -> None:
        # 个别样式选项在旧版本 Tk 上可能不存在，逐条忽略以保证整体可用
        try:
            style.configure(name, **kw)
        except tk.TclError:
            pass

    def smap(name: str, **kw) -> None:
        try:
            style.map(name, **kw)
        except tk.TclError:
            pass

    cfg(".", background=BG, foreground=TEXT, font=FONT)
    cfg("TFrame", background=BG)
    cfg("Side.TFrame", background=BG)
    cfg("Panel.TFrame", background=PANEL)
    cfg("Card.TFrame", background=PANEL)

    cfg("TLabel", background=BG, foreground=TEXT)
    cfg("Dim.TLabel", background=BG, foreground=DIM)
    cfg("Card.TLabel", background=PANEL, foreground=TEXT)
    cfg("CardDim.TLabel", background=PANEL, foreground=DIM)
    cfg("Mono.TLabel", background=PANEL, foreground=TEXT, font=FONT_MONO)
    cfg("MonoAccent.TLabel", background=PANEL, foreground=ACCENT, font=FONT_MONO_B)
    cfg("Danger.TLabel", background=PANEL, foreground=DANGER)

    cfg("Card.TLabelframe", background=PANEL, bordercolor=BORDER,
        relief="solid", borderwidth=1)
    cfg("Card.TLabelframe.Label", background=PANEL, foreground=FAINT,
        font=("Microsoft YaHei UI", 9, "bold"))

    cfg("TButton", background=PANEL_2, foreground=TEXT, bordercolor=BORDER,
        focusthickness=1, focuscolor=BORDER_2, padding=(12, 6))
    smap("TButton",
         background=[("pressed", BTN_ACTIVE), ("active", BTN_HOVER), ("disabled", PANEL_2)],
         foreground=[("disabled", FAINT)],
         bordercolor=[("active", BORDER_2), ("disabled", BORDER)])

    cfg("Accent.TButton", background=ACCENT, foreground=ACCENT_TEXT,
        bordercolor=ACCENT, font=FONT_BOLD, padding=(12, 6))
    smap("Accent.TButton",
         background=[("pressed", "#0ea5e9"), ("active", "#7dd3fc"), ("disabled", PANEL_2)],
         foreground=[("disabled", FAINT)],
         bordercolor=[("disabled", BORDER)])

    cfg("Danger.TButton", background="#3d2029", foreground="#fda4af",
        bordercolor="#5b2a35", padding=(12, 6))
    smap("Danger.TButton",
         background=[("pressed", "#57222f"), ("active", "#4a222d"), ("disabled", PANEL_2)],
         foreground=[("disabled", FAINT)],
         bordercolor=[("disabled", BORDER)])

    cfg("TCheckbutton", background=BG, foreground=TEXT)
    cfg("Card.TCheckbutton", background=PANEL, foreground=TEXT)
    smap("TCheckbutton", background=[("active", BG)])
    smap("Card.TCheckbutton", background=[("active", PANEL)])

    cfg("Horizontal.TScale", background=ACCENT, troughcolor=PANEL_2,
        bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

    cfg("TSpinbox", fieldbackground=PANEL_2, foreground=TEXT, background=PANEL_2,
        bordercolor=BORDER, insertcolor=TEXT, arrowcolor=DIM)
    cfg("TCombobox", fieldbackground=PANEL_2, foreground=TEXT, background=PANEL_2,
        bordercolor=BORDER, insertcolor=TEXT, arrowcolor=DIM,
        selectbackground=SEL_BG, selectforeground=TEXT)

    # clam 主题自带的状态映射会把只读控件刷成浅色（#dcdad5 等），
    # 必须逐状态覆盖，否则只读下拉框会出现「白底浅字」看不清的情况。
    smap("TCombobox",
         fieldbackground=[("readonly", "focus", SEL_BG), ("readonly", PANEL_2),
                          ("disabled", PANEL), ("!disabled", PANEL_2)],
         foreground=[("readonly", TEXT), ("disabled", FAINT), ("!disabled", TEXT)],
         background=[("readonly", PANEL_2), ("active", BTN_HOVER), ("pressed", BTN_ACTIVE)],
         arrowcolor=[("readonly", DIM), ("disabled", FAINT), ("!disabled", DIM)],
         selectbackground=[("readonly", SEL_BG), ("!disabled", SEL_BG)],
         selectforeground=[("readonly", TEXT), ("!disabled", TEXT)])
    smap("TSpinbox",
         fieldbackground=[("disabled", PANEL), ("!disabled", PANEL_2)],
         foreground=[("disabled", FAINT), ("!disabled", TEXT)],
         background=[("active", BTN_HOVER), ("!disabled", PANEL_2)],
         arrowcolor=[("disabled", FAINT), ("!disabled", DIM)])
    smap("TEntry",
         fieldbackground=[("disabled", PANEL), ("!disabled", PANEL_2)],
         foreground=[("disabled", FAINT), ("!disabled", TEXT)])

    cfg("TNotebook", background=BG, bordercolor=BG, tabmargins=(0, 4, 0, 0))
    cfg("TNotebook.Tab", background=BG, foreground=FAINT, padding=(14, 8))
    smap("TNotebook.Tab",
         background=[("selected", PANEL), ("active", PANEL_2)],
         foreground=[("selected", TEXT), ("active", DIM)])

    cfg("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
        bordercolor=BORDER, rowheight=26, font=FONT_SM)
    smap("Treeview",
         background=[("selected", SEL_BG)],
         foreground=[("selected", TEXT)])
    cfg("Treeview.Heading", background=PANEL_2, foreground=DIM,
        bordercolor=BORDER, relief="flat", padding=(4, 6))
    smap("Treeview.Heading", background=[("active", BTN_HOVER)])

    cfg("Vertical.TScrollbar", background=PANEL_2, troughcolor=PANEL,
        bordercolor=PANEL, arrowcolor=DIM)
    smap("Vertical.TScrollbar", background=[("active", BTN_HOVER)])

    cfg("Horizontal.TProgressbar", troughcolor=PANEL_2, background=ACCENT,
        bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)
    cfg("TSeparator", background=BORDER)


def _rgb(color: str) -> Tuple[int, int, int]:
    """``#rrggbb`` -> (r, g, b)。"""
    text = color.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def make_accent_button(root: tk.Tk, accent: str, text_color: str = ACCENT_TEXT) -> str:
    """为一个模型创建专属的强调按钮样式，返回样式名（供 ``ttk.Button(style=...)``）。

    这样渗流用青色、森林火灾用橙色，各视图的主按钮各不相同又风格统一。
    """
    style = ttk.Style(root)
    name = f"Accent{accent.lstrip('#')}.TButton"
    hover = lerp_color(_rgb(accent), (255, 255, 255), 0.32)   # 悬停时略微提亮
    pressed = lerp_color(_rgb(accent), (0, 0, 0), 0.22)       # 按下时略微压暗
    try:
        style.configure(name, background=accent, foreground=text_color,
                        bordercolor=accent, font=FONT_BOLD, padding=(12, 6))
        style.map(name,
                  background=[("pressed", pressed), ("active", hover), ("disabled", PANEL_2)],
                  foreground=[("disabled", FAINT)],
                  bordercolor=[("disabled", BORDER)])
    except tk.TclError:
        return "Accent.TButton"
    return name


def _style_popdown(combo: ttk.Combobox) -> None:
    """把下拉框的弹出列表也刷成暗色。

    ``option_add("*TCombobox*Listbox...")`` 在部分 Tk 版本／主题下不生效，
    会露出系统白色底，因此这里在控件创建后再显式配置一遍（弹出窗口会顺手被创建）。
    """
    def call(*args) -> None:
        try:
            combo.tk.call(*args)
        except tk.TclError:
            pass

    try:
        popdown = combo.tk.call("ttk::combobox::PopdownWindow", combo)
    except tk.TclError:
        return
    call(popdown, "configure", "-background", BORDER)
    call(f"{popdown}.f", "configure", "-borderwidth", 0, "-padding", 0)
    call(f"{popdown}.f.l", "configure",
         "-background", PANEL_2, "-foreground", TEXT,
         "-selectbackground", SEL_BG, "-selectforeground", TEXT,
         "-highlightthickness", 0, "-borderwidth", 0, "-selectborderwidth", 0,
         "-activestyle", "none", "-relief", "flat")


def polish_comboboxes(widget: tk.Misc) -> int:
    """递归处理 ``widget`` 下的所有下拉框（含弹出列表配色），返回处理个数。"""
    count = 0
    if isinstance(widget, ttk.Combobox):
        _style_popdown(widget)
        count += 1
    for child in widget.winfo_children():
        count += polish_comboboxes(child)
    return count


def bind_mousewheel(widget: tk.Misc, canvas: tk.Canvas) -> None:
    """让鼠标停在 ``widget`` 及其子控件上时，滚轮可以滚动 ``canvas``。"""

    def on_wheel(event) -> str:
        step = -1 if getattr(event, "delta", 0) > 0 else 1
        canvas.yview_scroll(step * 2, "units")
        return "break"

    def walk(node: tk.Misc) -> None:
        node.bind("<MouseWheel>", on_wheel, add="+")
        for child in node.winfo_children():
            walk(child)

    walk(widget)


class ScrollArea:
    """固定宽度的可滚动容器。

    侧边栏的卡片会随模型参数变多而变高，一旦超出窗口高度，``pack`` 会**直接不显示**
    装不下的控件（按钮就这么「消失」过），所以这里用 Canvas + Scrollbar 承载内容：
    把卡片 pack 进 :attr:`inner`，构建完成后调用 :meth:`bind_wheel` 绑定滚轮。
    """

    def __init__(self, parent: tk.Misc, width: Optional[int] = 306, bg: str = BG) -> None:
        """``width=None`` 表示宽度随父容器自适应（整页可滚动内容用得上）。"""
        self.outer = tk.Frame(parent, bg=bg)
        if width is not None:
            self.outer.configure(width=width)
            self.outer.grid_propagate(False)
        self.canvas = tk.Canvas(self.outer, bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self.scrollbar = ttk.Scrollbar(
            self.outer, orient="vertical", command=self.canvas.yview,
        )
        self.inner = ttk.Frame(self.canvas, style="Side.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def bind_wheel(self) -> None:
        """内容构建完成后调用：滚轮随处可用，并把下拉框弹出列表也刷成暗色。"""
        bind_mousewheel(self.inner, self.canvas)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(
            -2 if getattr(e, "delta", 0) > 0 else 2, "units"))
        polish_comboboxes(self.inner)
        self._on_inner_configure()
