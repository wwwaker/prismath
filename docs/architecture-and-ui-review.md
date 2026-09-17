# 架构与 UI 评审文档（awe_math）

> 生成日期：2026-09-15
> 适用代码版本：已包含 Step 1（P1–P4 修复、`CliArgs`、三层骨架文档同步）
> 阅读对象：本项目后续维护者 / 新增模型或界面后端的开发者

本文档记录项目的**架构现状**、**扩展方式**、**成熟度评估**、**遗留问题清单**与**改进路线**。
README 面向使用者，本文档面向开发者与后续重构决策。

---

## 1. 目的与范围

| 项目 | 说明 |
| --- | --- |
| 目标 | 把数学模型的**计算内核**、**元数据**与**界面**彻底分开，界面可插拔 |
| 范围 | 架构分层、核心机制、扩展指南、风险评估、UI 重构路线 |
| 不在范围 | 各模型的数学正确性论证（见各 `model.py` 的模块文档） |

---

## 2. 架构总览

### 2.1 分层

```
┌──────────────────────────────────────────────────────────────────┐
│ 入口层        main.py → launcher.py                               │
│               CLI 解析 / 默认桌面窗口 / --menu / 无图形环境降级     │
├──────────────────────────────────────────────────────────────────┤
│ 注册与元数据  registry.py（模型注册表 + 目录约定）                   │
│               spec.py（ParamSpec / ActionSpec / CliOption /        │
│                        CliArgs / ModelSpec）                       │
├──────────────────────────────────────────────────────────────────┤
│ 模型层        models/<模型包>/                                     │
│               model.py   纯计算（只依赖标准库）                     │
│               spec.py    元数据 + handler + cli + cli_options      │
│               views/     该模型在各后端下的特化视图（可选、懒加载）   │
├──────────────────────────────────────────────────────────────────┤
│ 界面后端层    ui/__init__.py   后端注册表 tk / cli / web            │
│               ui/tk/           桌面窗口（默认）                     │
│               ui/web/          网页（暂时弃用）                     │
├──────────────────────────────────────────────────────────────────┤
│ 桌面工具箱    ui/tk/kit/       三层骨架 + mixin + 契约 + 判据策略    │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
main.py                          唯一入口（转发给 launcher）
awe_math/
├── spec.py                      参数 / 动作 / CLI 选项 / 模型元数据规范
├── registry.py                  模型注册表 + 「一个模型长什么样」的目录约定
├── launcher.py                  入口流程；汇总各模型的 CLI 选项声明
├── models/
│   ├── _options.py              模型间共用的选项词表（中文标签 → 内部取值）
│   ├── _geometry.py             模型间共用的格子几何
│   ├── _cli.py                  渗流类模型共用的命令行选项声明
│   ├── buffon_needle/           非渗流：通用图表骨架 + Monte Carlo
│   ├── life_game/               栅格类：栅格图元 + 时间轴播放 + 点击涂改（元胞自动机）
│   ├── percolation/             边渗流
│   └── site_percolation/        点渗流（结构与边渗流对称）
└── ui/
    ├── __init__.py              后端注册表（tk / cli / web）
    ├── tk/
    │   ├── shell.py             窗口外壳：模型下拉框 + 门户 + 视图切换
    │   ├── portal.py            模型列表入口页
    │   ├── theme.py             深色扁平主题
    │   └── kit/                 桌面工具箱
    │       ├── base.py          ModelViewBase + PercolationViewBase
    │       ├── chart.py         ChartViewBase + ChartSpec
    │       ├── canvas.py        画布 / 逐层动画 / 图例 / 结论（mixin）
    │       ├── controls.py      左侧参数栏（mixin）
    │       ├── results.py       右侧三标签页 + P(p) 曲线（mixin）
    │       ├── jobs.py          后台任务：批量统计 / 曲线扫描（mixin）
    │       ├── form.py          按 spec.params 自动生成参数表单（mixin）
    │       ├── criteria.py      判据策略对象
    │       ├── common.py        术语表 / 结果归一化 / 共享配色
    │       ├── protocols.py     模型契约与视图属性契约
    │       └── __init__.py      视图注册表（按约定自动发现）
    └── web/                     网页界面（暂时弃用，代码保留）
```

### 2.3 三条硬规则

1. **`model.py` 只依赖标准库** —— 纯计算要能单独导入、单独测试；不得 import 界面代码。
2. **`views/` 只被对应后端懒加载** —— 不要在模型的 `__init__.py` 里 import 它，否则网页服务、终端模式会被迫加载 tkinter / matplotlib。
3. **界面骨架按后端放**（`ui/<后端>/`），**模型特化跟着模型走**（`models/<模型包>/views/<后端>.py`）—— 新增后端不必回头改模型，新增模型也不必改界面。

---

## 3. 核心机制

### 3.1 注册与发现：零中心清单

| 机制 | 位置 | 说明 |
| --- | --- | --- |
| 模型注册 | `registry.register` | 模型包 `__init__.py` 里 `register(build_spec())`，导入即注册 |
| 模型扫描 | `registry.load_models` | 遍历 `models/` 下的子包，跳过 `_` 开头的共用件（`_options` / `_geometry` / `_cli`） |
| 视图发现 | `kit.discover_views` | 按模板 `VIEW_MODULE_TPL = "awe_math.models.{package}.views.tk"` 尝试导入；`ModuleNotFoundError` 时跳过 |
| 视图登记 | `kit.register_view(key)` | 类装饰器，把视图类挂到 `spec.view == key` 名下 |
| 视图回落 | `shell.view_for(spec.view) or FallbackView` | 没有专用视图时自动落到通用兜底视图 |

**推导结果**：没有任何文件需要手写「模型 → 视图」映射，因此不存在「忘了登记」的可能。

### 3.2 两套契约

| 契约 | 字段 | 使用方 |
| --- | --- | --- |
| **数据级** | `spec.params` + `spec.handler(action, params, payload) -> dict` | 所有后端（cli / web / 通用视图 / 桌面兜底） |
| **对象级**（可选） | `spec.factory(params)` + `spec.batch` + `spec.scan` | 桌面画布、动画、后台统计 |

关键约束：**同一份「界面参数 → 模型」的换算只写一处**。渗流模型用 `spec.py` 里的 `build_grid()`
同时服务 `handler` 与 `factory`；非渗流模型只写 `handler` 即可（`ChartViewBase` 走数据级契约）。

### 3.3 CLI 选项归模型所有

```
模型声明 spec.cli_options: Tuple[CliOption, ...]
        ↓
launcher.build_parser → _add_model_options()
        ↓  按 flags 去重、启动期冲突守卫、多模型共用的在帮助里标注
argparse 解析
        ↓
spec.cli(CliArgs(raw_args, MY_OPTIONS))   ← 按「声明」取值
```

- `CliOption`：`flags` / `kind`（`str|int|float|choice|flag`）/ `default` / `choices` / `dest`。
- `CliArgs`：`args.rows` 的名字与默认值**都来自声明**，替代手写 `getattr(args, "rows", 40)` 魔法字符串；
  未声明的名字退化为普通属性访问（通常当场 `AttributeError`，而不是静默用默认值）。
- 启动期守卫：同一个属性名若来自**不同**的选项串声明，直接 `ValueError`（见 `launcher._add_model_options`）。
- 已知取舍：**不属于当前模型的选项会被接受但在执行时忽略**（一个入口、多个模型的代价）。

### 3.4 桌面视图三层骨架

按「要写多少界面代码」从少到多：

| 层次 | 类 | 自动完成 | 需自己写 | 适用 |
| --- | --- | --- | --- | --- |
| 1 | `ChartViewBase`（`kit/chart.py`） | 参数表单、动作按钮、画布、坐标轴/网格/参考线、逐帧动画、指标行 | `CHART_SPECS` + `RESULT_ROWS` 等**声明** | 多数非渗流模型 |
| 2 | `ModelViewBase`（`kit/base.py`） | 参数表单、动作按钮、状态栏、线程机制 | 中央画布 + 右侧面板 | 布局完全自定义 |
| 3 | `PercolationViewBase` | 在层次 2 之上补「概率 + 格子 + 判据 + 逐层蔓延」 | 术语表、指标行、几个画布钩子 | 渗流类模型 |

`ChartSpec.kind` 目前支持：`segments`（线段云）/ `series`（曲线族）/ `bars`（柱状）/
**`grid`（栅格：离散态逐帧差分刷新，或连续场图像缓冲）** / `text`（纯文字）。
带 `animate=True` 的图会逐帧出现，并可配 `_partial_rows` 让指标随样本实时刷新。

栅格图（`kind="grid"`）另外带来两件事：

* **时间轴**：`frames`（每帧一个 0/1 掩码）在动画里**每次前进恰好一帧**（而不是把总时长
  摊成固定 48 帧），于是"动画间隔"滑块就是"每一帧之间的停顿"，元胞自动机不会被跳帧；
* **播放控制与点击反查**：播放卡片是 **▶ 播放 / ⏸ 暂停 + ⏭ 下一帧**（对既有图表同样生效），
  `clickable=True` 时画布把按下 / 拖动反查成 `(行, 列)` 交给 `_on_cell_click(row, col, start)`
  （`start` 区分"按下"与"拖动中" —— 一次拖画算一笔，长按不会反复翻转）。

**注意**：`frames` 时间轴与"实时逐代播放"是两条并列的路子。生命游戏的桌面端选了后者
（不设代数上限，见 §6.1 的 S2-7），`frames` 留给无头后端（终端回放 / 未来的网页）；
两者共用同一套栅格差分渲染与同一个 `LifeWatch` 判定。

可选钩子（`ChartViewBase`）
--------------------------
* 数据类：`_badge_for(payload, values)`、`_partial_rows(payload, drawn)`、
  `_status_for(payload, values, partial)`、`_speed_hint()`；
* 交互类：`_on_cell_click(row, col, start)`（返回新 payload 表示"已修改，请原地重绘"）；
* 布局插槽：`_build_top_cards`（侧栏最上面）、`_build_player_extra`（播放卡片内）、
  `_param_card_footer(card, group)`（某个参数分组卡片底部）、`_build_right_extra(panel, row)`
  （右侧指标下方的空位）。四个插槽默认都是空的，所以既有视图不受影响。

### 3.5 判据策略对象

「什么算成功」的全部界面语义（徽章 / 结论 / 统计词 / 历史表列名 / 曲线标注 / 是否对应 `p_c`）
收在 `Criterion` 里，内置 `span` / `origin` / `area` 三种。工具箱不认识任何具体判据，
模型扩展判据只需覆盖 `PercolationViewBase.CRITERIA`。

### 3.6 术语表与结果归一化

- `Terms`：一个模型的全部用词（网格/格地、节点/格、浸润/蔓延……），基类文案由它拼出。
- `ActiveView`：把 `SimResult` / `SpreadResult` 的不同字段名归一化成同一套，基类只认归一化后的名字。

于是边渗流与点渗流两个视图结构完全对称，差异集中在术语、配色与画布钩子。

### 3.7 后台任务线程模型

```
后台线程（batch / scan）──► self._queue ──► 主线程 _poll_queue（root.after 轮询）
        ▲                                          │
        └──── self._cancel（threading.Event）◄─────┘ 「停止」按钮
```

计算线程绝不触碰 Tk 控件；视图切换 / 关闭时 `shutdown()` 取消全部挂起回调。

### 3.8 懒加载与优雅降级

| 场景 | 行为 |
| --- | --- |
| 未装 matplotlib | 曲线页显示提示，其余功能照常 |
| 无 tkinter / 无显示 | 交互终端 → `--menu` 菜单；非交互 → 直接跑 CLI 统计，不抛 traceback |
| 模型没有桌面视图 | 落到 `FallbackView`（参数表单 + 动作按钮 + JSON 结果） |
| 模型导入失败 | `_add_model_options` 静默跳过，不影响 `--help` / `--list` |

---

## 4. 扩展指南

### 4.1 新增模型（只加一个目录）

```
awe_math/models/<模型包>/
    __init__.py     # register(build_spec())
    model.py        # 纯计算，只 import 标准库
    spec.py         # PARAMS / ACTIONS / handler / cli / cli_options / view
    views/
        tk.py       # 可选：@register_view("<spec.view>")
```

1. 写 `spec.py`：给出 `view` 名 + `handler`；命令行参数用 `CliOption` 声明，`_cli` 里用 `CliArgs` 取值。
2. （可选）写 `views/tk.py`：按范式选骨架 —— 非渗流一般用 `ChartViewBase` 只写声明。
3. `python main.py` —— 入口页自动出现卡片；`--list` 也能立刻看到。

**不需要登记任何中心清单。**

### 4.2 新增判据

在模型的 `PercolationViewBase.CRITERIA` 里加一条 `Criterion` 策略（短名、统计词、徽章、结论、曲线标注），
不必改工具箱。

### 4.3 新增界面后端

在 `ui/__init__.py` 的 `UI_BACKENDS` 登记一个 `UIBackend(key, name, summary, entry, requires, deprecated, note)`，
`entry(spec, args) -> int`（`spec` 可为 `None`，表示「先让用户挑模型」）。

**注意两个当前未抽象的点（见 §7 R4 / R5）**：

- 视图发现模板 `VIEW_MODULE_TPL` 硬编码为 `...views.tk`，新后端需要自带一份发现逻辑；
- `launcher.main` 里 `if ui_key == "tk":` 分支决定「是否允许空 spec 进模型列表页」，新后端若要支持空 spec 需改此处。

---

## 5. 成熟度评估

| 维度 | 状态 | 说明 |
| --- | --- | --- |
| 模型 / 界面解耦 | ✅ 成熟 | 数据级 + 对象级双契约，模型不需要知道渲染方式 |
| 零中心清单扩展 | ✅ 成熟 | 模型扫描 + 视图发现均为约定驱动 |
| CLI 参数声明化 | ✅ 成熟 | `CliOption` + `CliArgs` + 启动期冲突守卫 |
| 桌面骨架复用 | ✅ 成熟 | 三层骨架成型；层 1 已有两个真实用例（`buffon_needle` 的 `segments`/`series`、`life_game` 的 `grid`/`series`，后者还用到播放控制与点击反查），层 3 由两个渗流模型共用（R2 已关闭） |
| 可视化范式覆盖 | 🟡 基本够用 | 栅格 / 热力图已由层 1 的 `kind="grid"` 覆盖（离散态 + 连续场两条渲染路径）；仍缺**图 / 网络**类（见 §8.1） |
| 界面后端数量 | 🟡 受限 | 实际可用只有 tk；cli 为统计模式；web 已弃用 |
| 依赖占用 | ✅ 优秀 | 零第三方依赖（tkinter 自带，matplotlib 可选） |
| 测试 | 🔴 缺失 | 仓库内没有测试；关键契约靠文档字符串约束 |

---

## 6. 已完成：Step 1 变更记录

Step 1 目标：修掉遗留问题并同步文档，为后续重构提供**正确的参照实现**。

| 编号 | 问题 | 处理方式 | 状态 |
| --- | --- | --- | --- |
| P1 | `ChartViewBase.on_key` 的数字快捷键是死代码，HINTS 却在宣传 | `shell.DesktopShell.__init__` 补 `1..9` 绑定（焦点在输入框时不转发） | ✅ 已修复 |
| P2 | `--model buffon --trials N` 静默失效（破坏性变更无提示） | README「已知状态」写明破坏性变更与替代命令；`_cli` 改走 `CliArgs` | ✅ 已修复 |
| P3 | `CliOption` 声明与 `_cli` 读取之间是隐式契约（改名即静默失效） | 新增 `CliArgs` 封装（名字+默认值同源）+ `launcher` 启动期冲突守卫 | ✅ 已修复（优于原建议） |
| P4 | 文档漂移（多处仍描述「两层骨架」「通用骨架」等旧结构） | 同步 `README.md` / `buffon_needle` 的 `__init__.py`、`spec.py`、`views/__init__.py` / `kit/__init__.py` / `spec.py` 模块文档 | ✅ 已修复 |
| — | `base.run_action` 状态栏时序会把渲染器文案吃掉 | 改为「先写通用文案，再交给 `_render_result`，允许渲染器覆盖」 | ✅ 已修复（Step 1 期间发现） |

**Step 1 的产出价值**：后续迁移到新后端时，有一份行为正确、文档自洽的 tk 参照实现可对照，
而不是从「带着已知 bug 的旧实现」出发。

### 6.1 已完成：Step 2 变更记录（抽象压测：栅格范式）

Step 2 目标是**把骨架集合压到定型**（不是加模型的数量）。第一步选了"像素栅格 / 元胞自动机"
这一范式，因为它是 §8.1 里两个 ❌ 之一，且正好命中 R1 / R2。

| 编号 | 问题 / 目标 | 处理方式 | 状态 |
| --- | --- | --- | --- |
| S2-1 | R1：层 1 缺栅格 / 热力图图元 | `ChartSpec` 新增 `kind="grid"`：离散态（`frames` / `cells`）走"预建矩形 + **差分刷新**"，连续场（`values` + `vmin/vmax` + `cmap`）走 `PhotoImage` 整数倍放大；新增 `CMAPS`（4 条内置色带） | ✅ |
| S2-2 | 栅格是"时间轴"，不能按老节奏摊成 48 帧 | 帧序列模式下动画**每步前进恰好一帧**（滑块即"每代间隔"）；新增 `_current_reveal()` —— 暂停后窗口缩放画出**同一帧**而不是跳到末帧 | ✅ |
| S2-3 | 播放只有"重播 / 直接显示全部" | 动画卡片改为 **▶ 播放 / ⏸ 暂停 + ⏭ 下一帧**（对既有图表同样生效），并**去掉**「重播动画」「直接显示全部」（▶ 本身就是重播：播完再按就是接着走）；空格 = 播放 / 暂停 | ✅ |
| S2-4 | 层 1 完全没有交互式画布 | `ChartSpec.clickable` + 像素→格反查 + `_on_cell_click(row, col, start)`（**返回新 payload** 即原地重绘）；默认不处理，既有模型零行为变化 | ✅ |
| S2-5 | 压测用的新模型：生命游戏 | `models/life_game/`：纯标准库内核（字节棋盘 + 一圈永久死边框 + 预计算邻居表 + 状态哈希周期检测 + 图案库）+ `handler`/`factory`/`cli_options`/`_cli`（含密度扫描）+ 两种返回结构（`life-grid` / `life-census`）；视图只有声明 + 4 个钩子 | ✅ |
| S2-6 | R7（同 flags 不同默认值静默覆盖）在真实模型上首次触发 | 生命游戏**不复用** `--rows`（默认值与渗流不同，会被 `entries[0]` 静默换掉），改用 `--cells`；只共用语义与默认值**完全一致**的 `--cols` / `--scan` / `--step` / `--trials` | ✅（规避；R7 本身仍未修，见 §7） |
| S2-7 | 生命游戏不该被"演化代数 N"限制住 | 桌面端改成**实时逐代播放**（`LifeBoard.step` + 定时器），不设代数上限；把周期 / 静止 / 消亡的判定从 `run()` 抽成 `LifeWatch`，**两条路径（无限播放 / 有上限的 `run`）共用同一个判官**，于是"周期多长"不会有两个答案。画布与人口曲线只做增量刷新 | ✅ |
| S2-8 | 侧栏顺序与"开局"玩法（用户反馈） | 新增四个插槽钩子：`_build_top_cards`（播放卡片置顶 —— 常用控件不该埋在参数下面）、`_build_player_extra`（播放卡片里加「清空棋盘」）、`_param_card_footer`（「开局」卡片底部加「生成开局」——参数是配方、按钮才动手）、`_build_right_extra`（右侧面板加实时人口曲线）。`PATTERN_BLANK` 让默认开局变成**空白手绘**；涂改语义对齐参考实现：**按下那一格决定这一笔是"画"还是"擦"，拖动只设值不翻转**（长按 / 来回蹭不再反复翻转） | ✅ |

**实测数据（写进代码文档，供后续后端对齐口径）**

| 环节 | 数值 |
| --- | --- |
| 内核每代（B3/S23，密度 0.3） | 50×50 **0.5 ms**、80×80 **1.3 ms**、120×120 **3.1 ms** |
| 画布每帧（900×700，格子边长取整数倍） | 差分刷新 ≈ **0.012 ms / 变化格**；全量重建 **30–56 ms/帧**；图像缓冲 **7–18 ms/帧** |
| 桌面实时播放的一步（编码 + 差分刷新 + 指标 + 曲线） | 50×50 约 **1–2 ms/代**：默认 10 代/秒（间隔 100 ms）很轻松；把间隔拉到 1 ms 实测约 150–180 代/秒 |
| 结论断言（`model.py` 自检） | 方块静止 / 闪烁器周期 2 / 脉冲星周期 3 / 滑翔机 4 代平移 (1,1) / 滑翔机枪 40 代不收敛 / 环面 12×12 八个种子全部收敛 / 滑翔机在环面上周期 = 4 × 边长（30×30 → 120，实测相符） |

**Step 2 的产出价值**：`ChartSpec(kind="grid")` 一旦落到层 1，**不需要第四套骨架**就能覆盖
元胞自动机、热力图、Mandelbrot（连续场 + 色带 + 点击放大）——于是迁移到新后端时，
要 1:1 搬的仍然是那三层，而不是四层。这正是 §9 里"先把接口压到稳定，再换实现"的意思。

---

## 7. 遗留问题与风险清单

> 状态：✅ 已解决；🟡 需关注；🔴 阻碍后续工作

| 编号 | 问题 | 影响 | 状态 |
| --- | --- | --- | --- |
| P1–P4 | 见 §6 | — | ✅ |
| R1 | `ChartSpec.kind` 只有 `segments/series/bars/text`，**没有 `image` / `heatmap`** | 栅格类模型（元胞自动机、Mandelbrot、热力图）无法用层 1 骨架表达 | ✅ 已解决：层 1 新增 `kind="grid"`（离散态矩形差分 / 连续场 `PhotoImage` 图像缓冲 + 色带），由 `life_game` 验证；Mandelbrot 与热力图可直接复用 |
| R2 | `ChartViewBase` 只被 `buffon_needle` **一个**模型验证 | 抽象是否够用未知；迁移后返工风险高 | ✅ 已解决：`life_game` 成为第二个真实用例，且比第一个更苛刻（栅格画布 + 手绘编辑 + 实时播放 + 右侧实时曲线），全部落在"声明 + 数据 / 交互 / 布局三类可选钩子"之内，未改动层 1 的结构（见 §6.1） |
| R3 | `PercolationViewBase` 与渗流语义强绑定 | 非渗流模型只能选层 1 或层 2，中间无过渡 | 🟡 |
| R4 | `VIEW_MODULE_TPL` 硬编码 `...views.tk` | 新增界面后端需自带发现逻辑（模型本身仍无需改动） | 🟡 |
| R5 | `launcher.main` 硬编码 `if ui_key == "tk"` 决定是否允许空 spec | 新后端若要支持「先选模型」页需改入口 | 🟡 |
| R6 | `ui/web` 只为 `view == "percolation"` 写了渲染器，且已 `deprecated=True` | `site_percolation` / `buffon_needle` 在 `--ui web` 下退化为通用视图 | 🟡（已弃用，低优先） |
| R7 | 同一组 `flags` 被两个模型以**不同默认值/类型**声明时，`entries[0]` 静默胜出 | 守卫只覆盖「同 key 不同 flags」，未覆盖「同 flags 不同声明」 | 🟡（已被真实触发：生命游戏的 `--rows` 若复用声明，默认值会被渗流的 40 覆盖；现以 `--cells` 规避。彻底修法见下） |
| R8 | 不属于当前模型的选项被接受但**静默忽略** | 用户看不出参数没生效（P2 的同类风险，仍是设计取舍） | 🟡（新增例：`--model life --rows 60` 会被接受但忽略 —— 生命游戏读的是 `--cells`） |
| R9 | 全仓库无测试 | 契约靠文档字符串约束；重构缺少回归保护 | 🔴 |
| R10 | `all_models()` 按 `(topic, order, name)` 字符串排序，中文主题序导致 `buffon_needle` 排第一 | 非交互 `_resolve_model` 的兜底模型是投针；门户按主题分组的展示顺序 | 🟡（观察项，非回归） |

---

## 8. 改进路线

### 8.1 Step 2：抽象压测（加异范式模型，目标不是堆数量）

| 范式 | 代表模型 | 现有骨架 | 覆盖状态 |
| --- | --- | --- | --- |
| 蒙特卡洛采样（独立随机 + 反解） | `buffon_needle` | `ChartViewBase(segments)` | ✅ |
| 网格 + 逐层扩散 + 相变判据 | `percolation` / `site_percolation` | `PercolationViewBase` | ✅ |
| 一维迭代 / 时间序列 | logistic map、SIR 传播 | `ChartViewBase(series)` | ⚠️ 未验证 |
| 分布 / 直方图 | Galton 板、中心极限定理 | `ChartViewBase(bars)` | ⚠️ 未验证 |
| 元胞自动机（离散栅格 + 时间轴） | `life_game` | `ChartViewBase(grid)` | ✅ 已完成 |
| 分形 / 连续场（色带 + 缩放） | Mandelbrot | `ChartViewBase(grid)` 的连续场路径 | ⚠️ 图元已就绪，尚无模型验证 |
| 图 / 网络 | 小世界、六度分隔 | 无 | ❌ 需新骨架（唯一剩下的 ❌） |

**完成门槛**：两个 ❌ 变 ✅，并验证两个 ⚠️。产出不是「更多模型」，而是**骨架集合定型**。
栅格那一行已完成，且结论与预期不同：**不需要新骨架**（原设想的 `ImageGridViewBase`）——
把栅格做成层 1 的一个**图元**即可，代价小、收益大（见 §6.1）。

**剩余待办**：① Mandelbrot（复用连续场路径，几乎零新代码，可顺带验证"色带 + 点击放大"）；
② logistic map / Galton 板（两个 ⚠️，层 1 已有 `series` / `bars`，成本低）；
③ 图 / 网络（唯一的 ❌，需要真正的新骨架，建议放在 §8.2 的 Flet 切片之后再定）。

### 8.2 Step 3：Flet 垂直切片（1–2 天 spike）

只跑通 1 个模型，目的拿到实测数据以决定是否正式迁移。建议验收指标：

| 指标 | 建议阈值 | 备注 |
| --- | --- | --- |
| 80×80（6400 单元）逐层动画帧率 | ≥ 30 fps 可接受，≥ 60 fps 理想 | 用「整块渲染成图像缓冲」而非逐图元 |
| 首屏生成耗时 | 与 tk 版同量级 | |
| 交互完整度 | 点击指定注水点、下拉框切换重建、后台进度与取消 | |
| 代码量对比 | 同一模型 view 行数 vs tk 版 | 口径需固定 |
| 打包 | 能否产出 Windows 独立可执行 | |

### 8.3 Step 4：正式建立 `ui/flet/`

把已定型的骨架 1:1 迁过去（层 1 的声明式结构尤其适合 Flet）。**tk 保留为零依赖兜底**，
这也正是架构设计的本意。此时开始加模型几乎零 UI 成本。

### 8.4 Step 5：Tauri 评估（仅在前述结论不达标时）

触发条件：Step 3/4 证明 Flet 的画布性能或打包体验不达标，且确有可视化需求无法满足。

---

## 9. 决策记录：Flet vs Tauri

| 维度 | Flet | Tauri + React/TS |
| --- | --- | --- |
| 语言 | 纯 Python（单一语言） | Python + TS（双语言 + 构建链） |
| 覆盖范围 | 桌面 + Web + 移动，可一次吃掉现有 tk + web 两套渲染器 | Web 前端为主，需 Python sidecar |
| 组件模板 | Material 全套，声明式 | 最丰富（shadcn/MUI 等） |
| 画布性能 | 需 Step 3 实测 | 最强（Konva/D3/WebGL） |
| 迁移成本 | 中（1:1 映射三层骨架） | 高（第二语言 + 构建链） |
| 对「零依赖」卖点 | 破坏（引入 Flutter 运行时） | 破坏更彻底（Node + 构建产物） |

**结论**：**先 Flet，Tauri 作为备选**。理由：单语言、单代码库、与现有三层骨架结构同构，
迁移风险可控；Tauri 只在 Flet 实测不达标时才考虑。两者都会打破「不需要安装任何第三方包」
这一卖点，因此**保留 tk 作为零依赖兜底**。

**反共识的一点**：不建议「先重构 UI 再加模型」。加模型的边际成本是线性的（一个目录），
而迁移骨架的成本是横切的（3 套骨架 + 7 个 mixin）。若骨架集合本身还会变，
先迁移等于把未定型的接口实现两遍。**先把接口压到稳定，再换实现。**

---

## 10. 附录：关键文件索引

| 想了解 | 看这里 |
| --- | --- |
| 模型怎么注册、目录约定 | `awe_math/registry.py` |
| 参数 / 动作 / CLI 选项 / 元数据规范 | `awe_math/spec.py`（`CliOption` / `CliArgs`） |
| 入口流程与无图形环境降级 | `awe_math/launcher.py` |
| 渗流类模型共用的 CLI 声明 | `awe_math/models/_cli.py` |
| 通用图表骨架（声明式图表 + 动画） | `awe_math/ui/tk/kit/chart.py` |
| 万能骨架 / 渗流特化骨架 | `awe_math/ui/tk/kit/base.py` |
| 桌面视图对模型的要求（可执行契约） | `awe_math/ui/tk/kit/protocols.py` |
| 参数表单怎么由 `spec.params` 生成 | `awe_math/ui/tk/kit/form.py` |
| 判据的全部界面语义 | `awe_math/ui/tk/kit/criteria.py` |
| 术语表 / 结果归一化 | `awe_math/ui/tk/kit/common.py` |
| 视图怎么被自动发现 | `awe_math/ui/tk/kit/__init__.py` |
| 一个真实渗流模型的完整视图 | `awe_math/models/percolation/views/tk.py` |
| 一个真实非渗流模型的完整实现（只有声明） | `awe_math/models/buffon_needle/` |
| 栅格图元、时间轴播放、点击反查怎么做 | `awe_math/ui/tk/kit/chart.py`（模块说明 + `_draw_grid` / `_paint_cells`） |
| 一个真实栅格类模型的完整实现（内核 + 声明式视图） | `awe_math/models/life_game/` |

### 术语约定

| 术语 | 含义 |
| --- | --- |
| 数据级契约 | `spec.params` + `spec.handler`，返回 JSON 可序列化结果 |
| 对象级契约 | `spec.factory` + `spec.batch` + `spec.scan`，供桌面画布与后台任务使用 |
| 三层骨架 | `ChartViewBase` / `ModelViewBase` / `PercolationViewBase` |
| 图元（`ChartSpec.kind`） | `segments` / `series` / `bars` / `grid` / `text` —— 栅格类模型复用层 1 而不是新开骨架 |
| 范式压测 | 用不同可视化范式的模型检验骨架抽象是否够用（Step 2） |
| 垂直切片 | 用最小实现跑通一条端到端链路，以获得实测数据（Step 3） |
