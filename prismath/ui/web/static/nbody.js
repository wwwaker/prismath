/* N 体模型：轨道、回放与守恒量诊断。 */
'use strict';

function renderNBodyPage(spec) {
  state.spec = spec;
  state.params = {};
  spec.params.forEach((param) => { state.params[param.key] = param.default; });
  state.payload = null;
  state.nbodyFrame = 0;
  state.nbodyPlaying = false;

  setTopbar(`
    <span class="chip">${spec.topic}</span>
    <span class="chip" id="runState"><span class="dot"></span>准备模拟</span>
    <a class="btn ghost" href="#/">返回模型集</a>`);

  $('#view').innerHTML = `
    <section class="model-head" style="--model-accent:${spec.accent}">
      <div class="icon">${spec.icon}</div>
      <div><h1>${spec.name}</h1><div class="meta"><span class="chip">轨道动力学</span><span class="chip">守恒量诊断</span></div><div class="desc">${spec.summary}</div></div>
    </section>
    <div class="workspace nbody-workspace">
      <div class="col col-left">
        <div class="card"><header><h3>模拟参数</h3><span class="sub">重新开始后生效</span></header><div class="body" id="paramBody"></div></div>
        <div class="card"><header><h3>观察提示</h3></header><div class="body"><p class="muted">先看轨道的整体形状，再观察能量漂移。规则没有改变，复杂性来自星体数量和初始条件。</p></div></div>
      </div>
      <div class="col col-mid">
        <div class="card canvas-card"><header><h3>轨道画布</h3><span class="sub" id="nbodyCanvasSub">等待模拟</span></header><div class="body"><div class="nbody-canvas-wrap"><canvas id="nbodyCanvas" aria-label="万有引力多星轨道画布"></canvas></div></div><div class="canvas-toolbar"><span class="muted" id="nbodyNote">点击“开始模拟”生成轨道。</span><span class="spacer"></span><button class="btn primary" id="btnNBodyRun">开始模拟</button><button class="btn" id="btnNBodyPlay" disabled>播放</button><button class="btn" id="btnNBodyStop" disabled>停止</button></div></div>
      </div>
      <div class="col col-right">
        <div class="card"><header><h3>诊断</h3><span class="sub" id="nbodyResultSub">尚未模拟</span></header><div class="body"><div class="stats"><div class="stat"><div class="k">当前时间</div><div class="v" id="nbodyTime">—</div></div><div class="stat"><div class="k">星体数</div><div class="v" id="nbodyCount">—</div></div><div class="stat"><div class="k">能量相对漂移</div><div class="v" id="nbodyDrift">—</div></div><div class="stat"><div class="k">最大半径</div><div class="v" id="nbodyRadius">—</div></div><div class="stat wide"><div class="k">状态</div><div class="v" id="nbodyStatus">—</div></div></div></div></div>
        <div class="card"><header><h3>能量曲线</h3><span class="sub">数值积分质量</span></header><div class="body"><div class="chart-wrap nbody-chart-wrap"><canvas id="nbodyChart"></canvas></div><p class="muted" id="nbodyChartNote">模拟后显示能量漂移。</p></div></div>
      </div>
    </div>`;

  buildParamControls(spec);
  $('#btnNBodyRun').addEventListener('click', renderNBody);
  $('#btnNBodyPlay').addEventListener('click', playNBody);
  $('#btnNBodyStop').addEventListener('click', stopNBody);
  renderNBody();
}

async function renderNBody() {
  stopNBody();
  const button = $('#btnNBodyRun');
  if (button) button.disabled = true;
  setRunState('计算中…', '#a2671b');
  try {
    const response = await API.action(state.spec.key, 'simulate', state.params, {});
    if (!response.ok) throw new Error(response.error || '接口异常');
    state.payload = response.result;
    state.nbodyFrame = 0;
    drawNBodyFrame();
    drawNBodyChart();
    $('#btnNBodyPlay').disabled = state.payload.frames.length < 2;
    setRunState('已就绪', '#287653');
  } catch (error) {
    toast(`模拟失败：${error.message}`, 'error');
    setRunState('模拟失败', '#b34d4d');
  } finally {
    if (button) button.disabled = false;
  }
}

function nbodyBounds(payload) {
  const extent = payload.extent || [-1, 1, -1, 1];
  return { x0: Number(extent[0]), x1: Number(extent[1]), y0: Number(extent[2]), y1: Number(extent[3]) };
}

function drawNBodyFrame() {
  const payload = state.payload;
  const canvas = $('#nbodyCanvas');
  if (!payload || !canvas) return;
  const wrap = canvas.parentElement;
  const width = Math.max(360, Math.round(wrap.clientWidth));
  const height = Math.max(340, Math.round(width * 0.68));
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); canvas.style.aspectRatio = '16 / 11';
  const context = canvas.getContext('2d'); context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.fillStyle = '#121b22'; context.fillRect(0, 0, width, height);
  const bounds = nbodyBounds(payload); const spanX = Math.max(1e-9, bounds.x1 - bounds.x0); const spanY = Math.max(1e-9, bounds.y1 - bounds.y0);
  const frames = payload.frames || []; const positions = frames[state.nbodyFrame] || [];
  const px = (value) => (Number(value) - bounds.x0) / spanX * width;
  const py = (value) => height - (Number(value) - bounds.y0) / spanY * height;
  const count = Number(payload.count || positions.length / 2);
  const colors = ['#d9784a', '#69b8c0', '#e3b35d', '#b89ad9', '#e8e4d4', '#9bbd78'];
  if (payload.trails) {
    context.strokeStyle = '#ffffff22'; context.lineWidth = 1;
    payload.trails.forEach((trail) => { context.beginPath(); trail.forEach((point, index) => { const x = px(point[0]); const y = py(point[1]); if (!index) context.moveTo(x, y); else context.lineTo(x, y); }); context.stroke(); });
  }
  for (let index = 0; index < count; index += 1) {
    const x = px(positions[index * 2]); const y = py(positions[index * 2 + 1]);
    const mass = Number(payload.masses?.[index] || 1); const radius = Math.max(3, Math.min(10, 3 + Math.sqrt(mass) * 3));
    context.fillStyle = colors[index % colors.length]; context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fill();
  }
  const sample = payload.samples?.[Math.min(payload.samples.length - 1, Math.floor(state.nbodyFrame / Math.max(1, frames.length - 1) * (payload.samples.length - 1)))];
  $('#nbodyCanvasSub').textContent = `第 ${state.nbodyFrame + 1} / ${frames.length} 帧 · ${count} 颗星`;
  $('#nbodyTime').textContent = sample ? Number(sample.t).toFixed(3) : Number(payload.time || 0).toFixed(3);
  $('#nbodyCount').textContent = count;
  $('#nbodyDrift').textContent = sample ? Number(sample.drift).toExponential(2) : Number(payload.energyDrift || 0).toExponential(2);
  $('#nbodyRadius').textContent = sample ? Number(sample.maxRadius).toFixed(3) : Number(payload.maxRadius || 0).toFixed(3);
  $('#nbodyStatus').textContent = payload.blownUp ? '数值爆炸：请减小 dt 或增大 ε' : (state.nbodyFrame >= frames.length - 1 ? '模拟完成' : '播放中');
  $('#nbodyNote').textContent = `场景：${payload.scenarioName || payload.scenario} · 时间步长 dt = ${Number(payload.dt).toFixed(4)}`;
}

function playNBody() {
  if (!state.payload || state.nbodyPlaying) return;
  if (state.nbodyFrame >= state.payload.frames.length - 1) state.nbodyFrame = 0;
  state.nbodyPlaying = true; $('#btnNBodyPlay').disabled = true; $('#btnNBodyStop').disabled = false; setRunState('播放中', '#2e6977');
  const tick = () => {
    if (!state.nbodyPlaying || !state.payload) return;
    drawNBodyFrame();
    if (state.nbodyFrame >= state.payload.frames.length - 1) { stopNBody(); setRunState('已播放完', '#287653'); return; }
    state.nbodyFrame += 1; state.nbodyRaf = setTimeout(() => requestAnimationFrame(tick), 60);
  };
  requestAnimationFrame(tick);
}

function stopNBody() {
  state.nbodyPlaying = false;
  if (state.nbodyRaf) clearTimeout(state.nbodyRaf);
  state.nbodyRaf = 0;
  if ($('#btnNBodyStop')) $('#btnNBodyStop').disabled = true;
  if ($('#btnNBodyPlay')) $('#btnNBodyPlay').disabled = !state.payload || state.payload.frames.length < 2;
}

function drawNBodyChart() {
  const payload = state.payload; const canvas = $('#nbodyChart');
  if (!payload || !canvas) return;
  const wrap = canvas.parentElement; const width = Math.max(280, wrap.clientWidth); const height = Math.max(220, wrap.clientHeight); const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); const context = canvas.getContext('2d'); context.setTransform(ratio, 0, 0, ratio, 0, 0); context.clearRect(0, 0, width, height);
  const points = payload.samples || []; if (!points.length) return;
  const pad = { left: 48, right: 12, top: 14, bottom: 28 }; const max = Math.max(1e-12, ...points.map((point) => Math.abs(Number(point.drift)))); const x = (index) => pad.left + index / Math.max(1, points.length - 1) * (width - pad.left - pad.right); const y = (value) => pad.top + (1 - (Number(value) + max) / (2 * max)) * (height - pad.top - pad.bottom);
  context.strokeStyle = '#d5cdbf'; context.beginPath(); context.moveTo(pad.left, y(0)); context.lineTo(width - pad.right, y(0)); context.stroke(); context.strokeStyle = '#a9552d'; context.lineWidth = 2; context.beginPath(); points.forEach((point, index) => { const px = x(index); const py = y(Number(point.drift)); if (!index) context.moveTo(px, py); else context.lineTo(px, py); }); context.stroke();
  context.fillStyle = '#78817f'; context.font = '11px ui-monospace, monospace'; context.fillText(`±${max.toExponential(1)}`, 4, 12); context.fillText('时间', width / 2 - 14, height - 6); $('#nbodyChartNote').textContent = `${points.length} 个诊断采样点 · 最大相对漂移 ${Number(payload.maxDrift || 0).toExponential(2)}`;
}

registerWebRenderer('n_body', renderNBodyPage);
