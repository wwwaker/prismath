# prismath：数学模型可视化工具箱

`prismath` 是一个面向学习和探索的数学实验室。模型负责计算，参数和动作由 `ModelSpec` 描述，桌面界面按模型自动发现，不需要维护中心注册表。

## 快速开始

```powershell
python -m pip install -r requirements.txt
python main.py
```

默认打开 Tk 桌面模型列表。没有图形环境时，程序会回落到终端模式。

常用命令：

```powershell
python main.py --list
python main.py --model probability_lab
python main.py --model mandelbrot --ui cli
python main.py --menu
```

`--model` 支持模型标识、序号和名称关键字；`--seed -1` 表示随机，非负整数用于复现实验。

## 模型

| 标识 | 模型 | 适合观察的现象 |
| --- | --- | --- |
| `percolation` / `site_percolation` | 边渗流 / 点渗流 | 临界概率、贯通和相变 |
| `life_game` | 生命游戏 | 滑翔机、振荡子和涌现结构 |
| `n_body` | 万有引力多星 | 轨道、守恒量和混沌 |
| `mandelbrot` | Mandelbrot 集 | 分形、自相似和缩放 |
| `logistic_map` / `henon_map` | 离散动力系统 | 分岔、吸引子和混沌 |
| `fourier_epicycles` | Fourier Epicycles | 旋转向量重绘轮廓 |
| `linear_transform` | 线性变换实验室 | 网格、基向量、行列式和面积 |
| `projectile_motion` | 抛体运动实验室 | 发射角、空气阻力和射程 |
| `gradient_descent` | 梯度下降实验室 | 学习率、局部最小值和收敛 |
| `probability_lab` | 概率实验室 | 大数定理、中心极限定理和高尔顿钉板 |
| `buffon_needle` | 蒲丰投针 | 蒙特卡洛估计 π |

概率实验室中可以切换大数定理、中心极限定理和高尔顿钉板；梯度下降包含抛物线、波纹函数、多势阱和光滑绝对值等预设。

## 依赖

- Python 3.10+
- `numpy`：所有数值模型的必需依赖
- `Pillow`、`opencv-python`：图片轮廓输入
- `matplotlib`：部分曲线页面的可选依赖
- `numba`：Mandelbrot 的可选 CPU 加速后端
- `tkinter`：桌面界面，通常随 Python 提供

安装基础依赖：

```powershell
python -m pip install -r requirements.txt
```

需要 Numba 时单独安装：

```powershell
python -m pip install numba
```

## 项目结构

```text
main.py                         统一入口
prismath/registry.py            模型自动发现与注册
prismath/spec.py                ModelSpec / ParamSpec / ActionSpec
prismath/models/<model>/
  model.py                      纯计算内核
  spec.py                       参数、动作和 handler
  views/tk.py                   可选的 Tk 专用视图
prismath/ui/tk/                 桌面外壳和通用图表工具
prismath/ui/web/                网页后端
prismath/ui/__init__.py         Tk / CLI / Web 后端入口
tests/                          单元测试、视图冒烟和基准
```

新增模型通常只需：

1. 新建 `prismath/models/<model>/` 包；
2. 在 `spec.py` 中提供 `ModelSpec` 和 `handler`；
3. 在 `__init__.py` 中调用 `register(build_spec())`；
4. 需要专用桌面交互时添加 `views/tk.py`；
5. 为数学结论和 payload 添加测试。

模型目录会被 `prismath.registry.load_models()` 自动扫描。

## 测试

```powershell
python -m unittest discover -s tests -q
python -m unittest tests.test_views_smoke -v
python -m tests.bench
```

提交前建议同时运行：

```powershell
git diff --check
```

详细的架构评估、产品计划、问题记录和旧版完整说明保留在本地 `docs/` 目录。该目录已加入 `.gitignore`，不会进入 Git 仓库。
