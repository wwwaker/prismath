'use strict';

window.Prismath = window.Prismath || {};
const PMFractal = Prismath.engines = Prismath.engines || {};

PMFractal.fractal = (model) => {
  const canvas = Prismath.$('#stageCanvas');
  const stage = Prismath.$('#stage');
  const palettes = {
    magma: ['#120c16', '#ee8b56'], viridis: ['#172b2b', '#e3c94b'],
    ice: ['#102331', '#8ed6e4'], heat: ['#281319', '#f0bf63']
  };
  const state = { centerX: -0.5, centerY: 0, span: 3.2, iterations: 180, palette: 'magma', dragging: null };
  let gl = null;
  let program = null;
  let raf = 0;

  Prismath.studio.guide('先看边界', '暗部是没有逃逸的点，亮部是逃逸的点。把指针放到边界附近，再滚轮放大。');
  Prismath.studio.tools(`<button class="tool-button" data-fractal="reset">重置取景</button><button class="tool-button" data-fractal="zoom-in">放大</button><button class="tool-button" data-fractal="zoom-out">缩小</button>`);
  Prismath.studio.deck(`${Prismath.range('最大迭代', 'iterations', 40, 900, 10, state.iterations)}${Prismath.select('色带', 'palette', Object.keys(palettes).map((key) => ({ value: key, label: key })), state.palette)}<p class="control-note">迭代越高，边界细节越完整；拖动画布平移，滚轮围绕指针缩放。</p>`);

  const compile = (type, source) => { const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader); return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null; };
  const setupGL = () => {
    gl = canvas.getContext('webgl2', { antialias: false, alpha: false });
    if (!gl) return false;
    const vertex = compile(gl.VERTEX_SHADER, '#version 300 es\nin vec2 p; void main(){gl_Position=vec4(p,0.,1.);}');
    const fragment = compile(gl.FRAGMENT_SHADER, `#version 300 es
      precision highp float; uniform vec2 center; uniform vec2 resolution; uniform float span; uniform float aspect; uniform float iterations; uniform vec3 low; uniform vec3 high; out vec4 color;
      void main(){vec2 c=center+vec2((gl_FragCoord.x/resolution.x-.5)*span,(gl_FragCoord.y/resolution.y-.5)*span*aspect);vec2 z=vec2(0.);float escape=0.;float value=0.;for(int i=0;i<900;i++){if(float(i)>=iterations)break;z=vec2(z.x*z.x-z.y*z.y+c.x,2.*z.x*z.y+c.y);if(dot(z,z)>256.){escape=1.;value=float(i)-log2(log2(dot(z,z)))*.5;break;}}float t=escape*clamp(value/max(iterations,1.),0.,1.);color=vec4(mix(low,high,sqrt(t)),1.);}`);
    if (!vertex || !fragment) return false;
    program = gl.createProgram(); gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return false;
    const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'p'); gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    return true;
  };
  const color = (hex) => [parseInt(hex.slice(1, 3), 16) / 255, parseInt(hex.slice(3, 5), 16) / 255, parseInt(hex.slice(5, 7), 16) / 255];
  const draw = () => {
    if (!gl || !program) {
      drawCanvasFallback();
      return;
    }
    const width = stage.clientWidth; const height = stage.clientHeight; const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); gl.viewport(0, 0, canvas.width, canvas.height); gl.useProgram(program);
    gl.uniform2f(gl.getUniformLocation(program, 'center'), state.centerX, state.centerY); gl.uniform2f(gl.getUniformLocation(program, 'resolution'), canvas.width, canvas.height); gl.uniform1f(gl.getUniformLocation(program, 'span'), state.span); gl.uniform1f(gl.getUniformLocation(program, 'aspect'), height / Math.max(width, 1)); gl.uniform1f(gl.getUniformLocation(program, 'iterations'), state.iterations);
    gl.uniform3fv(gl.getUniformLocation(program, 'low'), color(palettes[state.palette][0])); gl.uniform3fv(gl.getUniformLocation(program, 'high'), color(palettes[state.palette][1])); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    Prismath.studio.metrics([['中心', `${state.centerX.toFixed(4)} ${state.centerY >= 0 ? '+' : '−'} ${Math.abs(state.centerY).toFixed(4)}i`], ['取景宽度', state.span.toExponential(2)], ['最大迭代', state.iterations], ['渲染', 'WebGL']]);
    Prismath.studio.readout(`中心 ${state.centerX.toFixed(4)} ${state.centerY >= 0 ? '+' : '−'} ${Math.abs(state.centerY).toFixed(4)}i · ×${(3.2 / state.span).toFixed(1)}`);
  };
  const drawCanvasFallback = () => {
    const width = Math.min(720, Math.max(280, stage.clientWidth)); const height = Math.min(520, Math.max(220, stage.clientHeight));
    const { ctx } = Prismath.resizeCanvas(canvas, width, height); const image = ctx.createImageData(width, height); const low = palettes[state.palette][0]; const high = palettes[state.palette][1];
    const rgb = (hex) => [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)]; const start = rgb(low); const end = rgb(high);
    for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
      const cx = state.centerX + (x / width - .5) * state.span; const cy = state.centerY + (y / height - .5) * state.span * height / width; let zx = 0; let zy = 0; let iteration = 0;
      while (zx * zx + zy * zy <= 256 && iteration < state.iterations) { const nextX = zx * zx - zy * zy + cx; zy = 2 * zx * zy + cy; zx = nextX; iteration += 1; }
      const amount = iteration === state.iterations ? 0 : Math.sqrt(iteration / state.iterations); const offset = (y * width + x) * 4; image.data[offset] = Math.round(start[0] + (end[0] - start[0]) * amount); image.data[offset + 1] = Math.round(start[1] + (end[1] - start[1]) * amount); image.data[offset + 2] = Math.round(start[2] + (end[2] - start[2]) * amount); image.data[offset + 3] = 255;
    }
    ctx.putImageData(image, 0, 0); Prismath.studio.metrics([['中心', `${state.centerX.toFixed(4)} ${state.centerY >= 0 ? '+' : '−'} ${Math.abs(state.centerY).toFixed(4)}i`], ['取景宽度', state.span.toExponential(2)], ['最大迭代', state.iterations], ['渲染', 'Canvas 2D']]); Prismath.studio.readout(`中心 ${state.centerX.toFixed(4)} ${state.centerY >= 0 ? '+' : '−'} ${Math.abs(state.centerY).toFixed(4)}i · ×${(3.2 / state.span).toFixed(1)}`);
  };
  const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); };
  const reset = () => { state.centerX = -0.5; state.centerY = 0; state.span = 3.2; schedule(); };
  Prismath.$('[data-fractal="reset"]').addEventListener('click', reset);
  Prismath.$('[data-fractal="zoom-in"]').addEventListener('click', () => { state.span *= .5; schedule(); });
  Prismath.$('[data-fractal="zoom-out"]').addEventListener('click', () => { state.span = Math.min(3.2, state.span * 2); schedule(); });
  Prismath.$$('.control-field [data-control="iterations"]').forEach((input) => input.addEventListener('input', (event) => { state.iterations = Number(event.target.value); Prismath.$('[data-value="iterations"]').value = state.iterations; schedule(); }));
  Prismath.$('[data-control="palette"]').addEventListener('change', (event) => { state.palette = event.target.value; schedule(); });
  canvas.addEventListener('wheel', (event) => { event.preventDefault(); const p = Prismath.pointerPosition(event, canvas); const beforeX = state.centerX + (p.x / p.width - .5) * state.span; const beforeY = state.centerY + (p.y / p.height - .5) * state.span * p.height / p.width; const factor = event.deltaY < 0 ? .55 : 1.8; state.span = Prismath.clamp(state.span * factor, 0.0000002, 3.2); state.centerX = beforeX - (p.x / p.width - .5) * state.span; state.centerY = beforeY - (p.y / p.height - .5) * state.span * p.height / p.width; schedule(); }, { passive: false });
  canvas.addEventListener('pointerdown', (event) => { const p = Prismath.pointerPosition(event, canvas); state.dragging = { x: p.x, y: p.y }; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener('pointermove', (event) => { if (!state.dragging) return; const p = Prismath.pointerPosition(event, canvas); state.centerX -= (p.x - state.dragging.x) / p.width * state.span; state.centerY -= (p.y - state.dragging.y) / p.height * state.span * p.height / p.width; state.dragging = p; schedule(); });
  canvas.addEventListener('pointerup', () => { state.dragging = null; });
  canvas.addEventListener('click', (event) => { if (state.dragging) return; const p = Prismath.pointerPosition(event, canvas); const x = state.centerX + (p.x / p.width - .5) * state.span; const y = state.centerY + (p.y / p.height - .5) * state.span * p.height / p.width; Prismath.studio.readout(`取样点 ${x.toFixed(6)} ${y >= 0 ? '+' : '−'} ${Math.abs(y).toFixed(6)}i`); });
  const resize = () => schedule();
  const observer = Prismath.observeResize(stage, resize);
  setupGL(); Prismath.$('#stageEmpty').hidden = true; draw();
  return { destroy: () => observer.disconnect() };
};
