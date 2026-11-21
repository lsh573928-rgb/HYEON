/* 오른쪽 창 — 디버거처럼 세 칸.
     ① 2026.py   : 대본. 지금 실행 중인 줄에 막대가 내려가고, 끝난 줄은 ✓, 오류 난 줄은 ✕.
     ② newyear.js: 그 줄이 부른 코드(engine/newyear.js를 그대로 띄운다). 막대가 한 줄씩 내려가며 반복문을 돌고,
                   옆에 지금 값(d = 137)이 뜬다. 대본이 쉬는 동안에는 왼쪽 그림을 글자로 찍는 반복문이 돈다.
     ③ 터미널     : 실행 결과 한 줄씩, 오류는 at 2026.py:6, 맨 아래는 프레임·칸·글자 수(실제로 센 값). */
'use strict';
(function () {
  const U = window.U, Interp = window.Interp;

  const THEME = {
    bg: '#07080d', card: '#0d1018', cardEdge: 'rgba(255,255,255,0.08)',
    text: '#d4dbec', gutter: '#3c4560', gutterHot: '#c9d2ea',
    comment: '#6a7598', keyword: '#c792ea', func: '#82aaff', prop: '#89ddff', string: '#c3e88d', number: '#f78c6c',
    op: '#9aa6c8', punct: '#7e8aad', ident: '#d4dbec', kwarg: '#89ddff', object: '#7fe3c4', attr: '#82aaff',
    bar: '#8f8cff', ok: '#7cf0a4', error: '#ff6b7d', gold: '#ffd479',
  };

  const L = {
    x0: 540, x1: 1080, cardX: 552, cardW: 516, radius: 18,
    A: { y: 476, h: 362, head: 50, font: 25, pitch: 30, numX: 620, codeX: 638, markX: 574 },
    B: { y: 848, h: 410, head: 42, font: 16, pitch: 23, numX: 594, codeX: 606 },
    C: { y: 1268, h: 224, head: 38, font: 19, pitch: 28, x: 576 },
    signature: '삽질하는 토목직',
  };
  const monoW = (px) => px * 0.6;                  // JetBrains Mono 한 칸 폭
  const HANGUL = 1.66;                              // 한글 한 자의 폭(영문 칸 기준)
  function fontCode(px, w) { return `${w || 500} ${px}px "JetBrains Mono", "Pretendard", monospace`; }
  function fontKo(px, w) { return `${w || 700} ${px}px "Pretendard", sans-serif`; }

  // ───────── 글자 한 줄 그리기(한글은 두 칸) ─────────
  function drawTokens(g, tokens, x, y, px, colorOf, alpha) {
    const cw = monoW(px);
    let cell = 0;
    g.globalAlpha = alpha == null ? 1 : alpha;
    for (const tk of tokens) {
      g.fillStyle = colorOf(tk);
      for (const ch of Array.from(tk.text)) {
        const wide = Interp.cellWidth(ch) === 2 || (ch >= 'ㄱ' && ch <= 'ㆎ');
        if (ch !== ' ') {
          if (wide) { g.font = fontKo(px - 1, 600); g.textAlign = 'center'; g.fillText(ch, x + (cell + HANGUL / 2) * cw, y); }
          else { g.font = fontCode(px, tk.type === 'keyword' || tk.type === 'func' ? 700 : 500); g.textAlign = 'left'; g.fillText(ch, x + cell * cw, y); }
        }
        cell += wide ? HANGUL : 1;
      }
    }
    g.textAlign = 'left'; g.globalAlpha = 1;
    return cell * cw;
  }

  // ───────── 자바스크립트 색칠(여러 줄 주석까지) ─────────
  const JS_KEYWORDS = new Set(['const', 'let', 'var', 'function', 'return', 'for', 'if', 'else', 'throw', 'new', 'of', 'in', 'typeof', 'true', 'false', 'null', 'continue', 'break']);
  function tokenizeJS(lines) {
    let inBlock = false;
    return lines.map((line) => {
      const out = []; const c = Array.from(line); let i = 0;
      const push = (text, type) => { if (text) out.push({ text, type }); };
      while (i < c.length) {
        if (inBlock) {
          let j = i; while (j < c.length && !(c[j] === '*' && c[j + 1] === '/')) j++;
          if (j < c.length) { push(c.slice(i, j + 2).join(''), 'comment'); i = j + 2; inBlock = false; } else { push(c.slice(i).join(''), 'comment'); i = c.length; }
          continue;
        }
        const ch = c[i];
        if (ch === '/' && c[i + 1] === '*') { inBlock = true; continue; }
        if (ch === '/' && c[i + 1] === '/') { push(c.slice(i).join(''), 'comment'); break; }
        if (ch === "'" || ch === '"' || ch === '`') {
          let j = i + 1; while (j < c.length && c[j] !== ch) { if (c[j] === '\\') j++; j++; }
          push(c.slice(i, j + 1).join(''), 'string'); i = j + 1; continue;
        }
        if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(c[i + 1] || ''))) {
          let j = i; while (j < c.length && /[0-9._]/.test(c[j])) j++;
          push(c.slice(i, j).join(''), 'number'); i = j; continue;
        }
        if (/[A-Za-z_$가-힣]/.test(ch)) {
          let j = i; while (j < c.length && /[A-Za-z0-9_$가-힣]/.test(c[j])) j++;
          const w = c.slice(i, j).join('');
          const prev = out.length ? out[out.length - 1].text : '';
          let type = 'ident';
          if (JS_KEYWORDS.has(w)) type = 'keyword';
          else if (c[j] === '(') type = 'func';
          else if (prev.endsWith('.')) type = 'prop';
          push(w, type); i = j; continue;
        }
        if (ch === ' ') { let j = i; while (j < c.length && c[j] === ' ') j++; push(c.slice(i, j).join(''), 'space'); i = j; continue; }
        push(ch, '=+-*/<>%!&|?:'.includes(ch) ? 'op' : 'punct'); i++;
      }
      return out;
    });
  }
  // 긴 줄은 접는다(접힌 줄의 번호 자리에는 '-')
  function wrapRows(lines, tokens, maxCells) {
    const rows = [];
    lines.forEach((line, li) => {
      const indent = line.length - line.trimStart().length;
      let cur = [], cells = 0, first = true;
      const flush = () => { rows.push({ line: li, first, tokens: cur }); first = false; cur = [{ text: ' '.repeat(indent + 4), type: 'space' }]; cells = indent + 4; };
      for (const tk of tokens[li]) {
        let w = 0; for (const ch of Array.from(tk.text)) w += Interp.cellWidth(ch);
        if (cells + w > maxCells && cells > indent + 4 && tk.type !== 'space') flush();
        cur.push(tk); cells += w;
      }
      rows.push({ line: li, first, tokens: cur });
    });
    return rows;
  }

  /* ───────── 준비: 띄울 코드, 디버거 막대가 지나갈 길(투어), 터미널 줄 ─────────
     src: engine/newyear.js의 newyear 함수 원문(실제로 실행되는 그 코드) */
  function prepare(tl, st, src, Stage, cold) {
    const lines = src.split('\n');
    const tokens = tokenizeJS(lines);
    const maxCells = Math.floor((L.cardX + L.cardW - 12 - L.B.codeX) / monoW(L.B.font));
    const rows = wrapRows(lines, tokens, maxCells);
    const firstRow = [], lastRow = [];
    rows.forEach((r, i) => { if (r.first) firstRow[r.line] = i; lastRow[r.line] = i; });
    const find = (needle) => { const i = lines.findIndex(l => l.includes(needle)); if (i < 0) throw new Error('newyear.js에 없는 줄: ' + needle); return i; };
    // 줄이 속한 함수 이름(창 머리에 띄운다)
    const owner = lines.map((l, i) => {
      for (let k = i; k >= 0; k--) {
        const m = lines[k].match(/^\s*(C(?:\['[^']+'\]|\.\w+))\s*=/) || lines[k].match(/^\s*function (\w+)\(/) || lines[k].match(/^\s*(\w+)\([^)]*\) \{/);
        if (m) return m[1].startsWith('C') ? m[1] : m[1] + '()';
      }
      return '';
    });
    const M = {
      'year =': ["C['year =']", 'env.year = env.year0 = y;'],
      '= 삽질러': ["C['= 삽질러']", 'env.days = [];', "return { type: '삽질러' };"],
      'snow.fall': ["C['snow.fall']", 'env.snow = n;'],
      '삽질러.삽질': ["C['삽질러.삽질']", 'if (env.days.length + n > 365)', 'for (let d = 1; d <= n; d++)', 'env.days.push(d);', "throw RangeError('1년은 365일');"],
      'countdown': ['C.countdown', 'env.beats = [];', 'for (let k = n; k > 0; k--)', 'env.beats.push(k);'],
      'year +=': ["C['year +=']", 'if (!env.thanked)', "throw Error('\"수고했어\" 누락');", 'env.year += by;'],
      'say': ['C.say', "if (text.includes('수고'))", 'env.thanked = true;'],
      'fireworks': ['C.fireworks', 'env.shells = [];', 'for (let i = 0; i < n; i++)', 'env.shells.push(i % 12);'],
    };
    const at = {}; for (const k of Object.keys(M)) at[k] = M[k].map(find);
    const R = {
      cell: find('const cell = env.year > env.year0'), shrink: find('const px = shrink('), sobelCall: find('const edge = sobel('),
      begin: find('out.begin('), forY: find('for (let y = 0; y < rows; y++)'), forX: find('for (let x = 0; x < cols; x++)'),
      idx: find('const i = y * cols + x;'), line: find('const line = edge.mag[i]'), ch: find('const ch = line'), put: find('out.put(i, ch, px.rgb(i));'), end: find('return out.end();'),
      sMag: find('mag[i] = Math.hypot(gx, gy);'), sDir: find('dir[i] = Math.round('),
      wDraw: find('pane.drawImage(a, idx[i] * cell'), wPaint: find('paint(pane, tint,'),
    };

    // 투어: [{t, line, kind, val}] — kind: 'run'(보통) | 'error' | 'ok' | 'gold'
    const steps = [];
    const S = (t, line, kind, val, extra) => steps.push(Object.assign({ t, line, kind: kind || 'run', val: val || null }, extra || {}));
    const busy = [];                                         // 대본 명령이 코드 창을 쓰는 구간
    for (const f of tl.fires) {
      if (f.silent) continue;
      const key = f.ok ? f.key : f.tryKey;
      const m = at[key]; if (!m) continue;
      const T = f.t, a = f.args || [];
      let end = T + 0.5;
      if (key === 'year =') { S(T, m[0]); S(T + 0.12, m[1], 'run', `y = ${a[0]}`); }
      else if (key === '= 삽질러') { S(T, m[0]); S(T + 0.1, m[1]); S(T + 0.2, m[2]); }
      else if (key === 'snow.fall') { S(T, m[0]); S(T + 0.12, m[1], 'run', `n = ${a[0]}`); }
      else if (key === '삽질러.삽질') {
        S(T, m[0]); S(T + 0.1, m[1], 'run', `n = ${a[0]}`);
        if (!f.ok) { S(T + 0.2, m[4], 'error'); end = T + 1.2; }
        else if (st.dig) {
          S(T + 0.2, m[2]);
          const d = st.dig, n = Math.max(1, Math.round(d.D / 0.0834));
          for (let i = 0; i < n; i++) S(d.t + i * 0.0834, i % 2 ? m[2] : m[3], 'run', null, { dayAt: true });
          S(d.t + d.D, m[3], 'run', `d = ${d.n}`);
          end = d.t + d.D + 0.4;
        }
      }
      else if (key === 'countdown' && st.count) {
        S(T, m[0]); S(T + 0.1, m[1]); S(T + 0.18, m[2]);
        for (let i = 0; i < st.count.n; i++) S(st.count.t + i * Stage.COUNT_STEP, m[3], 'run', `k = ${st.count.n - i}`);
        end = st.count.t + st.count.n * Stage.COUNT_STEP;
      }
      else if (key === 'year +=') {
        S(T, m[0]); S(T + 0.08, m[1], 'run', `env.thanked = ${f.ok}`);
        if (!f.ok) { S(T + 0.16, m[2], 'error'); end = T + 1.25; }
        else {
          S(T + 0.16, m[3], 'run', `env.year = ${f.env.year}`);
          if (st.yearUp) { S(st.yearUp.lock, R.cell, 'gold', 'cell = 5'); end = st.yearUp.lock + 0.9; }
        }
      }
      else if (key === 'say') { S(T, m[0]); S(T + 0.1, m[1], 'run', `text = "${a[0]}"`); if (f.env.thanked) S(T + 0.2, m[2], 'ok'); end = T + 0.8; }
      else if (key === 'fireworks') {
        S(T, m[0]); S(T + 0.1, m[1]); S(T + 0.18, m[2]);
        st.bursts.forEach((b, i) => S(b.t0, m[3], 'run', `i = ${i}`));
        end = (st.bursts.length ? st.bursts[st.bursts.length - 1].t0 : T) + 0.6;
      }
      busy.push([T, end]);
    }
    // 대본이 쉬는 동안: 왼쪽 그림을 글자로 찍는 반복문이 돈다
    const isBusy = (t) => busy.some(([a, b]) => t >= a - 0.05 && t < b);
    const loopBody = [R.forX, R.idx, R.line, R.ch, R.put];
    const cycle = [R.shrink, R.sobelCall, R.sMag, R.sDir, R.sMag, R.sDir, R.begin, R.forY]
      .concat(loopBody, loopBody, loopBody, [R.forY], loopBody, loopBody, [R.end, R.wDraw, R.wDraw, R.wPaint]);
    const tEnd = Math.max(tl.scriptEnd + 4, 20);
    let k = 0;
    for (let i = 0; i * 0.1 < tEnd; i++) {
      const t = i * 0.1;
      if (isBusy(t)) { k = 0; continue; }
      S(t, cycle[k % cycle.length], 'run', null, { loop: true }); k++;
    }
    steps.sort((a, b) => a.t - b.t);

    // 터미널 줄
    const term = [{ t: cold.rewindEnd, text: 'node render.js 2026.py', color: '#8b95b7', prompt: true }];
    tl.fires.forEach((f) => {
      if (f.silent) return;
      const n = f.line + 1;
      if (f.ok) term.push({ t: f.t, mark: '✓', markColor: THEME.ok, text: `${n}  ${f.log || ''}`, color: '#e6ebf7' });
      else {
        term.push({ t: f.t + 0.16, mark: '✕', markColor: THEME.error, text: `${n}  ${f.error.type}: ${f.error.message}`, color: '#ff8f9c' });
        term.push({ t: f.t + 0.24, text: `    at 2026.py:${n}  ${f.text.trim()}`, color: '#b9707c' });
      }
    });
    const lastRun = tl.fires.filter(f => !f.silent).pop();
    const errors = tl.fires.filter(f => !f.ok).length;
    const waste = st.dig ? (st.gildT != null ? 0 : st.dig.labeled) : 0;
    const status = lastRun ? { t: lastRun.t + 1.0, text: `= 오류 ${errors}건 · 헛삽질 ${waste}건` } : null;
    if (status) term.push({ t: status.t, text: status.text, color: THEME.gold, bold: true });
    term.sort((a, b) => a.t - b.t);

    return { lines, rows, firstRow, lastRow, owner, steps, term, status, tl, st, Stage };
  }

  // 시각 t의 디버거 막대 자리
  function stepAt(model, t) {
    const s = model.steps;
    let lo = 0, hi = s.length - 1, idx = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (s[mid].t <= t) { idx = mid; lo = mid + 1; } else hi = mid - 1; }
    return { cur: idx >= 0 ? s[idx] : null, prev: idx > 0 ? s[idx - 1] : null };
  }

  // ───────── 공통 조각 ─────────
  function card(g, y, h) {
    U.roundRect(g, L.cardX, y, L.cardW, h, L.radius);
    g.fillStyle = THEME.card; g.fill();
    g.lineWidth = 1.5; g.strokeStyle = THEME.cardEdge; g.stroke();
  }
  function tabPill(g, x, cy, text, px) {
    g.font = fontCode(px, 600);
    const w = g.measureText(text).width + 24;
    U.roundRect(g, x, cy - 15, w, 30, 8);
    g.fillStyle = 'rgba(255,255,255,0.04)'; g.fill();
    g.lineWidth = 1.6; g.strokeStyle = 'rgba(170,182,220,0.55)'; g.stroke();
    g.fillStyle = '#dfe5f5'; g.textBaseline = 'middle'; g.fillText(text, x + 12, cy + 1); g.textBaseline = 'alphabetic';
    return w;
  }
  function crumb(g, x, cy, text) {
    g.textBaseline = 'middle';
    g.font = fontCode(17, 500); g.fillStyle = '#5d6789'; g.fillText('/', x, cy + 1);
    let cx = x + 18;
    for (const ch of Array.from(text)) {
      const wide = Interp.cellWidth(ch) === 2;
      g.font = wide ? fontKo(16, 700) : fontCode(17, 500); g.fillStyle = '#8f9cc0';
      g.fillText(ch, cx, cy + 1); cx += wide ? 17 : 10.2;
    }
    g.textBaseline = 'alphabetic';
  }
  function dots(g, y) {
    ['#ff6b6b', '#ffd166', '#6bdc8b'].forEach((c, i) => { g.fillStyle = c; g.globalAlpha = 0.85; g.beginPath(); g.arc(L.cardX + 24 + i * 20, y, 6, 0, Math.PI * 2); g.fill(); });
    g.globalAlpha = 1;
  }
  function drawCheck(g, x, y, s, color, p) {
    if (p <= 0) return;
    g.save(); g.strokeStyle = color; g.lineWidth = 3.6; g.lineCap = 'round'; g.lineJoin = 'round';
    const a = [x - s * 0.5, y], b = [x - s * 0.12, y + s * 0.38], c = [x + s * 0.55, y - s * 0.42];
    const p1 = U.clamp01(p / 0.4), p2 = U.clamp01((p - 0.4) / 0.6);
    g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(U.lerp(a[0], b[0], p1), U.lerp(a[1], b[1], p1));
    if (p2 > 0) g.lineTo(U.lerp(b[0], c[0], p2), U.lerp(b[1], c[1], p2));
    g.stroke(); g.restore();
  }
  function drawCross(g, x, y, s, color, p) {
    if (p <= 0) return;
    g.save(); g.strokeStyle = color; g.lineWidth = 3.8; g.lineCap = 'round';
    const q1 = U.clamp01(p * 2), q2 = U.clamp01((p - 0.5) * 2);
    g.beginPath(); g.moveTo(x - s * 0.4, y - s * 0.4); g.lineTo(x - s * 0.4 + s * 0.8 * q1, y - s * 0.4 + s * 0.8 * q1);
    if (q2 > 0) { g.moveTo(x + s * 0.4, y - s * 0.4); g.lineTo(x + s * 0.4 - s * 0.8 * q2, y - s * 0.4 + s * 0.8 * q2); }
    g.stroke(); g.restore();
  }
  function wavy(g, x, y, w, color) {
    g.save(); g.strokeStyle = color; g.lineWidth = 2.6; g.beginPath();
    for (let i = 0; i <= w; i += 4) { const yy = y + Math.sin(i / 4 * 1.2) * 2.6; if (i === 0) g.moveTo(x + i, yy); else g.lineTo(x + i, yy); }
    g.stroke(); g.restore();
  }
  function bar(g, y, h, color, alpha) {
    g.fillStyle = U.rgba(color, 0.14 * alpha); g.fillRect(L.cardX + 1, y, L.cardW - 2, h);
    g.fillStyle = U.rgba(color, Math.min(1, 0.95 * alpha)); g.fillRect(L.cardX + 1, y, 4, h);
  }

  // ───────── ① 2026.py ─────────
  function rowA(i) { return L.A.y + L.A.head + 30 + i * L.A.pitch; }
  function drawScript(g, t, model, opts) {
    const tl = model.tl, A = L.A;
    card(g, A.y, A.h);
    const hy = A.y + A.head / 2;
    dots(g, hy);
    tabPill(g, L.cardX + 86, hy, opts.fileName, 20);
    const failing = tl.fires.some(f => !f.ok && f.t <= t) && !(model.st.yearUp && t >= model.st.yearUp.t);
    const done = model.status && t >= model.status.t;
    const label = opts.rewinding ? '◀◀ 되감기' : (failing ? '● 오류' : (done ? '■ 완료' : (t >= tl.lines[0].fireAt - 0.6 ? '● 실행 중' : '○ 대기')));
    const lc = opts.rewinding ? '#9fb4ff' : (failing ? THEME.error : (done ? '#93a0c2' : THEME.ok));
    g.font = fontKo(18, 800); g.textAlign = 'right'; g.fillStyle = lc; g.textBaseline = 'middle';
    g.globalAlpha = label.startsWith('●') ? 0.75 + 0.25 * Math.sin(t * 7) : 1; g.fillText(label, L.cardX + L.cardW - 18, hy + 1);
    g.globalAlpha = 1; g.textAlign = 'left'; g.textBaseline = 'alphabetic';
    g.fillStyle = 'rgba(255,255,255,0.06)'; g.fillRect(L.cardX, A.y + A.head, L.cardW, 1);

    // 지금 실행 중인 줄(마지막으로 Enter가 떨어진 줄)
    let cur = -1, curT = 0, prevLine = -1;
    for (const ln of tl.lines) if (ln.fireAt <= t) { prevLine = cur; cur = ln.idx; curT = ln.fireAt; }
    const failIdx = tl.errorRows.length ? tl.errorRows[0].afterLine : -1;
    g.save(); g.beginPath(); g.rect(L.cardX, A.y + A.head + 1, L.cardW, A.h - A.head - 2); g.clip();
    if (cur >= 0) {
      const f = tl.lines[cur].fires[0];
      const slide = U.easeOutCubic(U.prog(t - curT, 0, 0.14));
      const yb = U.lerp(prevLine >= 0 ? rowA(prevLine) : rowA(cur), rowA(cur), slide) - A.pitch * 0.74;
      const col = !f.ok ? THEME.error : (f.silent && cur === tl.lines.length - 1 ? THEME.gold : THEME.bar);
      bar(g, yb, A.pitch, col, 1);
    }
    for (const ln of tl.lines) {
      const y = rowA(ln.idx), f = ln.fires[0];
      const ran = f && t >= f.t;
      const resolved = ran && !f.ok && model.st.yearUp && t >= model.st.yearUp.t + 0.2;
      // 줄 번호(오류가 예고된 줄은 처음부터 노랗게)
      g.font = fontCode(20, ln.idx === cur || ln.idx === failIdx ? 800 : 500); g.textAlign = 'right';
      g.fillStyle = ln.idx === failIdx && !ran ? '#ffe14d' : (ran && !f.ok ? THEME.error : (ln.idx === cur ? THEME.gutterHot : THEME.gutter));
      g.fillText(String(ln.idx + 1), A.numX, y - 1); g.textAlign = 'left';
      if (ran && !f.silent) {
        if (f.ok) drawCheck(g, A.markX, y - 9, 18, THEME.ok, U.easeOutCubic(U.prog(t - f.t, 0.06, 0.3)));
        else drawCross(g, A.markX, y - 9, 18, THEME.error, U.prog(t - f.t, 0.06, 0.26));
      }
      // 글자: 아직 안 돈 줄은 흐리게
      const shake = ran && !f.ok ? Math.sin((t - f.t) * 70) * 5 * (1 - U.prog(t - f.t, 0, 0.35)) : 0;
      const alpha = !ran ? 0.5 : (resolved ? 0.5 : 1);
      const isCta = f && f.silent && ln.idx === tl.lines.length - 1;
      const cta = isCta && ran ? U.prog(t - f.t, 0, 0.3) : 0;
      const w = drawTokens(g, Interp.tokenize(ln.text), A.codeX + shake, y, A.font,
        (tk) => (cta > 0 ? U.mix(THEME.comment, '#ffe9a8', cta) : (THEME[tk.type] || THEME.text)), alpha);
      if (ran && !f.ok) {
        g.globalAlpha = resolved ? 0.5 : 1; wavy(g, A.codeX, y + 5, w, THEME.error); g.globalAlpha = 1;
        // 오류 내용을 줄 끝에(에러 렌즈)
        g.font = fontKo(19, 800); g.fillStyle = THEME.error;
        g.globalAlpha = (resolved ? 0.5 : 1) * U.prog(t - f.t, 0.16, 0.3);
        g.fillText(`← ${f.error.message}`, A.codeX + w + 14, y - 2); g.globalAlpha = 1;
      }
    }
    g.restore();
  }

  // ───────── ② newyear.js ─────────
  function drawCode(g, t, model, opts) {
    const B = L.B, Stage = model.Stage;
    card(g, B.y, B.h);
    const hy = B.y + B.head / 2;
    const { cur, prev } = stepAt(model, t);
    const w = tabPill(g, L.cardX + 16, hy, 'newyear.js', 18);
    if (cur) crumb(g, L.cardX + 16 + w + 10, hy, model.owner[cur.line]);
    g.fillStyle = 'rgba(255,255,255,0.06)'; g.fillRect(L.cardX, B.y + B.head, L.cardW, 1);

    const top = B.y + B.head + 8, bottom = B.y + B.h - 8, visRows = Math.floor((bottom - top) / B.pitch);
    // 막대가 있는 줄이 창의 4할 높이에 오게 굴린다
    const targetOf = (s) => (s ? Math.max(0, model.firstRow[s.line] - Math.round(visRows * 0.4)) : 0);
    const k = cur ? U.easeInOutCubic(U.prog(t - cur.t, 0, cur.loop ? 0.08 : 0.16)) : 1;
    const scroll = U.lerp(targetOf(prev), targetOf(cur), k);
    g.save(); g.beginPath(); g.rect(L.cardX, top, L.cardW, bottom - top); g.clip();
    const r0 = Math.floor(scroll), off = (scroll - r0) * B.pitch;
    if (cur) {
      const r1 = model.firstRow[cur.line], r2 = model.lastRow[cur.line];
      const prevR = prev ? model.firstRow[prev.line] : r1;
      const yb = top + (U.lerp(prevR, r1, U.easeOutCubic(U.prog(t - cur.t, 0, 0.07))) - scroll) * B.pitch + 2;
      const col = cur.kind === 'error' ? THEME.error : (cur.kind === 'ok' ? THEME.ok : (cur.kind === 'gold' ? THEME.gold : THEME.bar));
      const flash = cur.kind === 'run' ? 1 : 1 + 0.6 * (1 - U.prog(t - cur.t, 0, 0.5));
      bar(g, yb, (r2 - r1 + 1) * B.pitch, col, flash);
    }
    for (let r = r0; r < Math.min(model.rows.length, r0 + visRows + 2); r++) {
      const row = model.rows[r];
      const y = top + (r - r0) * B.pitch - off + B.pitch * 0.74;
      const hot = cur && row.line === cur.line;
      g.font = fontCode(14, hot ? 700 : 500); g.textAlign = 'right'; g.fillStyle = hot ? THEME.gutterHot : THEME.gutter;
      g.fillText(row.first ? String(row.line + 1) : '-', B.numX, y - 1); g.textAlign = 'left';
      const ww = drawTokens(g, row.tokens, B.codeX, y, B.font, (tk) => THEME[tk.type] || THEME.text, hot ? 1 : 0.78);
      // 지금 값(디버거의 인라인 값)
      if (hot && r === model.lastRow[cur.line]) {
        let val = cur.val;
        const src = model.lines[cur.line], fi = Math.floor(t * 30);
        if (cur.dayAt) val = `d = ${Math.max(1, Stage.dayAt(model.st, t))}`;
        if (cur.loop) {
          if (/const i = |const ch = |const line = |out\.put|for \(let x/.test(src)) val = `x = ${(fi * 7) % (opts.cols || 67)}, y = ${(fi * 3) % (opts.rows || 133)}`;
          else if (/for \(let y/.test(src)) val = `y = ${(fi * 3) % (opts.rows || 133)}`;
          else if (/mag\[i\]|dir\[i\]/.test(src)) val = `i = ${(fi * 541) % ((opts.cols || 67) * (opts.rows || 133))}`;
          else if (/pane\.drawImage/.test(src)) val = `n = ${(opts.glyphs || 0).toLocaleString('en-US')}`;
          else if (/out\.begin/.test(src)) val = `${opts.cols}×${opts.rows}`;
        }
        if (val) {
          g.font = fontCode(14, 600); const vw = g.measureText(val).width + 14;
          const vx = Math.min(B.codeX + ww + 12, L.cardX + L.cardW - vw - 10);
          U.roundRect(g, vx - 4, y - 16, vw + 8, 23, 7); g.fillStyle = '#151a2a'; g.fill();          // 밑 글자를 가리는 바탕
          U.roundRect(g, vx, y - 15, vw, 21, 6);
          g.fillStyle = cur.kind === 'error' ? 'rgba(255,107,125,0.3)' : (cur.kind === 'gold' ? 'rgba(255,212,121,0.3)' : 'rgba(143,140,255,0.3)'); g.fill();
          g.fillStyle = cur.kind === 'error' ? '#ffb3bd' : (cur.kind === 'gold' ? '#ffe9a8' : '#c9c8ff'); g.fillText(val, vx + 7, y - 1);
        }
      }
    }
    g.restore();
    // 위아래 끝은 흐리게(굴러가는 느낌)
    const fade = (y0, y1, up) => { const gr = g.createLinearGradient(0, y0, 0, y1); gr.addColorStop(up ? 1 : 0, 'rgba(13,16,24,0)'); gr.addColorStop(up ? 0 : 1, 'rgba(13,16,24,0.95)'); g.fillStyle = gr; g.fillRect(L.cardX + 1, y0, L.cardW - 2, y1 - y0); };
    fade(top, top + 22, true); fade(bottom - 30, bottom, false);
  }

  // ───────── ③ 터미널 ─────────
  function drawTerminal(g, t, model, opts) {
    const C = L.C;
    card(g, C.y, C.h);
    const hy = C.y + C.head / 2;
    dots(g, hy);
    g.font = fontKo(18, 800); g.fillStyle = '#8f9cc0'; g.textBaseline = 'middle'; g.fillText(`${L.signature} — node`, L.cardX + 86, hy + 1); g.textBaseline = 'alphabetic';
    g.fillStyle = 'rgba(255,255,255,0.06)'; g.fillRect(L.cardX, C.y + C.head, L.cardW, 1);
    const shown = model.term.filter(e => e.t <= t);
    const maxRows = 5, top = C.y + C.head + 30;
    const rows = shown.slice(-maxRows);
    const newest = rows[rows.length - 1];
    const slide = shown.length > maxRows && newest ? 1 - U.easeOutCubic(U.prog(t - newest.t, 0, 0.18)) : 0;
    g.save(); g.beginPath(); g.rect(L.cardX, C.y + C.head + 4, L.cardW, C.h - C.head - 40); g.clip();
    rows.forEach((e, i) => {
      const y = top + (i + slide) * C.pitch;
      const isNew = e === newest;
      g.globalAlpha = isNew ? U.easeOutCubic(U.prog(t - e.t, 0, 0.15)) : 0.72;
      let x = C.x;
      if (e.prompt) { g.font = fontCode(C.font, 800); g.fillStyle = THEME.ok; g.fillText('$', x, y); x += 22; }
      if (e.mark) { g.font = fontCode(C.font, 800); g.fillStyle = e.markColor; g.fillText(e.mark, x, y); x += 26; }
      g.font = /[가-힣]/.test(e.text) ? fontKo(C.font + 1, e.bold || isNew ? 800 : 600) : fontCode(C.font, 600);
      g.fillStyle = e.color; g.fillText(e.text, x, y);
    });
    g.restore(); g.globalAlpha = 1;
    // 맨 아래: 지금 프레임(실제로 센 값)
    const sy = C.y + C.h - 16;
    g.fillStyle = 'rgba(255,255,255,0.05)'; g.fillRect(L.cardX + 12, sy - 22, L.cardW - 24, 1);
    const st = opts.rewinding ? '◀◀ 되감는 중' : `frame ${String(opts.frame).padStart(3, '0')}/${opts.frames} · ${opts.cols}×${opts.rows}칸 · ${(opts.glyphs || 0).toLocaleString('en-US')}자`;
    drawTokens(g, [{ text: st, type: 'text' }], C.x, sy, 15, () => '#6f7aa0', 1);
  }

  function draw(g, t, model, opts) {
    g.fillStyle = THEME.bg; g.fillRect(L.x0, 0, L.x1 - L.x0, 1920);
    drawScript(g, t, model, opts);
    drawCode(g, t, model, opts);
    drawTerminal(g, t, model, opts);
  }

  // 대본 줄이 놓인 자리(코드 줄에서 무대로 날아가는 빛의 출발점)
  function lineAnchor(idx) { return { x: L.A.codeX - 6, y: rowA(idx) - 10 }; }

  window.Editor = { prepare, draw, lineAnchor, rowA, L, THEME, fontCode, fontKo };
})();
