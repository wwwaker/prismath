'use strict';

window.Prismath = window.Prismath || {};
const PMProbability = Prismath.engines = Prismath.engines || {};

PMProbability.buffon = (model) => {
  const canvas = Prismath.$('#stageCanvas'); const stage = Prismath.$('#stage');
  const state = { ratio: .8, throws: 700, seed: -1, result: null };
  const draw = () => {
    const { ctx, width, height } = Prismath.resizeCanvas(canvas, stage.clientWidth, stage.clientHeight); ctx.fillStyle = '#fbf8ef'; ctx.fillRect(0, 0, width, height); const gap = Math.max(46, Math.min(88, width / 8)); ctx.strokeStyle = '#d4c9b6'; ctx.lineWidth = 1; for (let x = gap; x < width; x += gap) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
    const result = state.result; if (!result) { Prismath.studio.readout('准备投针'); return; } const random = Prismath.seeded(state.seed); const length = state.ratio * gap; let hits = 0; ctx.lineCap = 'round'; for (let i = 0; i < state.throws; i += 1) { const x = random() * width; const y = random() * height; const theta = random() * Math.PI; const dx = Math.cos(theta) * length / 2; const dy = Math.sin(theta) * length / 2; const hit = Math.floor((x - dx) / gap) !== Math.floor((x + dx) / gap); if (hit) hits += 1; ctx.strokeStyle = hit ? '#bd563a' : model.accent; ctx.lineWidth = state.throws > 3000 ? .7 : 1.25; ctx.beginPath(); ctx.moveTo(x - dx, y - dy); ctx.lineTo(x + dx, y + dy); ctx.stroke(); }
    const pi = hits ? 2 * state.ratio * state.throws / hits : 0; Prismath.studio.metrics([['投针数', state.throws], ['命中数', hits], ['命中率', `${(hits / state.throws * 100).toFixed(2)}%`], ['π 估计', pi ? pi.toFixed(5) : '—']]); Prismath.studio.readout(`L / d = ${state.ratio.toFixed(2)} · ${hits} / ${state.throws} 命中`); state.result = { hits, pi };
  };
  const controls = `${Prismath.range('针长 / 线距', 'ratio', .1, 1, .05, state.ratio)}${Prismath.range('投针数', 'throws', 100, 3000, 100, state.throws)}<label class="control-field"><span>随机种子</span><input type="number" data-control="seed" value="-1"></label><div class="control-actions">${Prismath.button('投针一次', 'throw', 'solid')}${Prismath.button('换一组', 'reroll')}</div>`;
  Prismath.studio.deck(controls); Prismath.studio.tools('<span class="tool-label"><i class="legend-hit"></i>命中 <i class="legend-miss"></i>未命中</span>'); Prismath.studio.guide('看收敛，不看单次答案', '一次投掷的估计会摇摆；增加样本量，观察它如何围绕 π 波动。');
  Prismath.$('[data-control="ratio"]').addEventListener('input', (event) => { state.ratio = Number(event.target.value); Prismath.$('[data-value="ratio"]').value = state.ratio; }); Prismath.$('[data-control="throws"]').addEventListener('input', (event) => { state.throws = Number(event.target.value); Prismath.$('[data-value="throws"]').value = state.throws; }); Prismath.$('[data-control="seed"]').addEventListener('change', (event) => { state.seed = Number(event.target.value); }); Prismath.$('[data-action="throw"]').addEventListener('click', () => { state.result = {}; draw(); }); Prismath.$('[data-action="reroll"]').addEventListener('click', () => { state.seed = -1; state.result = {}; draw(); });
  const observer = Prismath.observeResize(stage, () => { if (state.result) draw(); }); state.result = {}; draw(); return { destroy: () => observer.disconnect() };
};
