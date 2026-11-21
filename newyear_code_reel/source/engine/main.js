/* 조립 — 대본+박자표로 시각표를 만들고, 프레임 번호를 받으면 그 순간의 화면 한 장을 그린다.
   창에서 그냥 열면 실시간 재생(클릭: 멈춤/재생, ←→: 한 프레임), ?capture=1 이면 render.js가 프레임을 가져간다.

   영상 시각 T와 이야기 시각 τ는 첫머리만 다르다(timing.js의 coldOpen):
     0 ~ hold          완성 장면(τ = 끝)을 먼저 보여 준다    ← 마지막 프레임과 이어져서 반복 재생이 끊기지 않는다
     hold ~ select     코드가 전체 선택되고(파란 바탕)
     select ~ rewindEnd  지워진다 → 장면이 거꾸로 돌아 빈 무대로(τ: 끝 → rewindEnd)
     rewindEnd ~       처음부터 정속(τ = T)
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
  const COLD = (!noCold && T.coldOpen) || { hold: 0, select: 0, rewindEnd: 0, stageRewindEnd: 0 };
  const SRE = COLD.stageRewindEnd != null ? COLD.stageRewindEnd : COLD.rewindEnd;   // 무대가 다 풀리는 시각(창보다 늦다)

  /* 되감기: 17초를 그대로 빨리 돌리면 정신없기만 하므로 큰 동작만 차례로 보여 준다.
     ① 연도판 2027 → 2026  ② 금빛이 빠진다  ③ 흙더미가 내려앉는다  ④ 삽질러가 올라간다  ⑤ 연도판이 올라간다
     각 구간은 [되감기 구간 안의 비율 q0~q1, 이야기 시각 τ0 → τ1] */
  const REW = (function () {
    const seg = [];
    if (st.yearUp) seg.push([3, st.yearUp.lock + 0.25, st.yearUp.t - 0.02]);
    if (st.gildT != null) seg.push([4, st.gildT + 12 * Stage.GILD_STEP + 0.26, st.gildT - 0.02]);
    if (st.dig) seg.push([5, st.dig.t + st.dig.D, st.dig.t]);
    if (st.spawn) seg.push([2, st.spawn.t + Stage.DROP + 0.08, st.spawn.t - 0.01]);
    if (st.yearSet) seg.push([2, st.yearSet.t + Stage.DROP + 0.1, st.yearSet.t - 0.01]);
    const total = seg.reduce((a, s) => a + s[0], 0) || 1;
    let acc = 0;
    return seg.map(s => { const q0 = acc / total; acc += s[0]; return { q0, q1: acc / total, a: s[1], b: s[2] }; });
  })();
  function storyTime(Tv) {                                   // 무대의 이야기 시각
    if (Tv >= SRE) return Tv;
    if (Tv < COLD.select) return DURATION + Tv;                                   // 완성 장면이 계속 움직인다
    const q = (Tv - COLD.select) / (SRE - COLD.select);
    for (const s of REW) if (q >= s.q0 && q < s.q1) return U.lerp(s.a, s.b, (q - s.q0) / (s.q1 - s.q0));
    return SRE;
  }
  const rewinding = (Tv) => Tv >= COLD.select && Tv < SRE;
  // 오른쪽 창의 시각: 지워진 뒤(select~rewindEnd)에는 비어 있고, 그 뒤로는 무대가 아직 풀리는 중이어도 정속으로 첫 줄을 친다
  const editorTime = (Tv) => (Tv < COLD.select ? DURATION + Tv : Tv);
  const editorCleared = (Tv) => Tv >= COLD.select && Tv < COLD.rewindEnd;
  // 되감는 동안 눈은 제 시계로 천천히 거꾸로 올라간다(구간마다 시각이 건너뛰어도 눈발이 튀지 않게)
  const rewindSnowT = (Tv, t) => (st.snow && t > st.snow.t + 0.6 ? DURATION + COLD.select - (Tv - COLD.select) * 3 : t);

  // ── 위쪽 큰 글자: 처음엔 낚는 말, 새해로 넘어가면 맺는 말 ──
  const failLine = tl.lines.find(ln => ln.fires[0] && !ln.fires[0].ok && !ln.fires[0].silent);
  const success = !!st.yearUp;
  // 문구는 copy.js에서 바꾼다. 낚는 말 둘째 줄은 비워 두면 대본에서 처음 오류가 나는 줄 번호로 만든다(대본을 고쳐도 어긋나지 않게).
  const C0 = window.COPY || {};
  const autoHook2 = failLine ? `${failLine.idx + 1}번째 줄에서 에러 납니다` : '마지막 줄까지 보세요';
  const COPY = {
    hook: [(C0.hook && C0.hook[0]) || '올해 삽질만 했다면', (C0.hook && C0.hook[1]) || autoHook2],
    final: [(C0.final && C0.final[0]) || '헛삽질은 없었습니다', (C0.final && C0.final[1]) || '올해도 수고 많으셨습니다'],
  };
  const HEAD = { y1: 334, y2: 424, px: 76 };
  const swapT = success ? st.yearUp.lock - 0.12 : Infinity;        // 연도판이 잠기는 순간 맺는 말이 펴지기 시작한다

  function headLayer(text, color) {
    const font = `400 ${HEAD.px}px "Black Han Sans", "Pretendard", sans-serif`;
    return U.layer('head|' + text + color, 1, 1, (g0, c) => {
      g0.font = font; const w = g0.measureText(text).width, pad = 44;
      c.width = Math.ceil(w + pad * 2); c.height = Math.ceil(HEAD.px * 1.3 + pad * 2);
      const gg = c.getContext('2d'); gg.font = font; gg.textAlign = 'center'; gg.textBaseline = 'middle'; gg.lineJoin = 'round';
      const x = c.width / 2, y = c.height / 2;
      gg.shadowColor = 'rgba(2,4,16,0.85)'; gg.shadowBlur = 22; gg.shadowOffsetY = 6;
      gg.lineWidth = 16; gg.strokeStyle = '#0b0f2a'; gg.strokeText(text, x, y);
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
    // 끝에서는 맺는 말이 접히고 낚는 말이 다시 펴져 첫 프레임과 이어진다(반복 재생할 때 글자가 뚝 바뀌지 않게)
    const loop = isFinite(swapT);
    const endOut = loop ? U.prog(Tv, DURATION - 0.26, DURATION - 0.12) : 0;
    const endIn = loop ? U.easeOutBack(U.prog(Tv, DURATION - 0.14, DURATION), 1.6) : 0;
    // 낚는 말은 첫 프레임부터 가만히 떠 있다(첫 프레임이 곧 미리보기 그림)
    if (Tv < swapT + 0.14 || endIn > 0) {
      const out = Tv < swapT + 0.14 ? 1 - U.prog(Tv, swapT, swapT + 0.14) : endIn;
      // 예고한 그 줄에서 정말 오류가 나는 순간: 둘째 줄이 빨갛게 덜컥
      const ft = failLine ? Tv - failLine.fireAt : -1;
      const hot = ft >= 0 && ft < 1.1 && Tv >= COLD.rewindEnd && Tv < swapT;
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
      const sp = Tv - (swapT + 0.2);                          // 맺는 말이 뜨는 순간 양옆으로 반짝
      if (sp > 0 && sp < 0.8) {
        g.save(); g.globalCompositeOperation = 'lighter';
        for (let i = 0; i < 14; i++) {
          const a = (1 - sp / 0.8), ang = U.hash(i, 9) * Math.PI * 2, r = 60 + 420 * U.easeOutCubic(sp / 0.8) * (0.4 + U.hash(i, 10));
          U.dot(g, W / 2 + Math.cos(ang) * r, (HEAD.y1 + HEAD.y2) / 2 + Math.sin(ang) * r * 0.32, 26, i % 2 ? '#ffe14d' : '#ffffff', a * a, 0.25);
        }
        g.restore(); g.globalAlpha = 1;
      }
    }
  }

  // ── 되감기 표시 ──
  function drawRewind(Tv, frame) {
    if (!rewinding(Tv)) return;
    const q = (Tv - COLD.select) / (SRE - COLD.select);
    const a = U.bump(q, 0, 0.1, 0.78, 1);
    g.save();
    for (let i = 0; i < 5; i++) {                             // 가로 잡음 띠(무대 쪽만)
      const y = U.hash(frame, 40 + i) * H, hgt = 3 + U.hash(frame, 60 + i) * 12;
      g.fillStyle = `rgba(255,255,255,${(0.04 + 0.06 * U.hash(frame, 80 + i)) * a})`; g.fillRect(0, y, SPLIT, hgt);
    }
    const cx = 270, cy = 770, s = 50;                         // ◀◀
    g.globalAlpha = 0.92 * a; g.fillStyle = '#ffffff'; g.strokeStyle = '#0b0f2a'; g.lineWidth = 8; g.lineJoin = 'round';
    const nudge = -10 * ((Tv * 9) % 1);
    for (const dx of [-s * 0.55, s * 0.55]) {
      g.beginPath(); g.moveTo(cx + dx + s * 0.5 + nudge, cy - s * 0.62); g.lineTo(cx + dx - s * 0.5 + nudge, cy); g.lineTo(cx + dx + s * 0.5 + nudge, cy + s * 0.62); g.closePath();
      g.stroke(); g.fill();
    }
    g.restore(); g.globalAlpha = 1;
  }

  function drawDivider(amb) {
    g.save();
    const gr = g.createLinearGradient(SPLIT - 30, 0, SPLIT, 0);
    gr.addColorStop(0, 'rgba(0,0,10,0)'); gr.addColorStop(1, 'rgba(0,0,10,0.45)');
    g.fillStyle = gr; g.fillRect(SPLIT - 30, 0, 30, H);
    g.fillStyle = 'rgba(255,255,255,0.10)'; g.fillRect(SPLIT - 1, 0, 2, H);
    if (amb && amb.a > 0.01) {
      g.globalCompositeOperation = 'lighter';
      const lg = g.createLinearGradient(0, amb.y - 500, 0, amb.y + 500);
      lg.addColorStop(0, U.rgba(amb.color, 0)); lg.addColorStop(0.5, U.rgba(amb.color, 0.7 * amb.a)); lg.addColorStop(1, U.rgba(amb.color, 0));
      g.fillStyle = lg; g.fillRect(SPLIT - 2, amb.y - 500, 4, 1000);
    }
    g.restore();
  }

  // 코드 줄 → 무대: 줄이 실행되면 빛 하나가 그 효과가 생길 자리로 날아간다
  function drawCouriers(t) {
    for (const f of tl.fires) {
      if (!f.ok || f.silent) continue;
      const entry = Stage.REGISTRY[f.key]; if (!entry || !entry.target || entry.instant) continue;
      const from = { x: Editor.L.codeX - 8, y: Editor.lineY(tl, f.line, f.t) - 12 };
      Fx.courier(g, t, f.t, from, entry.target(st), entry.color || '#ffffff', Stage.COURIER);
    }
  }

  // 창 이름표: year 변수를 따라 바뀐다
  function fileNameAt(t) {
    if (!st.yearSet) return { name: 'untitled.py', ago: null };
    const setAt = tl.fires.find(f => f.ok && f.key === 'year =').t;
    if (t < setAt) return { name: 'untitled.py', ago: null };
    if (st.yearUp && t >= st.yearUp.lock) return { name: (st.yearSet.v + st.yearUp.by) + '.py', ago: t - st.yearUp.lock };
    return { name: st.yearSet.v + '.py', ago: t - setAt };
  }
  // 다 돌고 난 뒤의 맺음 한 줄: 오류 몇 건, 헛삽질 몇 건
  const lastRun = tl.fires.filter(f => !f.silent).pop();
  const errors = tl.fires.filter(f => !f.ok).length;
  const waste = st.dig ? (st.gildT != null ? 0 : st.dig.labeled) : 0;
  const status = lastRun ? { t: lastRun.t + 1.0, text: `오류 ${errors}건 · 헛삽질 ${waste}건` } : null;

  function render(frame) {
    const Tv = frame / FPS, t = storyTime(Tv), tE = editorTime(Tv), rw = rewinding(Tv), cleared = editorCleared(Tv);
    g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
    g.clearRect(0, 0, W, H);
    const out = Stage.draw(g, t, tl, st, { rewind: rw, snowT: rw ? rewindSnowT(Tv, t) : null });
    const fn = fileNameAt(tE);
    const selecting = Tv >= COLD.hold && Tv < COLD.select;
    Editor.draw(g, cleared ? DURATION + Tv : tE, tl, {
      ambient: out.ambient, fileName: cleared ? 'untitled.py' : fn.name, renamedAgo: cleared ? null : fn.ago, status,
      select: selecting || cleared ? U.prog(Tv, COLD.hold, COLD.hold + (COLD.select - COLD.hold) * 0.55) : 0,
      cleared, collapse: cleared ? (Tv - COLD.select) / 0.13 : 0,
      chip: selecting ? { text: '전체 선택', kind: 'select', age: Tv - COLD.hold } : (cleared && Tv < COLD.select + 0.34 ? { text: '삭제', kind: 'delete', age: Tv - COLD.select } : null),
    });
    drawDivider(out.ambient);
    if (!cleared) drawCouriers(tE);
    drawRewind(Tv, frame);
    drawHeadline(Tv);
    Fx.grain(g, frame, W, H, 0.05);
  }

  // 소리 합성용 시각표(영상 시각 기준)
  function events() {
    const ev = [{ t: 0, type: 'hook_slam' }];
    if (SRE > COLD.select) ev.push({ t: COLD.hold, type: 'select_all' }, { t: COLD.select, type: 'delete_all' }, { t: COLD.select, type: 'rewind', dur: SRE - COLD.select });
    for (const k of tl.keys) ev.push({ t: k.t, type: k.kind === 'enter' ? (k.ok ? 'enter' : 'enter_error') : k.kind, line: k.line });
    for (const f of tl.fires) {
      if (f.silent) continue;
      const key = f.ok ? f.key : f.tryKey;
      const entry = Stage.REGISTRY[key];
      if (f.ok && entry && !entry.instant) ev.push({ t: f.t, type: 'courier', key, dur: Stage.COURIER });
    }
    for (const e of Stage.soundEvents(st)) ev.push(e);
    if (isFinite(swapT)) ev.push({ t: swapT + 0.12, type: 'final_message' });
    ev.sort((a, b) => a.t - b.t);
    return ev.filter(e => e.t >= 0 && e.t < DURATION + 0.001).map(e => Object.assign({}, e, { t: Math.round(e.t * 10000) / 10000 }));
  }

  // 검증·소리 합성 쪽에서 쓰는 요약(줄별 실행 시각, 화면 배치)
  function summary() {
    return {
      script: scriptText.split('\n'),
      lines: tl.lines.map(ln => ({ idx: ln.idx, text: ln.text, row: ln.row, typeStart: ln.typeStart, typeEnd: ln.typeEnd, fireAt: ln.fireAt,
        ok: ln.fires[0].ok, silent: !!ln.fires[0].silent, error: ln.fires[0].error, key: ln.fires[0].key, args: ln.fires[0].args, log: ln.fires[0].log })),
      errorRows: tl.errorRows, env: tl.env, swapT: isFinite(swapT) ? swapT : null, success, coldOpen: COLD, copy: COPY, status,
      music: T.music || null,
      layout: { split: SPLIT, head: HEAD, editor: Editor.L, theme: Editor.THEME, stage: Stage.LAYOUT },
      state: { yearSet: st.yearSet, yearFail: st.yearFail, yearUp: st.yearUp, snow: st.snow, spawn: st.spawn, count: st.count, say: st.say, fw: st.fw, gildT: st.gildT,
        bursts: st.bursts.length,
        dig: st.dig ? { t: st.dig.t, n: st.dig.n, D: st.dig.D, h: st.dig.h, bands: st.dig.bands, labeled: st.dig.labeled } : null },
    };
  }

  const ready = (async () => {
    const need = ['500 32px "JetBrains Mono"', '700 32px "JetBrains Mono"', '800 32px "JetBrains Mono"', '500 32px "Pretendard"', '600 32px "Pretendard"',
      '700 32px "Pretendard"', '800 32px "Pretendard"', '400 32px "Black Han Sans"'];
    await Promise.all(need.map(f => document.fonts.load(f, '가a1')));
    await document.fonts.ready;
    render(0);
  })();

  window.REEL = { ready, render, events, summary, storyTime, canvas, fps: FPS, frames: FRAMES, duration: DURATION, width: W, height: H, tl, st, swapT };

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
