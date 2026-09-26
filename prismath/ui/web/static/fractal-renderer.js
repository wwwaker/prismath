/* Mandelbrot 的浏览器渲染器：低延迟 GPU 预览 + Python 高质量位图。 */
'use strict';

const FRACTAL_PALETTES = {
  magma: [[0, 0, 4], [252, 253, 191]],
  viridis: [[68, 1, 84], [253, 231, 37]],
  ice: [[12, 17, 24], [126, 231, 255]],
  heat: [[26, 11, 11], [255, 209, 102]],
};

let fractalGpu = null;

function drawFractal(payload) {
  const canvas = $('#fractalCanvas');
  if (!canvas) return;

  const cols = Number(payload.cols);
  const rows = Number(payload.rows);
  const values = payload.values;
  if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols < 1 || rows < 1) {
    throw new Error('返回的画布尺寸无效');
  }
  if (!values || values.length !== cols * rows) {
    throw new Error(`返回的像素数量无效：${values?.length || 0} / ${cols * rows}`);
  }

  const paletteParam = state.spec?.params?.find((param) => param.key === 'palette');
  const paletteIndex = paletteParam?.choices?.indexOf(state.params.palette) ?? 0;
  const paletteName = Object.keys(FRACTAL_PALETTES)[Math.max(0, paletteIndex)] || 'magma';
  const palette = FRACTAL_PALETTES[paletteName] || FRACTAL_PALETTES.magma;
  const levels = Math.max(2, Number(payload.levels) || 64);
  const pixels = new Uint8ClampedArray(cols * rows * 4);

  for (let index = 0; index < values.length; index += 1) {
    const level = clamp(Number(values[index]) || 0, 0, levels - 1);
    const amount = level / (levels - 1);
    const offset = index * 4;
    pixels[offset] = Math.round(palette[0][0] + (palette[1][0] - palette[0][0]) * amount);
    pixels[offset + 1] = Math.round(palette[0][1] + (palette[1][1] - palette[0][1]) * amount);
    pixels[offset + 2] = Math.round(palette[0][2] + (palette[1][2] - palette[0][2]) * amount);
    pixels[offset + 3] = 255;
  }

  canvas.width = cols;
  canvas.height = rows;
  const context = canvas.getContext('2d', { alpha: false });
  if (!context) throw new Error('当前浏览器不支持 2D 画布');
  context.putImageData(new ImageData(pixels, cols, rows), 0, 0);
  state.fractalImage = payload;
  updateFractalMetrics(payload);
}

function initFractalRenderer() {
  const canvas = $('#fractalGpuCanvas');
  if (!canvas) return;
  const gl = canvas.getContext('webgl2', { antialias: false, alpha: false });
  if (!gl) return;

  const vertex = `#version 300 es
    in vec2 aPosition;
    out vec2 vUv;
    void main() {
      vUv = aPosition * 0.5 + 0.5;
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }`;
  const fragment = `#version 300 es
    precision highp float;
    in vec2 vUv;
    uniform vec2 uCenter;
    uniform float uSpan;
    uniform float uAspect;
    uniform float uIterations;
    uniform vec3 uLow;
    uniform vec3 uHigh;
    out vec4 outColor;
    void main() {
      vec2 c = uCenter + vec2((vUv.x - 0.5) * uSpan,
                              (vUv.y - 0.5) * uSpan * uAspect);
      vec2 z = vec2(0.0);
      float escaped = 0.0;
      float smooth = 0.0;
      for (int i = 0; i < 2000; i += 1) {
        if (float(i) >= uIterations) break;
        float zx = z.x * z.x - z.y * z.y + c.x;
        float zy = 2.0 * z.x * z.y + c.y;
        z = vec2(zx, zy);
        float magnitude = dot(z, z);
        if (magnitude > 256.0) {
          escaped = 1.0;
          smooth = float(i) + 1.0 - log(log(sqrt(magnitude))) / log(2.0);
          break;
        }
      }
      if (escaped < 0.5) {
        outColor = vec4(uLow, 1.0);
      } else {
        float level = clamp(sqrt(max(smooth, 0.0) / max(uIterations, 1.0)), 0.0, 1.0);
        outColor = vec4(mix(uLow, uHigh, level), 1.0);
      }
    }`;

  const program = createFractalProgram(gl, vertex, fragment);
  if (!program) return;
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, 'aPosition');
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  fractalGpu = {
    canvas,
    gl,
    program,
    uniforms: {
      center: gl.getUniformLocation(program, 'uCenter'),
      span: gl.getUniformLocation(program, 'uSpan'),
      aspect: gl.getUniformLocation(program, 'uAspect'),
      iterations: gl.getUniformLocation(program, 'uIterations'),
      low: gl.getUniformLocation(program, 'uLow'),
      high: gl.getUniformLocation(program, 'uHigh'),
    },
  };
}

function createFractalProgram(gl, vertexSource, fragmentSource) {
  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  };
  const vertex = compile(gl.VERTEX_SHADER, vertexSource);
  const fragment = compile(gl.FRAGMENT_SHADER, fragmentSource);
  if (!vertex || !fragment) return null;
  const program = gl.createProgram();
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  return program;
}

function renderGpuPreview() {
  if (!fractalGpu || !state.spec || state.spec.view !== 'mandelbrot') return;
  const { canvas, gl, program, uniforms } = fractalGpu;
  const rect = $('#fractalStage').getBoundingClientRect();
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.round(rect.width * pixelRatio));
  canvas.height = Math.max(1, Math.round(rect.height * pixelRatio));
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.useProgram(program);

  const paletteParam = state.spec.params.find((param) => param.key === 'palette');
  const paletteIndex = paletteParam?.choices?.indexOf(state.params.palette) ?? 0;
  const paletteName = Object.keys(FRACTAL_PALETTES)[Math.max(0, paletteIndex)] || 'magma';
  const palette = FRACTAL_PALETTES[paletteName] || FRACTAL_PALETTES.magma;
  const low = palette[0].map((value) => value / 255);
  const high = palette[1].map((value) => value / 255);
  const span = Number(state.fractalImage?.span || 3.2) / (2 ** (Number(state.params.magnification) - Number(state.fractalImage?.magnification || 0)));
  const iterations = Number(state.params.iterations) > 0
    ? Number(state.params.iterations)
    : Math.min(2000, 200 * (2 ** (Math.max(Number(state.params.magnification), 0) / 2)));
  gl.uniform2f(uniforms.center, Number(state.params.center_x), Number(state.params.center_y));
  gl.uniform1f(uniforms.span, span);
  gl.uniform1f(uniforms.aspect, rect.height / Math.max(rect.width, 1));
  gl.uniform1f(uniforms.iterations, iterations);
  gl.uniform3fv(uniforms.low, low);
  gl.uniform3fv(uniforms.high, high);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
}

function showFractalPreview() {
  const stage = $('#fractalStage');
  if (!stage || !fractalGpu) return;
  stage.classList.add('previewing');
}

function hideFractalPreview() {
  const stage = $('#fractalStage');
  if (!stage) return;
  stage.classList.remove('previewing');
  $('#fractalCanvas').style.transform = '';
}
