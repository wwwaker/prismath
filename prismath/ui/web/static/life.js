/* 生命游戏：可播放的棋盘实验。 */
'use strict';

function renderLifePage(spec) {
  state.spec = spec;
  state.params = {};
  spec.params.forEach((param) => { state.params[param.key] = param.default; });
  state.payload = null;
  state.lifeFrame = 0;
  state.lifePlaying = false;

  setTopbar(`
    <span class="chip">${spec.topic}</span>
    <span class="chip" id="runState"><span class="dot"></span>准备棋盘</span>
    <a class="btn ghost" href="#/">返回模型集</a>`);

  $('#view').innerHTML = `
    <section class="model-head" style="--model-accent:${spec.accent}">
      <div class="icon">${spec.icon}</div>
      <div>
        <h1>${spec.name}</h1>
        <div class="meta"><span class="chip">细胞自动机</span><span class="chip">逐代演化</span></div>
        <div class="desc">${spec.summary}</div>
      </div>
    </section>
    <div class="workspace life-workspace">
      <div class="col col-left">
        <div class="card">
          <header><h3>实验参数</h3><span class="sub">重新生成后生效</span></header>
          <div class="body" id="paramBody"></div>
        </div>
        <div class="card">
          <header><h3>怎么观察</h3></header>
          <div class="body"><p class="muted">先观察随机或预设图案，再播放演化。人口曲线能帮助你分辨：图案是在消失、稳定，还是进入周期振荡。</p></div>
        </div>
      </div>
      <div class="col col-mid">
        <div class="card canvas-card">
          <header><h3>演化棋盘</h3><span class="sub" id="lifeCanvasSub">等待生成</span></header>
          <div class="body"><div class="life-canvas-wrap"><canvas id="lifeCanvas" aria-label="生命游戏棋盘"></canvas></div></div>
          <div class="canvas-toolbar"><span class="muted" id="lifeNote">点击“生成演化”开始实验。</span><span class="spacer"></span><button class="btn primary" id="btnLifeRun">生成演化</button><button class="btn" id="btnLifePlay" disabled>播放</button><button class="btn" id="btnLifeStop" disabled>停止</button></div>
        </div>
      </div>
      <div class="col col-right">
        <div class="card">
          <header><h3>当前状态</h3><span class="sub" id="lifeResultSub">尚未生成</span></header>
          <div class="body"><div class="stats">
            <div class="stat"><div class="k">当前代数</div><div class="v" id="lifeGeneration">—</div></div>
            <div class="stat"><div class="k">存活细胞</div><div class="v" id="lifePopulation">—</div></div>
            <div class="stat"><div class="k">当前密度</div><div class="v" id="lifeDensity">—</div></div>
            <div class="stat wide"><div class="k">演化结局</div><div class="v" id="lifeOutcome">—</div></div>
          </div></div>
        </div>
        <div class="card">
          <header><h3>人口曲线</h3><span class="sub">每一代的存活数量</span></header>
          <div class="body"><div class="chart-wrap life-chart-wrap"><canvas id="lifeChart"></canvas></div><p class="muted" id="lifeChartNote">生成后显示人口变化。</p></div>
        </div>
      </div>
    </div>`;

  buildParamControls(spec);
  $('#btnLifeRun').addEventListener('click', renderLife);
  $('#btnLifePlay').addEventListener('click', playLife);
  $('#btnLifeStop').addEventListener('click', stopLife);
  renderLife();
}

async function renderLife() {
  stopLife();
  const runButton = $('#btnLifeRun');
  if (runButton) runButton.disabled = true;
  setRunState('计算中…', '#a2671b');
  try {
    const response = await API.action(state.spec.key, 'evolve', state.params, {});
    if (!response.ok) throw new Error(response.error || '接口异常');
    state.payload = response.result;
    state.lifeFrame = 0;
    drawLifeFrame();
    drawLifeChart();
    $('#btnLifePlay').disabled = state.payload.frames.length < 2;
    $('#btnLifeStop').disabled = true;
    setRunState('已就绪', '#287653');
  } catch (error) {
    toast(`演化失败：${error.message}`, 'error');
    setRunState('演化失败', '#b34d4d');
  } finally {
    if (runButton) runButton.disabled = false;
  }
}

function drawLifeFrame() {
  const payload = state.payload;
  const canvas = $('#lifeCanvas');
  if (!payload || !canvas) return;
  const wrap = canvas.parentElement;
  const width = Math.max(320, Math.round(wrap.clientWidth));
  const height = Math.max(320, Math.round(width * Number(payload.rows) / Number(payload.cols)));
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.aspectRatio = `${payload.cols} / ${payload.rows}`;
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.fillStyle = '#fffdf8';
  context.fillRect(0, 0, width, height);
  const cellWidth = width / Number(payload.cols);
  const cellHeight = height / Number(payload.rows);
  const cells = payload.frames[state.lifeFrame] || payload.cells || '';
  context.fillStyle = '#2e6977';
  for (let index = 0; index < cells.length; index += 1) {
    if (cells[index] !== '1') continue;
    const row = Math.floor(index / Number(payload.cols));
    const col = index % Number(payload.cols);
    context.fillRect(col * cellWidth + 0.5, row * cellHeight + 0.5, Math.max(1, cellWidth - 1), Math.max(1, cellHeight - 1));
  }
  if (cellWidth >= 7 && cellHeight >= 7) {
    context.strokeStyle = '#e3dbcf';
    context.lineWidth = 0.5;
    for (let col = 1; col < Number(payload.cols); col += 1) {
      context.beginPath(); context.moveTo(col * cellWidth, 0); context.lineTo(col * cellWidth, height); context.stroke();
    }
    for (let row = 1; row < Number(payload.rows); row += 1) {
      context.beginPath(); context.moveTo(0, row * cellHeight); context.lineTo(width, row * cellHeight); context.stroke();
    }
  }
  const census = payload.census?.[state.lifeFrame] || payload.census?.[payload.census.length - 1];
  const generation = census?.generation ?? state.lifeFrame;
  const population = census?.population ?? payload.population;
  $('#lifeCanvasSub').textContent = `第 ${generation} 代 · ${population} 个存活细胞`;
  $('#lifeGeneration').textContent = generation;
  $('#lifePopulation').textContent = population;
  $('#lifeDensity').textContent = `${(Number(population) / (Number(payload.rows) * Number(payload.cols)) * 100).toFixed(1)}%`;
  $('#lifeOutcome').textContent = state.lifeFrame >= payload.frames.length - 1 ? payload.outcomeLabel : '播放中';
}

function playLife() {
  if (!state.payload || state.lifePlaying) return;
  if (state.lifeFrame >= state.payload.frames.length - 1) state.lifeFrame = 0;
  state.lifePlaying = true;
  $('#btnLifePlay').disabled = true;
  $('#btnLifeStop').disabled = false;
  setRunState('播放中', '#2e6977');
  const tick = () => {
    if (!state.lifePlaying || !state.payload) return;
    drawLifeFrame();
    if (state.lifeFrame >= state.payload.frames.length - 1) {
      stopLife();
      setRunState('已播放完', '#287653');
      return;
    }
    state.lifeFrame += 1;
    state.lifeRaf = setTimeout(() => requestAnimationFrame(tick), 90);
  };
  requestAnimationFrame(tick);
}

function stopLife() {
  state.lifePlaying = false;
  if (state.lifeRaf) clearTimeout(state.lifeRaf);
  state.lifeRaf = 0;
  const stopButton = $('#btnLifeStop');
  const playButton = $('#btnLifePlay');
  if (stopButton) stopButton.disabled = true;
  if (playButton) playButton.disabled = !state.payload || state.payload.frames.length < 2;
}

function drawLifeChart() {
  const payload = state.payload;
  const canvas = $('#lifeChart');
  if (!payload || !canvas) return;
  const wrap = canvas.parentElement;
  const width = Math.max(280, wrap.clientWidth);
  const height = Math.max(220, wrap.clientHeight);
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  const points = (payload.census || []).map((item, index) => ({ generation: item.generation ?? index, population: item.population ?? item.alive ?? 0 }));
  if (!points.length) return;
  const pad = { left: 38, right: 12, top: 14, bottom: 28 };
  const max = Math.max(1, ...points.map((point) => Number(point.population)));
  const x = (index) => pad.left + index / Math.max(1, points.length - 1) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (1 - Number(value) / max) * (height - pad.top - pad.bottom);
  context.strokeStyle = '#d5cdbf';
  context.lineWidth = 1;
  [0, max].forEach((value) => { context.beginPath(); context.moveTo(pad.left, y(value)); context.lineTo(width - pad.right, y(value)); context.stroke(); });
  context.strokeStyle = '#2e6977';
  context.lineWidth = 2;
  context.beginPath();
  points.forEach((point, index) => { const px = x(index); const py = y(point.population); if (!index) context.moveTo(px, py); else context.lineTo(px, py); });
  context.stroke();
  context.fillStyle = '#78817f';
  context.font = '11px ui-monospace, monospace';
  context.fillText(String(max), 8, y(max) + 4);
  context.fillText('0', 22, y(0) + 4);
  context.fillText('代数', width / 2 - 14, height - 6);
  $('#lifeChartNote').textContent = `${points.length} 个时间点 · ${payload.outcomeText || '演化完成'}`;
}

registerWebRenderer('life_game', renderLifePage);
