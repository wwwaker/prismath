/* ------------------------------------------------- 5a.1 沉浸式连续场体验 */
function renderMandelbrotPage(spec) {
  state.spec = spec;
  state.params = {};
  spec.params.forEach((p) => { state.params[p.key] = p.default; });
  state.mode = spec.experience?.defaultMode || 'guided';
  state.guideStep = 0;
  state.guideActive = state.mode === 'guided';
  state.inspected = null;
  state.fractalImage = null;

  setTopbar(`
    <span class="experience-mode" id="modeLabel">${state.guideActive ? '引导模式' : '自由探索'}</span>
    <span class="run-indicator" id="runState"><i></i>准备中</span>
    <button class="btn quiet" id="btnConsole">控制台</button>
    <a class="btn quiet" href="#/">返回模型集</a>`);

  $('#view').innerHTML = `
    <section class="immersive-page" style="--model-accent:${spec.accent}">
      <div class="immersive-head">
        <div class="immersive-title">
          <span class="eyebrow">${spec.topic} / 交互实验</span>
          <h1>${spec.icon} ${spec.name}</h1>
          <p>在复平面中追踪逃逸时间，靠近边界，观察分形如何长出新的细节。</p>
        </div>
        <div class="immersive-actions">
          <button class="btn quiet" id="btnRestartGuide">重新开始引导</button>
          <button class="btn accent" id="btnExplore">进入自由探索</button>
        </div>
      </div>

      <div class="stage-shell">
        <div class="stage-toolbar">
          <div class="stage-status"><span class="status-mark"></span><span id="fractalStatus">正在准备第一幅图</span></div>
          <div class="stage-tools">
            <span class="coord-readout" id="coordReadout">中心 — · 放大 ×1</span>
            <button class="icon-btn" id="btnResetFractal" title="重置视图">↺</button>
            <button class="icon-btn" id="btnStageConsole" title="打开控制台">☷</button>
          </div>
        </div>
        <div class="fractal-stage" id="fractalStage">
          <canvas id="fractalGpuCanvas" aria-hidden="true"></canvas>
          <canvas id="fractalCanvas" aria-label="Mandelbrot 集交互画布"></canvas>
          <div class="stage-crosshair" id="stageCrosshair"></div>
          <div class="stage-help">拖动平移 · 滚轮缩放 · 点击查看点</div>
          <div class="inspector-card" id="fractalInspector" hidden></div>
          <div class="stage-loading" id="fractalLoading"><span></span><b>正在计算</b><small>先显示取景，再补齐细节</small></div>
        </div>
      </div>

      <div class="experience-row">
        <section class="guide-card" id="guideCard">
          <div class="guide-kicker"><span id="guideProgress">引导 1 / ${spec.experience?.guide?.length || 0}</span><button class="text-btn" id="btnSkipGuide">跳过</button></div>
          <h2 id="guideTitle">准备观察</h2>
          <p id="guidePrompt">正在载入当前取景。</p>
          <div class="guide-explanation" id="guideExplanation"></div>
          <div class="guide-footer"><span class="guide-line"><i id="guideLine"></i></span><button class="btn accent" id="btnGuideNext" disabled>下一步</button></div>
        </section>
        <section class="fact-strip">
          <div><span>当前中心</span><b id="metricCenter">—</b></div>
          <div><span>放大倍率</span><b id="metricZoom">×1</b></div>
          <div><span>集合内比例</span><b id="metricInside">—</b></div>
          <div><span>渲染耗时</span><b id="metricCost">—</b></div>
        </section>
      </div>

      <aside class="control-drawer" id="controlDrawer" aria-hidden="true">
        <div class="drawer-head"><div><span class="eyebrow">实验室</span><h2>取景与渲染</h2></div><button class="icon-btn" id="btnCloseConsole">×</button></div>
        <p class="drawer-note">控制台只改变实验参数，主画布仍然保持沉浸式。</p>
        <div id="paramBody"></div>
        <div class="drawer-actions"><button class="btn accent block" id="btnRenderFractal">应用并重绘</button><button class="btn quiet block" id="btnDrawerReset">恢复默认取景</button></div>
      </aside>
      <div class="drawer-scrim" id="drawerScrim"></div>
    </section>`;

  buildParamControls(spec);
  bindMandelbrotExperience();
  initFractalRenderer();
  updateGuideCard();
  renderMandelbrot();
}

function bindMandelbrotExperience() {
  $('#btnConsole').addEventListener('click', openConsole);
  $('#btnStageConsole').addEventListener('click', openConsole);
  $('#btnCloseConsole').addEventListener('click', closeConsole);
  $('#drawerScrim').addEventListener('click', closeConsole);
  $('#btnExplore').addEventListener('click', () => enterExplore());
  $('#btnSkipGuide').addEventListener('click', () => enterExplore());
  $('#btnRestartGuide').addEventListener('click', resetMandelbrotGuide);
  $('#btnGuideNext').addEventListener('click', () => emitGuideEvent('manual_next'));
  $('#btnResetFractal').addEventListener('click', resetMandelbrot);
  $('#btnDrawerReset').addEventListener('click', resetMandelbrot);
  $('#btnRenderFractal').addEventListener('click', () => { closeConsole(); renderMandelbrot(); });

  const canvas = $('#fractalCanvas');
  canvas.addEventListener('wheel', onFractalWheel, { passive: false });
  canvas.addEventListener('pointerdown', onFractalPointerDown);
  canvas.addEventListener('pointermove', onFractalPointerMove);
  canvas.addEventListener('pointerup', onFractalPointerUp);
  canvas.addEventListener('pointercancel', onFractalPointerUp);
  canvas.addEventListener('pointerleave', () => { if (!state.fractalPointer) $('#stageCrosshair').hidden = true; });
}

function openConsole() {
  const drawer = $('#controlDrawer');
  if (!drawer) return;
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  $('#drawerScrim').classList.add('show');
}

function closeConsole() {
  const drawer = $('#controlDrawer');
  if (!drawer) return;
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  $('#drawerScrim').classList.remove('show');
}

function enterExplore() {
  state.mode = 'explore';
  state.guideActive = false;
  updateGuideCard();
  const label = $('#modeLabel');
  if (label) label.textContent = '自由探索';
}

function resetMandelbrotGuide() {
  state.mode = 'guided';
  state.guideActive = true;
  state.guideStep = 0;
  state.inspected = null;
  updateGuideCard();
  const label = $('#modeLabel');
  if (label) label.textContent = '引导模式';
  resetMandelbrot();
}

function emitGuideEvent(event) {
  if (!state.guideActive || !state.spec?.experience?.guide) return false;
  const step = state.spec.experience.guide[state.guideStep];
  if (!step || step.completionEvent !== event) return false;
  state.guideStep += 1;
  if (state.guideStep >= state.spec.experience.guide.length) enterExplore();
  updateGuideCard();
  return true;
}

function updateGuideCard() {
  const card = $('#guideCard');
  if (!card || !state.spec) return;
  const steps = state.spec.experience?.guide || [];
  const step = state.guideActive ? steps[state.guideStep] : null;
  card.classList.toggle('explore', !state.guideActive);
  if (!step) {
    $('#guideProgress').textContent = '自由探索';
    $('#guideTitle').textContent = '现在轮到你了';
    $('#guidePrompt').textContent = '拖动、缩放，或者打开控制台调整迭代次数和色带。';
    $('#guideExplanation').textContent = '没有唯一正确的路径；选择一个局部结构，记录它和整体有什么相似之处。';
    $('#guideLine').style.width = '100%';
    $('#btnGuideNext').disabled = true;
    return;
  }
  $('#guideProgress').textContent = `引导 ${state.guideStep + 1} / ${steps.length}`;
  $('#guideTitle').textContent = step.title;
  $('#guidePrompt').textContent = step.prompt;
  $('#guideExplanation').textContent = step.explanation;
  $('#guideLine').style.width = `${(state.guideStep / steps.length) * 100}%`;
  $('#btnGuideNext').disabled = true;
}

function updateFractalMetrics(payload) {
  const center = `${Number(payload.centerX).toFixed(4)} ${Number(payload.centerY) >= 0 ? '+' : '−'} ${Math.abs(Number(payload.centerY)).toFixed(4)}i`;
  const zoom = `×${Number(payload.zoomFactor || 1).toFixed(Number(payload.zoomFactor || 1) < 10 ? 2 : 0)}`;
  $('#coordReadout').textContent = `中心 ${center} · 放大 ${zoom}`;
  $('#metricCenter').textContent = center;
  $('#metricZoom').textContent = zoom;
  $('#metricInside').textContent = `${(Number(payload.insideRatio || 0) * 100).toFixed(1)}%`;
  $('#metricCost').textContent = `${Number(payload.elapsedMs || 0).toFixed(1)} ms`;
}

async function renderMandelbrot(action = 'render') {
  if (!state.spec || state.spec.view !== 'mandelbrot') return;
  const token = ++state.token;
  setRunState('计算中…', '#f6c453');
  const loading = $('#fractalLoading');
  if (loading) loading.classList.toggle('show', !state.fractalImage);
  try {
    const res = await API.action(state.spec.key, action, state.params, fractalRenderRequest());
    if (token !== state.token) return;
    if (!res.ok) throw new Error(res.error);
    state.payload = res.result;
    drawFractal(state.payload);
    hideFractalPreview();
    if (action === 'render') emitGuideEvent('view_ready');
    const status = $('#fractalStatus');
    if (status) status.textContent = `${state.payload.sizeText} · ${state.payload.maxIter} 次迭代 · ${state.payload.paletteName}`;
    setRunState('已就绪', '#39d98a');
  } catch (err) {
    if (token !== state.token) return;
    const detail = err instanceof Error ? err.message : String(err);
    const status = $('#fractalStatus');
    if (status) status.textContent = `渲染失败：${detail}`;
    toast(`渲染失败：${detail}`, 'error');
    setRunState('渲染失败', '#ef6b73');
  } finally {
    if (token === state.token && loading) loading.classList.remove('show');
  }
}

function fractalRenderRequest() {
  const stage = $('#fractalStage');
  const width = Math.max(320, Math.min(1100, Math.round(stage?.clientWidth || 720)));
  const height = Math.max(240, Math.round(stage?.clientHeight || width * 0.68));
  return { pixels: width, aspect: height / width };
}

function scheduleFractalRender(delay = 160) {
  if (state.fractalRenderTimer) clearTimeout(state.fractalRenderTimer);
  state.fractalRenderTimer = setTimeout(() => {
    state.fractalRenderTimer = 0;
    renderMandelbrot();
  }, delay);
}

function resetMandelbrot() {
  if (!state.spec) return;
  state.spec.params.forEach((p) => {
    state.params[p.key] = p.default;
  });
  buildParamControls(state.spec);
  renderMandelbrot('reset_view');
}

function fractalPoint(event) {
  const canvas = $('#fractalCanvas');
  const rect = $('#fractalStage').getBoundingClientRect();
  const x = clamp(event.clientX - rect.left, 0, rect.width);
  const y = clamp(event.clientY - rect.top, 0, rect.height);
  const payload = state.fractalImage;
  if (!payload) return null;
  const worldX = Number(payload.centerX) + (x / rect.width - 0.5) * Number(payload.span);
  const worldY = Number(payload.centerY) + (y / rect.height - 0.5) * Number(payload.span) * Number(payload.rows) / Number(payload.cols);
  const col = Math.min(Number(payload.cols) - 1, Math.floor(x / rect.width * Number(payload.cols)));
  const row = Math.min(Number(payload.rows) - 1, Math.floor(y / rect.height * Number(payload.rows)));
  return { x, y, worldX, worldY, col, row, level: Number(payload.values[row * Number(payload.cols) + col] || 0) };
}

function showFractalInspector(point) {
  state.inspected = point;
  const box = $('#fractalInspector');
  if (!box) return;
  box.hidden = false;
  box.innerHTML = `<span class="inspector-label">当前点</span><strong>${point.worldX.toFixed(6)} ${point.worldY >= 0 ? '+' : '−'} ${Math.abs(point.worldY).toFixed(6)}i</strong><small>逃逸色阶 ${point.level} / 63</small>`;
  box.style.left = `${point.x}px`;
  box.style.top = `${point.y}px`;
  $('#stageCrosshair').hidden = false;
  $('#stageCrosshair').style.left = `${point.x}px`;
  $('#stageCrosshair').style.top = `${point.y}px`;
}

function onFractalPointerDown(event) {
  if (event.button !== 0) return;
  const point = fractalPoint(event);
  if (!point) return;
  event.currentTarget.setPointerCapture(event.pointerId);
  state.fractalPointer = { startX: event.clientX, startY: event.clientY, lastX: event.clientX, lastY: event.clientY, moved: false };
}

function onFractalPointerMove(event) {
  const pointer = state.fractalPointer;
  if (!pointer) return;
  const dx = event.clientX - pointer.lastX;
  const dy = event.clientY - pointer.lastY;
  if (Math.abs(event.clientX - pointer.startX) + Math.abs(event.clientY - pointer.startY) > 4) pointer.moved = true;
  pointer.lastX = event.clientX;
  pointer.lastY = event.clientY;
  if (!pointer.moved || !state.fractalImage) return;
  const totalX = event.clientX - pointer.startX;
  const totalY = event.clientY - pointer.startY;
  const rect = $('#fractalCanvas').getBoundingClientRect();
  state.params.center_x = Number(state.params.center_x) - dx / rect.width * Number(state.fractalImage.span);
  state.params.center_y = Number(state.params.center_y) - dy / rect.height * Number(state.fractalImage.span) * Number(state.fractalImage.rows) / Number(state.fractalImage.cols);
  $('#fractalStatus').textContent = '正在平移 · 松开后细化';
  $('#fractalCanvas').style.transform = `translate3d(${totalX}px, ${totalY}px, 0)`;
  showFractalPreview();
  renderGpuPreview();
}

function onFractalPointerUp(event) {
  const pointer = state.fractalPointer;
  if (!pointer) return;
  state.fractalPointer = null;
  const point = fractalPoint(event);
  if (!pointer.moved && point) {
    showFractalInspector(point);
    emitGuideEvent(state.guideStep === 2 ? 'boundary_inspected' : 'point_inspected');
  } else if (pointer.moved) {
    $('#fractalCanvas').style.transform = '';
    emitGuideEvent('navigated');
    renderMandelbrot();
  }
}

function onFractalWheel(event) {
  event.preventDefault();
  const point = fractalPoint(event);
  if (!point) return;
  const factor = event.deltaY < 0 ? 2 : 0.5;
  const nextMag = clamp(Number(state.params.magnification) + (factor > 1 ? 1 : -1), -24, 24);
  const nextSpan = Number(state.fractalImage.span) / factor;
  const rect = $('#fractalCanvas').getBoundingClientRect();
  state.params.center_x = point.worldX - (point.x / rect.width - 0.5) * nextSpan;
  state.params.center_y = point.worldY - (point.y / rect.height - 0.5) * nextSpan * Number(state.fractalImage.rows) / Number(state.fractalImage.cols);
  state.params.magnification = nextMag;
  $('#fractalCanvas').style.transform = '';
  emitGuideEvent('zoomed');
  showFractalPreview();
  renderGpuPreview();
  scheduleFractalRender();
}

registerWebRenderer('mandelbrot', renderMandelbrotPage);
