'use strict';

window.Prismath = window.Prismath || {};
const PMApp = Prismath.app = {};
let activeEngine = null;

const engineFor = {
  fractal: Prismath.engines.fractal,
  life: Prismath.engines.life,
  buffon: Prismath.engines.buffon,
  percolation: Prismath.engines.percolation,
  nbody: Prismath.engines.nbody
};

const renderHome = () => {
  if (activeEngine) { activeEngine.destroy(); activeEngine = null; }
  document.body.style.removeProperty('--model-accent');
  PM.$('#topbarActions').innerHTML = '<span class="status-pill"><i></i>本地就绪</span>';
  PM.$('#view').innerHTML = `
    <section class="home">
      <div class="home-heading"><span class="eyebrow">数学实验目录</span><h1>从一个规则开始。</h1><p>选择一个模型，把参数变成画布上的变化。</p></div>
      <div class="model-index">${Prismath.catalog.map((model, index) => `<a class="index-row" href="#/model/${model.key}" style="--row-accent:${model.accent}"><span class="index-number">0${index + 1}</span><span class="index-symbol">${model.icon}</span><span class="index-copy"><strong>${model.name}</strong><small>${model.topic} · ${model.summary}</small></span><span class="index-tags">${model.tags.map((tag) => `<i>${tag}</i>`).join('')}</span><span class="index-arrow">↗</span></a>`).join('')}</div>
      <div class="home-note"><span>浏览器直接运行</span><span>拖动 / 播放 / 观察</span><span>六个模型</span></div>
    </section>`;
};

const renderModel = (key) => {
  const model = Prismath.modelByKey(key);
  if (!model) { location.hash = '#/'; return; }
  if (activeEngine) activeEngine.destroy();
  Prismath.studio.renderShell(model);
  activeEngine = engineFor[model.kind](model);
};

const route = () => { const match = /^#\/model\/([\w.-]+)/.exec(location.hash || ''); match ? renderModel(match[1]) : renderHome(); };

window.addEventListener('hashchange', route);
window.addEventListener('keydown', (event) => { if (event.key === 'Escape') { Prismath.studio.hide('controlDeck'); Prismath.studio.hide('studioGuide'); } });
route();
