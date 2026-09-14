# 数学模型可视化工具箱（awe_math）

把数学模型的**计算内核**、**元数据**与**界面**分开组织：一个模型一个目录，同一个模型可以挂到
桌面窗口 / 终端 / 网页等不同界面后端上，而界面代码跟着模型走。

* **一个模型 = 一个目录**：新增模型只加目录，不改任何已有文件；
* **界面可更换**：模型只负责计算与数据结构，不关心渲染方式；
* **默认入口是桌面窗口**：`python main.py` 先给出一张模型列表，点卡片进入。

---

## 快速开始

```bash
python main.py
```

不需要安装任何第三方包（tkinter 是 Python 自带的）；装了 `matplotlib` 才会有右侧的 P(p) 曲线页。

---

## 入口与命令行

| 命令 | 行为 |
| --- | --- |
| `python main.py` | 桌面窗口 → **模型列表入口页**（点卡片进入某个模型） |
| `python main.py --model percolation` | 跳过列表，直接进这个模型的窗口 |
| `python main.py --menu` | **终端交互模式**：在命令行里依次选模型、选界面 |
| `python main.py --list` | 列出全部模型与界面后端（含"暂时弃用"标注） |
| `python main.py --model perc --ui cli --p 0.5 --trials 500` | 终端里跑一次批量统计 |
| `python main.py --model percolation --ui cli --scan` | 终端里扫描 P(p) 曲线（不开窗口） |
| `python main.py --ui web` | 网页界面（**暂时弃用**，需显式指定，见下文） |
| `python -m awe_math.ui.tk` | 等价于 `python main.py`（直接从包内部启动桌面窗口） |

`--model` 支持标识（`percolation`）、序号（`1`）与名称关键字（`perc`）。
进入模型后，窗口顶部的「模型」下拉框与「☰ 模型列表」按钮可以随时切换。

**没有图形环境时不会报错**：交互终端会自动转成 `--menu` 的终端菜单，非交互调用则直接跑
终端统计模式，不会甩一个 traceback 出来。

---

## 当前模型

| 标识 | 名称 | 主题 | 关键数字 |
| --- | --- | --- | --- |
| `percolation` | ≋ 边渗流模型 | 量变引起质变 | 方格网 p_c = 0.5、三角网 ≈ 0.3473、有向 ≈ 0.6447 |
| `site_percolation` | ▦ 点渗流模型 | 量变引起质变 | 方格网 p_c ≈ 0.5927、三角网 0.5 |

两个模型都支持：方形 / 矩形区域、方格网 / 三角网、四种方向模式（无向、不允许向上、
只允许向下向右、只允许向下向左）、三种注水方式，以及三种成功判据 + 批量统计 + 曲线扫描。

### 三种「成功判据」不是一回事（本项目最容易误解的地方）

| 判据 | 回答的问题 | 曲线与 50% 的交点 |
| --- | --- | --- |
| **贯通** `span`（默认） | 整片区域是否存在顶行 ↔ 底行的**纵贯簇** | **= p_c**，且与注水方式无关 |
| **起点** `origin` | 从注水点出发的那一簇是否纵贯 | 高于 p_c（顶端整行注水时相等） |
| **面积** `area` | 从注水点出发的活动面积是否达到设定比例 | **不是 p_c**，随比例 / 尺寸 / 注水方式漂移 |

界面上凡随判据变化的东西（统计行标题、结论徽章、曲线纵轴、p_c 参考线、历史表列名）都会
跟着改，所以「p_c」只在贯通判据下才有定义。

---

## 界面后端

| key | 状态 | 说明 |
| --- | --- | --- |
| `tk` | **默认** | 桌面窗口：模型列表入口页 + 逐层动画 + 批量统计 + P(p) 曲线 |
| `cli` | 可用 | 终端统计模式，适合批量化出数与脚本化 |
| `web` | **暂时弃用** | 网页界面；不再出现在入口页与终端菜单里，只能 `--ui web` 显式进入（代码保留） |

---

## 项目结构

```
main.py                          唯一入口（转发给 launcher）
awe_math/
├── spec.py                      模型元数据规范：参数 / 动作 / 视图
├── registry.py                  模型注册表 + 「一个模型长什么样」的目录约定
├── launcher.py                  入口流程：默认桌面窗口 / --menu / --ui 指定后端
├── models/                      各数学模型（每个包自带自己的界面）
│   ├── _options.py              模型间共用的选项词表
│   ├── _geometry.py             模型间共用的格子几何
│   ├── percolation/             边渗流
│   │   ├── __init__.py          register(spec)：导入本包即完成注册
│   │   ├── model.py             纯计算内核（并查集 + BFS 分层）
│   │   ├── spec.py              参数 / 动作 / view="percolation"
│   │   └── views/tk.py          桌面视图（@register_view 登记）
│   └── site_percolation/        点渗流（结构同上）
└── ui/                          界面后端
    ├── __init__.py              后端注册表（tk / cli / web）
    ├── tk/                      桌面窗口（默认）
    │   ├── __main__.py          支持 python -m awe_math.ui.tk
    │   ├── shell.py             窗口外壳：模型下拉框 + 「☰ 模型列表」+ 视图切换
    │   ├── portal.py            模型列表入口页
    │   ├── theme.py             深色扁平主题（配色 / 字体 / ttk 样式）
    │   └── kit/                 桌面界面工具箱：与模型无关的共享骨架
    │       ├── base.py          视图基类：装配 + 参数判据状态机 + 钩子契约
    │       ├── canvas.py        画布、逐层动画、图例、结论
    │       ├── controls.py      左侧参数栏（卡片族）
    │       ├── results.py       右侧三个标签页 + P(p) 曲线
    │       ├── jobs.py          后台任务（线程 / 队列 / 进度 / 停止）
    │       ├── common.py        术语表、结果归一化、共享配色与工具
    │       └── __init__.py      视图注册表（按约定自动发现）
    └── web/                     网页界面（暂时弃用，代码保留）
```

**三条硬规则**（改代码时请遵守）：

1. `model.py` **只依赖标准库**，不要 import 界面代码——纯计算要能单独导入、单独测试；
2. `views/` **只被对应后端懒加载**：不要在模型的 `__init__.py` 里 import 它，否则网页服务、
   终端模式会被迫加载 tkinter / matplotlib；
3. **界面骨架按后端放**（`ui/<后端>/`），**模型特化跟着模型走**
   （`models/<模型包>/views/<后端>.py`）——所以新增界面后端不必回头改模型，新增模型也不必
   改界面。

---

## 新增一个模型

以「蒲丰投针」为例，只加一个目录（不改任何已有文件）：

```
awe_math/models/buffon_needle/
    __init__.py     # register(build_spec())
    model.py        # 投针几何 + Monte Carlo 估计（纯计算）
    spec.py         # 参数（针长 / 线距 / 投针次数）、动作、view="buffon_needle"
    cli.py          # 可选：--ui cli 下的入口（spec.cli）
    views/
        tk.py       # 可选：桌面视图
```

**第一步**：`spec.py` 里给一个 `view` 名（就是渲染器标识）：

```python
ModelSpec(
    key="buffon_needle", name="蒲丰投针", topic="概率与统计",
    summary="随机投针估计 π", view="buffon_needle",
    params=(...), actions=(...), handler=handle,
)
```

**第二步（可选）**：想要专属桌面界面，就在同一个包里写 `views/tk.py`，继承工具箱基类并用
装饰器登记**同名** view：

```python
from awe_math.ui.tk.kit import PercolationViewBase, Terms, register_view

@register_view("buffon_needle")
class BuffonView(PercolationViewBase):
    TERMS = Terms(arena="桌面", unit="针", active_verb="命中", ...)
    STAT_ROWS = (("投针次数", "p"), ("估计 π", "size"), ...)

    def _create_model(self, **kwargs): return BuffonNeedle(**kwargs)
    def _active_view(self): ...
    def _draw_base(self): ...
```

**第三步**：`python main.py` —— 入口页会自动出现这张卡片；终端里 `python main.py --list`
也能立刻看到它。没有 `views/tk.py` 的模型同样能用，会落到「跑动作 + 看 JSON 结果」的
通用视图，不会因为"没写界面"而报错。

> **关于第二步的适用性**：桌面视图基类 `PercolationViewBase` 目前是围绕「概率 p + 格子 +
> 判据 + 逐层蔓延」这一类模型设计的（钩子清单见 `base.py` 顶部与 `kit/` 各 mixin）。
> 非渗流模型如果不贴合，可以：① 先不写 `views/tk.py`，用通用视图；② 或者直接用 `kit` 里的
> 画布 / 面板 / 后台任务 mixin 拼一个更贴合的基类。接入第一个非渗流模型，正是把基类抽象
> 改准的最佳时机。

---

## 环境要求

| 依赖 | 说明 |
| --- | --- |
| Python | 3.9+（开发与实测环境：3.13.9 / Anaconda） |
| tkinter | Python 自带；部分 Linux 发行版需另装 `python3-tk` |
| matplotlib | **可选**，只有 P(p) 曲线页需要；缺失时该页显示提示，其余功能照常 |

---

## 想深入了解代码

模块文档字符串写得比较细，按需跳读：

| 想了解 | 看这里 |
| --- | --- |
| 模型怎么注册、一个模型包含哪些文件 | `awe_math/registry.py` |
| 参数 / 动作 / 视图的元数据规范 | `awe_math/spec.py` |
| 入口流程与无图形环境的降级策略 | `awe_math/launcher.py` |
| 桌面视图的骨架与需要子类实现的钩子 | `awe_math/ui/tk/kit/base.py` |
| 视图怎么被自动发现（约定优于中心清单） | `awe_math/ui/tk/kit/__init__.py` |
| 一个真实模型的完整视图实现 | `awe_math/models/percolation/views/tk.py` |

---

## 已知状态

* **网页后端暂时弃用**：代码保留在 `ui/web/`，把 `awe_math/ui/__init__.py` 里 `web` 的
  `deprecated` 改回 `False` 即可恢复为可选后端；
* 桌面视图基类目前只被两个渗流类模型用过：接入非渗流模型（例如蒲丰投针）时，若发现
  `_active_view` / `_draw_base` 这类钩子不够通用，正是把抽象改准的时机。
* `ui/tk/kit/` 里的画布 / 面板 / 后台任务是按 mixin 拆的，它们依赖「由基类最终提供」的
  属性（`self.model`、`self.var_status`、`self._terms` 等）。运行完全正常，但**静态检查器
  单独分析某个 mixin 时会报一堆 "Cannot access attribute"**——这是 mixin 的固有代价。
  如果需要消掉这些提示，可以加一份 `TYPE_CHECKING` 下的属性契约（把所有共享属性声明一遍，
  让各 mixin 继承它）；顺带也能把「基类必须提供什么」写成可执行的文档。
