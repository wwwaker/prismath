/* ==========================================================================
 * prismath · 前端应用
 *
 * 结构：
 *   1. 工具函数与 API
 *   2. 全局状态
 *   3. 路由：门户页 / 模型页
 *   4. 参数控件生成（由后端 ModelSpec 驱动）
 *   5. 渲染器：网格视图（含逐层动画）、曲线视图、通用回退视图
 *   6. 批量统计与曲线扫描（分块调用 + 可中断）
 * ========================================================================== */
'use strict';

/* ------------------------------------------------------------------ 1. 工具 */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const toNum = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
const fixed = (v, d = 3) => (Number.isFinite(Number(v)) ? Number(v).toFixed(d) : '—');

function debounce(fn, ms) {
  let timer = 0;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function toast(message, kind = '') {
  const box = document.createElement('div');
  box.className = `toast ${kind}`;
  box.textContent = message;
  $('#toasts').appendChild(box);
  setTimeout(() => {
    box.classList.add('hide');
    setTimeout(() => box.remove(), 320);
  }, 3200);
}

const API = {
  async models() {
    const res = await fetch('api/models');
    return res.json();
  },
  async action(modelKey, action, params, payload = {}) {
    const res = await fetch(`api/model/${encodeURIComponent(modelKey)}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, params, payload }),
    });
    return res.json();
  },
};

/* ------------------------------------------------------------------ 2. 状态 */
const state = {
  models: [],
  uis: [],
  spec: null,
  params: {},
  lock: null,      // 'batch' | 'scan' | null
  token: 0,        // 迭代令牌，用于中断异步循环

  // 网格视图
  payload: null,
  geom: null,
  nodeLayer: null,
  wet: null,
  playing: false,
  raf: 0,
  shownLayers: 0,
  speed: 35,
  showBlocked: true,
  showNodes: true,

  // 批量统计与曲线
  scan: [],
  chartHover: null,
};

/* 会触发“自动重绘”的参数（其余参数只作为动作配置） */
const LIVE_KEYS = new Set(['p', 'size', 'directed', 'seed']);

/* ------------------------------------------------------------------ 3. 路由 */
async function boot() {
  try {
    const data = await API.models();
    if (!data.ok) throw new Error(data.error || '接口异常');
    state.models = data.models || [];
    state.uis = data.uis || [];
  } catch (err) {
    $('#view').innerHTML = `<div class="card"><div class="body">无法连接本地服务：${err.message}</div></div>`;
    return;
  }
  $('#footerMeta').textContent = `模型 ${state.models.length} 个 · 界面后端 ${state.uis.length} 种`;
  window.addEventListener('hashchange', route);
  document.addEventListener('keydown', shortcut);   // 只注册一次，避免路由切换后重复触发
  route();
}

function route() {
  const hash = location.hash || '#/';
  const match = /^#\/model\/([\w.-]+)/.exec(hash);
  stopAll();
  if (match) {
    const spec = state.models.find((m) => m.key === match[1]);
    if (!spec) {
      toast(`没有找到模型：${match[1]}`, 'error');
      location.hash = '#/';
      return;
    }
    renderModelPage(spec);
  } else {
    renderPortal();
  }
}

function stopAll() {
  state.token += 1;            // 令牌自增即可让所有异步循环在下一轮退出
  state.playing = false;
  if (state.raf) cancelAnimationFrame(state.raf);
  state.raf = 0;
  state.lock = null;
  state.scan = [];
  state.payload = null;
  // 循环退出时不会再走 finally 里的复位（令牌已变），这里显式恢复按钮状态
  lockButtons(false);
  const bs = $('#btnBatchStop');
  const ss = $('#btnScanStop');
  if (bs) bs.disabled = true;
  if (ss) ss.disabled = true;
}

function setTopbar(extra = '') {
  $('#topbarActions').innerHTML = extra || `<span class="chip"><span class="dot"></span>本机服务运行中</span>`;
}

/* -------------------------------------------------------------- 门户页 */
function renderPortal() {
  state.spec = null;    // 门户页不再持有模型上下文，避免快捷键误触发计算
  setTopbar();
  const topics = new Map();
  state.models.forEach((m) => {
    if (!topics.has(m.topic)) topics.set(m.topic, []);
    topics.get(m.topic).push(m);
  });

  const sections = [...topics.entries()].map(([topic, models]) => `
    <div class="section-title"><h2>${topic}</h2><span>${models.length} 个模型</span></div>
    <div class="cards">
      ${models.map(cardHTML).join('')}
    </div>`).join('');

  const uiCards = state.uis.map((ui) => `
    <div class="card" style="--card-accent:#34d399">
      <div class="body">
        <div class="field-label"><span>${ui.name}</span><span class="val">--ui ${ui.key}</span></div>
        <p class="muted" style="margin:0">${ui.summary}</p>
        ${ui.requires.length ? `<p class="muted" style="margin:8px 0 0">依赖：${ui.requires.join('、')}</p>` : ''}
      </div>
    </div>`).join('');

  $('#view').innerHTML = `
    <section class="hero">
      <h1>让数学模型的量变<br>看得见质变</h1>
      <p>
        这是一个可扩展的数学模型可视化工具箱：每个模型只描述“参数 + 计算”，
        界面负责把它变成可交互的画面。当前页面由本地 Python 服务提供，
        所有计算都在你自己的机器上完成。
      </p>
      <div class="hero-tags">
        <span class="chip"><span class="dot"></span>模型 <b>${state.models.length}</b> 个</span>
        <span class="chip">界面后端 <b>${state.uis.length}</b> 种</span>
        <span class="chip">新增模型 = 新建一个包并注册，无需改动入口</span>
      </div>
    </section>
    ${sections}
    <div class="section-title"><h2>界面后端</h2><span>同一个模型，三种打开方式</span></div>
    <div class="cards">${uiCards}</div>
    <div class="section-title"><h2>命令行入口</h2><span>统一入口：先选模型，再选界面</span></div>
    <div class="card"><div class="body">
      <pre class="code">python main.py                          <b># 交互式门户：列出模型与界面供选择</b>
python main.py --list                   <b># 只看有哪些模型</b>
python main.py --model percolation --ui web   <b># 直接打开某个模型的网页界面</b>
python main.py --model percolation --ui tk    <b># 用桌面窗口打开</b>
python main.py --model percolation --ui cli --scan  <b># 终端里扫描 P(p) 曲线</b></pre>
    </div></div>`;
}

function cardHTML(spec) {
  return `
  <a class="model-card" href="#/model/${spec.key}" style="--card-accent:${spec.accent}">
    <div class="model-card-head">
      <div class="model-icon">${spec.icon}</div>
      <div>
        <h3>${spec.name}</h3>
        <div class="topic">${spec.topic}</div>
      </div>
    </div>
    <p>${spec.summary}</p>
    <ul class="highlights">${spec.highlights.map((h) => `<li>${h}</li>`).join('')}</ul>
    <div class="enter">进入模型 <span aria-hidden="true">→</span></div>
  </a>`;
}

/* -------------------------------------------------------------- 模型页 */
function renderModelPage(spec) {
  canvases = null;              // 页面重建后旧的 canvas 引用已失效
  state.spec = spec;
  state.params = {};
  spec.params.forEach((p) => { state.params[p.key] = p.default; });
  state.scan = [];
  state.shownLayers = 0;

  setTopbar(`
    <span class="chip">${spec.topic}</span>
    <span class="chip" id="runState"><span class="dot" style="background:#64708c;box-shadow:none"></span>就绪</span>
    <a class="btn ghost" href="#/">← 返回门户</a>`);

  $('#view').innerHTML = `
    <section class="model-head" style="--model-accent:${spec.accent}">
      <div class="icon">${spec.icon}</div>
      <div>
        <h1>${spec.name}</h1>
        <div class="meta">
          <span class="chip">模型标识 <b>${spec.key}</b></span>
          <span class="chip">视图 <b>${spec.view}</b></span>
        </div>
        <div class="desc">${spec.description || spec.summary}</div>
      </div>
    </section>

    <div class="workspace">
      <div class="col col-left">
        <div class="card">
          <header><h3>参数调节</h3><span class="sub">改动即时重绘</span></header>
          <div class="body" id="paramBody"></div>
        </div>
        <div class="card">
          <header><h3>使用提示</h3><span class="sub">Tips</span></header>
          <div class="body">
            <div class="kv-list">
              <div class="row"><span>播放动画</span><span>空格</span></div>
              <div class="row"><span>重新生成</span><span>R</span></div>
              <div class="row"><span>立即完成</span><span>F</span></div>
            </div>
            <p class="muted" style="margin:12px 0 0">
              水从顶端整行注入，沿流通边上下左右蔓延；只要有一个底端节点被浸润，
              就认为本次渗流成功。
            </p>
          </div>
        </div>
      </div>

      <div class="col col-mid" id="colMid"></div>

      <div class="col col-right">
        <div class="card">
          <header><h3>本次模拟</h3><span class="sub" id="statsSub">单次生成结果</span></header>
          <div class="body">
            <div class="verdict-badge" id="verdictBadge">
              <div>
                <div class="note">是否渗流出水</div>
                <div class="big" id="verdictText">—</div>
              </div>
              <div class="note" id="verdictNote">等待生成</div>
            </div>
            <div class="stats" style="margin-top:12px">
              <div class="stat wide hero"><div class="k">当前概率 p</div><div class="v" id="sP">—</div></div>
              <div class="stat"><div class="k">网格规模</div><div class="v" id="sSize">—</div></div>
              <div class="stat"><div class="k">渗透层数</div><div class="v" id="sDepth">—</div></div>
              <div class="stat"><div class="k">流通边比例</div><div class="v" id="sOpen">—</div></div>
              <div class="stat"><div class="k">浸润节点</div><div class="v" id="sWet">—</div></div>
            </div>
          </div>
        </div>

        <div class="card">
          <header><h3>批量统计</h3><span class="sub">独立重复实验</span></header>
          <div class="body">
            <div class="stats">
              <div class="stat"><div class="k">模拟次数 N</div><div class="v" id="bTotal">—</div></div>
              <div class="stat"><div class="k">成功次数</div><div class="v" id="bSuccess">—</div></div>
              <div class="stat wide hero"><div class="k">渗流概率</div><div class="v" id="bProb">—</div></div>
            </div>
            <div class="progress"><i id="batchBar"></i></div>
            <div class="btn-row" style="margin-top:14px">
              <button class="btn primary" id="btnBatch">开始批量统计</button>
              <button class="btn danger" id="btnBatchStop" disabled>停止</button>
            </div>
            <p class="muted" id="batchNote" style="margin:12px 0 0">尚未开始。</p>
          </div>
        </div>

        <div class="card">
          <header><h3>P(p) 曲线</h3><span class="sub">渗流概率随 p 的变化</span></header>
          <div class="body">
            <div class="chart-wrap" id="chartWrap">
              <canvas id="chart"></canvas>
              <div class="tooltip" id="chartTip"></div>
            </div>
            <div class="progress"><i id="scanBar"></i></div>
            <div class="btn-row" style="margin-top:14px">
              <button class="btn primary" id="btnScan">扫描并绘制</button>
              <button class="btn danger" id="btnScanStop" disabled>停止</button>
            </div>
            <p class="muted" id="scanNote" style="margin:12px 0 0">尚未开始。</p>
          </div>
        </div>
      </div>
    </div>`;

  buildParamControls(spec);
  if (spec.view === 'percolation') buildPercolationView(spec);
  else buildGenericView(spec);

  generate({ animate: true });
}

function shortcut(event) {
  if (event.target.matches('input, textarea')) return;
  const key = event.key.toLowerCase();
  if (key === ' ') { event.preventDefault(); playPause(); }
  if (key === 'r') generate({ animate: false });
  if (key === 'f') finishInstant();
}

/* ------------------------------------------------- 4. 参数控件（自动生成） */
function buildParamControls(spec) {
  const groups = new Map();
  spec.params.forEach((p) => {
    if (!groups.has(p.group)) groups.set(p.group, []);
    groups.get(p.group).push(p);
  });

  $('#paramBody').innerHTML = [...groups.entries()].map(([group, params]) => `
    <div class="param-group">
      <h4>${group}</h4>
      ${params.map(paramHTML).join('')}
    </div>`).join('');

  spec.params.forEach((p) => bindParam(p));
}

function paramHTML(p) {
  if (p.kind === 'bool') {
    return `
    <div class="field">
      <label class="switch">
        <input type="checkbox" data-key="${p.key}" ${p.default ? 'checked' : ''}>
        <span class="track"></span>
        <span class="txt">${p.label}</span>
      </label>
      ${p.hint ? `<div class="hint">${p.hint}</div>` : ''}
    </div>`;
  }
  if (p.kind === 'choice') {
    return `
    <div class="field">
      <div class="field-label"><span>${p.label}</span></div>
      <div class="seg" data-key="${p.key}">
        ${p.choices.map((c) => `<button type="button" data-value="${c}" class="${String(p.default) === String(c) ? 'on' : ''}">${c}</button>`).join('')}
      </div>
      ${p.hint ? `<div class="hint">${p.hint}</div>` : ''}
    </div>`;
  }
  const isFloat = p.kind === 'float';
  const step = p.step ?? (isFloat ? 0.01 : 1);
  const spread = toNum(p.max ?? 1) - toNum(p.min ?? 0);
  const label = `${p.label}${p.unit ? ` <b style="color:var(--faint);font-weight:400">${p.unit}</b>` : ''}`;

  // 取值范围过大的整数（例如随机种子）用输入框而不是滑块
  if (p.kind === 'int' && spread > 1000) {
    return `
    <div class="field">
      <div class="field-label"><span>${label}</span></div>
      <input type="number" data-key="${p.key}" value="${p.default}">
      ${p.hint ? `<div class="hint">${p.hint}</div>` : ''}
    </div>`;
  }

  return `
  <div class="field">
    <div class="field-label">
      <span>${label}</span>
      <span class="val" data-for="${p.key}">${p.default}</span>
    </div>
    <input type="range" data-key="${p.key}" min="${p.min ?? 0}" max="${p.max ?? 1}" step="${step}" value="${p.default}">
    ${p.hint ? `<div class="hint">${p.hint}</div>` : ''}
  </div>`;
}

function bindParam(p) {
  const ranges = $$(`input[type="range"][data-key="${p.key}"]`, $('#paramBody'));
  const numbers = $$(`input[type="number"][data-key="${p.key}"]`, $('#paramBody'));
  const toggles = $$(`input[type="checkbox"][data-key="${p.key}"]`, $('#paramBody'));
  const segs = $$(`.seg[data-key="${p.key}"]`, $('#paramBody'));
  const labels = $$(`.val[data-for="${p.key}"]`, $('#paramBody'));
  const isFloat = p.kind === 'float';

  const paint = (value) => {
    labels.forEach((l) => { l.textContent = isFloat ? Number(value).toFixed(2) : value; });
    ranges.forEach((r) => {
      const span = toNum(r.max) - toNum(r.min) || 1;
      r.style.setProperty('--fill', `${((Number(value) - toNum(r.min)) / span) * 100}%`);
    });
  };

  const commit = (value, from) => {
    state.params[p.key] = value;
    paint(value);
    if (from !== 'range') ranges.forEach((r) => { r.value = value; });
    if (from !== 'number') numbers.forEach((n) => { n.value = value; });
    if (LIVE_KEYS.has(p.key)) autoRegenerate();
  };

  const onRange = (event) => commit(isFloat ? Number(event.target.value) : parseInt(event.target.value, 10), 'range');
  ranges.forEach((r) => {
    r.addEventListener('input', onRange);
    const span = toNum(r.max) - toNum(r.min) || 1;
    r.style.setProperty('--fill', `${((toNum(r.value) - toNum(r.min)) / span) * 100}%`);
  });
  numbers.forEach((n) => n.addEventListener('change', () => {
    const raw = parseInt(n.value, 10);
    commit(clamp(Number.isFinite(raw) ? raw : p.default, p.min ?? 0, p.max ?? 0), 'number');
  }));
  toggles.forEach((t) => t.addEventListener('change', () => commit(t.checked, 'toggle')));
  segs.forEach((seg) => seg.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-value]');
    if (!button) return;
    $$('button', seg).forEach((b) => b.classList.toggle('on', b === button));
    commit(button.dataset.value, 'seg');
  }));

  paint(p.default);
}

const autoRegenerate = debounce(() => {
  if (state.spec && state.spec.view === 'percolation') generate({ animate: false });
}, 220);

/* ------------------------------------------------- 5a. 网格视图（渗流） */
function buildPercolationView(spec) {
  $('#colMid').innerHTML = `
    <div class="card canvas-card">
      <header>
        <h3>网格渗透过程</h3>
        <span class="sub" id="gridSub">等待生成…</span>
      </header>
      <div class="canvas-toolbar">
        <button class="btn primary" id="btnPlay">▶ 播放渗透</button>
        <button class="btn" id="btnReplay">↻ 重播</button>
        <button class="btn" id="btnInstant">⤓ 立即完成</button>
        <span class="spacer"></span>
        <label>速度 <input type="range" id="speed" min="1" max="200" value="${state.speed}"></label>
        <label><input type="checkbox" id="showBlocked" checked> 阻断边</label>
        <label><input type="checkbox" id="showNodes" checked> 节点</label>
      </div>
      <div class="body">
        <div class="grid-wrap" id="gridWrap">
          <canvas id="baseCanvas"></canvas>
          <canvas id="wetCanvas"></canvas>
          <canvas id="displayCanvas"></canvas>
          <div class="overlay-legend">
            <div><i style="background:#38bdf8"></i>流通边</div>
            <div><i style="background:rgba(148,163,184,.35)"></i>阻断边</div>
            <div><span class="dot" style="background:#fde047"></span> 早浸润</div>
            <div><span class="dot" style="background:#f43f5e"></span> 晚浸润</div>
          </div>
          <div class="verdict" id="verdict"></div>
          <div class="tooltip" id="gridTip"></div>
        </div>
      </div>
    </div>`;

  $('#btnPlay').addEventListener('click', playPause);
  $('#btnReplay').addEventListener('click', () => play(true));
  $('#btnInstant').addEventListener('click', finishInstant);
  $('#speed').addEventListener('input', (e) => { state.speed = toNum(e.target.value, 35); });
  $('#showBlocked').addEventListener('change', (e) => { state.showBlocked = e.target.checked; rebuildBase(); composite(); });
  $('#showNodes').addEventListener('change', (e) => { state.showNodes = e.target.checked; rebuildBase(); composite(); });
  $('#btnBatch').addEventListener('click', runBatch);
  $('#btnBatchStop').addEventListener('click', stopAll);
  $('#btnScan').addEventListener('click', runScan);
  $('#btnScanStop').addEventListener('click', stopAll);

  const wrap = $('#gridWrap');
  $('#displayCanvas').addEventListener('mousemove', onGridHover);
  $('#displayCanvas').addEventListener('mouseleave', () => $('#gridTip').classList.remove('show'));
  new ResizeObserver(() => {
    if (!state.payload) return;
    rebuildBase();
    replayWet();
  }).observe(wrap);

  drawChart();
  bindChartHover();
}

let canvases = null;

function ensureCanvases() {
  if (canvases) return canvases;
  const base = $('#baseCanvas');
  const wet = $('#wetCanvas');
  const display = $('#displayCanvas');
  canvases = {
    base, wet, display,
    bctx: base.getContext('2d'),
    wctx: wet.getContext('2d'),
    dctx: display.getContext('2d'),
    span: 1,
    last: performance.now(),
    acc: 0,
    perFrame: 1,
  };
  return canvases;
}

function computeGeom() {
  const n = state.payload.size;
  const wrap = $('#gridWrap');
  const w = Math.max(wrap.clientWidth, 240);
  const h = Math.max(wrap.clientHeight, 240);
  const pad = clamp(Math.min(w, h) * 0.06, 16, 34);
  const cell = Math.min((w - 2 * pad) / (n - 1 || 1), (h - 2 * pad) / (n - 1 || 1));
  return {
    n, w, h, cell,
    ox: (w - cell * (n - 1)) / 2,
    oy: (h - cell * (n - 1)) / 2,
    rad: clamp(cell * 0.17, 0.9, 5),
    lw: clamp(cell * 0.13, 0.7, 2.6),
  };
}

const nodeXY = (g, index) => {
  const r = Math.floor(index / g.n);
  const c = index % g.n;
  return [g.ox + c * g.cell, g.oy + r * g.cell];
};

function rebuildBase() {
  const cv = ensureCanvases();
  const g = computeGeom();
  state.geom = g;
  const dpr = window.devicePixelRatio || 1;

  [cv.base, cv.wet, cv.display].forEach((c) => {
    c.width = Math.round(g.w * dpr);
    c.height = Math.round(g.h * dpr);
    c.style.width = `${g.w}px`;
    c.style.height = `${g.h}px`;
  });
  cv.bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cv.wctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cv.dctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cv.bctx.clearRect(0, 0, g.w, g.h);
  cv.wctx.clearRect(0, 0, g.w, g.h);

  // 三角网没有 v/dl/dr 之外的编码，缺字段时按空串处理（不绘制，但不报错）
  const { n, h: hEdges = '', v: vEdges = '' } = state.payload;

  // ---- 阻断边（虚线，批量成一条路径绘制） ----
  if (state.showBlocked && g.cell > 2.2) {
    cv.bctx.beginPath();
    for (let r = 0; r < n; r += 1) {
      for (let c = 0; c < n - 1; c += 1) {
        if (hEdges[r * (n - 1) + c] === '0') {
          const [x, y] = nodeXY(g, r * n + c);
          cv.bctx.moveTo(x, y);
          cv.bctx.lineTo(x + g.cell, y);
        }
      }
    }
    for (let r = 0; r < n - 1; r += 1) {
      for (let c = 0; c < n; c += 1) {
        if (vEdges[r * n + c] === '0') {
          const [x, y] = nodeXY(g, r * n + c);
          cv.bctx.moveTo(x, y);
          cv.bctx.lineTo(x, y + g.cell);
        }
      }
    }
    cv.bctx.setLineDash([2, 3]);
    cv.bctx.lineWidth = Math.max(0.6, g.lw * 0.62);
    cv.bctx.strokeStyle = 'rgba(148,163,184,0.20)';
    cv.bctx.stroke();
    cv.bctx.setLineDash([]);
  }

  // ---- 流通边 ----
  cv.bctx.beginPath();
  for (let r = 0; r < n; r += 1) {
    for (let c = 0; c < n - 1; c += 1) {
      if (hEdges[r * (n - 1) + c] === '1') {
        const [x, y] = nodeXY(g, r * n + c);
        cv.bctx.moveTo(x, y);
        cv.bctx.lineTo(x + g.cell, y);
      }
    }
  }
  for (let r = 0; r < n - 1; r += 1) {
    for (let c = 0; c < n; c += 1) {
      if (vEdges[r * n + c] === '1') {
        const [x, y] = nodeXY(g, r * n + c);
        cv.bctx.moveTo(x, y);
        cv.bctx.lineTo(x, y + g.cell);
      }
    }
  }
  cv.bctx.lineWidth = g.lw;
  cv.bctx.lineCap = 'round';
  cv.bctx.strokeStyle = 'rgba(56,189,248,0.62)';
  cv.bctx.stroke();

  // ---- 节点 ----
  if (state.showNodes && g.rad >= 1.1) {
    cv.bctx.fillStyle = 'rgba(148,163,184,0.5)';
    cv.bctx.beginPath();
    for (let r = 1; r < n - 1; r += 1) {
      for (let c = 0; c < n; c += 1) {
        const [x, y] = nodeXY(g, r * n + c);
        cv.bctx.moveTo(x + g.rad, y);
        cv.bctx.arc(x, y, g.rad, 0, Math.PI * 2);
      }
    }
    cv.bctx.fill();
  }

  // ---- 顶端水源 / 底端出口 ----
  cv.bctx.fillStyle = 'rgba(56,189,248,0.9)';
  cv.bctx.strokeStyle = 'rgba(56,189,248,0.9)';
  cv.bctx.lineWidth = 1.6;
  for (let c = 0; c < n; c += 1) {
    const [x, y] = nodeXY(g, c);
    cv.bctx.beginPath();
    cv.bctx.arc(x, y, Math.max(g.rad, 2), 0, Math.PI * 2);
    cv.bctx.fill();
  }
  cv.bctx.fillStyle = 'rgba(52,211,153,0.9)';
  cv.bctx.strokeStyle = 'rgba(52,211,153,0.9)';
  for (let c = 0; c < n; c += 1) {
    const [x, y] = nodeXY(g, (n - 1) * n + c);
    cv.bctx.beginPath();
    cv.bctx.arc(x, y, Math.max(g.rad, 2), 0, Math.PI * 2);
    cv.bctx.fill();
  }
}

const WET_RAMP = [
  [0.00, [253, 224, 71]],
  [0.42, [251, 146, 60]],
  [0.74, [244, 63, 94]],
  [1.00, [168, 85, 247]],
];

function layerColor(t) {
  const v = clamp(t, 0, 1);
  for (let i = 1; i < WET_RAMP.length; i += 1) {
    const [pos, rgb] = WET_RAMP[i];
    if (v <= pos) {
      const [p0, c0] = WET_RAMP[i - 1];
      const k = (v - p0) / (pos - p0 || 1);
      const mix = c0.map((ch, j) => Math.round(ch + (rgb[j] - ch) * k));
      return `rgb(${mix[0]},${mix[1]},${mix[2]})`;
    }
  }
  return 'rgb(168,85,247)';
}

/* 把第 index 层涂到“浸润层”画布上（增量绘制，动画时不必整幅重画） */
function paintLayer(index) {
  const cv = ensureCanvases();
  const g = state.geom || computeGeom();
  const layers = state.payload.layers;
  const nodes = layers[index];
  if (!nodes) return;
  const total = layers.length;
  const color = layerColor(total > 1 ? index / (total - 1) : 0);
  const n = g.n;

  nodes.forEach((idx) => { state.wet[idx] = 1; });

  // 已浸润边：与已浸润邻居之间的流通边
  cv.wctx.beginPath();
  nodes.forEach((idx) => {
    const [x, y] = nodeXY(g, idx);
    const r = Math.floor(idx / n);
    const c = idx % n;
    if (c + 1 < n && state.wet[idx + 1]) { cv.wctx.moveTo(x, y); cv.wctx.lineTo(x + g.cell, y); }
    if (c > 0 && state.wet[idx - 1]) { cv.wctx.moveTo(x, y); cv.wctx.lineTo(x - g.cell, y); }
    if (r + 1 < n && state.wet[idx + n]) { cv.wctx.moveTo(x, y); cv.wctx.lineTo(x, y + g.cell); }
    if (r > 0 && state.wet[idx - n]) { cv.wctx.moveTo(x, y); cv.wctx.lineTo(x, y - g.cell); }
  });
  cv.wctx.lineWidth = Math.max(1.6, g.lw * 1.5);
  cv.wctx.lineCap = 'round';
  cv.wctx.strokeStyle = 'rgba(253,224,71,0.85)';
  cv.wctx.stroke();

  // 节点
  cv.wctx.fillStyle = color;
  cv.wctx.beginPath();
  const rad = Math.max(g.rad, 1.6);
  nodes.forEach((idx) => {
    const [x, y] = nodeXY(g, idx);
    cv.wctx.moveTo(x + rad, y);
    cv.wctx.arc(x, y, rad, 0, Math.PI * 2);
  });
  cv.wctx.fill();
}

function composite() {
  const cv = ensureCanvases();
  if (!state.geom) return;
  cv.dctx.clearRect(0, 0, state.geom.w, state.geom.h);
  cv.dctx.drawImage(cv.base, 0, 0, state.geom.w, state.geom.h);
  cv.dctx.drawImage(cv.wet, 0, 0, state.geom.w, state.geom.h);
}

function replayWet() {
  const cv = ensureCanvases();
  cv.wctx.clearRect(0, 0, state.geom.w, state.geom.h);
  state.wet = new Uint8Array(state.payload.size * state.payload.size);
  for (let i = 0; i < state.shownLayers; i += 1) paintLayer(i);
  composite();
}

/* ------------------------------------------------------- 生成与动画流程 */
async function generate({ animate = true } = {}) {
  if (!state.spec || state.spec.view !== 'percolation') return;
  const token = ++state.token;
  state.playing = false;
  if (state.raf) cancelAnimationFrame(state.raf);
  setRunState('计算中…', '#fbbf24');

  let res;
  try {
    res = await API.action(state.spec.key, 'generate', state.params);
  } catch (err) {
    toast(`请求失败：${err.message}`, 'error');
    return;
  }
  if (token !== state.token) return;
  if (!res.ok) { toast(res.error, 'error'); setRunState('出错', '#fb7185'); return; }

  const info = res.result;
  const unsupported = (info.lattice && info.lattice !== 'square')
    || (info.cols && info.cols !== info.rows);
  if (unsupported) {   // 网页渲染器只支持方格网，三角网 / 矩形网格请到桌面端看
    state.payload = null;
    toast('三角网 / 矩形网格请在桌面端查看（python main.py --ui tk）：网页渲染器目前只支持方格网。', 'error');
    $('#gridSub').textContent = '该网格类型请在桌面端查看';
    setRunState('已跳过绘制', '#fbbf24');
    return;
  }

  state.payload = res.result;
  state.showNodes = true;
  if ($('#showNodes') && info.size > 44) { // 超密网格默认隐藏节点，避免糊成一团
    state.showNodes = false;
    $('#showNodes').checked = false;
  }

  const n = info.size;
  state.wet = new Uint8Array(n * n);
  state.nodeLayer = new Int16Array(n * n).fill(-1);
  info.layers.forEach((layer, i) => layer.forEach((idx) => { state.nodeLayer[idx] = i; }));
  state.shownLayers = 0;
  state.scan = [];
  drawChart();

  rebuildBase();
  composite();
  paintStats();
  $('#gridSub').textContent = `${n}×${n} 网格 · ${info.totalEdges} 条边 · 生成耗时 ${fixed(info.elapsedMs, 1)} ms`;
  setRunState('就绪', '#34d399');

  if (animate) play(true);
  else finishInstant();
}

function play(reset = false) {
  if (!state.payload) return;
  const cv = ensureCanvases();
  if (reset || state.shownLayers >= state.payload.layers.length) {
    state.shownLayers = 0;
    state.wet = new Uint8Array(state.payload.size * state.payload.size);
    cv.wctx.clearRect(0, 0, state.geom.w, state.geom.h);
    composite();
  }
  state.playing = true;
  cv.perFrame = Math.max(1, Math.ceil(state.payload.layers.length / 70));
  cv.acc = 0;
  cv.last = performance.now();
  $('#btnPlay').innerHTML = '⏸ 暂停';
  setRunState('播放中…', '#38bdf8');
  if (state.raf) cancelAnimationFrame(state.raf);
  state.raf = requestAnimationFrame(tick);
}

function tick(now) {
  const cv = ensureCanvases();
  if (!state.playing || !state.payload) return;
  const total = state.payload.layers.length;

  cv.acc += now - cv.last;
  cv.last = now;
  if (cv.acc >= state.speed) {
    cv.acc = 0;
    for (let k = 0; k < cv.perFrame && state.shownLayers < total; k += 1) {
      paintLayer(state.shownLayers);
      state.shownLayers += 1;
    }
    composite();
    $('#verdict').classList.remove('show');
  }

  if (state.shownLayers < total) {
    state.raf = requestAnimationFrame(tick);
  } else {
    finishAnimation();
  }
}

function finishAnimation() {
  state.playing = false;
  state.raf = 0;
  $('#btnPlay').innerHTML = '▶ 播放渗透';
  showVerdict();
  paintStats();
  setRunState('就绪', '#34d399');
}

function finishInstant() {
  if (!state.payload) return;
  state.playing = false;
  if (state.raf) cancelAnimationFrame(state.raf);
  state.raf = 0;
  $('#btnPlay').innerHTML = '▶ 播放渗透';
  state.shownLayers = state.payload.layers.length;
  replayWet();
  showVerdict();
  paintStats();
  setRunState('已显示最终结果', '#34d399');
}

function playPause() {
  if (!state.payload) return;
  if (state.playing) {
    state.playing = false;
    if (state.raf) cancelAnimationFrame(state.raf);
    state.raf = 0;
    $('#btnPlay').innerHTML = '▶ 继续播放';
    setRunState('已暂停', '#fbbf24');
  } else {
    play(false);
  }
}

function showVerdict() {
  const box = $('#verdict');
  const ok = state.payload.percolates;
  box.className = `verdict show ${ok ? 'ok' : 'bad'}`;
  box.textContent = ok ? '✔ 水已从顶端贯通到底端' : '✘ 未贯通：水被阻断';
}

function onGridHover(event) {
  const g = state.geom;
  const tip = $('#gridTip');
  if (!g || !state.payload) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const c = Math.round((x - g.ox) / g.cell);
  const r = Math.round((y - g.oy) / g.cell);
  if (r < 0 || c < 0 || r >= g.n || c >= g.n) { tip.classList.remove('show'); return; }
  const idx = r * g.n + c;
  const layer = state.nodeLayer ? state.nodeLayer[idx] : -1;
  const revealed = layer >= 0 && layer < state.shownLayers;
  tip.innerHTML = `节点 (${r}, ${c})<br>${revealed ? `第 ${layer} 层到达` : '尚未浸润'}`;
  tip.style.left = `${g.ox + c * g.cell}px`;
  tip.style.top = `${g.oy + r * g.cell}px`;
  tip.classList.add('show');
}

function setRunState(text, color) {
  const chip = $('#runState');
  if (!chip) return;
  chip.innerHTML = `<span class="dot" style="background:${color};box-shadow:0 0 10px ${color}"></span>${text}`;
}

/* --------------------------------------------------------- 指标与统计 */
function paintStats() {
  const info = state.payload;
  if (!info) return;
  $('#sP').textContent = fixed(info.p, 2);
  $('#sSize').innerHTML = `${info.size}×${info.size}<small>${info.nodeCount} 节点</small>`;
  $('#sDepth').innerHTML = `${state.shownLayers}<small>/ ${info.layers.length} 层</small>`;
  $('#sOpen').innerHTML = `${fixed(info.openRatio, 3)}<small>${info.openEdges}/${info.totalEdges}</small>`;
  const wetShown = state.shownLayers >= info.layers.length ? info.wetCount : 0;
  $('#sWet').innerHTML = wetShown
    ? `${wetShown}<small>${(info.wetRatio * 100).toFixed(1)}%</small>`
    : `—<small>播放结束后显示</small>`;

  const badge = $('#verdictBadge');
  const final = state.shownLayers >= info.layers.length;
  badge.className = `verdict-badge ${final ? (info.percolates ? 'ok' : 'bad') : ''}`;
  $('#verdictText').textContent = final ? (info.percolates ? '渗流出水 ✔' : '未贯通 ✘') : '渗透中…';
  $('#verdictNote').innerHTML = final
    ? `判定耗时 ${fixed(info.elapsedMs, 1)} ms<br>理论阈值 p_c = ${info.theoreticalPc}`
    : '正在逐层渲染';
}

/* --------------------------------------------- 6. 批量统计（分块 + 可中断） */
async function runBatch() {
  if (state.lock) return;
  const total = toNum(state.params.trials, 1000);
  const { size, p, directed, seed } = state.params;
  const token = ++state.token;
  state.lock = 'batch';
  lockButtons(true);
  $('#btnBatchStop').disabled = false;
  $('#bTotal').textContent = total;
  $('#bSuccess').textContent = '0';
  $('#bProb').textContent = '…';

  const chunk = clamp(Math.ceil(total / 40), 25, 400);
  let done = 0;
  let success = 0;
  const started = performance.now();
  setRunState(`批量统计 ${done}/${total}`, '#fbbf24');

  try {
    while (done < total) {
      if (token !== state.token) return;
      const k = Math.min(chunk, total - done);
      const payload = { trials: k, seed: seed >= 0 ? seed + done * 7919 : -1 };
      const res = await API.action(state.spec.key, 'batch', state.params, payload);
      if (!res.ok) throw new Error(res.error);
      success += res.result.success;
      done += k;
      $('#bSuccess').textContent = success;
      $('#bProb').textContent = fixed(success / done, 4);
      $('#batchBar').style.width = `${(done / total) * 100}%`;
      $('#batchNote').textContent = `已完成 ${done}/${total} 次 · 用时 ${fixed((performance.now() - started) / 1000, 1)} s`;
      setRunState(`批量统计 ${done}/${total}`, '#fbbf24');
      await nextFrame();
    }
    const prob = success / total;
    $('#bProb').innerHTML = `${fixed(prob, 4)}<small>${(prob * 100).toFixed(1)}%</small>`;
    $('#batchNote').textContent =
      `p = ${fixed(p, 2)} 时渗流概率 ≈ ${fixed(prob, 4)}（${success}/${total}），用时 ${fixed((performance.now() - started) / 1000, 2)} s`;
    toast(`统计完成：${success}/${total} 次贯通`, 'ok');
  } catch (err) {
    toast(`统计中断：${err.message}`, 'error');
  } finally {
    if (token === state.token) {
      state.lock = null;
      lockButtons(false);
      $('#btnBatchStop').disabled = true;
      setRunState('就绪', '#34d399');
    }
  }
}

async function runScan() {
  if (state.lock) return;
  const trials = toNum(state.params.scanTrials, 200);
  const step = toNum(state.params.scanStep, 0.05);
  const { size, directed, seed } = state.params;
  const token = ++state.token;
  state.lock = 'scan';
  lockButtons(true);
  $('#btnScanStop').disabled = false;

  const points = [];
  for (let i = 0; i * step <= 1 + 1e-9; i += 1) {
    points.push({ p: Math.round(i * step * 1000) / 1000, prob: null, success: 0, trials: 0 });
  }
  state.scan = points;
  drawChart();

  const chunk = clamp(Math.ceil(trials / 8), 20, 200);
  setRunState(`扫描曲线 0/${points.length}`, '#fbbf24');

  try {
    for (let i = 0; i < points.length; i += 1) {
      let done = 0;
      let success = 0;
      while (done < trials) {
        if (token !== state.token) return;
        const k = Math.min(chunk, trials - done);
        const payload = {
          trials: k,
          p: points[i].p,
          size,
          directed,
          seed: seed >= 0 ? seed + i * 104729 + done * 7919 : -1,
        };
        const res = await API.action(state.spec.key, 'batch', state.params, payload);
        if (!res.ok) throw new Error(res.error);
        success += res.result.success;
        done += k;
        points[i] = { p: points[i].p, success, trials: done, prob: success / done };
        state.scan = points;
        drawChart();
        $('#scanNote').textContent =
          `正在计算 p = ${fixed(points[i].p, 2)}（${done}/${trials} 次）· 已完成 ${i}/${points.length} 个点`;
        setRunState(`扫描 ${i + 1}/${points.length}`, '#fbbf24');
        await nextFrame();
      }
      $('#scanBar').style.width = `${((i + 1) / points.length) * 100}%`;
    }
    $('#scanNote').textContent = `完成：${points.length} 个 p 值，每点 ${trials} 次模拟（网格 ${size}×${size}）`;
    toast('P(p) 曲线绘制完成', 'ok');
  } catch (err) {
    toast(`扫描中断：${err.message}`, 'error');
  } finally {
    if (token === state.token) {
      state.lock = null;
      lockButtons(false);
      $('#btnScanStop').disabled = true;
      setRunState('就绪', '#34d399');
    }
  }
}

function lockButtons(locked) {
  ['#btnBatch', '#btnScan', '#btnPlay', '#btnReplay', '#btnInstant'].forEach((sel) => {
    const node = $(sel);
    if (node) node.disabled = locked;
  });
}

/* ------------------------------------------------------------ 曲线绘制 */
function drawChart() {
  const cv = $('#chart');
  if (!cv) return;
  const wrap = $('#chartWrap');
  const w = Math.max(wrap.clientWidth, 200);
  const h = Math.max(wrap.clientHeight, 160);
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.round(w * dpr);
  cv.height = Math.round(h * dpr);
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const padL = 42;
  const padR = 12;
  const padT = 16;
  const padB = 28;
  const x0 = padL;
  const x1 = w - padR;
  const y0 = h - padB;
  const y1 = padT;
  const X = (p) => x0 + p * (x1 - x0);
  const Y = (q) => y0 - q * (y0 - y1);

  ctx.font = '10px ui-monospace, Consolas, monospace';
  ctx.strokeStyle = 'rgba(255,255,255,.07)';
  ctx.fillStyle = '#66748f';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const q = i / 4;
    ctx.beginPath();
    ctx.moveTo(x0, Y(q));
    ctx.lineTo(x1, Y(q));
    ctx.stroke();
    ctx.textAlign = 'right';
    ctx.fillText(`${q * 100}%`, x0 - 8, Y(q) + 3.5);
  }
  for (let i = 0; i <= 5; i += 1) {
    const p = i / 5;
    ctx.beginPath();
    ctx.moveTo(X(p), y0);
    ctx.lineTo(X(p), y1);
    ctx.stroke();
    ctx.textAlign = 'center';
    ctx.fillText(p.toFixed(1), X(p), y0 + 15);
  }
  ctx.textAlign = 'left';
  ctx.fillText('P(p)', x0 - 34, y1 - 4);

  // 理论阈值线
  ctx.save();
  ctx.setLineDash([5, 5]);
  ctx.strokeStyle = 'rgba(251,113,133,.85)';
  ctx.beginPath();
  ctx.moveTo(X(0.5), y0);
  ctx.lineTo(X(0.5), y1);
  ctx.stroke();
  ctx.restore();
  ctx.fillStyle = 'rgba(251,113,133,.95)';
  ctx.fillText('p_c = 0.5', X(0.5) + 6, y1 + 10);

  const pts = state.scan.filter((d) => d.prob !== null && d.prob !== undefined);
  if (!pts.length) {
    ctx.fillStyle = '#66748f';
    ctx.textAlign = 'center';
    ctx.font = '11px system-ui, sans-serif';
    ctx.fillText('点击「扫描并绘制」开始计算', (x0 + x1) / 2, (y0 + y1) / 2);
    return;
  }

  // 面积填充
  const grad = ctx.createLinearGradient(0, y1, 0, y0);
  grad.addColorStop(0, 'rgba(56,189,248,.30)');
  grad.addColorStop(1, 'rgba(56,189,248,.02)');
  ctx.beginPath();
  ctx.moveTo(X(pts[0].p), y0);
  pts.forEach((d) => ctx.lineTo(X(d.p), Y(d.prob)));
  ctx.lineTo(X(pts[pts.length - 1].p), y0);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // 折线
  ctx.beginPath();
  pts.forEach((d, i) => (i ? ctx.lineTo(X(d.p), Y(d.prob)) : ctx.moveTo(X(d.p), Y(d.prob))));
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#38bdf8';
  ctx.shadowColor = 'rgba(56,189,248,.55)';
  ctx.shadowBlur = 9;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // 数据点
  pts.forEach((d) => {
    ctx.beginPath();
    ctx.arc(X(d.p), Y(d.prob), 3, 0, Math.PI * 2);
    ctx.fillStyle = '#0b1120';
    ctx.fill();
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = '#e9eefb';
    ctx.stroke();
  });

  // 悬停提示
  if (state.chartHover) {
    const d = state.chartHover;
    const px = X(d.p);
    const py = Y(d.prob);
    ctx.beginPath();
    ctx.arc(px, py, 6, 0, Math.PI * 2);
    ctx.strokeStyle = '#fde047';
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

function bindChartHover() {
  const cv = $('#chart');
  if (!cv) return;
  cv.addEventListener('mousemove', (event) => {
    const pts = state.scan.filter((d) => d.prob !== null && d.prob !== undefined);
    const tip = $('#chartTip');
    if (!pts.length) { tip.classList.remove('show'); state.chartHover = null; drawChart(); return; }
    const rect = cv.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const w = Math.max(cv.parentElement.clientWidth, 200);
    const padL = 42;
    const padR = 12;
    const p = clamp((x - padL) / ((w - padR) - padL), 0, 1);
    let best = pts[0];
    pts.forEach((d) => { if (Math.abs(d.p - p) < Math.abs(best.p - p)) best = d; });
    state.chartHover = best;
    drawChart();
    tip.innerHTML = `p = ${fixed(best.p, 2)}<br>渗流概率 ${fixed(best.prob, 4)}<br>样本 ${best.trials} 次`;
    tip.style.left = `${42 + best.p * ((w - padR) - padL)}px`;
    tip.style.top = `${16 + (1 - best.prob) * (cv.parentElement.clientHeight - 44)}px`;
    tip.classList.add('show');
  });
  cv.addEventListener('mouseleave', () => {
    state.chartHover = null;
    $('#chartTip').classList.remove('show');
    drawChart();
  });
}

/* --------------------------------------------- 5b. 通用回退视图（其它模型） */
function buildGenericView(spec) {
  const primary = spec.actions[0] || { key: 'run', label: '运行' };
  $('#colMid').innerHTML = `
    <div class="card">
      <header><h3>计算结果</h3><span class="sub">通用视图（该模型尚未提供专用渲染器）</span></header>
      <div class="body">
        <div class="btn-row"><button class="btn primary" id="btnGenericRun">${primary.label}</button></div>
        <div id="genericOut" style="margin-top:14px"></div>
      </div>
    </div>`;
  $('#btnGenericRun').addEventListener('click', async () => {
    const res = await API.action(spec.key, primary.key, state.params, {});
    const out = $('#genericOut');
    out.innerHTML = res.ok
      ? `<details class="raw" open><summary>返回结果（JSON）</summary><pre>${JSON.stringify(res.result, null, 2)}</pre></details>`
      : `<p class="muted">出错：${res.error}</p>`;
  });
}

/* ------------------------------------------------------------------ 启动 */
boot();
window.addEventListener('resize', debounce(() => { if ($('#chart')) drawChart(); }, 160));
