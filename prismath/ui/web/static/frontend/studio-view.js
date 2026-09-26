'use strict';

window.Prismath = window.Prismath || {};
const PMStudio = Prismath.studio = {};

PMStudio.renderShell = (model) => {
  document.body.style.setProperty('--model-accent', model.accent);
  PM.$('#topbarActions').innerHTML = `<span class="status-pill"><i></i><span id="studioStatus">就绪</span></span><a class="top-link" href="#/">模型目录</a>`;
  PM.$('#view').innerHTML = `
    <section class="studio" data-kind="${model.kind}">
      <div class="studio-heading">
        <div class="heading-copy"><a class="back-link" href="#/">← 模型目录</a><div class="model-kicker"><span class="model-symbol">${model.icon}</span><span>${model.topic}</span></div><h1>${model.name}</h1><p>${model.summary}</p></div>
        <div class="heading-actions"><button class="outline-button" data-action="guide">观察提示</button><button class="solid-button" data-action="controls">调整参数</button></div>
      </div>
      <div class="stage-frame">
        <div class="stage-header"><span class="stage-label">实验画布</span><span class="stage-coordinate" id="stageReadout">拖动、点击或播放</span></div>
        <div class="stage" id="stage"><canvas id="stageCanvas"></canvas><div class="stage-empty" id="stageEmpty"><span>${model.icon}</span><b>正在准备画布</b></div><div class="stage-overlay" id="stageOverlay"></div></div>
        <div class="stage-footer"><div class="stage-tools" id="stageTools"></div><div class="stage-hint" id="stageHint">浏览器本地计算</div></div>
      </div>
      <div class="studio-metrics" id="studioMetrics"></div>
      <section class="studio-guide" id="studioGuide" hidden><div><span class="eyebrow">观察提示</span><h2 id="guideTitle">从画布开始</h2><p id="guideText">先观察整体，再改变一个参数，记录画面发生了什么。</p></div><button class="text-button" data-action="close-guide">收起</button></section>
      <section class="control-deck" id="controlDeck" hidden><div class="deck-heading"><div><span class="eyebrow">实验设置</span><h2>改变一个条件</h2></div><button class="text-button" data-action="close-controls">收起</button></div><div class="deck-controls" id="deckControls"></div></section>
    </section>`;
  PM.$('#stageEmpty').hidden = true;
  PM.$('[data-action="controls"]').addEventListener('click', () => PMStudio.toggle('controlDeck'));
  PM.$('[data-action="guide"]').addEventListener('click', () => PMStudio.toggle('studioGuide'));
  PM.$('[data-action="close-guide"]').addEventListener('click', () => PMStudio.hide('studioGuide'));
  PM.$('[data-action="close-controls"]').addEventListener('click', () => PMStudio.hide('controlDeck'));
};

PMStudio.toggle = (id) => PM.$(`#${id}`).toggleAttribute('hidden');
PMStudio.hide = (id) => { const element = PM.$(`#${id}`); if (element) element.hidden = true; };
PMStudio.metrics = (items) => {
  PM.$('#studioMetrics').innerHTML = items.map(([label, value, tone = '']) => `<div class="metric"><span>${label}</span><strong class="${tone}">${value}</strong></div>`).join('');
};
PMStudio.deck = (html) => { PM.$('#deckControls').innerHTML = html; PM.$('#controlDeck').hidden = true; };
PMStudio.guide = (title, text) => { PM.$('#guideTitle').textContent = title; PM.$('#guideText').textContent = text; };
PMStudio.tools = (html) => { PM.$('#stageTools').innerHTML = html; };
PMStudio.readout = (text) => { const element = PM.$('#stageReadout'); if (element) element.textContent = text; };
