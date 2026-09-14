# -*- coding: utf-8 -*-
"""
统一入口
=========

程序只有一个入口，默认直接打开**桌面窗口的「模型列表」入口页**：

    python main.py                                   # 默认：桌面窗口 → 模型列表 → 选一个模型
    python main.py --model percolation               # 跳过列表，直接进边渗流模型的窗口
    python main.py --list                            # 只列出模型与界面后端后退出
    python main.py --menu                            # 终端交互模式：在命令行里选模型与界面
    python main.py --model percolation --ui cli --scan   # 终端里跑统计 / 扫描曲线
    python main.py --ui web                          # 网页界面（暂时弃用，需显式指定）

几个约定：

* ``--ui`` 省略时用 ``tk``（桌面窗口）；``--model`` 省略时先停在模型列表页让用户挑。
* 网页后端 ``web`` **暂时弃用**：不出现在入口页与终端菜单里，只能 ``--ui web`` 显式进入。
* 终端交互模式（原来不带参数时的流程：选模型 → 选界面）保留在 ``--menu`` 下。
* 若这台机器开不了桌面窗口（无显示 / 没装 tkinter），自动回落到终端交互模式（非交互
  终端则直接跑终端统计模式），不会甩一个 traceback 给用户。

URL 风格的选择也支持：``--model 1``（按序号）、``--model perc``（按名称模糊匹配）。
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from typing import Any, List, Optional, Sequence

from .registry import ModelNotFound, find, load_models
from .spec import ModelSpec
from .ui import UIBackend, get_ui, list_uis

__all__ = ["main", "build_parser"]


# ----------------------------------------------------------------------
# 终端排版小工具（中文按 2 个字符宽度计算，保证表格对齐）
# ----------------------------------------------------------------------
def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def _pad(text: Any, width: int, align: str = "left") -> str:
    text = str(text)
    space = " " * max(0, width - _width(text))
    return space + text if align == "right" else text + space


def _rule(char: str = "─", width: int = 74) -> str:
    return char * width


# ----------------------------------------------------------------------
# 命令行参数
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awe_math",
        description="数学模型可视化工具箱：默认打开桌面窗口的模型列表入口页",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python main.py                               打开桌面窗口的模型列表（默认）\n"
            "  python main.py --model percolation           直接进边渗流模型的窗口\n"
            "  python main.py --menu                        终端交互模式（选模型 → 选界面）\n"
            "  python main.py --model perc --ui cli --scan  终端里扫描 P(p) 曲线\n"
            "  python main.py --ui web                      网页界面（暂时弃用，需显式指定）\n"
        ),
    )
    parser.add_argument("--list", action="store_true", help="列出所有模型与界面后端后退出")
    parser.add_argument("--model", "-m", default=None,
                        help="模型标识、序号或名称关键字；省略则先在模型列表里挑")
    parser.add_argument("--ui", "-u", default=None, choices=("tk", "cli", "web"),
                        help="界面后端：tk（默认，桌面窗口）/ cli（终端统计）/ "
                             "web（网页，暂时弃用，需显式指定）")
    parser.add_argument("--menu", action="store_true",
                        help="终端交互模式：在命令行里依次选择模型与界面后端")

    web = parser.add_argument_group("网页界面选项（暂时弃用的 web 后端）")
    web.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1（仅本机）")
    web.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765（被占用时自动顺延）")
    web.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    web.add_argument("--desktop", action="store_true",
                     help="用独立桌面窗口打开（需 pip install pywebview），否则用浏览器")

    model = parser.add_argument_group("模型参数（终端模式下使用；桌面/网页界面可在界面里调）")
    model.add_argument("--p", type=float, default=None,
                       help="概率参数（边渗流=流通概率，点渗流=占据密度）；省略则用模型默认值")
    model.add_argument("--size", type=int, default=40, help="行数（方格网时即边长），默认 40")
    model.add_argument("--cols", type=int, default=None,
                       help="列数；与行数不同即为矩形网格，省略则与行数相同")
    model.add_argument("--lattice", choices=("square", "triangular"), default=None,
                       help="格子类型：square 方格网（4 邻域）/ triangular 三角网（6 邻域）")
    model.add_argument("--direction", default=None,
                       choices=("undirected", "no_up", "down_right", "down_left"),
                       help="方向模式：无向 / 不允许向上 / 只允许向下向右 / 只允许向下向左")
    model.add_argument("--inject", choices=("top", "center", "random"), default=None,
                       help="注水（起始）方式：顶端整行 / 中心 / 随机单点；省略则用模型默认值")
    model.add_argument("--criterion", choices=("span", "origin", "area"), default=None,
                       help="成功判据：span = 整片网格存在纵贯簇（对应 p_c，默认）；"
                            "origin = 注水点出发的那一簇是否纵贯（随注水方式变化）；"
                            "area = 面积比例达到阈值（无固定临界值）")
    model.add_argument("--threshold", choices=("0.3", "0.5", "0.7", "0.9"), default=None,
                       help="（判据 = area 时）面积判据的比例阈值，默认 0.5")
    model.add_argument("--trials", type=int, default=1000, help="统计次数，默认 1000")
    model.add_argument("--scan", action="store_true", help="扫描 p 从 0 到 1 的概率曲线")
    model.add_argument("--step", type=float, default=0.05, help="扫描步长，默认 0.05")
    model.add_argument("--seed", type=int, default=-1, help="随机种子，-1 表示随机")
    model.add_argument("--directed", action="store_true",
                       help="（旧选项）等价于 --direction no_up")
    return parser


# ----------------------------------------------------------------------
# 选择逻辑（终端）
# ----------------------------------------------------------------------
def _print_models() -> List[ModelSpec]:
    models = load_models()
    print(_rule("═"))
    print(" 可用的数学模型")
    print(_rule("═"))
    print(f" {'序号':<6}{_pad('标识', 18)}{_pad('名称', 18)}{_pad('主题', 20)}简介")
    print(_rule())
    for index, spec in enumerate(models, start=1):
        print(
            f" [{index}]  {_pad(spec.key, 18)}{_pad(spec.icon + ' ' + spec.name, 18)}"
            f"{_pad(spec.topic, 20)}{spec.summary[:34]}…"
        )
    print(_rule())
    return models


def _print_uis() -> None:
    print(" 可用的界面后端（--ui）")
    print(_rule())
    for ui in list_uis():
        print(f" {_pad(ui.key, 8)}{_pad(ui.name, 20)}{ui.summary}")
    for ui in list_uis(include_deprecated=True):
        if ui.deprecated:
            print(_rule("·"))
            print(f" {_pad(ui.key, 8)}{_pad(ui.name + '（暂时弃用）', 26)}{ui.note}")
    print(_rule())


def _ask(prompt: str, count: int, default: int = 0) -> Optional[int]:
    """让用户在终端里选一项；返回下标，输入 q 时返回 None。"""
    try:
        raw = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if raw.lower() in ("q", "quit", "exit"):
        return None
    if not raw:
        return default
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < count:
            return index
    print("  输入无效，使用默认选项。")
    return default


def _choose_model() -> Optional[ModelSpec]:
    models = _print_models()
    if not models:
        print("还没有注册任何模型。")
        return None
    print()
    index = _ask(f" 请选择数学模型 [1-{len(models)}]（回车默认 1，q 退出）：", len(models))
    return None if index is None else models[index]


def _choose_ui() -> Optional[str]:
    uis = list_uis()          # 暂时弃用的后端不进菜单（只能 --ui <key> 显式进入）
    print("\n 请选择界面后端：")
    for i, ui in enumerate(uis, start=1):
        print(f"   [{i}] {_pad(ui.name, 16)}{ui.summary}")
    print()
    index = _ask(f" 请输入序号 [1-{len(uis)}]（回车默认 1 = {uis[0].name}，q 退出）：", len(uis))
    return None if index is None else uis[index].key


def _resolve_model(args) -> Optional[ModelSpec]:
    """把 ``--model`` 解析成具体模型；没给则交互选择（非交互终端取第一个）。"""
    if args.model:
        try:
            return find(args.model)
        except ModelNotFound as exc:
            print(f"× {exc}", file=sys.stderr)
            _print_models()
            return None

    if sys.stdin.isatty():
        return _choose_model()

    models = load_models()
    print("未指定 --model 且当前不是交互式终端，默认使用第一个模型。")
    return models[0] if models else None


# ----------------------------------------------------------------------
# 启动
# ----------------------------------------------------------------------
def _announce(spec: Optional[ModelSpec], backend: UIBackend) -> None:
    if backend.deprecated and backend.note:
        print(f" ! {backend.note}")
    if spec is None:
        print("\n 模型：待选择（进入桌面窗口的模型列表）")
    else:
        print(f"\n 模型：{spec.name}（{spec.key}）")
    print(f" 界面：{backend.name}\n")


def _interactive_flow(args) -> int:
    """终端交互模式：先在命令行里选模型，再选界面后端（``--menu``）。"""
    spec = _resolve_model(args)
    if spec is None:
        return 1
    ui_key = _choose_ui()
    if ui_key is None:
        return 0

    backend = get_ui(ui_key)
    _announce(spec, backend)
    try:
        return int(backend.entry(spec, args) or 0)
    except KeyboardInterrupt:
        print("\n已中断。")
        return 0
    except Exception as exc:
        print(f"\n× 启动失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _looks_headless(exc: Exception) -> bool:
    """异常是不是「这台机器开不了桌面窗口」（无显示 / 没装 tkinter）。"""
    return isinstance(exc, ImportError) or "TclError" in type(exc).__name__


def _fallback_without_gui(args, exc: Exception) -> int:
    """桌面窗口起不来时的降级：交互终端 → 终端菜单；否则 → 终端统计模式。"""
    print(f"\n ! 无法启动桌面窗口：{type(exc).__name__}: {exc}", file=sys.stderr)
    if sys.stdin.isatty():
        print("   （可能没有图形环境）改用终端交互模式。\n")
        return _interactive_flow(args)

    print("   （可能没有图形环境，且当前不是交互式终端）改用终端统计模式。\n")
    spec = _resolve_model(args)
    if spec is None:
        return 1
    try:
        return int(get_ui("cli").entry(spec, args) or 0)
    except Exception as cli_exc:
        print(f"× 终端模式也未能运行：{type(cli_exc).__name__}: {cli_exc}", file=sys.stderr)
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        _print_models()
        print()
        _print_uis()
        return 0

    print()
    print(_rule("═"))
    print(" 数学模型可视化工具箱 · 统一入口")
    print(_rule("═"))

    # 保留原来的终端交互流程（选模型 → 选界面）
    if args.menu:
        return _interactive_flow(args)

    ui_key = args.ui or "tk"          # 默认：桌面窗口
    try:
        backend = get_ui(ui_key)
    except KeyError as exc:
        print(f"× {exc}", file=sys.stderr)
        return 1

    if ui_key == "tk":
        # 桌面窗口：给了 --model 就直接进那个模型，否则先显示模型列表入口页
        spec: Optional[ModelSpec] = None
        if args.model:
            try:
                spec = find(args.model)
            except ModelNotFound as exc:
                print(f"× {exc}", file=sys.stderr)
                _print_models()
                return 1
    else:
        # cli / web 必须落到具体模型上
        spec = _resolve_model(args)
        if spec is None:
            return 1

    _announce(spec, backend)

    try:
        return int(backend.entry(spec, args) or 0)
    except KeyboardInterrupt:
        print("\n已中断。")
        return 0
    except Exception as exc:  # 给用户一个友好的失败提示
        if ui_key == "tk" and _looks_headless(exc):
            return _fallback_without_gui(args, exc)
        print(f"\n× 启动失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
