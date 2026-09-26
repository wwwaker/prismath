'use strict';

window.Prismath = window.Prismath || {};
const PM = Prismath;

PM.$ = (selector, root = document) => root.querySelector(selector);
PM.$$ = (selector, root = document) => [...root.querySelectorAll(selector)];
PM.clamp = (value, min, max) => Math.min(max, Math.max(min, value));
PM.number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
PM.escape = (value) => String(value).replace(/[&<>\"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
PM.seeded = (seed) => {
  let value = Number(seed);
  if (!Number.isFinite(value) || value < 0) return Math.random;
  value = (value >>> 0) || 1;
  return () => {
    value = (value * 1664525 + 1013904223) >>> 0;
    return value / 4294967296;
  };
};
PM.resizeCanvas = (canvas, width, height) => {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.round(width * ratio));
  canvas.height = Math.max(1, Math.round(height * ratio));
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, ratio, width, height };
};
PM.status = (text, tone = '') => {
  const element = PM.$('#studioStatus');
  if (!element) return;
  element.textContent = text;
  element.dataset.tone = tone;
};
PM.toast = (message, tone = '') => {
  const box = document.createElement('div');
  box.className = `toast ${tone}`;
  box.textContent = message;
  PM.$('#toasts').appendChild(box);
  setTimeout(() => box.remove(), 3600);
};
PM.format = (value, digits = 2) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—';
PM.range = (label, key, min, max, step, value) => `<label class="control-field"><span>${label}<output data-value="${key}">${value}</output></span><input type="range" data-control="${key}" min="${min}" max="${max}" step="${step}" value="${value}"></label>`;
PM.select = (label, key, options, value) => `<label class="control-field"><span>${label}</span><select data-control="${key}">${options.map((option) => `<option value="${option.value}" ${String(option.value) === String(value) ? 'selected' : ''}>${option.label}</option>`).join('')}</select></label>`;
PM.button = (label, key, tone = '') => `<button class="tool-button ${tone}" data-action="${key}">${label}</button>`;
PM.observeResize = (element, callback) => {
  const observer = new ResizeObserver(() => callback());
  observer.observe(element);
  return observer;
};
PM.pointerPosition = (event, canvas) => {
  const rect = canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top, width: rect.width, height: rect.height };
};
