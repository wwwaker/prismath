'use strict';

window.Prismath = window.Prismath || {};
const PMPercolation = Prismath.engines = Prismath.engines || {};

PMPercolation.percolation = (model) => {
  const canvas = Prismath.$('#stageCanvas');
  const stage = Prismath.$('#stage');
  const state = { rows: 30, cols: 30, probability: model.site ? .6 : .58, site: !!model.site, occupied: null, horizontal: null, vertical: null, distance: null, layers: [], shown: 0, running: false, timer: 0, speed: 35, showBlocked: true };
  const nodeIndex = (row, col) => row * state.cols + col;
  const edgeHIndex = (row, col) => row * (state.cols - 1) + col;
  const edgeVIndex = (row, col) => row * state.cols + col;
  const neighbors = (row, col, callback) => { if (row > 0) callback(row - 1, col); if (row + 1 < state.rows) callback(row + 1, col); if (col > 0) callback(row, col - 1); if (col + 1 < state.cols) callback(row, col + 1); };
  const connection = (row, col, nextRow, nextCol) => state.site ? state.occupied[nodeIndex(row, col)] && state.occupied[nodeIndex(nextRow, nextCol)] : (row === nextRow ? state.horizontal[edgeHIndex(row, Math.min(col, nextCol))] : state.vertical[edgeVIndex(Math.min(row, nextRow), col)]);

  function make() {
    const random = Prismath.seeded(-1); const total = state.rows * state.cols;
    state.occupied = new Uint8Array(total); state.horizontal = new Uint8Array(state.rows * (state.cols - 1)); state.vertical = new Uint8Array((state.rows - 1) * state.cols);
    if (state.site) for (let index = 0; index < total; index += 1) state.occupied[index] = random() < state.probability ? 1 : 0;
    else { state.occupied.fill(1); state.horizontal.forEach((_, index) => { state.horizontal[index] = random() < state.probability ? 1 : 0; }); state.vertical.forEach((_, index) => { state.vertical[index] = random() < state.probability ? 1 : 0; }); }
    state.distance = new Int16Array(total).fill(-1); const queue = [];
    for (let col = 0; col < state.cols; col += 1) { const index = nodeIndex(0, col); if (state.occupied[index]) { state.distance[index] = 0; queue.push(index); } }
    state.layers = [];
    for (let head = 0; head < queue.length; head += 1) { const index = queue[head]; const row = Math.floor(index / state.cols); const col = index % state.cols; const layer = state.distance[index]; if (!state.layers[layer]) state.layers[layer] = []; state.layers[layer].push(index); neighbors(row, col, (nextRow, nextCol) => { const next = nodeIndex(nextRow, nextCol); if (state.distance[next] < 0 && connection(row, col, nextRow, nextCol)) { state.distance[next] = layer + 1; queue.push(next); } }); }
    state.shown = 0; state.running = false; clearTimeout(state.timer); draw();
  }

  function point(g, row, col) { return [g.ox + col * g.cell, g.oy + row * g.cell]; }
  function wet(index) { return state.distance[index] >= 0 && state.distance[index] < state.shown; }
  function wetColor(index) { return `hsl(${42 + state.distance[index] / Math.max(1, state.layers.length - 1) * 295} 66% 52%)`; }
  function drawEdge(context, g, row, col, nextRow, nextCol, open) {
    const index = nodeIndex(row, col); const next = nodeIndex(nextRow, nextCol); if (!open && !state.showBlocked) return;
    const [x, y] = point(g, row, col); const [nextX, nextY] = point(g, nextRow, nextCol); const active = open && wet(index) && wet(next);
    context.beginPath(); context.moveTo(x, y); context.lineTo(nextX, nextY); context.lineCap = 'round'; context.lineWidth = active ? Math.max(3, g.cell * .22) : Math.max(1, g.cell * .08); context.strokeStyle = active ? wetColor(next) : (open ? '#6f9694' : '#d2c8ba'); if (!open) context.setLineDash([Math.max(2, g.cell * .16), Math.max(3, g.cell * .18)]); context.stroke(); context.setLineDash([]);
  }
  function draw() {
    const { ctx, width, height } = Prismath.resizeCanvas(canvas, stage.clientWidth, stage.clientHeight); ctx.fillStyle = '#fbf8ef'; ctx.fillRect(0, 0, width, height);
    const pad = Math.min(width, height) * .11; const cell = Math.min((width - pad * 2) / Math.max(1, state.cols - 1), (height - pad * 2) / Math.max(1, state.rows - 1)); const g = { cell, ox: (width - cell * (state.cols - 1)) / 2, oy: (height - cell * (state.rows - 1)) / 2 };
    for (let row = 0; row < state.rows; row += 1) for (let col = 0; col < state.cols - 1; col += 1) drawEdge(ctx, g, row, col, row, col + 1, state.site ? Boolean(state.occupied[nodeIndex(row, col)] && state.occupied[nodeIndex(row, col + 1)]) : Boolean(state.horizontal[edgeHIndex(row, col)]));
    for (let row = 0; row < state.rows - 1; row += 1) for (let col = 0; col < state.cols; col += 1) drawEdge(ctx, g, row, col, row + 1, col, state.site ? Boolean(state.occupied[nodeIndex(row, col)] && state.occupied[nodeIndex(row + 1, col)]) : Boolean(state.vertical[edgeVIndex(row, col)]));
    for (let row = 0; row < state.rows; row += 1) for (let col = 0; col < state.cols; col += 1) { const index = nodeIndex(row, col); const [x, y] = point(g, row, col); const open = Boolean(state.occupied[index]); const isWet = wet(index); const radius = Math.max(2.4, Math.min(7, cell * .16)); ctx.beginPath(); ctx.arc(x, y, radius + (isWet ? 1.5 : 0), 0, Math.PI * 2); if (isWet) { ctx.fillStyle = wetColor(index); ctx.fill(); } else if (open) { ctx.fillStyle = state.site ? '#fffdf7' : '#6f9694'; ctx.fill(); ctx.strokeStyle = '#6f9694'; ctx.lineWidth = 1.2; ctx.stroke(); } else { ctx.fillStyle = '#fbf8ef'; ctx.fill(); ctx.strokeStyle = '#c9bfb0'; ctx.lineWidth = 1; ctx.stroke(); } }
    ctx.fillStyle = '#3974a3'; ctx.fillRect(g.ox - 4, g.oy - 23, cell * (state.cols - 1) + 8, 3); ctx.fillStyle = '#4b9b6d'; ctx.fillRect(g.ox - 4, g.oy + cell * (state.rows - 1) + 20, cell * (state.cols - 1) + 8, 3);
    const reached = Array.from({ length: state.cols }, (_, col) => state.distance[nodeIndex(state.rows - 1, col)] >= 0).some(Boolean); Prismath.studio.metrics([['概率 p', state.probability.toFixed(2)], ['网络规模', `${state.cols} × ${state.rows}`], ['已浸润层', `${Math.min(state.shown, state.layers.length)} / ${state.layers.length}`], ['结果', reached ? '贯通' : '未贯通']]); Prismath.studio.readout(`${state.site ? '点渗流' : '边渗流'} · ${reached ? '已找到贯通簇' : '观察连通结构'}`);
  }
  function play() { if (state.running) { state.running = false; return; } state.running = true; const tick = () => { if (!state.running) return; state.shown = Math.min(state.layers.length, state.shown + 1); draw(); if (state.shown < state.layers.length) state.timer = setTimeout(tick, Math.max(8, 150 - state.speed * 2)); else state.running = false; }; tick(); }
  const controls = `${Prismath.range('开放概率 p', 'probability', .2, .9, .01, state.probability)}${Prismath.range('网络规模', 'size', 12, 58, 1, state.rows)}${Prismath.range('动画速度', 'speed', 1, 70, 1, state.speed)}<label class="toggle-field"><input type="checkbox" data-control="showBlocked" checked><span>显示阻断边</span></label><div class="control-actions">${Prismath.button('重新生成', 'generate', 'solid')}${Prismath.button('播放浸润', 'play')}${Prismath.button('立即完成', 'finish')}</div>`;
  Prismath.studio.deck(controls); Prismath.studio.tools('<span class="tool-label"><i class="legend-open"></i>开放边 <i class="legend-blocked"></i>阻断边 <i class="legend-wet"></i>浸润</span>'); Prismath.studio.guide('寻找贯通时刻', '先看网络本身，再播放浸润。开放边组成的连通簇，是否能从蓝色顶端抵达绿色底端？');
  Prismath.$('[data-control="probability"]').addEventListener('input', (event) => { state.probability = Number(event.target.value); Prismath.$('[data-value="probability"]').value = state.probability.toFixed(2); }); Prismath.$('[data-control="size"]').addEventListener('input', (event) => { state.rows = state.cols = Number(event.target.value); Prismath.$('[data-value="size"]').value = state.rows; }); Prismath.$('[data-control="speed"]').addEventListener('input', (event) => { state.speed = Number(event.target.value); Prismath.$('[data-value="speed"]').value = state.speed; }); Prismath.$('[data-control="showBlocked"]').addEventListener('change', (event) => { state.showBlocked = event.target.checked; draw(); }); Prismath.$('[data-action="generate"]').addEventListener('click', make); Prismath.$('[data-action="play"]').addEventListener('click', play); Prismath.$('[data-action="finish"]').addEventListener('click', () => { state.running = false; state.shown = state.layers.length; draw(); });
  const observer = Prismath.observeResize(stage, draw); make(); return { destroy: () => { state.running = false; clearTimeout(state.timer); observer.disconnect(); } };
};
