/* 조립 — 대본(script.js)을 실행해 시각표를 만들고, 프레임 번호를 받으면 그 순간의 화면 한 장을 그린다.
     왼쪽: 무대를 그림판에 그린 뒤 newyear.js의 ascii()로 글자로 바꿔 찍고, 읽어야 하는 글자만 또렷하게 얹는다.
     오른쪽: 디버거 세 칸(editor.js) — 대본, 지금 실행 중인 newyear.js, 터미널.
   창에서 그냥 열면 실시간 재생(클릭: 멈춤/재생, ←→: 한 프레임), ?capture=1 이면 render.js가 프레임을 가져간다.

   영상 시각 T와 이야기 시각 τ는 첫머리만 다르다(timing.js의 coldOpen):
     0 ~ hold              완성 장면(τ = 끝)을 먼저 보여 준다    ← 마지막 프레임과 이어져서 반복 재생이 끊기지 않는다
     hold ~ stageRewindEnd 거꾸로 돌린다(큰 움직임만 차례로: 연도 → 금빛 → 흙더미 → 삽질러 → 연도판)
     그 뒤                 처음부터 정속(τ = T)
   ?cold=0 을 붙이면 첫머리 없이 빈 무대에서 바로 시작한다(비교용). */
'use strict';
(function () {
  const U = window.U, Fx = window.Fx, Editor = window.Editor, Stage = window.Stage, Timeline = window.Timeline;
  const canvas = document.getElementById('c');
  const g = canvas.getContext('2d');
  const W = 1080, H = 1920, SPLIT = 540;
  const T = window.TIMING;
  const FPS = T.fps || 30;

  const scriptText = window.SCRIPT_OVERRIDE || window.SCRIPT_TEXT;
  const tl = Timeline.build(scriptText, T, Stage.REGISTRY);
  const st = Stage.collect(tl);
  const DURATION = T.duration;
  const FRAMES = Math.round(DURATION * FPS);
  const noCold = /[?&]cold=0/.test(location.search) || window.NO_COLD_OPEN;
  const COLD = (!noCold && T.coldOpen) || { hold: 0, rewindEnd: 0, stageRewindEnd: 0 };
  const SRE = COLD.stageRewindEnd != null ? COLD.stageRewindEnd : COLD.rewindEnd;
  const firstFire = tl.lines.length ? tl.lines[0].fireAt : 1;

  // ── 첫머리 되감기: 큰 동작만 차례로. 각 구간 [몫, 이야기 시각 a → b] ──
  const REW = (function () {
    const seg = [];
    if (st.yearUp) seg.push([3, st.yearUp.lock + 0.25, st.yearUp.t - 0.02]);
    if (st.gildT != null) seg.push([4, st.gildT + 12 * Stage.GILD_STEP + 0.26, st.gildT - 0.02]);
    if (st.dig) seg.push([5, st.dig.t + st.dig.D, st.dig.t]);
    if (st.spawn) seg.push([2, st.spawn.t + Stage.DROP + 0.08, st.spawn.t - 0.01]);
    if (st.yearSet) seg.push([2, st.yearSet.t + Stage.DROP + 0.1, Math.min(st.yearSet.t, firstFire) - 0.01]);
    const total = seg.reduce((a, s) => a + s[0], 0) || 1;
    let acc = 0;
    return seg.map(s => { const q0 = acc / total; acc += s[0]; return { q0, q1: acc / total, a: s[1], b: s[2] }; });
  })();
  function storyTime(Tv) {
    if (Tv >= SRE) return Tv;
    if (Tv < COLD.hold) return DURATION + Tv;                                     // 완성 장면이 계속 움직인다
    const q = (Tv - COLD.hold) / (SRE - COLD.hold);
    for (const s of REW) if (q >= s.q0 && q < s.q1) return U.lerp(s.a, s.b, (q - s.q0) / (s.q1 - s.q0));
    return SRE;
  }
  const rewinding = (Tv) => Tv >= COLD.hold && Tv < SRE;
  // 되감는 동안 눈은 제 시계로 천천히 거꾸로 올라간다(구간마다 시각이 건너뛰어도 눈발이 튀지 않게)
  const rewindSnowT = (Tv, t) => (st.snow && t > st.snow.t + 0.6 ? DURATION + COLD.hold - (Tv - COLD.hold) * 3 : t);

  // ── 위쪽 큰 글자: 처음엔 낚는 말, 새해로 넘어가면 맺는 말 ──
  // 문구는 copy.js에서 바꾼다. 낚는 말 둘째 줄을 비워 두면 대본에서 처음 오류가 나는 줄 번호로 만든다(대본을 고쳐도 어긋나지 않게).
  const failLine = tl.lines.find(ln => ln.fires[0] && !ln.fires[0].ok && !ln.fires[0].silent);
  const success = !!st.yearUp;
  const C0 = window.COPY || {};
  const autoHook2 = failLine ? `${failLine.idx + 1}번째 줄에서 에러 납니다` : '마지막 줄까지 보세요';
  const COPY = {
    hook: [(C0.hook && C0.hook[0]) || '올해 삽질만 했다면', (C0.hook && C0.hook[1]) || autoHook2],
    final: [(C0.final && C0.final[0]) || '헛삽질은 없었습니다', (C0.final && C0.final[1]) || '올해도 수고 많으셨습니다'],
  };
  const HEAD = { y1: 338, y2: 426, px: 74 };
  const swapT = success ? st.yearUp.lock - 0.12 : Infinity;

  function headLayer(text, color) {
    const font = `400 ${HEAD.px}px "Black Han Sans", "Pretendard", sans-serif`;
    return U.layer('head|' + text + color, 1, 1, (g0, c) => {
      g0.font = font; const w = g0.measureText(text).width, pad = 44;
      c.width = Math.ceil(w + pad * 2); c.height = Math.ceil(HEAD.px * 1.3 + pad * 2);
      const gg = c.getContext('2d'); gg.font = font; gg.textAlign = 'center'; gg.textBaseline = 'middle'; gg.lineJoin = 'round';
      const x = c.width / 2, y = c.height / 2;
      gg.shadowColor = 'rgba(0,0,0,0.9)'; gg.shadowBlur = 22; gg.shadowOffsetY = 6;
      gg.lineWidth = 16; gg.strokeStyle = '#05060b'; gg.strokeText(text, x, y);
      gg.shadowColor = 'transparent'; gg.shadowBlur = 0; gg.shadowOffsetY = 0;
      gg.lineWidth = 16; gg.strokeText(text, x, y);
      gg.fillStyle = color; gg.fillText(text, x, y);
    });
  }
  function drawHeadLine(text, color, y, scale, squashY, dx) {
    const layer = headLayer(text, color);
    const fit = Math.min(1, (W - 64) / layer.width) * scale;
    g.save(); g.translate(W / 2 + (dx || 0), y); g.scale(fit, fit * squashY);
    g.drawImage(layer, -layer.width / 2, -layer.height / 2); g.restore();
  }
  function drawHeadline(Tv) {
    // 끝에서는 맺는 말이 접히고 낚는 말이 다시 펴져 첫 프레임과 이어진다
    const loop = isFinite(swapT);
    const endOut = loop ? U.prog(Tv, DURATION - 0.26, DURATION - 0.12) : 0;
    const endIn = loop ? U.easeOutBack(U.prog(Tv, DURATION - 0.14, DURATION), 1.6) : 0;
    if (Tv < swapT + 0.14 || endIn > 0) {
      const out = Tv < swapT + 0.14 ? 1 - U.prog(Tv, swapT, swapT + 0.14) : endIn;
      // 예고한 그 줄에서 정말 오류가 나는 순간: 둘째 줄이 빨갛게 덜컥
      const ft = failLine ? Tv - failLine.fireAt : -1;
      const hot = ft >= 0 && ft < 1.1 && Tv >= SRE && Tv < swapT;
      const red = hot ? (ft < 0.9 ? 1 : 1 - U.prog(ft, 0.9, 1.1)) : 0;
      const dx = hot ? Math.sin(ft * 70) * 10 * (1 - U.prog(ft, 0, 0.4)) : 0;
      const sc = hot ? 1 + 0.07 * U.bump(ft, 0, 0.08, 0.1, 0.4) : 1;
      drawHeadLine(COPY.hook[0], '#ffffff', HEAD.y1, 1, out, 0);
      if (red < 1) drawHeadLine(COPY.hook[1], '#ffe14d', HEAD.y2, sc, out, dx);
      if (red > 0) { g.globalAlpha = red; drawHeadLine(COPY.hook[1], '#ff6b7d', HEAD.y2, sc, out, dx); g.globalAlpha = 1; }
    }
    if (Tv >= swapT + 0.12 && endOut < 1) {
      const p = U.easeOutBack(U.prog(Tv, swapT + 0.12, swapT + 0.36), 2.2) * (1 - endOut);
      const pop = 1 + 0.08 * U.bump(Tv, swapT + 0.12, swapT + 0.3, swapT + 0.32, swapT + 0.55);
      drawHeadLine(COPY.final[0], '#ffffff', HEAD.y1, pop, p, 0);
      drawHeadLine(COPY.final[1], '#ffe14d', HEAD.y2, pop, p, 0);
    }
  }

  // ── 되감기 표시 ──
  function drawRewind(Tv, frame) {
    if (!rewinding(Tv)) return;
    const q = (Tv - COLD.hold) / (SRE - COLD.hold);
    const a = U.bump(q, 0, 0.1, 0.78, 1);
    g.save();
    for (let i = 0; i < 5; i++) {                             // 가로 잡음 띠(무대 쪽만)
      const y = U.hash(frame, 40 + i) * H, hgt = 3 + U.hash(frame, 60 + i) * 12;
      g.fillStyle = `rgba(255,255,255,${(0.04 + 0.06 * U.hash(frame, 80 + i)) * a})`; g.fillRect(0, y, SPLIT, hgt);
    }
    const cx = 270, cy = 770, s = 50;                         // ◀◀
    g.globalAlpha = 0.92 * a; g.fillStyle = '#ffffff'; g.strokeStyle = '#05060b'; g.lineWidth = 8; g.lineJoin = 'round';
    const nudge = -10 * ((Tv * 9) % 1);
    for (const dx of [-s * 0.55, s * 0.55]) {
      g.beginPath(); g.moveTo(cx + dx + s * 0.5 + nudge, cy - s * 0.62); g.lineTo(cx + dx - s * 0.5 + nudge, cy); g.lineTo(cx + dx + s * 0.5 + nudge, cy + s * 0.62); g.closePath();
      g.stroke(); g.fill();
    }
    g.restore(); g.globalAlpha = 1;
  }

  // 대본 줄 → 무대: 줄이 실행되면 빛 하나가 그 효과가 생길 자리로 날아간다
  function drawCouriers(t) {
    for (const f of tl.fires) {
      if (!f.ok || f.silent) continue;
      const entry = Stage.REGISTRY[f.key]; if (!entry || !entry.target || entry.instant) continue;
      Fx.courier(g, t, f.t, Editor.lineAnchor(f.line), entry.target(st), entry.color || '#ffffff', Stage.COURIER);
    }
  }

  // ── 왼쪽: 무대를 그림판에 그리고 글자로 바꿔 찍는다 ──
  const scene = document.createElement('canvas'); scene.width = SPLIT; scene.height = H;
  const sg = scene.getContext('2d');
  const NY = Stage.NY;
  const out = NY.writer(g, '"JetBrains Mono", monospace');
  const y0 = st.yearSet ? st.yearSet.v : undefined;
  const yNew = st.yearUp ? y0 + st.yearUp.by : y0;
  const RING = { x: Stage.CX, y: Stage.BOARD.cy, r: 1500 };
  const RAW = /[?&]ascii=0/.test(location.search);
  function drawLeft(t, rw, Tv) {
    sg.setTransform(1, 0, 0, 1, 0, 0); sg.globalAlpha = 1; sg.globalCompositeOperation = 'source-over';
    sg.clearRect(0, 0, SPLIT, H);
    const res = Stage.drawScene(sg, t, st, { rewind: rw, snowT: rw ? rewindSnowT(Tv, t) : null });
    g.fillStyle = '#030408'; g.fillRect(0, 0, SPLIT, H);
    // 새해가 '철컥' 잠기면 연도판에서 고리가 퍼지며 고리 안쪽부터 칸이 작아진다(해상도 업)
    const reveal = st.yearUp ? U.easeOutCubic(U.prog(t - st.yearUp.lock, 0, 0.8)) : 0;
    const info = { cols: 0, rows: 0, glyphs: 0 };
    const run = (year) => {
      const n = NY.ascii(scene, { year, year0: y0 }, out);
      const cell = year > y0 ? 5 : 8;
      info.cols = SPLIT / cell | 0; info.rows = H / cell / 1.8 | 0; info.glyphs = n;
    };
    if (RAW) { g.drawImage(scene, 0, 0); Stage.drawOverlay(g, t, st, { rewind: rw }); return Object.assign(info, res); }   // ?ascii=0: 글자로 바꾸기 전 그림(비교용)
    if (reveal < 1) run(y0);
    if (reveal > 0) {
      g.save(); g.beginPath(); g.arc(RING.x, RING.y, reveal * RING.r, 0, Math.PI * 2); g.clip();
      g.fillStyle = '#030408'; g.fillRect(0, 0, SPLIT, H);
      run(yNew);
      g.restore();
    }
    Stage.drawOverlay(g, t, st, { rewind: rw });
    if (reveal > 0 && reveal < 1) {                           // 퍼져 나가는 고리
      g.save(); g.beginPath(); g.rect(0, 0, SPLIT, H); g.clip(); g.globalCompositeOperation = 'lighter';
      const f = 1 - reveal;
      g.strokeStyle = '#ffe9a8'; g.globalAlpha = Math.min(1, 1.6 * f); g.lineWidth = 3 + 9 * f;
      g.beginPath(); g.arc(RING.x, RING.y, reveal * RING.r, 0, Math.PI * 2); g.stroke();
      g.restore(); g.globalAlpha = 1;
    }
    return Object.assign(info, res);
  }

  // ── 오른쪽: 디버거 세 칸 ──
  const model = Editor.prepare(tl, st, window.NEWYEAR.toString(), Stage, COLD);
  const fileName = (t) => (st.yearUp && t >= st.yearUp.lock ? `${yNew}.py` : `${y0 || 2026}.py`);

  function render(frame) {
    const Tv = frame / FPS, t = storyTime(Tv), rw = rewinding(Tv);
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
    const left = drawLeft(t, rw, Tv);
    Editor.draw(g, t, model, { fileName: fileName(t), rewinding: rw, frame, frames: FRAMES, cols: left.cols, rows: left.rows, glyphs: left.glyphs });
    g.fillStyle = 'rgba(255,255,255,0.08)'; g.fillRect(SPLIT - 1, 0, 2, H);       // 가운데 경계선
    if (!rw) drawCouriers(t);
    drawRewind(Tv, frame);
    drawHeadline(Tv);
    Fx.grain(g, frame, W, H, 0.04);
    return left;
  }

  // 소리 합성용 시각표(영상 시각 기준)
  function events() {
    const ev = [{ t: 0, type: 'hook_slam' }];
    if (SRE > COLD.hold) ev.push({ t: COLD.hold, type: 'rewind', dur: SRE - COLD.hold });
    for (const f of tl.fires) {
      ev.push({ t: f.t, type: f.ok ? 'enter' : 'enter_error', line: f.line, silent: !!f.silent });
      if (f.silent) continue;
      const entry = Stage.REGISTRY[f.ok ? f.key : f.tryKey];
      if (f.ok && entry && !entry.instant) ev.push({ t: f.t, type: 'courier', key: f.key, dur: Stage.COURIER });
    }
    for (const s of model.steps) if (!s.loop && s.t >= 0) ev.push({ t: s.t, type: 'step', kind: s.kind });
    for (const e of Stage.soundEvents(st)) ev.push(e);
    if (isFinite(swapT)) ev.push({ t: swapT + 0.12, type: 'final_message' });
    ev.sort((a, b) => a.t - b.t);
    return ev.filter(e => e.t >= 0 && e.t < DURATION + 0.001).map(e => Object.assign({}, e, { t: Math.round(e.t * 10000) / 10000 }));
  }

  // 검증·소리 합성 쪽에서 쓰는 요약(줄별 실행 시각, 화면 배치)
  function summary() {
    return {
      script: scriptText.split('\n'),
      lines: tl.lines.map(ln => ({ idx: ln.idx, text: ln.text, fireAt: ln.fireAt,
        ok: ln.fires[0].ok, silent: !!ln.fires[0].silent, error: ln.fires[0].error, key: ln.fires[0].key, args: ln.fires[0].args, log: ln.fires[0].log, env: ln.fires[0].env })),
      errorRows: tl.errorRows, swapT: isFinite(swapT) ? swapT : null, success, coldOpen: COLD, copy: COPY, status: model.status,
      music: T.music || null,
      layout: { split: SPLIT, head: HEAD, editor: Editor.L, theme: Editor.THEME, stage: Stage.LAYOUT, ring: RING, rowA: tl.lines.map(ln => Editor.rowA(ln.idx)) },
      state: { yearSet: st.yearSet, yearFail: st.yearFail, yearUp: st.yearUp, snow: st.snow, spawn: st.spawn, count: st.count, say: st.say, fw: st.fw, gildT: st.gildT,
        bursts: st.bursts.length,
        dig: st.dig ? { t: st.dig.t, n: st.dig.n, D: st.dig.D, h: st.dig.h, bands: st.dig.bands, labeled: st.dig.labeled } : null },
    };
  }

  const ready = (async () => {
    const need = ['500 32px "JetBrains Mono"', '600 32px "JetBrains Mono"', '700 32px "JetBrains Mono"', '800 32px "JetBrains Mono"', '500 32px "Pretendard"', '600 32px "Pretendard"',
      '700 32px "Pretendard"', '800 32px "Pretendard"', '400 32px "Black Han Sans"'];
    await Promise.all(need.map(f => document.fonts.load(f, '가a1')));
    await document.fonts.ready;
    render(0);
  })();

  window.REEL = { ready, render, events, summary, storyTime, canvas, fps: FPS, frames: FRAMES, duration: DURATION, width: W, height: H, tl, st, swapT, model };

  // ── 실시간 미리보기 ──
  if (!/[?&]capture=1/.test(location.search)) {
    document.body.classList.add('live');
    const hud = document.getElementById('hud');
    let playing = true, frame = 0, last = null, acc = 0;
    const tick = (now) => {
      if (last == null) last = now;
      if (playing) { acc += (now - last) / 1000; while (acc >= 1 / FPS) { acc -= 1 / FPS; frame = (frame + 1) % FRAMES; } render(frame); }
      last = now;
      hud.textContent = `${(frame / FPS).toFixed(2)}초 / ${DURATION.toFixed(1)}초 · 프레임 ${frame} · 클릭: 멈춤/재생 · ←→: 한 프레임`;
      requestAnimationFrame(tick);
    };
    ready.then(() => requestAnimationFrame(tick));
    canvas.addEventListener('click', () => { playing = !playing; });
    window.addEventListener('keydown', (e) => {
      if (e.key === ' ') { playing = !playing; e.preventDefault(); }
      if (e.key === 'ArrowRight') { playing = false; frame = (frame + 1) % FRAMES; render(frame); }
      if (e.key === 'ArrowLeft') { playing = false; frame = (frame + FRAMES - 1) % FRAMES; render(frame); }
    });
  }
})();
