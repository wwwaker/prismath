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
    python main.py --ui qt                           # Qt 桌面界面（默认）

几个约定：

* ``--ui`` 省略时用 ``qt``（桌面窗口）；``--model`` 省略时先停在模型列表页让用户挑。
* ``tk`` 保留为旧视图兼容后端；项目默认不启动浏览器网页界面。
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

from ._deps import exit_if_missing
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
        prog="prismath",
        description="数学模型可视化工具箱：默认打开桌面窗口的模型列表入口页",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python main.py                               打开桌面窗口的模型列表（默认）\n"
            "  python main.py --model percolation           直接进边渗流模型的窗口\n"
            "  python main.py --menu                        终端交互模式（选模型 → 选界面）\n"
            "  python main.py --model perc --ui cli --scan  终端里扫描 P(p) 曲线\n"
            "  python main.py --model buffon --ui cli --ratio 0.6 --throws 5000\n"
            "                                               终端里投针估计 π\n"
            "  python main.py --ui qt                       Qt 桌面界面（默认）\n"
        ),
    )
    parser.add_argument("--list", action="store_true", help="列出所有模型与界面后端后退出")
    parser.add_argument("--model", "-m", default=None,
                        help="模型标识、序号或名称关键字；省略则先在模型列表里挑")
    parser.add_argument("--ui", "-u", default=None, choices=("qt", "tk", "cli"),
                        help="界面后端：qt（默认，PySide6 桌面窗口）/ tk（兼容）/ "
                             "cli（终端统计）")
    parser.add_argument("--menu", action="store_true",
                        help="终端交互模式：在命令行里依次选择模型与界面后端")
    parser.add_argument("--seed", type=int, default=-1,
                        help="随机种子，-1 表示随机（所有模型通用）")

    _add_model_options(parser)
    return parser


def _add_model_options(parser: argparse.ArgumentParser) -> None:
    """把各模型用 ``spec.cli_options`` 声明的命令行参数汇总进解析器。

    同一组选项串只登记一次（多个模型共用时会标注在帮助里），因此渗流模型可以共用一套
    ``GRID_CLI_OPTIONS``，而蒲丰投针用自己的 ``--ratio`` / ``--throws`` —— 
    **不再是"借别人的参数名当别名"**。

    不属于当前模型的选项会被解析器接受但在执行时忽略：这是"一个入口、多个模型"的取舍，
    换来的是每个模型的参数名都能贴合自己的语义。
    """
    try:
        models = load_models()
    except Exception:            # 模型导入失败时不影响 --help / --list 等基础功能
        return

    collected: "dict[tuple, list]" = {}
    for spec in models:
        for option in getattr(spec, "cli_options", ()) or ():
            collected.setdefault(tuple(option.flags), []).append((spec, option))
    if not collected:
        return

    # 同一个属性名不能由两组不同的选项串声明：argparse 允许这么加，后写的会静默覆盖先写的，
    # 于是 _cli 取到的默认值属于谁就说不清了 —— 这种隐患在启动时直接报错更省事。
    by_key: "dict[str, tuple]" = {}
    for flags, entries in collected.items():
        for _spec, option in entries:
            previous = by_key.setdefault(option.key, flags)
            if previous != flags:
                raise ValueError(
                    f"命令行选项声明冲突：属性名 {option.key!r} 同时来自 {previous} 与 {flags}；"
                    "请用 CliOption(dest=...) 明确区分，或合并成一个声明"
                )

    group = parser.add_argument_group(
        "模型参数（含义随所选模型而定；不属于当前模型的参数会被忽略）")
    for flags, entries in collected.items():
        option = entries[0][1]
        kwargs = option.to_argparse()
        owners = list(dict.fromkeys(spec.name for spec, _ in entries))
        if len(owners) > 1 and kwargs.get("help"):
            kwargs["help"] = f"{kwargs['help']}（{' / '.join(owners)} 通用）"
        try:
            group.add_argument(*flags, **kwargs)
        except argparse.ArgumentError:      # 与通用选项冲突：跳过，保留通用那个
            continue


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
    uis = list_uis()
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
    """异常是不是「这台机器开不了桌面窗口」（无显示 / 没装 tkinter）。

    只认 tkinter / Tcl 相关的失败。早先这里对**任何** ImportError 都返回 True，
    于是"缺 numpy"（模型包在导入期抛 ModuleNotFoundError）会被误判成"没有图形环境"，
    白绕一圈终端降级、最后仍然抛出堆栈 —— 现在依赖问题由 :func:`exit_if_missing`
    在入口处拦下，这里也就不该再认领它。
    """
    if "TclError" in type(exc).__name__:
        return True
    if isinstance(exc, ImportError):
        name = str(getattr(exc, "name", "") or "")
        return name in ("tkinter", "_tkinter") or name.startswith("tkinter.")
    return False


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
    # argparse 先跑：`--help` / `--version` 这类"只看不用"的请求不该被依赖检查拦住
    # （build_parser 里汇总模型选项那步已经吞掉了导入失败，所以这一步不需要 numpy）。
    args = build_parser().parse_args(argv)

    # 依赖自检：缺 numpy 时给一句可操作的提示，而不是让模型包在深处抛 ImportError 堆栈。
    # 放在这里而不是 main.py：所有入口（默认 tk / --menu / --list / --ui）都会经过它。
    exit_if_missing()

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

    ui_key = args.ui or "qt"          # 默认：PySide6 桌面窗口
    try:
        backend = get_ui(ui_key)
    except KeyError as exc:
        print(f"× {exc}", file=sys.stderr)
        return 1

    if ui_key in ("tk", "qt"):
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
        # cli 必须落到具体模型上
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
        if ui_key in ("tk", "qt") and _looks_headless(exc):
            return _fallback_without_gui(args, exc)
        print(f"\n× 启动失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
