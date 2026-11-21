/* 무대 효과 모음 — 전부 "시각 t → 그림"인 순수 함수(상태를 쌓지 않는다).
   입자 위치는 닫힌 식(저항 + 중력)으로 바로 계산하므로 어느 프레임부터 그려도 같은 그림이 나온다. */
'use strict';
(function () {
  const U = window.U;
  const Fx = {};
  const TAU = Math.PI * 2;

  // ───────────────────────── 하늘 ─────────────────────────
  Fx.sky = function (g, x0, w, h, lift) {
    // lift: 불꽃이 터질 때 하늘이 살짝 밝아지는 정도(0..1)
    const gr = g.createLinearGradient(0, 0, 0, h);
    gr.addColorStop(0.00, '#03051a');
    gr.addColorStop(0.30, '#07102e');
    gr.addColorStop(0.55, '#101d4d');
    gr.addColorStop(0.70, '#232a68');
    gr.addColorStop(0.765, '#3b3378');
    gr.addColorStop(0.80, '#4d3a7d');
    gr.addColorStop(1.00, '#2a2a66');
    g.fillStyle = gr; g.fillRect(x0, 0, w, h);
    if (lift > 0.003) { g.fillStyle = `rgba(70,80,160,${0.16 * lift})`; g.fillRect(x0, 0, w, h); }
  };

  const STAR_POOL = (function () {
    const r = U.rng(20261231), out = [];
    for (let i = 0; i < 600; i++) {
      out.push({ x: r(), y: Math.pow(r(), 1.25), s: 0.7 + Math.pow(r(), 4) * 2.6, ph: r() * TAU, sp: 0.7 + r() * 2.4, tint: r(), order: r() });
    }
    return out;
  })();
  // n개의 별. t0부터 하나씩 켜진다(켜지는 순간 살짝 반짝).
  Fx.stars = function (g, t, t0, n, x0, w, skyH, dimBy) {
    n = Math.max(0, Math.min(STAR_POOL.length, Math.round(n)));
    g.save(); g.globalCompositeOperation = 'lighter';
    for (let i = 0; i < n; i++) {
      const s = STAR_POOL[i];
      const born = t0 + s.order * 0.9;
      const age = t - born;
      if (age < 0) continue;
      const pop = 1 + 1.6 * U.bump(age, 0, 0.08, 0.1, 0.5);
      const tw = 0.62 + 0.38 * Math.sin(t * s.sp + s.ph);
      const a = U.clamp01(age / 0.25) * tw * (0.55 + 0.45 * Math.min(1, s.s / 2)) * (1 - (dimBy || 0));
      const col = s.tint < 0.15 ? '#ffd9a8' : (s.tint < 0.4 ? '#a9c8ff' : '#ffffff');
      const size = (5 + s.s * 5.5) * pop;
      U.dot(g, x0 + s.x * w, s.y * skyH, size, col, a, 0.22);
      if (s.s > 2.3) {                       // 큰 별은 십자 빛살
        const len = (9 + s.s * 6) * pop * (0.7 + 0.3 * tw);
        g.globalAlpha = a * 0.55; g.strokeStyle = '#ffffff'; g.lineWidth = 1.2;
        const sx = x0 + s.x * w, sy = s.y * skyH;
        g.beginPath(); g.moveTo(sx - len, sy); g.lineTo(sx + len, sy); g.moveTo(sx, sy - len); g.lineTo(sx, sy + len); g.stroke();
      }
    }
    g.restore(); g.globalAlpha = 1;
  };

  // ───────────────────────── 글자 조각 ─────────────────────────
  // 글자 하나를 작은 그림판에 그려 두고 찍는다(글자 세상에서 눈·별·흙덩이로 쓴다)
  const glyphCache = new Map();
  Fx.glyph = function (ch, px, color, weight) {
    const key = ch + '|' + px + '|' + color + '|' + (weight || 800);
    let c = glyphCache.get(key);
    if (c) return c;
    c = document.createElement('canvas'); const s = Math.ceil(px * 1.4); c.width = c.height = s;
    const g = c.getContext('2d');
    g.font = `${weight || 800} ${px}px "Pretendard", sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = color;
    g.fillText(ch, s / 2, s / 2 + px * 0.04);
    glyphCache.set(key, c);
    return c;
  };
  Fx.stamp = function (g, sprite, x, y, alpha) {
    if (alpha <= 0.003) return;
    const prev = g.globalAlpha; g.globalAlpha = alpha > 1 ? 1 : alpha;
    g.drawImage(sprite, x - sprite.width / 2, y - sprite.height / 2);
    g.globalAlpha = prev;
  };

  // ───────────────────────── 눈 ─────────────────────────
  // n송이. t0부터 위에서 차례로 내려온다(공중에서 갑자기 나타나지 않는다).
  const WORD_PX = [11, 12, 14, 17, 20, 25];              // 글자 눈송이 크기(먼 눈 → 가까운 눈)
  Fx.snow = function (g, t, t0, n, x0, w, h, opts) {
    opts = opts || {};
    const layerLo = opts.layerLo == null ? 0 : opts.layerLo, layerHi = opts.layerHi == null ? 1 : opts.layerHi;
    const fadeOut = opts.fade == null ? 1 : opts.fade;
    if (fadeOut <= 0) return;
    g.save(); g.globalCompositeOperation = opts.word ? 'source-over' : 'lighter';
    const span = h + 80;
    const age = t - t0;
    if (age < 0) { g.restore(); return; }
    const front = -40 + age * 3600;                      // 처음 반 초 동안 위에서부터 쏟아져 내려와 화면을 채운다
    for (let i = 0; i < n; i++) {
      const isGold = i === opts.gold;
      const d = isGold ? 0.9 : U.hash(i, 101);          // 0 먼 눈 … 1 가까운 눈 (금색 한 송이는 늘 가까운 눈)
      if (d < layerLo || d >= layerHi) continue;
      const dd = d * d;
      const speed = 85 + 210 * dd + 30 * U.hash(i, 102);
      // 송이마다 제 높이에서 시작해 끝없이 돈다 → n송이가 늘 화면(과 위아래 여백) 안에 있다
      const y = -40 + ((age * speed + (isGold ? 0.36 : U.hash(i, 103)) * span) % span);
      if (y > front) continue;
      const sway = (10 + 26 * dd) * Math.sin(t * (0.6 + 0.9 * U.hash(i, 104)) + U.hash(i, 105) * TAU);
      const bx = isGold ? w * 0.78 : U.hash(i, 106) * (w + 60) - 30;
      const x = x0 + bx + sway;
      const xx = x0 + (((x - x0) % (w + 60)) + (w + 60)) % (w + 60) - 30;
      const size = 5 + 17 * dd;
      const a = (0.34 + 0.6 * d) * fadeOut;
      if (opts.word) {                                    // 글자 세상: 눈송이가 '눈'이라는 글자(자리는 진짜 눈과 똑같다)
        const px = WORD_PX[Math.min(WORD_PX.length - 1, Math.floor(dd * WORD_PX.length))];
        if (isGold) Fx.stamp(g, Fx.glyph(opts.word, 30, '#ffd24a', 800), xx, y, fadeOut);
        else Fx.stamp(g, Fx.glyph(opts.word, px, '#eaf2ff', 800), xx, y, Math.min(1, a * 1.25));
      }
      else if (isGold) U.dot(g, xx, y, 46, '#ffd24a', fadeOut, 0.42);     // 딱 한 송이는 금색
      else U.dot(g, xx, y, size * 1.9, '#eaf2ff', a, 0.34);
    }
    g.restore(); g.globalAlpha = 1;
  };

  // ───────────────────────── 불꽃놀이 ─────────────────────────
  /* b: {t0(쏘는 시각), x, y(터지는 곳), ground(쏘는 높이), rise, color, color2, n, R(반지름), type, seed}
     type: 'peony' 둥근 꽃 | 'ring' 고리 | 'willow' 금빛 버들 | 'double' 두 겹 */
  Fx.fireworkFlash = function (t, b) {
    const tau = t - (b.t0 + b.rise);
    if (tau < 0 || tau > 0.6) return 0;
    return Math.pow(1 - tau / 0.6, 2);
  };
  Fx.firework = function (g, t, b) {
    const tb = b.t0 + b.rise;
    g.save(); g.globalCompositeOperation = 'lighter'; g.lineCap = 'round';
    // 올라가는 불씨: 밝은 머리 + 길게 끌리는 꼬리 + 떨어지는 불티
    if (t >= b.t0 && t < tb + 0.12) {
      const pos = (tt) => {
        const p = U.easeOutCubic(U.clamp01((tt - b.t0) / b.rise));
        return { x: b.x + Math.sin(tt * 22 + b.seed) * 4 * (1 - p) + (b.drift || 0) * (1 - p), y: U.lerp(b.ground, b.y, p) };
      };
      const fadeTop = 1 - U.prog(t, tb - 0.05, tb + 0.12);
      let prev = pos(Math.min(t, tb));
      for (let j = 1; j <= 14; j++) {
        const tt = Math.min(t, tb) - j * 0.014; if (tt < b.t0) break;
        const p = pos(tt), tail = 1 - j / 15;
        g.globalAlpha = 0.8 * tail * tail * fadeTop; g.strokeStyle = j < 4 ? '#fff1cf' : '#ffb347'; g.lineWidth = 1 + 4.5 * tail;
        g.beginPath(); g.moveTo(prev.x, prev.y); g.lineTo(p.x, p.y); g.stroke();
        prev = p;
      }
      if (t < tb) { const h = pos(t); U.dot(g, h.x, h.y, 30, '#fff6dc', 0.95, 0.3); }
      for (let i = 0; i < 10; i++) {                       // 불티
        const born = b.t0 + U.hash(b.seed + i, 31) * b.rise, age = t - born;
        if (age < 0 || age > 0.5) continue;
        const p0 = pos(born);
        U.dot(g, p0.x + (U.hash(b.seed + i, 32) - 0.5) * 26 * age * 3, p0.y + 120 * age * age + 14 * age, 8, '#ffcf87', (1 - age / 0.5) * 0.8, 0.4);
      }
    }
    const tau = t - tb;
    const willow = b.type === 'willow';
    const life = b.life || (willow ? 3.2 : 2.1);
    if (tau >= 0 && tau < life + 0.3) {
      const k = willow ? 1.7 : 2.7;                 // 공기 저항
      const grav = willow ? 150 : 62;
      const R = b.R || 180;
      const v0 = R * k;
      const n = b.n == null ? 110 : b.n;
      const J = willow ? 15 : 7, dt = willow ? 0.045 : 0.028;
      // 섬광과 남는 빛무리
      if (tau < 0.5) {
        const f = Math.pow(1 - tau / 0.5, 2);
        U.dot(g, b.x, b.y, R * 3.4, b.color, 0.4 * f, 0.08);
      }
      if (tau < 0.12) U.dot(g, b.x, b.y, R * 0.7, '#ffffff', 0.35 * (1 - tau / 0.12), 0.06);
      if (tau < 1.6) U.dot(g, b.x, b.y + 30 * tau, R * 2.8, b.color, 0.12 * (1 - tau / 1.6), 0.05);
      for (let i = 0; i < n; i++) {
        const h1 = U.hash(b.seed * 977 + i, 1), h2 = U.hash(b.seed * 977 + i, 2), h3 = U.hash(b.seed * 977 + i, 3);
        let dx, dy, sp;
        if (b.type === 'ring') {
          const a = (i / n) * TAU + h3 * 0.04;
          dx = Math.cos(a); dy = Math.sin(a) * 0.92; sp = 0.96 + 0.08 * h1;
        } else {
          const z = h1 * 2 - 1, ph = h2 * TAU, rr = Math.sqrt(1 - z * z);     // 공 껍질을 옆에서 본 모양
          dx = rr * Math.cos(ph); dy = rr * Math.sin(ph); sp = 0.9 + 0.2 * h3;
          if (b.type === 'double' && i % 2 === 0) sp *= 0.55;
        }
        const col = (b.type === 'double' && i % 2 === 0) || (b.color2 && h3 > 0.72) ? (b.color2 || b.color) : b.color;
        const lifeI = life * (0.78 + 0.22 * h2);
        const at = (tt) => {
          const e = (1 - Math.exp(-k * tt)) / k;
          return { x: b.x + dx * sp * v0 * e, y: b.y + dy * sp * v0 * e + grav * (tt / k - e / k) };
        };
        let a0 = 1 - U.prog(tau, lifeI * 0.5, lifeI);
        if (a0 <= 0) continue;
        if (tau > lifeI * 0.45) a0 *= 0.55 + 0.45 * Math.sin(tau * 34 + h1 * 40);          // 꺼지기 전 깜박임
        const head = at(tau);
        let prev = head;
        g.strokeStyle = col;
        for (let j = 1; j <= J; j++) {                    // 꼬리: 선으로 이어 그려 끊기지 않게
          const tt = tau - j * dt; if (tt < 0) break;
          const p = at(tt), tail = 1 - j / (J + 1);
          g.globalAlpha = a0 * (willow ? tail : tail * tail) * 0.85; g.lineWidth = 0.8 + (willow ? 3.6 : 4.2) * tail;
          g.beginPath(); g.moveTo(prev.x, prev.y); g.lineTo(p.x, p.y); g.stroke();
          prev = p;
        }
        U.dot(g, head.x, head.y, willow ? 17 : 21, tau < 0.2 ? '#ffffff' : col, a0, 0.32);
        if (i % 2 === 0) U.dot(g, head.x, head.y, 52, col, a0 * 0.22, 0.05);          // 번지는 빛
      }
      // 터진 뒤 흩날리는 잔불
      if (tau > 0.5 && !willow) {
        const m = Math.round(n * 0.4);
        for (let i = 0; i < m; i++) {
          const h1 = U.hash(b.seed * 331 + i, 7), h2 = U.hash(b.seed * 331 + i, 8), h3 = U.hash(b.seed * 331 + i, 9);
          const born = 0.5 + h3 * 1.0; const age = tau - born;
          if (age < 0 || age > 0.5) continue;
          const a = h1 * TAU, rad = Math.sqrt(h2) * R * 1.02;
          const x = b.x + Math.cos(a) * rad, y = b.y + Math.sin(a) * rad + 40 * tau;
          U.dot(g, x, y, 11, '#ffffff', (1 - age / 0.5) * (0.5 + 0.5 * Math.sin(age * 60 + h1 * 9)), 0.4);
        }
      }
    }
    g.restore(); g.globalAlpha = 1;
  };

  // ───────────────────────── 글자를 점으로 ─────────────────────────
  // 글자 모양 안쪽에 점을 뿌려 좌표 목록으로 돌려준다(가운데 정렬, 기준점 0,0).
  Fx.samplePoints = function (text, font, step, seed) {
    const c = document.createElement('canvas');
    const g0 = c.getContext('2d'); g0.font = font;
    const m = g0.measureText(text);
    const w = Math.ceil(m.width) + 40, asc = Math.ceil(m.actualBoundingBoxAscent) + 20, desc = Math.ceil(m.actualBoundingBoxDescent) + 20;
    c.width = w; c.height = asc + desc;
    const g = c.getContext('2d', { willReadFrequently: true });
    g.font = font; g.fillStyle = '#fff'; g.textBaseline = 'alphabetic'; g.fillText(text, 20, asc);
    const data = g.getImageData(0, 0, c.width, c.height).data;
    const pts = []; const r = U.rng(seed || 5);
    for (let y = step / 2; y < c.height; y += step) {
      for (let x = step / 2; x < c.width; x += step) {
        const jx = x + (r() - 0.5) * step * 0.7, jy = y + (r() - 0.5) * step * 0.7;
        const ix = Math.max(0, Math.min(c.width - 1, Math.round(jx))), iy = Math.max(0, Math.min(c.height - 1, Math.round(jy)));
        if (data[(iy * c.width + ix) * 4 + 3] > 140) pts.push({ x: jx - w / 2, y: jy - (asc + desc) / 2, u: r(), v: r(), k: r() });
      }
    }
    return { pts, w, h: asc + desc };
  };
  /* 점들이 origin에서 터져 나와 글자 자리(cx,cy 기준)에 내려앉고, 그 자리에서 반짝인다.
     o: {size, colorA, colorB, spread, settle(초), fade(0..1 전체 밝기)} */
  Fx.sparkText = function (g, t, t0, sample, cx, cy, ox, oy, o) {
    const tau = t - t0; if (tau < 0) return;
    o = o || {};
    const size = o.size || 9, settle = o.settle || 0.95, spread = o.spread || 150, fade = o.fade == null ? 1 : o.fade;
    g.save(); g.globalCompositeOperation = 'lighter';
    for (const p of sample.pts) {
      const d = settle * (0.55 + 0.45 * p.u);
      const q = U.clamp01(tau / d);
      const e = U.easeOutCubic(q);
      const ang = p.v * TAU, burst = Math.sin(Math.PI * Math.min(1, q * 1.15)) * (1 - q) * spread * (0.4 + p.k);
      const tx = cx + p.x, ty = cy + p.y;
      const x = U.lerp(ox, tx, e) + Math.cos(ang) * burst;
      const y = U.lerp(oy, ty, e) + Math.sin(ang) * burst;
      const tw = q < 1 ? 1 : 0.62 + 0.38 * Math.sin(t * (3 + 5 * p.u) + p.v * 40);
      const col = p.k < (o.mixB == null ? 0.35 : o.mixB) ? (o.colorB || '#ffffff') : (o.colorA || '#ffd479');
      U.dot(g, x, y, size * (q < 1 ? 1.5 - 0.5 * q : 1) * (0.8 + 0.5 * p.k), col, fade * tw * (0.5 + 0.5 * q), 0.3);
    }
    g.restore(); g.globalAlpha = 1;
  };

  // ───────────────────────── 빛나는 글자(한 번 그려 두고 재사용) ─────────────────────────
  /* key가 같으면 다시 그리지 않는다. 돌려주는 것: 그림판과 가운데 정렬용 치수 */
  Fx.glowText = function (key, text, font, fill, glowColor, blur, stroke) {
    return U.layer('gt|' + key, 1, 1, function (g0, c) {
      g0.font = font;
      const lines = String(text).split('\n');
      const lh = parseInt(font.match(/(\d+)px/)[1], 10) * 1.22;
      let w = 0; for (const ln of lines) w = Math.max(w, g0.measureText(ln).width);
      const pad = Math.ceil(blur * 2.4 + 12);
      c.width = Math.ceil(w + pad * 2); c.height = Math.ceil(lh * lines.length + pad * 2);
      const g = c.getContext('2d');
      g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle';
      lines.forEach((ln, i) => {
        const y = pad + lh * (i + 0.5), x = c.width / 2;
        if (blur > 0) {
          g.shadowColor = glowColor; g.shadowBlur = blur; g.fillStyle = glowColor;
          g.globalAlpha = 0.9; g.fillText(ln, x, y); g.fillText(ln, x, y);
          g.shadowBlur = 0; g.globalAlpha = 1;
        }
        if (stroke) { g.lineJoin = 'round'; g.lineWidth = stroke.w; g.strokeStyle = stroke.color; g.strokeText(ln, x, y); }
        g.fillStyle = fill; g.fillText(ln, x, y);
      });
    });
  };
  Fx.drawCentered = function (g, layer, cx, cy, scale, alpha) {
    if (alpha <= 0.003) return;
    const w = layer.width * (scale || 1), h = layer.height * (scale || 1);
    g.globalAlpha = Math.min(1, alpha);
    g.drawImage(layer, cx - w / 2, cy - h / 2, w, h);
    g.globalAlpha = 1;
  };

  // ───────────────────────── 코드 줄 → 무대로 날아가는 빛 ─────────────────────────
  Fx.courier = function (g, t, t0, from, to, color, dur) {
    dur = dur || 0.42;
    const tau = t - t0; if (tau < -0.02 || tau > dur + 0.45) return;
    g.save(); g.globalCompositeOperation = 'lighter';
    const cx = (from.x + to.x) / 2, cy = Math.min(from.y, to.y) - 150 - Math.abs(from.x - to.x) * 0.12;
    const at = (q) => {
      const e = U.easeInOutCubic(q), m = 1 - e;
      return { x: m * m * from.x + 2 * m * e * cx + e * e * to.x, y: m * m * from.y + 2 * m * e * cy + e * e * to.y };
    };
    for (let j = 0; j < 22; j++) {
      const q = (tau - j * 0.011) / dur;
      if (q < 0 || q > 1) continue;
      const p = at(q), tail = 1 - j / 22;
      U.dot(g, p.x, p.y, (j === 0 ? 34 : 22) * (0.35 + 0.65 * tail), j < 2 ? '#ffffff' : color, tail * tail, 0.26);
    }
    // 도착: 작은 고리 + 반짝
    const ta = tau - dur;
    if (ta >= 0 && ta < 0.45) {
      const f = 1 - ta / 0.45;
      U.dot(g, to.x, to.y, 60 + 200 * U.easeOutCubic(ta / 0.45), color, 0.5 * f * f, 0.12);
      g.globalAlpha = 0.7 * f; g.strokeStyle = color; g.lineWidth = 3 * f + 0.5;
      g.beginPath(); g.arc(to.x, to.y, 14 + 70 * U.easeOutCubic(ta / 0.45), 0, TAU); g.stroke();
    }
    g.restore(); g.globalAlpha = 1;
  };

  // ───────────────────────── 화면 마무리 ─────────────────────────
  let grainTile = null;
  Fx.grain = function (g, frame, w, h, alpha) {
    if (!grainTile) {
      grainTile = document.createElement('canvas'); grainTile.width = grainTile.height = 256;
      const gg = grainTile.getContext('2d'); const img = gg.createImageData(256, 256); const r = U.rng(4242);
      for (let i = 0; i < img.data.length; i += 4) { const v = Math.floor(r() * 255); img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255; }
      gg.putImageData(img, 0, 0);
    }
    g.save(); g.globalCompositeOperation = 'overlay'; g.globalAlpha = alpha;
    const ox = Math.floor(U.hash(frame, 1) * 256), oy = Math.floor(U.hash(frame, 2) * 256);
    for (let y = -oy; y < h; y += 256) for (let x = -ox; x < w; x += 256) g.drawImage(grainTile, x, y);
    g.restore(); g.globalAlpha = 1;
  };
  Fx.vignette = function (g, x0, w, h, strength) {
    const rg = g.createRadialGradient(x0 + w / 2, h * 0.5, h * 0.25, x0 + w / 2, h * 0.5, h * 0.75);
    rg.addColorStop(0, 'rgba(0,0,0,0)'); rg.addColorStop(1, `rgba(0,0,10,${strength})`);
    g.fillStyle = rg; g.fillRect(x0, 0, w, h);
  };

  window.Fx = Fx;
})();
