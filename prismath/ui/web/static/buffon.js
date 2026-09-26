/* 蒲丰投针：几何实验页面。 */
'use strict';

function renderBuffonPage(spec) {
  state.spec = spec;
  state.params = {};
  spec.params.forEach((param) => { state.params[param.key] = param.default; });
  state.payload = null;
  state.buffonConvergence = null;

  setTopbar(`
    <span class="chip">${spec.topic}</span>
    <span class="chip" id="runState"><span class="dot"></span>准备实验</span>
    <a class="btn ghost" href="#/">返回模型集</a>`);

  $('#view').innerHTML = `
    <section class="model-head" style="--model-accent:${spec.accent}">
      <div class="icon">${spec.icon}</div>
      <div>
        <h1>${spec.name}</h1>
        <div class="meta"><span class="chip">概率与统计</span><span class="chip">随机几何</span></div>
        <div class="desc">${spec.summary}</div>
      </div>
    </section>
    <div class="workspace buffon-workspace">
      <div class="col col-left">
        <div class="card">
          <header><h3>实验参数</h3><span class="sub">调整后重新投针</span></header>
          <div class="body" id="paramBody"></div>
        </div>
        <div class="card">
          <header><h3>观察提示</h3></header>
          <div class="body"><p class="muted">命中表示针与平行线相交。投针数量越多，命中频率通常越接近理论值，π 的估计也会更稳定。</p></div>
        </div>
      </div>
      <div class="col col-mid">
        <div class="card canvas-card">
          <header><h3>随机投针</h3><span class="sub" id="buffonCanvasSub">等待生成</span></header>
          <div class="body"><div class="buffon-canvas-wrap"><canvas id="buffonCanvas" aria-label="蒲丰投针几何实验画布"></canvas></div></div>
          <div class="canvas-toolbar"><span class="muted" id="buffonNote">点击“投针一次”开始实验。</span><span class="spacer"></span><button class="btn primary" id="btnBuffonThrow">投针一次</button><button class="btn" id="btnBuffonConverge">观察收敛</button></div>
        </div>
      </div>
      <div class="col col-right">
        <div class="card">
          <header><h3>本次结果</h3><span class="sub" id="buffonResultSub">尚未投掷</span></header>
          <div class="body"><div class="stats">
            <div class="stat"><div class="k">投针数 N</div><div class="v" id="buffonThrows">—</div></div>
            <div class="stat"><div class="k">命中数 H</div><div class="v" id="buffonHits">—</div></div>
            <div class="stat"><div class="k">实测命中率</div><div class="v" id="buffonHitRate">—</div></div>
            <div class="stat"><div class="k">理论命中率</div><div class="v" id="buffonTheoryRate">—</div></div>
            <div class="stat wide hero"><div class="k">π 的估计</div><div class="v" id="buffonPi">—</div></div>
          </div></div>
        </div>
        <div class="card">
          <header><h3>累计收敛</h3><span class="sub" id="buffonConvergeSub">尚未计算</span></header>
          <div class="body"><div class="chart-wrap buffon-chart-wrap"><canvas id="buffonChart"></canvas></div><p class="muted" id="buffonConvergeNote">重复多组实验，观察估计值如何靠近 π。</p></div>
        </div>
      </div>
    </div>`;

  buildParamControls(spec);
  $('#btnBuffonThrow').addEventListener('click', () => renderBuffonAction('throw'));
  $('#btnBuffonConverge').addEventListener('click', () => renderBuffonAction('converge'));
  renderBuffonAction('throw');
}

async function renderBuffonAction(action) {
  const button = action === 'throw' ? $('#btnBuffonThrow') : $('#btnBuffonConverge');
  if (button) button.disabled = true;
  setRunState('计算中…', '#a2671b');
  try {
    const response = await API.action(state.spec.key, action, state.params, {});
    if (!response.ok) throw new Error(response.error || '接口异常');
    if (action === 'throw') {
      state.payload = response.result;
      drawBuffonNeedles(state.payload);
      updateBuffonResult(state.payload);
    } else {
      state.buffonConvergence = response.result;
      drawBuffonConvergence(state.buffonConvergence);
      const result = state.buffonConvergence;
      $('#buffonConvergeSub').textContent = `${result.repeats} 组 · ${result.totalThrows} 根针`;
      $('#buffonConvergeNote').textContent = result.piEstimate == null
        ? '本次累计没有命中，暂时无法反解 π。'
        : `累计估计 π ≈ ${Number(result.piEstimate).toFixed(6)}，标准误 ${Number(result.stderr || 0).toFixed(5)}`;
    }
    setRunState('已就绪', '#287653');
  } catch (error) {
    toast(`实验失败：${error.message}`, 'error');
    setRunState('实验失败', '#b34d4d');
  } finally {
    if (button) button.disabled = false;
  }
}

function drawBuffonNeedles(payload) {
  const canvas = $('#buffonCanvas');
  if (!canvas) return;
  const wrap = canvas.parentElement;
  const width = Math.max(320, Math.round(wrap.clientWidth));
  const height = Math.max(300, Math.round(width * Number(payload.height) / Number(payload.width)));
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.aspectRatio = `${payload.width} / ${payload.height}`;
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.fillStyle = '#fffdf8';
  context.fillRect(0, 0, width, height);
  const scaleX = width / Number(payload.width);
  const scaleY = height / Number(payload.height);
  context.strokeStyle = '#d5cdbf';
  context.lineWidth = 1;
  for (let y = 0; y <= Number(payload.height); y += Number(payload.gap)) {
    context.beginPath();
    context.moveTo(0, y * scaleY);
    context.lineTo(width, y * scaleY);
    context.stroke();
  }
  const xs = payload.xs || [];
  const ys = payload.ys || [];
  const thetas = payload.thetas || [];
  const mask = payload.hitsMask || '';
  const half = Number(payload.length) / 2;
  for (let index = 0; index < xs.length; index += 1) {
    const x = Number(xs[index]) * scaleX;
    const y = Number(ys[index]) * scaleY;
    const theta = Number(thetas[index]);
    const dx = half * Math.cos(theta) * scaleX;
    const dy = half * Math.sin(theta) * scaleY;
    context.strokeStyle = mask[index] === '1' ? '#a9552d' : '#2e6977';
    context.lineWidth = xs.length > 5000 ? 0.7 : 1.1;
    context.beginPath();
    context.moveTo(x - dx, y - dy);
    context.lineTo(x + dx, y + dy);
    context.stroke();
  }
  $('#buffonCanvasSub').textContent = `${payload.throws} 根针 · ${payload.hits} 根命中`;
  $('#buffonNote').textContent = `橙色为命中，蓝绿色为未命中 · 耗时 ${Number(payload.elapsedMs).toFixed(1)} ms`;
}

function updateBuffonResult(payload) {
  $('#buffonThrows').textContent = payload.throws;
  $('#buffonHits').textContent = payload.hits;
  $('#buffonHitRate').textContent = `${(Number(payload.hitRate) * 100).toFixed(2)}%`;
  $('#buffonTheoryRate').textContent = `${(Number(payload.theoryRate) * 100).toFixed(2)}%`;
  $('#buffonPi').textContent = payload.piEstimate == null ? '—' : Number(payload.piEstimate).toFixed(6);
  $('#buffonResultSub').textContent = payload.piEstimate == null ? '命中数不足' : `误差 ${Number(payload.absError).toFixed(5)}`;
}

function drawBuffonConvergence(payload) {
  const canvas = $('#buffonChart');
  if (!canvas) return;
  const wrap = canvas.parentElement;
  const width = Math.max(280, wrap.clientWidth);
  const height = Math.max(220, wrap.clientHeight);
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  const points = (payload.samples || []).filter((sample) => sample.estimate != null);
  if (!points.length) return;
  const pad = { left: 42, right: 12, top: 16, bottom: 28 };
  const values = points.map((point) => Number(point.estimate));
  const min = Math.min(3.0, ...values, Number(payload.piTrue)) - 0.08;
  const max = Math.max(3.3, ...values, Number(payload.piTrue)) + 0.08;
  const x = (index) => pad.left + index / Math.max(1, points.length - 1) * (width - pad.left - pad.right);
  const y = (value) => pad.top + (max - value) / (max - min) * (height - pad.top - pad.bottom);
  context.strokeStyle = '#d5cdbf';
  context.lineWidth = 1;
  [min, Number(payload.piTrue), max].forEach((value) => {
    context.beginPath();
    context.moveTo(pad.left, y(value));
    context.lineTo(width - pad.right, y(value));
    context.stroke();
  });
  context.fillStyle = '#78817f';
  context.font = '11px ui-monospace, monospace';
  context.fillText('π', 10, y(Number(payload.piTrue)) - 4);
  context.strokeStyle = '#a9552d';
  context.lineWidth = 2;
  context.beginPath();
  points.forEach((point, index) => {
    const px = x(index);
    const py = y(Number(point.estimate));
    if (!index) context.moveTo(px, py); else context.lineTo(px, py);
  });
  context.stroke();
  context.fillStyle = '#a9552d';
  points.forEach((point, index) => context.fillRect(x(index) - 2, y(Number(point.estimate)) - 2, 4, 4));
  context.fillStyle = '#78817f';
  context.fillText('累计投针数', width / 2 - 28, height - 6);
}

registerWebRenderer('buffon_needle', renderBuffonPage);
