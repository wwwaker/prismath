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

**依赖 `numpy`**：所有模型的计算内核都基于 numpy 向量化，所以先
`pip install -r requirements.txt`。`matplotlib` 仍是可选的（只影响曲线页，缺失时该页给出提示，
其余功能照常）；tkinter 随 Python 自带。

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
| `python main.py --model buffon --ui cli --ratio 0.6 --throws 5000` | 终端里投针估计 π（用自己的参数名） |
| `python main.py --model life --ui cli --generations 300 --pattern glider` | 终端里跑生命游戏（末态字符画 + 终局判定 + 周期） |
| `python main.py --model life --ui cli --scan --step 0.1 --trials 20` | 终端里扫描「初始密度 → 长期存活率」 |
| `python main.py --model n_body --ui cli --frames 200` | 终端里跑一段多星运动（守恒量 + 末态星图） |
| `python main.py --model n_body --ui cli --scan` | 终端里扫描「时间步长 dt → 最大能量漂移」（看二阶收敛） |
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
| `buffon_needle` | π 蒲丰投针模型 | 概率与统计 | L ≤ d 时命中概率 = 2L/(πd)，故 π ≈ 2LN/(dH) |
| `n_body` | ✷ 万有引力多星模型 | 确定性与混沌 | F = Gm₁m₂/r²：8 字三体周期 6.32591398、圆轨道 T = 2πa^(3/2)/√(GM)、能量漂移 ≈ dt² |
| `life_game` | ▩ 生命游戏模型 | 简单规则与涌现 | B3/S23：滑翔机每 4 代平移一格、闪烁器周期 2、脉冲星周期 3 |
| `percolation` | ≋ 边渗流模型 | 量变引起质变 | 方格网 p_c = 0.5、三角网 ≈ 0.3473、有向 ≈ 0.6447 |
| `site_percolation` | ▦ 点渗流模型 | 量变引起质变 | 方格网 p_c ≈ 0.5927、三角网 0.5 |

两个**渗流类**模型（边渗流 / 点渗流）都支持：方形 / 矩形区域、方格网 / 三角网、四种方向
模式（无向、不允许向上、只允许向下向右、只允许向下向左）、三种注水方式，以及三种成功判据
+ 批量统计 + 曲线扫描。

`buffon_needle` 是**非渗流**模型（随机投针估计 π）：它走**通用图表骨架**（`ChartViewBase`，
图表只写声明），参数表单由
`spec.params` 自动生成，动作是「投针一次」与「多组重复估计」。**「投针一次」带动态投针
效果**：针从零开始逐根出现（左侧**顶部**的「动画」卡片可调速，播放中可暂停 / 单步），
右侧的命中率与 π 估计随针数实时刷新。它同时是"接入一个不同范式的模型"的参考实现
（见下文「新增一个模型」）。

`life_game` 是本项目的**第一个栅格类模型**（元胞自动机）：每个格子只看周围 8 格，按
`B3/S23` 同时更新（活细胞有 2~3 个邻居就存活，死细胞恰好 3 个邻居才新生）。
**三条局部规则、没有中央控制、没有随机性**，却同时长出静止物、振荡子、会走路的结构与
无限增长的结构（滑翔机枪）——复杂度可以来自规则本身，而不来自规则的复杂。

桌面界面上的看点：

* **开局自己画**：棋盘一开始是**空的**，按住左键在画布上拖动就是画笔 —— 按下那一格决定
  这一笔是「画」还是「擦」，拖动只是把经过的格子设成这个状态，所以按住不动、来回蹭都
  **不会反复翻转**。图案 / 密度 / 种子只是「配方」，按「生成开局」才会铺上去；
  「清空棋盘」回到全空；
* **实时播放，不设代数上限**：左侧**顶部**的播放卡片有 `▶ 播放 / ⏸ 暂停`、`⏭ 下一帧` 与
  间隔滑块，按 ▶ 就一代一代往下走，一直到消亡 / 进入周期，或你按暂停 —— 想要第几代就第几代，
  不用先猜一个 N；
* **人口曲线在右侧实时生长**：活细胞数随代数变化，与画布上"第几代"严格对齐；
* **自动检测状态重复**：消亡（活细胞归零）、静止（周期 1）、周期振荡（如闪烁器周期 2）
  会被识别出来并**自动停下来报周期长度**，徽章持续显示结论；
* **随时改**：改规则 / 边界不清空棋盘（作用在现有棋盘上）；涂改会让周期检测与人口曲线
  从这一代重新开始 —— 之前那一段已经属于另一条轨迹了。

**两个容易误解的地方**（已写进模型说明与终端提示）：

1. **"必然周期化"不等于"等得到"**：环面上状态有限（2^(n·m) 种）、演化完全确定，所以
   状态序列迟早重复 —— 但瞬态长度没有上界。12×12 的小棋盘上几十代就收敛，20×20 的环面
   跑 600 代可能仍在变化。滑翔机在环面上的周期是 **4 × 边长**（每 4 代整体平移一格，要绕
   一圈才回到原位），在死边界上则会撞墙消失。
2. **初始密度不是临界值**：密度 0.9 的棋盘一代之内就全灭（每格邻居都超过 3 个），太低则
   很快消亡，中间一段（约 0.2–0.4）才容易长出长时间活跃的结构。这**不是**渗流那种有确定
   临界点的相变，曲线是平缓的 —— 终端里的 `--scan` 扫的就是它。

`n_body` 是本项目的第一个**连续时间动力学**模型（前面几个都是离散步：生命游戏按"代"、
渗流按"逐层"、投针按"根"）。`N` 颗星两两之间只有万有引力，用的是**辛（symplectic）
速度 Verlet 积分器**：

* **N = 2** 时有解析解：轨迹是圆锥曲线，周期满足 `T = 2πa^(3/2)/√(GM)`；
  界面上的「太阳 + 四行星」场景里，半径越大周期越长（开普勒第三定律）直接画在轨迹上；
* **N = 3** 时已经有精确周期解的漂亮例子（**8 字三体**，三个等质量星体沿同一条"8"字
  首尾相接，周期 6.32591398），而一般三体问题**没有解析解**；
* **N 更多**时是混沌：随机星团会冷塌缩、近距遭遇把个别星体甩出去，
  初值只差最后一位小数，长期轨道就完全不同 —— **确定性不等于可预测**。

界面上的看点：

* **选场景就等于选初值**：8 字三体（精度标尺）/ 双星 + 行星 / 太阳 + 四行星 /
  随机星团（混沌）/ 星系盘。切换场景会自动套用该场景推荐的软化半径 ε（精确解场景是 0）；
* **▶ 播放**逐帧推进（可暂停 / 单步 / 调速、「↺ 重置模拟」回到初值）；
  星体大小与颜色随质量，尾迹按星体着色 —— 轨道形状、双星的抖动、星团的散开都在尾迹上；
* **右侧指标行盯着四个守恒量**：总能量 E、总动量 P、角动量 L 与"回到出发点"的偏差
  （8 字三体一个周期后偏差约 `7e-5`）；下方的**能量漂移曲线**画 `E − E₀` 随时间的变化
  （贴着 0 线小幅振荡就说明积分器稳，鼓包越大越说明 dt 该减小）。横轴是**滑动窗口**：
  只保留最近一段历史，但始终铺满整幅图 —— 模拟时间再长，曲线也不会被挤到右边一角；
* **画布可以动手**：滚轮缩放（以光标为中心）、拖动空白处平移、`⌖ 恢复视图` 回到自动视角
  （自动视角下画面不追逃逸者：半径只增不减，星多时按半径的 90% 分位数取景）；
  点一下星体即可选中（自动暂停），拖动它换位置、拉「星体编辑」的滑块改质量 ——
  改完能量基准 E₀ 会重新锚定到当前状态、曲线从这一刻重画（同生命游戏"涂改后曲线重来"）；
* **终端里的 `--scan`** 扫「时间步长 dt → 最大相对能量漂移」，能直接看到二阶收敛
  （dt 减半、漂移降为约 1/4），以及"误差有界振荡而不是单调漂移"这条辛积分器的性质。

**两个容易踩的坑**（已写进模型说明与界面提示）：

1. **ε = 0 才是严格牛顿引力**：8 字三体这类精确解必须用 0；随机星团建议 ε ≥ 0.1，
   否则近距遭遇会让速度发散 —— 那时界面会显示"数值爆炸"并提示减小 dt 或增大 ε，
   而不是甩一个 traceback（模型检测到 `inf/NaN` 就停下并标记）；
2. **同一初值 ≠ 同一长期命运**：混沌场景里换个随机种子（甚至只改 dt）就会走出一条
   完全不同的历史，这不是 bug，而是模型要展示的结论。

### 三种「成功判据」不是一回事（本项目最容易误解的地方）

| 判据 | 回答的问题 | 曲线与 50% 的交点 |
| --- | --- | --- |
| **贯通** `span`（默认） | 整片区域是否存在顶行 ↔ 底行的**纵贯簇** | **= p_c**，且与注水方式无关 |
| **起点** `origin` | 从注水点出发的那一簇是否纵贯 | 高于 p_c（顶端整行注水时相等） |
| **面积** `area` | 从注水点出发的活动面积是否达到设定比例 | **不是 p_c**，随比例 / 尺寸 / 注水方式漂移 |

界面上凡随判据变化的东西（统计行标题、结论徽章、曲线纵轴、p_c 参考线、历史表列名）都会
跟着改，所以「p_c」只在贯通判据下才有定义。

这些语义全部收在 `ui/tk/kit/criteria.py` 的**判据策略对象**（`Criterion`）里：工具箱不再
到处写 `if criterion == "span" ...`，而是按策略取文案与判定结果。模型要加自己的判据，只需
往 `PercolationViewBase.CRITERIA` 里加一条策略，不必改工具箱。

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
requirements.txt                 依赖声明：numpy（必需）/ matplotlib（可选，曲线页）
docs/                            架构与 UI 评审文档（面向开发者，含依赖策略 §2.4）
tests/                           回归网：金样本 + 单元测试 + 微基准（见下文「测试与基准」）
awe_math/
├── spec.py                      模型元数据规范：参数 / 动作 / 视图
├── registry.py                  模型注册表 + 「一个模型长什么样」的目录约定
├── launcher.py                  入口流程：默认桌面窗口 / --menu / --ui 指定后端
├── models/                      各数学模型（每个包自带自己的界面）
│   ├── _options.py              模型间共用的选项词表
│   ├── _geometry.py             模型间共用的格子几何
│   ├── _cli.py                  渗流类模型共用的命令行选项声明
│   ├── buffon_needle/           蒲丰投针（非渗流：通用图表骨架 + Monte Carlo）
│   │   ├── __init__.py          register(spec)：导入本包即完成注册
│   │   ├── model.py             纯计算内核（投针几何 + π 估计）
│   │   ├── spec.py              参数 / 动作 / view="buffon_needle" / cli_options
│   │   └── views/tk.py          桌面视图（继承 ChartViewBase，只有声明没有绘图代码）
│   ├── life_game/               生命游戏（栅格类：栅格图元 + 时间轴播放 + 点击涂改）
│   │   ├── __init__.py          register(spec)：导入本包即完成注册
│   │   ├── model.py             纯计算内核（numpy 布尔棋盘 + 规则查找表 + 周期检测 + 图案库）
│   │   ├── spec.py              参数 / 动作 / view / cli_options / factory / 密度扫描
│   │   └── views/tk.py          桌面视图（继承 ChartViewBase，用 kind="grid" 栅格）
│   ├── n_body/                  万有引力多星（连续时间动力学：自带图种 kind="orbits"）
│   │   ├── __init__.py          register(spec)：导入本包即完成注册
│   │   ├── model.py             纯计算内核（速度 Verlet + 场景库 + 守恒量 + dt 扫描）
│   │   ├── spec.py              参数 / 动作 / view / cli_options / factory / payload
│   │   └── views/tk.py          桌面视图（继承 ChartViewBase，自己补星体 + 轨迹的画布）
│   ├── percolation/             边渗流
│   │   ├── __init__.py          register(spec)：导入本包即完成注册
│   │   ├── model.py             纯计算内核（并查集 + BFS 分层）
│   │   ├── spec.py              参数 / 动作 / view / cli_options / factory+batch+scan
│   │   └── views/tk.py          桌面视图（继承 PercolationViewBase）
│   └── site_percolation/        点渗流（结构同上）
└── ui/                          界面后端
    ├── __init__.py              后端注册表（tk / cli / web）
    ├── tk/                      桌面窗口（默认）
    │   ├── __main__.py          支持 python -m awe_math.ui.tk
    │   ├── shell.py             窗口外壳：模型下拉框 + 「☰ 模型列表」+ 视图切换
    │   ├── portal.py            模型列表入口页
    │   ├── theme.py             深色扁平主题（配色 / 字体 / ttk 样式）
    │   └── kit/                 桌面界面工具箱：通用图表 / 万能 / 渗流特化 三层骨架
    │       ├── base.py          ModelViewBase（万能骨架）+ PercolationViewBase（渗流特化）
    │       ├── chart.py         ChartViewBase：通用图表骨架（声明式图表 + 逐帧动画
    │       │                     + 栅格图元 grid：差分刷新 / 图像缓冲 / 播放控制）
    │       ├── protocols.py     模型契约与视图属性契约（Protocol / ViewContract）
    │       ├── form.py          按 spec.params 自动生成参数表单
    │       ├── criteria.py      成功判据策略（徽章 / 结论 / 曲线文案，模型可扩展）
    │       ├── canvas.py        画布、逐层动画、图例、结论
    │       ├── controls.py      左侧参数栏（渗流卡片族，值域/候选项取自 spec）
    │       ├── results.py       右侧三个标签页 + P(p) 曲线
    │       ├── jobs.py          后台任务（批量统计 / 曲线扫描）
    │       ├── common.py        术语表、结果归一化、共享配色与工具
    │       └── __init__.py      视图注册表（按约定自动发现）
    └── web/                     网页界面（暂时弃用，代码保留）
```

**三条硬规则**（改代码时请遵守）：

1. `model.py` **只依赖标准库 + numpy**，不要 import 界面代码——纯计算要能单独导入、单独测试，
   并且四个内核都支持**直接运行**（`python -m awe_math.models.<模型>.model` 跑自检）；
2. `views/` **只被对应后端懒加载**：不要在模型的 `__init__.py` 里 import 它，否则网页服务、
   终端模式会被迫加载 tkinter / matplotlib；
3. **界面骨架按后端放**（`ui/<后端>/`），**模型特化跟着模型走**
   （`models/<模型包>/views/<后端>.py`）——所以新增界面后端不必回头改模型，新增模型也不必
   改界面。

### 依赖规则（**numpy 是必需依赖**）

数值内核（元胞自动机演化、渗流单遍扫描、蒙特卡洛批量采样、分形逃逸时间）全部基于
`numpy` 向量化，因此 **`numpy` 是必需依赖**：

| 依赖 | 必需？ | 作用 |
| --- | --- | --- |
| `numpy` | **必需** | 全部模型的计算内核（向量化演化 / 批量统计 / 并查集扫描 / 随机场） |
| `matplotlib` | 可选 | 曲线页（渗流的 P(p) 曲线等）；缺失时该页显示提示，其余功能照常 |
| `pywebview` | 可选 | 网页后端想要独立窗口时用（web 后端已暂时弃用） |

安装：`pip install -r requirements.txt`。

**为什么不再写"标准库回退"**：同一个算法维护两套实现，成本与"两套答案不一致"的风险
（浮点差异、RNG 差异）都高于 numpy 带来的收益，代码也因此更短更直白。取而代之的三条纪律：

1. **语义不变**：重写只许换实现、不许换定义 —— 每个模型内置的自检（`python -m
   awe_math.models.<模型>.model`）必须继续全绿；
2. **实测进文档**：重写后要重新标定并把数字写回 docstring / README（本仓库的惯例是
   **性能数字必须是实测值**，不许估算）；
3. **入口友好报错**：缺 `numpy` 时提示 `pip install -r requirements.txt`，而不是抛 ImportError 堆栈。

`views/` 的**懒加载**照旧保留 —— 它不再是"为了省依赖"，而是为了让终端模式不被 tkinter 拖累。

**新增依赖前先问一句"标准库真的做不到吗"**：能用标准库就别引包，引包只为止损
（性能瓶颈或标准库确实没有的能力，例如数值数组、图像编解码）。

---

## 测试与基准

```powershell
python -m unittest discover -s tests -t .     # 全量测试（当前 129 条，约 78 s）
python -m tests.bench                         # 四个模型的微基准（中位数 + 波动 + 环境行）
python -m tests.bench life_game               # 只跑一个模型
python -m tests._harness --update <模型>      # 重新生成金样本（谨慎，见下）
```

四层网，各管一件事：

| 文件 | 管什么 |
| --- | --- |
| `tests/test_golden.py` + `tests/golden/<模型>.txt` | **金样本**：各模型的 `python -m awe_math.models.<模型>.model` 自检输出**逐字比对**。自检输出是确定性的（连跑两次逐字相同），所以能用最严格的方式比 —— 改内核后这里变红，先问"这个变化是有意的吗" |
| `tests/test_life_game.py` 等五份单元测试 | 教材结论与契约断言：纯整数结论（方块 / 闪烁器 / 脉冲星 / 滑翔机位移）**精确相等**；统计量**固定种子 + 容差**。渗流的两份还带**等价性护栏**：邻居/边表必须与几何逐条一致、向量化推进必须与朴素 BFS 同集合同分层、并查集与 BFS 必须同答案、`bytes` 掩码必须与分类型边表互相对得上；`n_body` 那份钉住守恒量（动量到 1e-12）、开普勒第三定律、辛积分器的二阶收敛（比值 3–5.5）、"误差有界不漂移"，以及**视图交互**（滚轮缩放保持光标下的世界点不动、拖动平移、选中星体并拖动、质量滑块对数映射与重锚基准、能量曲线滑动窗口铺满横轴） |
| `tests/test_views_smoke.py` | **视图无头冒烟**：按外壳的真实路径真开一个窗口、建出视图，断言画布上真有图元（没有图形环境时自动跳过）。这一层专盯"骨架与内核之间的参数契约" —— 内核测试一个窗口都不建，所以漏过一次"进模型一片空白"（见 `docs` §6.2） |
| `tests/bench.py` | 微基准 —— **文档里所有性能数字的唯一来源**（中位数 + 预热 + 波动范围） |
| `tests/_harness.py` | 金样本读写 + 差异报告 + `--update`；每次刷新都要在文件顶部写一句"为什么"（已有 life_game / buffon_needle / site_percolation / percolation / n_body 五条记录） |

两条纪律：**性能数字只写实测值并注明复现命令**；波动大的用例（例如小 N 的投针、Windows 上的单代计时）
不要往文档里写 —— `bench` 会把波动一并打出来，就是为了让人一眼看出哪个数字不可信。

金样本是**允许刷新**的：改 RNG、改算法都会让数字变，这时要刷新 + 写原因；但"纯整数结论"那一批
（滑翔机坐标、p_c 表的方向性、判据之间的大小关系）不该跟着变 —— 若它们变了，是语义被改了，不是噪声。

---

## 新增一个模型

**参考实现**：`awe_math/models/buffon_needle/` 就是一个真实的例子（**非渗流**模型）。
照抄它的结构即可 —— 只加一个目录，不改任何已有文件：

```
awe_math/models/<模型包>/
    __init__.py     # register(build_spec())
    model.py        # 投针几何 + Monte Carlo 估计（纯计算，只 import 标准库 + numpy）
    spec.py         # 参数（针长 / 线距 / 投针根数 / 重复组数）、动作、view="buffon_needle"
    views/
        tk.py       # 可选：桌面视图，@register_view("<spec.view>")
```

**第一步**：`spec.py` 里给一个 `view` 名（就是渲染器标识），并实现 `handler`：

```python
ModelSpec(
    key="buffon_needle", name="蒲丰投针模型", topic="概率与统计",
    summary="随机投针估计 π", view="buffon_needle",
    params=PARAMS, actions=ACTIONS, handler=handle,
    cli=_cli, cli_options=CLI_OPTIONS,   # 终端入口 + 它自己的命令行参数
    # 可选（非渗流模型用不到）：桌面后端要直接驱动模型对象时用
    factory=build_grid, batch=batch_fn, scan=scan_fn,
)
```

**第二步（可选）**：想要专属桌面界面，就在同一个包里写 `views/tk.py`，用装饰器登记
**同名** view。**非渗流模型一般继承通用图表骨架** `ChartViewBase`，只写声明：

```python
from awe_math.ui.tk.kit import ChartSpec, ChartViewBase, register_view

@register_view("buffon_needle")
class BuffonNeedleView(ChartViewBase):
    CHART_SPECS = {                            # 哪种返回结构（payload["view"]）怎么画
        "buffon-needle": ChartSpec(kind="segments", animate=True, ...),
        "buffon-converge": ChartSpec(kind="series", ref=PI, ...),
    }
    RESULT_ROWS = (("投针根数 N", "n"), ("π 估计值", "pi"), ...)
    ROW_SOURCES = {"n": "throws", "pi": "piEstimate", ...}   # 指标行从哪些字段取
    RESULT_FORMATS = {"pi": "{:.5f}", "cost": "{:.1f} ms"}   # 怎么格式化
```

左侧参数栏（按 `spec.params` 的 `kind` 生成滑块 / 数字框 / 复选框 / 下拉框）、动作按钮
（按 `spec.actions` 生成）、画布与坐标轴、逐帧动画、右侧指标行都由基类自动完成 —— **视图里
一行 Tk 代码都不用写**。想要完全不同的布局时，再退回 `ModelViewBase` 自己画。

**第三步**：`python main.py` —— 入口页会自动出现这张卡片；终端里 `python main.py --list`
也能立刻看到它。没有 `views/tk.py` 的模型同样能用，会落到通用兜底视图 `FallbackView`
（同样由 `spec` 驱动：参数表单 + 动作按钮 + JSON 结果），不会因为"没写界面"而报错。

新增模型后**不需要登记任何中心清单**：`registry.load_models` 会扫描 `models/` 下的每个子包
（`_` 开头的除外），`kit.discover_views` 会尝试导入每个包的 `views/tk.py`。

**两套契约，一份换算**：`spec.handler(action, params)` 是**数据级**入口（网页 / 通用视图 /
终端用它），`spec.factory(params)` + `spec.batch` + `spec.scan` 是**对象级**入口（桌面视图
直接拿模型对象画图、跑后台批量统计与曲线扫描）。桌面骨架默认就用后者，所以「界面参数 →
模型」的换算（例如 `percolation/spec.py` 的 `build_grid`）只写一份，不会在 `handler` 与
`views/tk.py` 里各写一遍；非渗流模型（如 `buffon_needle`）只写 `handler` 就够了。

`life_game` 多了一层"翻译"值得对照：`build_board` 与 `build_grid` 同一约定，只认**内部取值**
（`"torus"` / `"glider"` / `"B3/S23"`），界面上的中文标签先过 `spec.py` 的
`options_from_ui`；数据级契约在 `handler` 里翻一次，桌面视图在造"可涂改的棋盘对象"时翻一次 ——
终端则直接用内部取值，不必经过翻译。

> **该继承哪个基类？** 桌面视图层分三层，按「要写多少界面代码」从少到多：
>
> 1. **通用图表骨架** `ChartViewBase`（`ui/tk/kit/chart.py`）—— **多数非渗流模型选它**：
>    参数表单、动作按钮、**侧栏顶部的「动画 / 播放」卡片**（▶ 播放 / ⏸ 暂停、⏭ 下一帧、
>    间隔滑块）、画布、坐标轴 / 网格 / 参考线、逐帧动画、右侧指标行全部自动生成，
>    自己只写**声明**：`CHART_SPECS`（哪种返回结构怎么画）+ `RESULT_ROWS` + 可选钩子。
>    图元有五种：`segments`（线段云）/ `series`（曲线族）/ `bars`（柱状）/
>    **`grid`（栅格：离散态走矩形差分刷新，或连续场走图像缓冲）** / `text`。
>    `buffon_needle` 是**纯声明**（视图里一行 Tk 绘图代码都没有）；`life_game` 用同一套声明，
>    另外通过四个"插槽钩子"把玩法接进去：`_build_player_extra`（播放卡片里加「清空棋盘」）、
>    `_param_card_footer`（「开局」卡片底部加「生成开局」）、`_build_right_extra`（右侧加实时
>    人口曲线）、`_on_cell_click(row, col, start)`（实现"按下决定这一笔是画还是擦、拖动不重复
>    翻转"）。它同时是"层 1 抽象够不够用"的第二个真实用例（对应 `docs/` 里的 R2）。
> 2. **万能骨架** `ModelViewBase`（`ui/tk/kit/base.py`）—— 想要完全不同的布局时用：
>    只有参数表单与动作按钮是自动的，中央 / 右侧自己画。
> 3. **渗流特化骨架** `PercolationViewBase` —— 渗流类模型用：在万能骨架之上补上
>    「概率 p + 格子 + 判据 + 逐层蔓延」，只需给术语表、指标行与几个画布钩子
>    （`percolation` / `site_percolation` 就是这种）。
>
> 三者都支持 `spec.factory` / `spec.batch` / `spec.scan`（对象级契约），
> 模型必须满足的接口写在 `ui/tk/kit/protocols.py`（`PercolationModel` 等），照契约实现即可。
>
> 4. **图元不够用时，模型可以自带图种**：在 `CHART_SPECS` 里声明一个自己的 `kind`，
>    再在自己的视图里覆盖 `_draw` 处理它 —— `n_body` 的 `kind="orbits"`
>    （运动的点云 + 轨迹带）就是这么做的。这样"新增一个渲染范式"不必回头改
>    `ui/tk/kit/chart.py`，也就不会牵动别的模型；代价是那几十行 Tk 绘图代码归模型自己维护。

**命令行参数也归模型所有**：模型用 `spec.cli_options`（`CliOption`）声明自己需要的终端选项，
入口 `launcher.build_parser` 把所有模型的声明汇总成一个解析器（同名只登记一次，帮助里标注
哪些模型通用）。于是蒲丰投针用自己的 `--ratio / --throws / --repeats`，**不必再借**渗流的
`--p / --trials` 当别名；不属于当前模型的选项会被接受但忽略。

---

## 环境要求

| 依赖 | 必需？ | 说明 |
| --- | --- | --- |
| Python | **必需** | 3.9+（开发与实测环境：3.13.9 / Anaconda） |
| numpy | **必需** | 全部模型的计算内核（向量化）；缺了跑不起来 |
| tkinter | **必需**（桌面窗口） | Python 自带；部分 Linux 发行版需另装 `python3-tk` |
| matplotlib | 可选 | 曲线页（渗流的 P(p) 曲线等）；缺失时该页显示提示，其余功能照常 |
| pywebview | 可选 | 网页后端想要独立窗口时用；缺失时用浏览器打开（web 后端已暂时弃用） |

一次装齐：`pip install -r requirements.txt`。

---

## 想深入了解代码

模块文档字符串写得比较细，按需跳读：

| 想了解 | 看这里 |
| --- | --- |
| 模型怎么注册、一个模型包含哪些文件 | `awe_math/registry.py` |
| 参数 / 动作 / 视图的元数据规范 | `awe_math/spec.py` |
| 入口流程与无图形环境的降级策略 | `awe_math/launcher.py` |
| 桌面视图的万能骨架（不认识模型） | `awe_math/ui/tk/kit/base.py` 的 `ModelViewBase` |
| 桌面视图对模型的要求（可执行契约） | `awe_math/ui/tk/kit/protocols.py` |
| 参数表单怎么由 spec.params 生成 | `awe_math/ui/tk/kit/form.py` |
| 通用图表怎么声明与绘制（含逐帧动画与**栅格图元**、播放控制、点击反查） | `awe_math/ui/tk/kit/chart.py` |
| 判据的全部界面语义（徽章 / 结论 / 曲线标注） | `awe_math/ui/tk/kit/criteria.py` |
| 数据级 / 对象级两套契约的字段说明 | `awe_math/spec.py`（模块说明） |
| 视图怎么被自动发现（约定优于中心清单） | `awe_math/ui/tk/kit/__init__.py` |
| 一个真实渗流模型的完整视图实现 | `awe_math/models/percolation/views/tk.py` |
| 一个真实**非渗流**模型的完整实现（通用图表骨架 + 纯 Monte Carlo） | `awe_math/models/buffon_needle/` |
| 一个真实**栅格类**模型的完整实现（栅格图元 + 周期检测 + 图案库） | `awe_math/models/life_game/` |

---

## 已知状态

* **网页后端暂时弃用**：代码保留在 `ui/web/`，把 `awe_math/ui/__init__.py` 里 `web` 的
  `deprecated` 改回 `False` 即可恢复为可选后端；
* 桌面视图层已拆成**三层骨架**：通用图表 `ChartViewBase`（声明式图表 + 动画 + 栅格图元）/
  万能 `ModelViewBase` / 渗流特化 `PercolationViewBase`，并已由 `buffon_needle` 与
  `life_game`（都用第一层，但前者是 `segments`/`series`、后者是 `grid`/`series`）以及两个
  渗流模型共同验证；新增模型按"要写多少界面代码"选一层即可。
* **栅格 / 热力图**这类范式现在由第一层的 `ChartSpec(kind="grid")` 覆盖（离散态走矩形差分
  刷新、连续场走图像缓冲，并支持逐帧时间轴与点击反查），因此**没有新增第四层骨架**：
  需要栅格能力时用它，而不是另起一个基类。仍是缺口的是**图 / 网络**类可视化。
* **移动的点云 / 轨迹带**（`n_body`）走的是另一条路：**模型自带图种**
  `kind="orbits"`，在自己的 `views/tk.py` 里覆盖 `_draw` 画星体与尾迹，
  播放节奏由自己的积分循环驱动。`ui/tk/kit/chart.py` **一行都没改** ——
  共享骨架仍只管"参数表单 + 播放卡片 + 指标行 + 徽章"，
  因此再多一个渲染范式也不会让别的模型跟着变。
* `life_game` 的桌面端是**实时逐代播放**（不设代数上限，用 `LifeWatch` 增量判定周期 /
  静止 / 消亡）；数据级契约（`spec.handler`）仍按 `--generations` 跑一段**有上限**的演化并
  回传 `frames`，供终端 / 网页等无头后端回放。两条路共用同一个 `LifeWatch`，
  所以"周期多长"不会给出两个答案。
* **破坏性变更**：命令行参数已归模型所有，蒲丰投针不再复用渗流的参数名 ——
  `--model buffon --trials 5000` 这类旧命令**不会报错也不会生效**（`--trials` 仍被解析器
  接受，因为它属于渗流模型；投针模型读的是 `--throws`）。请改用
  `--model buffon --throws 5000`（另有 `--ratio` / `--repeats`）。
* 网页端只为 `view == "percolation"` 写了专用渲染器（`ui/web/static/app.js`），所以
  `site_percolation` / `buffon_needle` / `life_game` 在 `--ui web` 下会退化成「参数表单 +
  动作按钮 + JSON 结果」的通用视图（web 已弃用，未投入维护）。
* `ui/tk/kit/` 里的画布 / 面板 / 后台任务是按 mixin 拆的，它们依赖「由基类最终提供」的
  属性与相互调用的方法（`self.model`、`self.var_status`、`self._terms`、
  `self._active_view()` 等）。这些共享属性与方法已集中声明在 `kit/protocols.py` 的
  `ViewContract` 里（`TYPE_CHECKING` 下），各 mixin 与基类都继承它，因此单独分析某个 mixin
  也不会再报 "Cannot access attribute"；它同时也是「基类必须提供什么」的可执行文档。
