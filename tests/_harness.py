"""重构护栏 1：金样本回归（把"重构前的结果"钉死）。

各模型的内核自检（``python -m awe_math.models.<模型>.model``）已实测为**完全确定性**
（连跑两次逐字节相同），所以可以当"金样本"逐字比对。这是本仓库性价比最高的一张网：
它一次性覆盖了所有已经写进文档的教学结论 ——

* 渗流（键/点）：四种方向模式的表观交点 vs p_c、尺寸依赖、三种判据 × 三种注水方式、
  "同一批格地/网格"的一致性对照；
* 投针：固定种子下 π 估计随 N 的收敛表、多组重复的均值 ± 标准差；
* 生命游戏：方块 / 闪烁器 / 脉冲星 / 滑翔机 / 滑翔机枪 / R 五连块、图案表、环面收敛、
  初始密度 → 长期结局的扫描表；
* 万有引力多星：两体圆轨道与 8 字三体的回位偏差、守恒量（能量/动量/角动量）、
  固定种子下随机场景的末态半径与逃逸数、以及 dt -> 最大能量漂移的二阶收敛表。

**为什么用子进程跑**：用户就是这么跑的（``python -m …``），子进程能同时钉住
"能否独立运行"这件事；顺带避免把模型的 import 副作用带进测试进程。
stderr 里的 ``RuntimeWarning``（``-m`` 导入同名模块的提示）是解释器噪音，不参与比对。

重新生成金样本（**只在确认结果的变化是有意为之之后**）::

    python -m tests._harness --update                # 全部模型刷新
    python -m tests._harness --update life_game      # 只刷新一个（重构时通常只需要这样）

文件格式：``tests/golden/<模型>.txt``，UTF-8 无 BOM，行尾统一 ``\\n``。

金样本更新记录（每次刷新都要在这里写一句"为什么"）
--------------------------------------------------
* 2026-09-22 ``n_body``：**新增模型**（万有引力多星），首次生成金样本。
  自检输出全是确定性数字：两体圆轨道的半径/回位偏差、8 字三体一个周期后的最大偏差、
  随机场景（固定种子 20260922）的末态最大半径与逃逸数、以及 dt -> 最大能量漂移的
  二阶收敛表（dt 减半、漂移降为约 1/4）。它钉住的是**积分器与守恒量**，
  不是"某一帧长什么样"。
* 2026-09-17 ``life_game``：内核改为 numpy 向量化，随机源由 ``random.Random`` 换成
  ``numpy.random.default_rng``。**随机相关的几行随之变化**：12×12 环面的收敛代数列表、
  密度扫描表、以及"环面 20×20（600 代）"那一行的结局（换了个随机开局，于是它这次
  收敛到了周期 2）。纯确定性的结论（方块 / 闪烁器 / 脉冲星 / 滑翔机坐标 / 图案表 /
  R 五连块在 200 代后的 61 个细胞）一字未改 —— 这也是为什么"改 RNG"不等于"改语义"。
* 2026-09-17 ``buffon_needle``：内核改为 numpy 向量化（几何由"逐根对象"改成数组，
  ``ThrowResult.needles`` 变成按需构建的兼容属性），随机源同样换 ``default_rng`` ——
  于是**整张 π 收敛表与"多组重复"那一行都变了**（同一批种子现在抽出的是另一组针；
  量级一致、误差仍在 1/√N 的预期带内，例如 2 万针的误差 0.0198 → 0.0102）。
* 2026-09-18 ``site_percolation``：内核向量化（格地改 numpy 布尔数组、一次抽满；
  蔓延改"预编译邻居表 + bytes 标记"的紧凑循环），随机源换 ``default_rng`` ——
  于是表观交点、各判据的 P 与平均比例都变了，但**量级与方向性不变**（无向表观交点
  仍在 p_c = 0.5927 附近；"起点判据 < 贯通判据"、"面积判据最低"那档关系不变）。
  这次重构的等价性由 ``tests/test_site_percolation.py`` 单独钉住（边表与几何逐条一致、
  蔓延与朴素 BFS 同集合同分层），所以这里的数字变化只是换随机源。
  同日又把点渗流的**默认注水方式由 ``random`` 改成 ``top``**（与边渗流一致，也对齐
  p_c 的经典实验"顶端整行注水 → 能否到底端"）：自检 1 的"平均比例"列随之变化
  （0.196 → 0.322 等，顶端整行注水的簇本来就比"随机一格"的簇大得多），而
  **P 值那一列一字未动** —— 恰好再次验证了"贯通判据与注水方式无关"。
* 2026-09-18 ``percolation``：内核向量化（边由逐边 Python 随机改成一次抽满 numpy 数组、
  蔓延改"预编译邻居表 + bytes 掩码"的紧凑循环、``encode_edges`` 向量化），随机源换
  ``default_rng`` —— p_c 表与各判据的 P/平均比例随之变化，量级与方向性不变
  （无向表观交点 0.4980 → 0.5004；尺寸依赖 n = 40/80 → 0.4991/0.4972，都在 p_c = 0.5 附近）。
  等价性由 ``tests/test_percolation.py`` 的 16 条护栏钉住（邻居表逐条一致、逐层推进与
  朴素 BFS 同集合同分层、并查集与 BFS 同答案、bytes 掩码与分类型边表互相对得上）。
  **这次护栏当场抓到一个真 bug**：三角网的斜边数组里夹着"越界占位"，于是"边号 → 拼接
  下标"被挤偏 —— 方格网（自检唯一覆盖的格子类型）完全正常，是护栏把它挖出来的。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import Optional, Sequence

__all__ = [
    "GOLDEN_DIR",
    "MODELS",
    "ROOT",
    "first_diff",
    "golden_path",
    "main",
    "normalize",
    "read_golden",
    "run_selfcheck",
    "write_golden",
]

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN_DIR = pathlib.Path(__file__).resolve().parent / "golden"

#: 参与金样本回归的模型（顺序 = 报告顺序；与 ``requirements.txt`` / README 的模型表一致）
MODELS: Sequence[str] = ("life_game", "buffon_needle", "site_percolation", "percolation", "n_body")


def normalize(text: str) -> str:
    """统一行尾并保证以单个换行结尾（Windows / Linux 上都能逐字比对）。"""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"


def run_selfcheck(model: str, timeout: float = 900.0) -> str:
    """在仓库根目录跑一个模型的内核自检，返回归一化后的 stdout。"""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", f"awe_math.models.{model}.model"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"{model} 的自检没能跑完（退出码 {proc.returncode}）：\n{proc.stderr.strip()}"
        )
    return normalize(proc.stdout)


def golden_path(model: str) -> pathlib.Path:
    return GOLDEN_DIR / f"{model}.txt"


def read_golden(model: str) -> str:
    return normalize(golden_path(model).read_text(encoding="utf-8"))


def write_golden(model: str, text: str) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    golden_path(model).write_text(normalize(text), encoding="utf-8", newline="\n")


def first_diff(expected: str, actual: str, limit: int = 8) -> str:
    """逐行比对，返回"从第一处差异开始"的报告；完全一致时返回空串。

    不用 ``assertEqual`` 直接比整份文本：那会在失败时把几百行都打出来，
    而真正有用的信息只有"从哪一行开始不一样、差在哪"。
    """
    exp = expected.splitlines()
    act = actual.splitlines()
    if exp == act:
        return ""
    out = []
    for i in range(max(len(exp), len(act))):
        e = exp[i] if i < len(exp) else "<这一行起金样本就没有了>"
        a = act[i] if i < len(act) else "<金样本多出这一行>"
        if e != a:
            out.append(f"  第 {i + 1} 行\n    金样本: {e}\n    实际  : {a}")
            if len(out) >= limit:
                out.append(f"  …（金样本共 {len(exp)} 行，实际共 {len(act)} 行）")
                break
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--update" not in args:
        print(__doc__)
        print("（加 --update 才真的写入；可再给一个模型名只刷新它，否则全部刷新）")
        return 0
    names = [arg for arg in args if not arg.startswith("-")] or list(MODELS)
    for model in names:
        if model not in MODELS:
            print(f"没有这个模型：{model}（可选：{', '.join(MODELS)}）", file=sys.stderr)
            return 2
        write_golden(model, run_selfcheck(model))
        print(f"已写入 {golden_path(model).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
