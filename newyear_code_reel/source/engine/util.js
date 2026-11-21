/* 공용 도구 — 씨앗 고정 난수, 보간, 빛 조각(스프라이트), 글자 그림 보관.
   모든 프레임은 시각 t의 순수 함수여야 하므로 Math.random()·Date는 쓰지 않는다. */
'use strict';
(function () {
  const U = {};

  // ── 난수(씨앗 고정) ──
  U.rng = function (seed) {
    let s = (seed >>> 0) || 1;
    return function () {
      s = (s + 0x6D2B79F5) >>> 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  // 정수 두 개로 0..1 값 하나(프레임과 무관한 고정 잡음)
  U.hash = function (a, b) {
    let h = Math.imul((a | 0) ^ 0x9E3779B9, 0x85EBCA6B) ^ Math.imul((b | 0) + 0x7F4A7C15, 0xC2B2AE35);
    h ^= h >>> 15; h = Math.imul(h, 0x2C1B3C6D); h ^= h >>> 12; h = Math.imul(h, 0x297A2D39); h ^= h >>> 15;
    return (h >>> 0) / 4294967296;
  };

  // ── 보간 ──
  U.clamp = (x, a, b) => x < a ? a : (x > b ? b : x);
  U.clamp01 = x => x < 0 ? 0 : (x > 1 ? 1 : x);
  U.lerp = (a, b, t) => a + (b - a) * t;
  U.prog = (t, a, b) => U.clamp01((t - a) / (b - a));            // t가 a→b일 때 0→1
  U.smooth = x => { x = U.clamp01(x); return x * x * (3 - 2 * x); };
  U.easeOutCubic = x => { x = U.clamp01(x); return 1 - Math.pow(1 - x, 3); };
  U.easeOutQuint = x => { x = U.clamp01(x); return 1 - Math.pow(1 - x, 5); };
  U.easeInCubic = x => { x = U.clamp01(x); return x * x * x; };
  U.easeInOutCubic = x => { x = U.clamp01(x); return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
  U.easeOutBack = (x, s) => { x = U.clamp01(x); s = s == null ? 1.70158 : s; const y = x - 1; return 1 + (s + 1) * y * y * y + s * y * y; };
  U.easeOutElastic = x => {
    x = U.clamp01(x); if (x === 0 || x === 1) return x;
    return Math.pow(2, -10 * x) * Math.sin((x * 10 - 0.75) * (2 * Math.PI / 3)) + 1;
  };
  // 켜졌다가 꺼지는 봉우리: a에서 올라 b에 최대, c부터 내려 d에 0
  U.bump = (t, a, b, c, d) => Math.min(U.prog(t, a, b), 1 - U.prog(t, c, d));

  // ── 색 ──
  U.hexToRgb = function (hex) {
    if (hex[0] !== '#') {                       // 'rgb(r,g,b)' 꼴도 받는다(U.mix 결과를 다시 섞을 때)
      const m = hex.match(/(\d+(?:\.\d+)?)/g);
      return [Number(m[0]), Number(m[1]), Number(m[2])];
    }
    const h = hex.slice(1);
    const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  U.rgba = function (hex, a) { const c = U.hexToRgb(hex); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; };
  U.mix = function (h1, h2, t) {
    const a = U.hexToRgb(h1), b = U.hexToRgb(h2);
    const m = i => Math.round(a[i] + (b[i] - a[i]) * t);
    return `rgb(${m(0)},${m(1)},${m(2)})`;
  };

  // ── 빛 조각: 색마다 한 번만 그려 두고 drawImage로 찍는다(shadowBlur보다 수백 배 빠름) ──
  const glowCache = new Map();
  U.glow = function (color, core) {
    core = core == null ? 0.18 : core;
    const key = color + '|' + core;
    let c = glowCache.get(key);
    if (c) return c;
    const S = 128;
    c = document.createElement('canvas'); c.width = c.height = S;
    const g = c.getContext('2d');
    const [r, gg, b] = U.hexToRgb(color);
    const rg = g.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    rg.addColorStop(0, 'rgba(255,255,255,1)');
    rg.addColorStop(core * 0.6, `rgba(${Math.round((r + 255) / 2)},${Math.round((gg + 255) / 2)},${Math.round((b + 255) / 2)},0.95)`);
    rg.addColorStop(core, `rgba(${r},${gg},${b},0.62)`);
    rg.addColorStop(core + (1 - core) * 0.35, `rgba(${r},${gg},${b},0.2)`);
    rg.addColorStop(core + (1 - core) * 0.7, `rgba(${r},${gg},${b},0.05)`);
    rg.addColorStop(1, `rgba(${r},${gg},${b},0)`);
    g.fillStyle = rg; g.fillRect(0, 0, S, S);
    glowCache.set(key, c);
    return c;
  };
  // 빛 점 하나. size는 지름(px). 'lighter'로 겹쳐 찍는 것을 전제로 한다.
  U.dot = function (g, x, y, size, color, alpha, core) {
    if (alpha <= 0.003 || size <= 0) return;
    const prev = g.globalAlpha;                 // 찍고 나서 투명도를 되돌려 놓는다(뒤에 그리는 것이 흐려지지 않게)
    g.globalAlpha = alpha > 1 ? 1 : alpha;
    g.drawImage(U.glow(color, core), x - size / 2, y - size / 2, size, size);
    g.globalAlpha = prev;
  };

  // ── 화면 밖 그림판 보관(글자 번짐처럼 비싼 그림을 한 번만 그릴 때) ──
  const layerCache = new Map();
  U.layer = function (key, w, h, draw) {
    let c = layerCache.get(key);
    if (c) return c;
    c = document.createElement('canvas'); c.width = Math.ceil(w); c.height = Math.ceil(h);
    draw(c.getContext('2d'), c);
    layerCache.set(key, c);
    return c;
  };
  U.clearLayers = function () { layerCache.clear(); };

  U.roundRect = function (g, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    g.beginPath();
    g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.arcTo(x + w, y, x + w, y + r, r);
    g.lineTo(x + w, y + h - r); g.arcTo(x + w, y + h, x + w - r, y + h, r);
    g.lineTo(x + r, y + h); g.arcTo(x, y + h, x, y + h - r, r);
    g.lineTo(x, y + r); g.arcTo(x, y, x + r, y, r); g.closePath();
  };

  window.U = U;
})();
