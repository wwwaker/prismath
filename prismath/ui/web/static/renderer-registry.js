/* Web 模型渲染器注册表。主应用只按 view 查找，不持有模型分支。 */
'use strict';

const WEB_RENDERERS = new Map();

function registerWebRenderer(view, render) {
  if (!view || typeof render !== 'function') {
    throw new TypeError('Web 渲染器必须提供 view 和 render 函数');
  }
  if (WEB_RENDERERS.has(view)) {
    throw new Error(`重复注册 Web 渲染器：${view}`);
  }
  WEB_RENDERERS.set(view, render);
}

function getWebRenderer(view) {
  return WEB_RENDERERS.get(view) || null;
}
