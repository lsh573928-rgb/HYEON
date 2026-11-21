/* 오른쪽 코드 창 — 대본 글자가 한 자씩 찍히고, 줄이 끝나면 실행 표시(✓ 또는 ✕)와 함께 빛이 훑고 지나간다.
   실행하다 오류가 난 줄은 그 아래에 오류 줄이 끼어든다(뒤 줄들은 한 칸씩 밀린다). */
'use strict';
(function () {
  const U = window.U, Interp = window.Interp, Timeline = window.Timeline;

  const THEME = {
    bgTop: '#0c1124', bgBottom: '#090c18',
    card: '#10172b', cardEdge: 'rgba(255,255,255,0.08)',
    text: '#dbe3f5', comment: '#6f7fa3', keyword: '#ff86c1', func: '#ffd479', object: '#7fe3c4', attr: '#9cc9ff',
    number: '#ffa46b', string: '#b8f08a', op: '#c3cde6', punct: '#93a0c2', kwarg: '#9cc9ff', ident: '#dbe3f5',
    gutter: '#3a4667', gutterActive: '#93a0c2', ok: '#7cf0a4', error: '#ff6b7d',
    lineActive: 'rgba(255,255,255,0.05)', cursor: '#ffd479',
  };

  const L = {                     // 배치(px)
    x0: 540, x1: 1080,
    cardX: 554, cardY: 472, cardW: 510, cardH: 1020, radius: 26,
    tabH: 62,
    codeTop: 586,                 // 첫 줄 글자 밑선
    lineH: 64, fontPx: 36, cellW: 21.6,
    gutterX: 600,                 // 줄 번호 오른쪽 끝
    codeX: 624,
    logGap: 84, logRows: 3, logRowH: 52,
    fileName: 'untitled.py',
    signature: '삽질하는 토목직',
  };
  const HANGUL_ADV = 1.56;        // 한글 한 자의 폭(영문 칸 기준)

  function fontCode(px, w) { return `${w || 500} ${px}px "JetBrains Mono", "Pretendard", monospace`; }
  function fontKo(px, w) { return `${w || 700} ${px}px "Pretendard", sans-serif`; }
  function rowY(row) { return L.codeTop + row * L.lineH; }

  function drawBackground(g, t, ambient) {
    const gr = g.createLinearGradient(0, 0, 0, 1920);
    gr.addColorStop(0, THEME.bgTop); gr.addColorStop(1, THEME.bgBottom);
    g.fillStyle = gr; g.fillRect(L.x0, 0, L.x1 - L.x0, 1920);
    // 무대 쪽에서 새어 드는 빛(불꽃이 터지면 창 왼쪽 가장자리가 물든다)
    if (ambient && ambient.a > 0.004) {
      g.save(); g.beginPath(); g.rect(L.x0, 0, L.x1 - L.x0, 1920); g.clip();
      g.globalCompositeOperation = 'lighter';
      const rg = g.createRadialGradient(L.x0 - 40, ambient.y, 0, L.x0 - 40, ambient.y, 900);
      rg.addColorStop(0, U.rgba(ambient.color, 0.34 * ambient.a));
      rg.addColorStop(0.45, U.rgba(ambient.color, 0.1 * ambient.a));
      rg.addColorStop(1, U.rgba(ambient.color, 0));
      g.fillStyle = rg; g.fillRect(L.x0, 0, L.x1 - L.x0, 1920);
      g.restore();
    }
  }

  function drawCard(g, fileName, renamedAgo, crumb) {
    g.save();
    U.roundRect(g, L.cardX, L.cardY, L.cardW, L.cardH, L.radius);
    g.fillStyle = THEME.card; g.fill();
    g.lineWidth = 1.5; g.strokeStyle = THEME.cardEdge; g.stroke();
    g.save(); U.roundRect(g, L.cardX, L.cardY, L.cardW, L.cardH, L.radius); g.clip();
    g.fillStyle = 'rgba(255,255,255,0.04)'; g.fillRect(L.cardX, L.cardY, L.cardW, L.tabH);
    g.fillStyle = 'rgba(255,255,255,0.07)'; g.fillRect(L.cardX, L.cardY + L.tabH - 1, L.cardW, 1);
    g.restore();
    const cy = L.cardY + L.tabH / 2;
    ['#ff6b6b', '#ffd166', '#6bdc8b'].forEach((c, i) => {
      g.fillStyle = c; g.globalAlpha = 0.9; g.beginPath(); g.arc(L.cardX + 30 + i * 24, cy, 7, 0, Math.PI * 2); g.fill();
    });
    g.globalAlpha = 1;
    // 파일 이름은 year 변수를 따라 바뀐다(untitled.py → 2026.py → 2027.py). 바뀌는 순간 잠깐 밝아진다.
    const hot = renamedAgo != null && renamedAgo >= 0 ? 1 - U.prog(renamedAgo, 0, 0.9) : 0;
    g.font = fontCode(24, hot > 0.3 ? 700 : 500); g.fillStyle = U.mix('#b4c0df', '#ffd479', hot); g.textBaseline = 'middle'; g.textAlign = 'left';
    g.fillText(fileName || L.fileName, L.cardX + 112, cy + 1);
    if (crumb) {                                            // 파일 이름 / 지금 실행 중인 호출
      const fw = g.measureText(fileName || L.fileName).width;
      g.font = fontCode(22, 500); g.fillStyle = '#5d6a8f'; g.fillText('/', L.cardX + 112 + fw + 14, cy + 1);
      let x = L.cardX + 112 + fw + 36;
      for (const ch of Array.from(crumb)) {
        const wide = Interp.cellWidth(ch) === 2;
        g.font = wide ? fontKo(21, 700) : fontCode(22, 500); g.fillStyle = '#8f9cc0';
        g.fillText(ch, x, cy + 1); x += wide ? 21 : 13.2;
      }
    }
    g.textBaseline = 'alphabetic';
    g.restore();
  }

  function drawLive(g, t, running, bad) {
    const x = L.cardX + L.cardW - 34, y = L.cardY + L.tabH / 2;
    const pulse = 0.55 + 0.45 * Math.sin(t * 6.0);
    g.save(); g.globalCompositeOperation = 'lighter';
    U.dot(g, x, y, 32, bad ? '#ff6b7d' : (running ? '#7cf0a4' : '#93a0c2'), (running || bad ? 0.95 : 0.35) * pulse);
    g.restore(); g.globalAlpha = 1;
  }

  function drawCheck(g, x, y, s, color, p) {       // p: 0→1 그려지는 정도
    if (p <= 0) return;
    g.save(); g.strokeStyle = color; g.lineWidth = 4; g.lineCap = 'round'; g.lineJoin = 'round';
    const a = [x - s * 0.5, y], b = [x - s * 0.12, y + s * 0.38], c = [x + s * 0.55, y - s * 0.42];
    g.beginPath(); g.moveTo(a[0], a[1]);
    const p1 = U.clamp01(p / 0.4), p2 = U.clamp01((p - 0.4) / 0.6);
    g.lineTo(U.lerp(a[0], b[0], p1), U.lerp(a[1], b[1], p1));
    if (p2 > 0) g.lineTo(U.lerp(b[0], c[0], p2), U.lerp(b[1], c[1], p2));
    g.stroke(); g.restore();
  }
  function drawCross(g, x, y, s, color, p) {
    if (p <= 0) return;
    g.save(); g.strokeStyle = color; g.lineWidth = 4; g.lineCap = 'round';
    const q1 = U.clamp01(p * 2), q2 = U.clamp01((p - 0.5) * 2);
    g.beginPath(); g.moveTo(x - s * 0.4, y - s * 0.4); g.lineTo(x - s * 0.4 + s * 0.8 * q1, y - s * 0.4 + s * 0.8 * q1);
    if (q2 > 0) { g.moveTo(x + s * 0.4, y - s * 0.4); g.lineTo(x + s * 0.4 - s * 0.8 * q2, y - s * 0.4 + s * 0.8 * q2); }
    g.stroke(); g.restore();
  }

  // 한 줄 그리기. opts: {color(단색), px(글자 크기)} — 돌려주는 것: 쓴 칸 수
  function drawLineText(g, text, x, y, opts) {
    const px = (opts && opts.px) || L.fontPx, cw = px * 0.6;
    const tokens = (opts && opts.plain) ? [{ text, type: 'text' }] : Interp.tokenize(text);
    let cell = 0;
    for (const tk of tokens) {
      g.fillStyle = (opts && opts.color) || THEME[tk.type] || THEME.text;
      for (const ch of Array.from(tk.text)) {
        const wide = Interp.cellWidth(ch) === 2;
        if (ch !== ' ') {
          if (wide) {
            g.font = fontKo(px - 2, 700); g.textAlign = 'center';
            g.fillText(ch, x + (cell + HANGUL_ADV / 2) * cw, y);
          } else if (ch >= 'ㄱ' && ch <= 'ㆎ') {           // 치는 중인 낱자(ㅅ, ㄱ …)
            g.font = fontKo(px - 2, 700); g.textAlign = 'center';
            g.fillText(ch, x + (cell + HANGUL_ADV / 2) * cw, y);
          } else {
            g.font = fontCode(px, tk.type === 'func' || tk.type === 'keyword' ? 700 : 500); g.textAlign = 'left';
            g.fillText(ch, x + cell * cw, y);
          }
        }
        cell += (wide || (ch >= 'ㄱ' && ch <= 'ㆎ')) ? HANGUL_ADV : 1;
      }
    }
    g.textAlign = 'left';
    return cell * cw;
  }

  function wavyUnderline(g, x, y, w, color, alpha) {
    g.save(); g.strokeStyle = color; g.globalAlpha = alpha; g.lineWidth = 3; g.beginPath();
    for (let i = 0; i <= w; i += 4) { const yy = y + Math.sin(i / 4 * 1.2) * 3; if (i === 0) g.moveTo(x + i, yy); else g.lineTo(x + i, yy); }
    g.stroke(); g.restore();
  }

  // 오류가 난 줄이 나중에 같은 글자로 다시 실행돼 통과했으면 그 시각(흐리게 만들 때 쓴다)
  function resolvedAt(tl, ln) {
    for (const other of tl.lines) {
      if (other.idx > ln.idx && other.text.trim() === ln.text.trim() && other.fires[0] && other.fires[0].ok) return other.fires[0].t;
    }
    return null;
  }

  // 창 머리의 작은 알림표(전체 선택 → 삭제)
  function drawChip(g, chip) {
    if (!chip) return;
    const pop = U.easeOutBack(U.prog(chip.age, 0, 0.12), 2.4), red = chip.kind === 'delete';
    g.save(); g.font = fontKo(22, 800); const w = g.measureText(chip.text).width + 28;
    g.translate(L.cardX + L.cardW - 62 - w / 2, L.cardY + L.tabH / 2); g.scale(pop, pop);
    U.roundRect(g, -w / 2, -17, w, 34, 10); g.fillStyle = red ? 'rgba(255,107,125,0.22)' : 'rgba(96,150,255,0.26)'; g.fill();
    g.lineWidth = 2; g.strokeStyle = red ? '#ff8f9c' : '#8fb4ff'; g.stroke();
    g.fillStyle = red ? '#ffc2c9' : '#d5e3ff'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(chip.text, 0, 1);
    g.restore(); g.textBaseline = 'alphabetic'; g.textAlign = 'left';
  }

  /* 편집기 전체. tl: Timeline.build 결과.
     opts: {ambient, fileName, renamedAgo, status, select(0..1 전체 선택이 덮인 정도), cleared(지워진 뒤), collapse(0..1 지워지는 중), chip} */
  function draw(g, t, tl, opts) {
    opts = opts || {};
    drawBackground(g, t, opts.ambient);
    const gone = opts.cleared && !(opts.collapse < 1);
    // 지금(또는 마지막으로) 실행된 줄이 부른 것
    let crumb = null;
    if (!opts.cleared) for (const f of tl.fires) { if (f.t > t || f.silent) continue; const p = f.parsed; crumb = p.kind === 'call' ? p.name.split('.').pop() + '()' : (p.kind === 'assign' ? (p.value && p.value.call ? p.value.call + '()' : p.target) : crumb); }
    drawCard(g, opts.fileName, opts.renamedAgo, crumb);
    drawChip(g, opts.chip);
    if (gone) {                                              // 전체 삭제 뒤: 빈 창에 커서만
      drawLive(g, t, false, false);
      if (Math.floor(t * 2.2) % 2 === 0) { g.fillStyle = THEME.cursor; g.fillRect(L.codeX + 3, rowY(0) - L.fontPx * 0.86, 4.5, L.fontPx * 1.08); }
      drawSignature(g);
      return;
    }
    const openError = tl.errorRows.some(e => { const r = resolvedAt(tl, tl.lines[e.afterLine]); return t >= e.t && (r == null || t < r); });
    const running = t >= tl.lines[0].typeStart && t <= tl.scriptEnd + 0.4;
    drawLive(g, t, running, openError);

    let active = -1;
    for (const ln of tl.lines) if (t >= ln.typeStart) active = ln.idx;
    const failIdx = tl.errorRows.length ? tl.errorRows[0].afterLine : -1;     // 낚는 말이 예고한 그 줄
    const lastIdx = tl.lines.length - 1;

    g.save();
    g.beginPath(); g.rect(L.cardX, L.cardY + L.tabH, L.cardW, L.cardH - L.tabH); g.clip();
    if (opts.cleared) { const q = U.clamp01(opts.collapse); g.translate(-46 * U.easeInCubic(q), 0); g.globalAlpha = 1 - q; }   // 지워지는 순간: 왼쪽으로 쓸려 나간다
    const baseAlpha = g.globalAlpha;
    for (const ln of tl.lines) {
      const st = Timeline.lineState(ln, t);
      // 오류 줄이 끼어들 때는 뒤 줄들이 스르륵 밀려 내려간다
      let row = ln.idx;
      for (const e of tl.errorRows) if (e.afterLine < ln.idx) row += U.easeOutCubic(U.prog(t - e.t, 0, 0.22));
      const y = rowY(row);
      const isFailLine = ln.idx === failIdx;
      if (st.state === 'idle') {                             // 아직 안 친 줄도 번호는 보인다(예고한 줄은 노랗게)
        g.textAlign = 'right';
        if (isFailLine) { g.font = fontCode(28, 800); g.fillStyle = '#ffe14d'; g.fillText(String(ln.idx + 1), L.gutterX + 2, y - 1); }
        else { g.font = fontCode(24, 500); g.fillStyle = THEME.gutter; g.fillText(String(ln.idx + 1), L.gutterX, y - 2); }
        g.textAlign = 'left';
        continue;
      }
      const txt = Timeline.visibleText(ln, t);
      const isActive = ln.idx === active && t < ln.fireAt + 0.25;
      const fixedAt = st.state === 'error' ? resolvedAt(tl, ln) : null;
      const dim = fixedAt != null ? 1 - 0.58 * U.prog(t - fixedAt, 0, 0.4) : 1;
      const isCta = ln.idx === lastIdx && st.state === 'silent';             // 맨 끝의 주석 한 줄(보내 달라는 말)
      const cta = isCta ? U.prog(t - ln.fireAt, 0, 0.3) : 0;

      if (isActive) { g.fillStyle = THEME.lineActive; g.fillRect(L.cardX, y - L.lineH * 0.7, L.cardW, L.lineH); }

      // 실행 순간: 줄 전체를 빛이 왼→오로 훑는다
      const f = st.fire;
      if (f && (!f.silent || isCta)) {
        const dt = t - f.t;
        if (dt >= 0 && dt < 0.7) {
          const col = isCta ? '#ffd479' : (f.ok ? THEME.ok : THEME.error);
          g.fillStyle = U.rgba(col, (1 - U.prog(dt, 0, 0.7)) * 0.22); g.fillRect(L.cardX, y - L.lineH * 0.7, L.cardW, L.lineH);
          const sx = L.cardX + (L.cardW + 160) * U.easeOutCubic(U.prog(dt, 0, 0.32)) - 80;
          const sg = g.createLinearGradient(sx - 90, 0, sx + 90, 0);
          sg.addColorStop(0, U.rgba(col, 0)); sg.addColorStop(0.5, U.rgba(col, 0.45 * (1 - U.prog(dt, 0.1, 0.36)))); sg.addColorStop(1, U.rgba(col, 0));
          g.fillStyle = sg; g.fillRect(sx - 90, y - L.lineH * 0.7, 180, L.lineH);
        }
      }

      g.globalAlpha = baseAlpha * dim;
      // 줄 번호 / 실행 표시
      if (st.state === 'ok') {
        const p = U.easeOutCubic(U.prog(t - f.t, 0, 0.28));
        const pop = 1 + 0.5 * U.bump(t - f.t, 0, 0.1, 0.12, 0.34);
        drawCheck(g, L.gutterX - 13, y - 12, 20 * pop, THEME.ok, p);
      } else if (st.state === 'error') {
        // 오류가 난 줄: 한동안 줄 번호가 빨갛게 뛰다가 ✕로 바뀐다
        const dt = t - f.t, hold = isFailLine ? 1.1 : 0;
        if (dt < hold + 0.2) {
          const a = 1 - U.prog(dt, hold, hold + 0.2), pop = 1 + 0.35 * U.bump(dt, 0, 0.08, 0.1, 0.4);
          g.save(); g.globalAlpha *= a; g.translate(L.gutterX - 11, y - 12); g.scale(pop, pop);
          g.font = fontCode(32, 800); g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = THEME.error; g.fillText(String(ln.idx + 1), 0, 1);
          g.restore(); g.textBaseline = 'alphabetic';
        }
        if (dt >= hold) drawCross(g, L.gutterX - 13, y - 12, 22, THEME.error, U.prog(dt - hold, 0, 0.2));
      } else {
        g.textAlign = 'right';
        if (isFailLine) { g.font = fontCode(28, 800); g.fillStyle = '#ffe14d'; g.fillText(String(ln.idx + 1), L.gutterX + 2, y - 1); }
        else { g.font = fontCode(24, 500); g.fillStyle = isActive ? THEME.gutterActive : THEME.gutter; g.fillText(String(ln.idx + 1), L.gutterX, y - 2); }
        g.textAlign = 'left';
      }

      // 글자
      const shake = st.state === 'error' ? Math.sin((t - f.t) * 70) * 6 * (1 - U.prog(t - f.t, 0, 0.35)) : 0;
      const w = drawLineText(g, txt, L.codeX + shake, y, cta > 0 ? { color: U.mix(THEME.comment, '#ffe9a8', cta), plain: true } : null);
      if (st.state === 'error') wavyUnderline(g, L.codeX, y + 13, w, THEME.error, 0.95 * dim);
      g.globalAlpha = baseAlpha;

      // 커서(치는 동안은 켜 두고, 쉬면 깜박임)
      if (ln.idx === active && st.state === 'typing') {
        let lastT = -1; for (const s of ln.strokes) { if (s.t <= t) lastT = s.t; else break; }
        const idle = lastT < 0 ? 1 : t - lastT;
        if (idle < 0.2 || Math.floor(t * 2.2) % 2 === 0) { g.fillStyle = THEME.cursor; g.fillRect(L.codeX + w + 3, y - L.fontPx * 0.86, 4.5, L.fontPx * 1.08); }
      }
    }

    // 전체 선택(파란 바탕): 맨 윗줄부터 차례로 덮인다
    if (opts.select > 0) {
      const total = tl.rows, upto = total * U.clamp01(opts.select);
      for (let r = 0; r < Math.min(total, Math.ceil(upto)); r++) {
        g.fillStyle = 'rgba(96,150,255,0.36)'; g.fillRect(L.cardX + 8, rowY(r) - L.lineH * 0.7, L.cardW - 16, L.lineH - 4);
      }
    }

    // 오류 줄
    for (const e of tl.errorRows) {
      const dt = t - e.t; if (dt < 0) continue;
      const src = tl.lines[e.afterLine];
      let row = src.idx + 1;
      for (const e2 of tl.errorRows) if (e2.afterLine < src.idx) row += 1;
      const p = U.easeOutCubic(U.prog(dt, 0, 0.22));
      const y = rowY(row) - (1 - p) * L.lineH * 0.6;
      const fixed = resolvedAt(tl, src);
      const dim = fixed != null ? 1 - 0.58 * U.prog(t - fixed, 0, 0.4) : 1;
      g.globalAlpha = baseAlpha * p * dim;
      const flash = 0.16 + 0.2 * (1 - U.prog(dt, 0, 0.8)) + (fixed == null || t < fixed ? 0.05 * Math.sin(t * 7) : 0);
      g.fillStyle = U.rgba(THEME.error, flash); g.fillRect(L.cardX, y - L.lineH * 0.7, L.cardW, L.lineH);
      g.fillStyle = THEME.error; g.fillRect(L.cardX, y - L.lineH * 0.7, 6, L.lineH);
      // 긴 오류문은 창 안에 들어오도록 글자를 줄인다
      let cells = 0; for (const ch of Array.from(e.text)) cells += Interp.cellWidth(ch) === 2 ? HANGUL_ADV : 1;
      const epx = Math.max(18, Math.min(31, Math.floor((L.cardW - 44) / (cells * 0.6))));
      drawLineText(g, e.text, L.codeX - 44, y - 2, { color: '#ffb3bd', px: epx, plain: true });
      g.globalAlpha = baseAlpha;
    }

    // 다음 줄 대기 커서
    if (active >= 0 && active < tl.lines.length - 1 && !opts.cleared) {
      const cur = tl.lines[active], stc = Timeline.lineState(cur, t);
      if (stc.state !== 'typing' && stc.state !== 'idle' && Math.floor(t * 2.2) % 2 === 0) {
        let row = active + 1;
        for (const e of tl.errorRows) if (e.afterLine < active + 1) row += U.easeOutCubic(U.prog(t - e.t, 0, 0.22));
        g.fillStyle = THEME.cursor; g.fillRect(L.codeX + 3, rowY(row) - L.fontPx * 0.86, 4.5, L.fontPx * 1.08);
      }
    }
    g.restore();

    if (opts.cleared) g.globalAlpha = 1 - U.clamp01(opts.collapse);
    drawLog(g, t, tl, opts.status);
    g.globalAlpha = 1;
    drawSignature(g);
  }
  // 서명(오른쪽 아래는 앱의 좋아요·댓글 단추가 덮으므로 왼쪽 아래에 둔다)
  function drawSignature(g) {
    g.font = fontKo(24, 700); g.textAlign = 'left'; g.fillStyle = 'rgba(180,192,223,0.55)';
    g.fillText(L.signature, L.cardX + 30, L.cardY + L.cardH - 28);
  }

  /* 코드 아래 한 줄 설명(코드를 안 읽어도 무슨 일이 일어났는지 알 수 있게). 최근 것 몇 줄만.
     status: {t, text} — 다 돌고 난 뒤의 맺음 요약 한 줄(금색) */
  function drawLog(g, t, tl, status) {
    const shown = tl.fires.filter(f => !f.silent && f.t <= t && (f.log || f.error)).map(f => ({ t: f.t, ok: f.ok, text: f.ok ? f.log : '새해로 못 넘어감' }));
    if (status && t >= status.t) shown.push({ t: status.t, ok: true, text: status.text, gold: true });
    if (!shown.length) return;
    const maxRows = L.logRows, rowH = L.logRowH;
    const top = rowY(tl.rows - 1) + L.logGap;
    const rows = shown.slice(-maxRows);
    const newest = rows[rows.length - 1];
    const slide = shown.length > maxRows ? 1 - U.easeOutCubic(U.prog(t - newest.t, 0, 0.25)) : 0;
    g.save();
    g.fillStyle = 'rgba(255,255,255,0.07)'; g.fillRect(L.cardX + 24, top - rowH - 6, L.cardW - 48, 1.5);
    g.beginPath(); g.rect(L.cardX, top - rowH + 4, L.cardW, rowH * maxRows + 14); g.clip();
    rows.forEach((f, i) => {
      const y = top + i * rowH + slide * rowH;
      const age = t - f.t, isNew = f === newest;
      const a = isNew ? U.easeOutCubic(U.prog(age, 0, 0.22)) : 0.5;
      const dx = isNew ? (1 - U.easeOutCubic(U.prog(age, 0, 0.25))) * 18 : 0;
      g.globalAlpha = a;
      g.font = fontCode(27, 700); g.fillStyle = f.gold ? '#ffd479' : (f.ok ? THEME.ok : THEME.error); g.textAlign = 'left';
      g.fillText(f.gold ? '=' : (f.ok ? '>' : '!'), L.codeX - 40 + dx, y);
      g.font = fontKo(30, isNew ? 800 : 600); g.fillStyle = f.gold ? '#ffe9a8' : (f.ok ? (isNew ? '#eef3ff' : '#aeb9d6') : '#ff8f9c');
      g.fillText(f.text, L.codeX - 6 + dx, y);
    });
    g.restore(); g.globalAlpha = 1;
  }

  // 줄이 놓인 칸의 y(오류 줄 때문에 밀린 것까지) — 무대로 날아가는 빛의 출발점
  function lineY(tl, idx, t) {
    let row = idx;
    for (const e of tl.errorRows) if (e.afterLine < idx && t >= e.t) row += 1;
    return rowY(row);
  }

  window.Editor = { draw, lineY, rowY, L, THEME, fontCode, fontKo };
})();
