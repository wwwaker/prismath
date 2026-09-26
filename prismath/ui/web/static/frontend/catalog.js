'use strict';

window.Prismath = window.Prismath || {};

Prismath.catalog = [
  {
    key: 'mandelbrot', name: 'Mandelbrot 集', topic: '复动力系统', icon: '◌', accent: '#c65b36',
    summary: '在复平面中移动和放大，观察简单迭代如何形成无穷细节。',
    kind: 'fractal', tags: ['复平面', '分形', '缩放']
  },
  {
    key: 'life_game', name: '康威生命游戏', topic: '细胞自动机', icon: '▦', accent: '#277c73',
    summary: '只用邻域规则，让图案在画布上自行演化。',
    kind: 'life', tags: ['涌现', '绘制', '逐代']
  },
  {
    key: 'buffon_needle', name: '蒲丰投针', topic: '概率与几何', icon: '╱', accent: '#a46a24',
    summary: '把随机投掷变成可见的命中率与 π 的估计。',
    kind: 'buffon', tags: ['随机', '估计', '收敛']
  },
  {
    key: 'n_body', name: '万有引力多星模型', topic: '轨道动力学', icon: '✦', accent: '#6f58a6',
    summary: '从同一条引力规则出发，观察周期轨道与混沌分岔。',
    kind: 'nbody', tags: ['轨道', '三体', '能量']
  },
  {
    key: 'percolation', name: '键渗流', topic: '统计物理', icon: '⌁', accent: '#3974a3',
    summary: '逐层点亮随机连通网络，寻找从顶到底的通路。',
    kind: 'percolation', tags: ['网络', '阈值', '连通']
  },
  {
    key: 'site_percolation', name: '点渗流', topic: '统计物理', icon: '·', accent: '#8c5d75',
    summary: '关闭或打开节点，观察一片随机空间何时贯通。',
    kind: 'percolation', site: true, tags: ['节点', '阈值', '连通']
  }
];

Prismath.modelByKey = (key) => Prismath.catalog.find((model) => model.key === key) || null;
