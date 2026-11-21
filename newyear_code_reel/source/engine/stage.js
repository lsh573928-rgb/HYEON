/* 왼쪽 무대 — 대본 한 줄이 실행될 때마다 그 값대로 장면이 한 겹씩 생긴다.
   대본이 부르는 이름이 실제로 하는 일은 engine/newyear.js의 C에 있다(화면 가운데 창에 뜨는 그 코드).
   여기 META는 그 이름마다 값의 범위, 한 줄 설명, 빛이 날아갈 자리만 적는다. 없는 이름은 NameError.
   줄거리: 올해(2026) 삽질 365번이 12달치 흙더미로 쌓인다 → 새해로 넘기려니 오류("수고했어" 누락)
          → 수고했어 한마디에 흙더미가 금빛으로 → 2027 → 불꽃. */
'use strict';
(function () {
  const U = window.U, Fx = window.Fx, Worker = window.Worker;
  const W = 540, H = 1920, CX = 270, TAU = Math.PI * 2;
  const GROUND = 1460;                                   // 흙더미 바닥선(이 아래는 앱의 계정 이름·자막이 얹히는 자리)
  const BANDS = 12, FULL_H = 410, BAND_H = FULL_H / BANDS; // 12달 = 410px(달마다 날 수만큼)
  const BASE_HALF = 210, TOP_HALF = 96;
  const YEAR_DAYS = 365;
  const BOARD = { cy: 570, cw: 92, ch: 132, gap: 8 };
  /* 박자: 영상 전체가 120bpm(한 박 0.5초) 격자 위에 있다 — 소리(audio.py)가 같은 격자로 음악을 깐다. */
  const COURIER = 0.25;                                  // 코드 줄에서 무대까지 빛이 날아오는 시간(8분음표)
  const COUNT_STEP = 0.5;                                // 카운트다운 한 박
  const ROLL = 1 / 3;                                    // 연도판 마지막 칸이 넘어가 '철컥' 잠기기까지
  const GILD_STEP = 0.0625;                              // 금빛이 한 달 올라가는 간격
  const DROP = 0.25;                                     // 연도판·삽질러가 떨어져 내려앉는 시간
  const COUNT_Y = 760;
  const WORKER_SCALE = 1.5;
  const MONTH_NOTES = ['계획', '시작', '어라?', '다시', '또다시', '수정', '재수정', '최종', '진짜최종', '찐최종', '마무리', '완성'];
  const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  // 달마다 날 수만큼 두껍다(2월이 가장 얇다). BAND_TOP[k] = k번째 달이 끝나는 높이(px)
  const BAND_TOP = (function () { let acc = 0; return MONTH_DAYS.map(d => (acc += d) / YEAR_DAYS * FULL_H); })();
  const bandBottom = (k) => (k ? BAND_TOP[k - 1] : 0);
  const CUM_DAYS = (function () { let a = 0; return MONTH_DAYS.map(d => (a += d)); })();
  // 삽질 박자: 1~10월은 8분음표(0.25초)마다, 11·12월은 16분음표로 몰아서 닫힌다(삽질 시작 기준 시각, 12월이 2.75초)
  const DIG_GRID = Array.from({ length: 10 }, (_, k) => 0.25 * (k + 1)).concat([2.625, 2.75]);
  const SOIL = ['#5e4740', '#6d5348'];
  const GOLD = ['#f3b63a', '#ffd15e'];

  let REWIND = false;                                    // 되감는 중인지(draw가 켠다)
  /* 이름마다: args = 값 검사([이름, 최소, 최대, 넘었을 때 말] 또는 [이름, 'string']),
     log = 터미널에 찍을 한 줄, target = 대본 줄에서 날아온 빛이 닿는 자리, instant = 빛 없이 바로 */
  const META = {
    'year =': {
      args: [['year', 1000, 9998]],
      log: (a) => `올해는 ${a[0]}년`,
      target: () => ({ x: CX, y: BOARD.cy }), color: '#bcd4ff',
    },
    'snow.fall': {
      args: [['눈', 0, 1500]],
      log: (a) => `눈 ${a[0]}송이`,
      target: () => ({ x: 400, y: 250 }), color: '#eaf2ff',
    },
    '= 삽질러': {
      args: [],
      log: () => '삽질러 등장',
      target: () => ({ x: CX, y: GROUND - 70 }), color: '#ffc93c',
    },
    '삽질러.삽질': {
      args: [['삽질', 1, 100000]],                         // 1년 365일 검사는 newyear.js가 한다
      log: (a) => `삽질 ${a[0]}번 = ${a[0]}일`,
      target: () => ({ x: CX, y: GROUND - 90 }), color: '#ffb347',
    },
    'countdown': {
      args: [['카운트', 1, 5]],
      log: (a) => Array.from({ length: a[0] }, (_, i) => a[0] - i).join(' · '),
      target: () => ({ x: CX, y: COUNT_Y }), color: '#ffffff',
    },
    'year +=': {
      args: [['더할 값', 1, 1, '한 해씩만 넘어갑니다']],
      log: (a, env) => `${env.year}년 도착`,
      instant: true, target: () => ({ x: CX, y: BOARD.cy }), color: '#ffd479',
    },
    'say': {
      args: [['할 말', 'string']],
      log: (a) => `"${a[0]}" 한마디`,
      target: (st) => ({ x: CX + 120, y: GROUND - (st.dig ? st.dig.h : 0) - 137 * WORKER_SCALE - 66 }), color: '#ffe9a8',
    },
    'fireworks': {
      args: [['불꽃', 1, 60]],
      log: (a) => a[0] === 12 ? '불꽃 12발 · 열두 달' : `불꽃 ${a[0]}발`,
      target: () => ({ x: CX, y: GROUND - 16 }), color: '#ff9ac8',
    },
  };
  // 타임라인에 넘기는 표: 이름 → { fn(실제로 하는 일), 검사·설명·자리 }
  const NY = window.NEWYEAR();
  const REGISTRY = {};
  for (const key of Object.keys(META)) REGISTRY[key] = Object.assign({ fn: NY.C[key.replace(/^say$/, 'say')] }, META[key]);

  // ───────────── 실행된 줄 → 무대 상태 ─────────────
  function collect(tl) {
    const st = { yearSet: null, yearFail: null, yearUp: null, snow: null, spawn: null, dig: null, count: null, say: null, fw: null, bursts: [], sfx: [] };
    let daysBefore = 0;
    for (const f of tl.fires) {
      if (f.silent) continue;
      const key = f.ok ? f.key : f.tryKey;
      const entry = REGISTRY[key];
      if (!entry) continue;
      const t = f.t + (entry.instant ? 0 : COURIER);
      if (!f.ok) { if (key === 'year +=' && !st.yearFail) st.yearFail = { t, fireT: f.t, message: f.error.message }; continue; }
      const a = f.args, env = f.env;                      // env: 그 줄을 실행한 직후의 상태(newyear.js가 바꾼 값)
      if (key === 'year =') st.yearSet = { t, fireT: f.t, v: env.year };
      else if (key === 'snow.fall') st.snow = { t, fireT: f.t, n: env.snow };
      else if (key === '= 삽질러') st.spawn = { t, fireT: f.t };
      else if (key === '삽질러.삽질') {
        const n = env.days - daysBefore; daysBefore = env.days;   // 이번에 더해진 날 수
        st.dig = { t, fireT: f.t, n, D: digDuration(n), h: env.days / YEAR_DAYS * FULL_H };
      }
      else if (key === 'countdown') st.count = { t, fireT: f.t, n: env.beats.length };
      else if (key === 'year +=') st.yearUp = { t, fireT: f.t, by: env.year - env.year0, lock: t + ROLL };
      else if (key === 'say') st.say = { t, fireT: f.t, text: String(a[0]), thanked: env.thanked };
      else if (key === 'fireworks') st.fw = { t, fireT: f.t, n: env.shells.length, months: env.shells };
    }
    if (st.dig) prepareDig(st);
    if (st.fw) st.bursts = planFireworks(st, st.fw.t, st.fw.n, st.fw.months);
    // 금빛은 말풍선이 뜨고 한 박 뒤부터 차오른다
    st.gildT = st.say && st.say.thanked && st.dig ? st.say.t + 0.5 : null;
    return st;
  }
  // 삽질하는 동안 지금 며칠째인지(코드 창의 d 값과 같은 수)
  function dayAt(st, t) { return st.dig ? Math.round(digCountAt(st.dig, t - st.dig.t)) : 0; }

  // ───────────── 삽질: 몇 번째 삽인지 / 어디까지 쌓였는지 ─────────────
  // 삽질 시작 뒤 tau초에 몇 번째 삽인지: 달이 닫히는 박자(DIG_GRID)마다 그 달 말일에 닿도록 곧게 잇는다
  function digCountAt(d, tau) {
    if (tau <= 0) return 0;
    let k = 0; while (k < 12 && tau > DIG_GRID[k]) k++;
    if (k >= 12) return d.n;
    const t0 = k ? DIG_GRID[k - 1] : 0, c0 = k ? CUM_DAYS[k - 1] : 0;
    return Math.min(d.n, c0 + (CUM_DAYS[k] - c0) * (tau - t0) / (DIG_GRID[k] - t0));
  }
  // n번째 삽이 떨어지는 시각 = 삽질이 끝나는 시각
  function digDuration(n) {
    let k = 0; while (k < 11 && CUM_DAYS[k] < n) k++;
    const t0 = k ? DIG_GRID[k - 1] : 0, c0 = k ? CUM_DAYS[k - 1] : 0;
    return t0 + (DIG_GRID[k] - t0) * (n - c0) / (CUM_DAYS[k] - c0);
  }
  // 지금 쌓고 있는 달과 그 달 안에서의 진행(0..1) — 삽 한 번 휘두르는 동작이 한 달이다
  function digBand(tau) {
    let k = 0; while (k < 11 && tau > DIG_GRID[k]) k++;
    const t0 = k ? DIG_GRID[k - 1] : 0;
    return { k, t0, dur: DIG_GRID[k] - t0, ph: U.clamp01((tau - t0) / (DIG_GRID[k] - t0)) };
  }
  function bandsShown(h) { let n = 0; while (n < BANDS && bandBottom(n) < h - 0.5) n++; return n; }
  function prepareDig(st) {
    const d = st.dig;
    d.bands = bandsShown(d.h);
    d.bandT = [];                                             // 이름표가 붙는 시각(다 찬 달만)
    for (let k = 0; k < 12 && CUM_DAYS[k] <= d.n; k++) d.bandT.push(d.t + DIG_GRID[k]);
    d.labeled = d.bandT.length;
    d.clods = [];                                             // 흙덩이: 달마다 네 덩이
    for (let k = 0; k < 12; k++) {
      const t0 = k ? DIG_GRID[k - 1] : 0, dur = DIG_GRID[k] - t0;
      if (t0 >= d.D) break;
      for (let j = 0; j < 4; j++) { const born = t0 + dur * (0.3 + 0.14 * j); if (born < d.D) d.clods.push({ born, fl: Math.min(0.2, dur * 0.8) }); }
    }
  }
  function fillH(st, t) {
    if (!st.dig) return 0;
    return digCountAt(st.dig, t - st.dig.t) / YEAR_DAYS * FULL_H;
  }
  const halfAt = (y) => BASE_HALF - (BASE_HALF - TOP_HALF) * ((GROUND - y) / FULL_H);

  // ───────────── 불꽃 계획 ─────────────
  const FW_COLORS = [['#ffd76a', '#fff3d1'], ['#ff7f9f', '#ffd1e6'], ['#7ce8ff', '#e0fbff'], ['#b89bff', '#efe6ff'], ['#7cf0a4', '#e3ffe9'], ['#ffa46b', '#ffe3c2'], ['#ffffff', '#ffd76a']];
  /* n발. 한 발씩 차례로 그 달의 흙띠 옆구리에서 솟는다(12발이면 달마다 한 발).
     작은 꽃들이 양옆에서 16분음표 간격으로 → 금빛 버들 네 발이 높이 → 마지막 한 발은 삽 모양. */
  function planFireworks(st, t0, n, months) {
    const out = [];
    const hasShovel = n >= 4, willows = n >= 9 ? 4 : 0, smalls = n - willows - (hasShovel ? 1 : 0);
    const step = smalls > 1 ? Math.min(0.125, 0.75 / (smalls - 1)) : 0;
    const bandsUp = st.dig ? st.dig.bands : 0;
    const types = ['peony', 'double', 'ring', 'peony', 'double', 'peony'];
    for (let i = 0; i < n; i++) {
      const h1 = U.hash(i, 501), h2 = U.hash(i, 502), h3 = U.hash(i, 503), h4 = U.hash(i, 504);
      const side = i % 2 ? 1 : -1;
      const col = FW_COLORS[(i * 3 + 1) % FW_COLORS.length];
      let burstT, x, y, R, type, color = col[0], color2 = col[1], nP, life, shape = null;
      if (i < smalls) {
        burstT = t0 + 0.25 + i * step;
        const high = i % 4 === 2;                             // 몇 발은 제목 위로 높이
        x = CX + side * (150 + h2 * 80); y = high ? 250 + h3 * 80 : 700 + h3 * 190;
        R = 90 + h4 * 38; type = types[i % types.length]; nP = 64 + Math.floor(h2 * 26); life = 1.0;
      } else if (i < smalls + willows) {
        const k = i - smalls;
        burstT = t0 + 0.5 + k * 0.25;
        x = [128, 414, 452, 270][k]; y = [330, 300, 770, 292][k]; R = [150, 150, 118, 170][k];
        type = 'willow'; color = '#ffd76a'; color2 = '#fff3d1'; nP = 120; life = 3.6;
      } else {
        burstT = t0 + 1.5; x = 96; y = 806; R = 120; type = 'shape'; shape = 'shovel'; color = '#ffd76a'; color2 = '#ffffff'; nP = 0;
      }
      const rise = 0.3 + 0.1 * h4;
      // 쏘는 자리: (i번째) 달의 옆구리. 쌓인 달이 없으면 바닥에서.
      let lx = x, ly = GROUND - 8, band = -1;
      if (bandsUp > 0) {
        band = (months ? months[i] : i) % bandsUp;
        const ym = GROUND - (bandBottom(band) + Math.min(BAND_TOP[band], st.dig.h)) / 2;
        lx = CX + side * (halfAt(ym) - 6); ly = ym;
      }
      out.push({ t0: burstT - rise, rise, x, y, ground: ly, drift: lx - x, color, color2, n: nP, R, type, shape, seed: 1000 + i * 17, life, band, h1 });
    }
    return out;
  }
  // 삽 모양 불꽃: 점들이 터져 나와 삽 모양으로 잠깐 모였다가 흩어진다(찾는 재미)
  let shovelPts = null;
  function getShovelPts() {
    if (shovelPts) return shovelPts;
    const c = document.createElement('canvas'); c.width = 120; c.height = 220;
    const g = c.getContext('2d', { willReadFrequently: true });
    g.fillStyle = '#fff'; g.strokeStyle = '#fff'; g.lineCap = 'round';
    g.lineWidth = 13; g.beginPath(); g.moveTo(60, 24); g.lineTo(60, 128); g.stroke();          // 자루
    g.lineWidth = 13; g.beginPath(); g.moveTo(34, 22); g.lineTo(86, 22); g.stroke();           // 손잡이
    g.beginPath(); g.moveTo(20, 120); g.lineTo(100, 120); g.lineTo(100, 160); g.quadraticCurveTo(94, 198, 60, 214); g.quadraticCurveTo(26, 198, 20, 160); g.closePath(); g.fill();   // 삽날
    const data = g.getImageData(0, 0, 120, 220).data; const r = U.rng(31); const pts = [];
    for (let y = 3; y < 220; y += 6.5) for (let x = 3; x < 120; x += 6.5) {
      const jx = x + (r() - 0.5) * 3, jy = y + (r() - 0.5) * 3;
      if (data[(Math.round(jy) * 120 + Math.round(jx)) * 4 + 3] > 128) pts.push({ x: jx - 60, y: jy - 110, u: r(), v: r(), k: r() });
    }
    shovelPts = pts; return pts;
  }
  function drawShapeBurst(g, t, b) {
    Fx.firework(g, t, Object.assign({}, b, { n: 0, type: 'peony' }));          // 올라가는 불씨·섬광만
    const tau = t - (b.t0 + b.rise); if (tau < 0 || tau > 2.8) return;
    const pts = getShovelPts(); const rot = -0.3, sc = 1.0, cs = Math.cos(rot), sn = Math.sin(rot);
    g.save(); g.globalCompositeOperation = 'lighter';
    for (const p of pts) {
      const q = U.clamp01(tau / (0.3 + 0.14 * p.u)), e = U.easeOutCubic(q);
      const tx = b.x + (p.x * cs - p.y * sn) * sc, ty = b.y + (p.x * sn + p.y * cs) * sc;
      const over = Math.sin(Math.PI * Math.min(1, q)) * (1 - q) * 46 * (0.3 + p.k), ang = p.v * TAU;
      const fall = tau > 1.7 ? (tau - 1.7) : 0;                          // 한동안 삽 모양으로 떠 있다가 금가루로 흩어진다
      const x = U.lerp(b.x, tx, e) + Math.cos(ang) * over + (p.v - 0.5) * 30 * fall;
      const y = U.lerp(b.y, ty, e) + Math.sin(ang) * over + 150 * fall * fall;
      const a = (1 - U.prog(tau, 1.8, 2.7)) * (q < 1 ? 1 : 0.72 + 0.28 * Math.sin(t * (9 + 9 * p.u) + p.v * 30));
      U.dot(g, x, y, 14, p.k < 0.3 ? '#ffffff' : '#ffd76a', a, 0.34);
    }
    g.restore(); g.globalAlpha = 1;
  }

  // ───────────── 배경 ─────────────
  const BG_STARS = (function () { const r = U.rng(8), o = []; for (let i = 0; i < 110; i++) o.push({ x: r() * W, y: Math.pow(r(), 1.2) * 1330, s: 0.6 + Math.pow(r(), 3) * 2.2, ph: r() * TAU, sp: 0.7 + r() * 2.2, big: r() > 0.9 }); return o; })();
  function drawStars(g, t, dimBy) {
    g.save(); g.globalCompositeOperation = 'lighter';
    for (const s of BG_STARS) {
      const tw = 0.6 + 0.4 * Math.sin(t * s.sp + s.ph);
      const a = tw * (0.4 + 0.5 * Math.min(1, s.s / 2)) * (1 - dimBy);
      U.dot(g, s.x, s.y, 5 + s.s * 5, '#ffffff', a, 0.22);
      if (s.big) {
        const len = (8 + s.s * 6) * (0.7 + 0.3 * tw);
        g.globalAlpha = a * 0.5; g.strokeStyle = '#ffffff'; g.lineWidth = 1.1;
        g.beginPath(); g.moveTo(s.x - len, s.y); g.lineTo(s.x + len, s.y); g.moveTo(s.x, s.y - len); g.lineTo(s.x, s.y + len); g.stroke();
      }
    }
    g.restore(); g.globalAlpha = 1;
  }
  function drawFar(g, t, lift, dawn) {
    g.save();
    if (dawn > 0.01) {                                      // 해돋이 직전의 빛
      const dg = g.createLinearGradient(0, GROUND - 520, 0, GROUND);
      dg.addColorStop(0, 'rgba(255,150,110,0)'); dg.addColorStop(0.6, `rgba(255,140,105,${0.26 * dawn})`); dg.addColorStop(1, `rgba(255,205,130,${0.62 * dawn})`);
      g.fillStyle = dg; g.fillRect(0, GROUND - 520, W, 520);
      g.globalCompositeOperation = 'lighter';
      g.save(); g.translate(CX, GROUND - 30); g.scale(1, 0.42); U.dot(g, 0, 0, 1100, '#ffb46a', 0.5 * dawn, 0.06); g.restore();
      g.globalCompositeOperation = 'source-over'; g.globalAlpha = 1;
    }
    g.fillStyle = U.mix(U.mix('#141c4e', '#2a3478', lift * 0.5), '#3d2f66', dawn * 0.7);
    g.beginPath(); g.moveTo(0, GROUND + 40);
    for (let x = 0; x <= W; x += 10) g.lineTo(x, GROUND - 96 - 58 * Math.sin(x / W * Math.PI * 1.1 + 0.4) - 22 * Math.sin(x / 47 + 1.3));
    g.lineTo(W, GROUND + 40); g.closePath(); g.fill();
    g.fillStyle = U.mix(U.mix('#1b2660', '#34408c', lift * 0.5), '#33295f', dawn * 0.7);
    g.beginPath(); g.moveTo(0, GROUND + 40);
    for (let x = 0; x <= W; x += 10) g.lineTo(x, GROUND - 44 - 34 * Math.sin(x / W * Math.PI * 1.7 + 2.2) - 10 * Math.sin(x / 31));
    g.lineTo(W, GROUND + 40); g.closePath(); g.fill();
    g.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 10; i++) {                         // 멀리 마을 불빛
      const hx = 16 + U.hash(i, 61) * (W - 32), hy = GROUND - 26 - U.hash(i, 62) * 40;
      U.dot(g, hx, hy, 14, '#ffcf87', 0.5 + 0.2 * Math.sin(t * 1.3 + i), 0.3);
    }
    g.restore(); g.globalAlpha = 1;
  }
  function drawGround(g, t, st, lift, gold, pile) {
    g.save();
    const gr = g.createLinearGradient(0, GROUND - 10, 0, H);
    gr.addColorStop(0, U.mix('#8e9bd6', '#c9d4ff', U.clamp01(lift * 0.9)));
    gr.addColorStop(0.1, U.mix('#55629f', '#8d9ad6', U.clamp01(lift * 0.8)));
    gr.addColorStop(0.4, '#1f2756');
    gr.addColorStop(1, '#070a1a');                         // 아래쪽은 어둡게(앱 자막이 얹히는 자리)
    g.fillStyle = gr;
    g.beginPath(); g.moveTo(0, H);
    for (let x = 0; x <= W; x += 6) g.lineTo(x, GROUND + 5 * Math.sin(x / 71 + 1) + 3 * Math.sin(x / 23));
    g.lineTo(W, H); g.closePath(); g.fill();
    // 흙더미 그림자
    const h = fillH(st, t);
    if (h > 2) { g.fillStyle = 'rgba(20,24,70,0.28)'; g.beginPath(); g.ellipse(CX + 14, GROUND + 14, BASE_HALF + 26, 20, 0, 0, TAU); g.fill(); }
    g.globalCompositeOperation = 'lighter';
    if (gold > 0.01) { g.save(); g.translate(CX, GROUND + 30); g.scale(1, 0.22); U.dot(g, 0, 0, 900, '#ffc45a', 0.5 * gold, 0.08); g.restore(); }
    for (let i = 0; i < 46; i++) {                          // 눈밭 반짝임
      const x = U.hash(i, 71) * W, y = GROUND + 14 + U.hash(i, 72) * 300;
      const a = Math.max(0, Math.sin(t * (1.2 + U.hash(i, 73) * 2.2) + U.hash(i, 74) * TAU));
      U.dot(g, x, y, 9, gold > 0.5 && i % 3 === 0 ? '#ffe9a8' : '#ffffff', 0.5 * a * a * (0.5 + pile * 0.5), 0.4);
    }
    g.restore(); g.globalAlpha = 1;
  }

  // ───────────── 흙더미(12달) ─────────────
  function bandGild(st, t, k) { return st.gildT == null ? 0 : U.prog(t - (st.gildT + k * GILD_STEP), 0, 0.26); }
  // 그 달에서 불꽃이 솟는 순간 띠가 번쩍
  function bandFlash(st, t, k) {
    let f = 0;
    for (const b of st.bursts) if (b.band === k) f = Math.max(f, U.bump(t - b.t0, 0, 0.03, 0.06, 0.32));
    return f;
  }
  function drawMound(g, t, st, lift) {
    if (!st.dig) return;
    const h = fillH(st, t); if (h <= 0.5) return;
    const digging = t < st.dig.t + st.dig.D;
    g.save();
    // 금빛일 때 뒤로 번지는 빛
    const gAll = st.gildT == null ? 0 : U.prog(t - st.gildT, 0.1, 1.1);
    if (gAll > 0.01) { g.globalCompositeOperation = 'lighter'; U.dot(g, CX, GROUND - h * 0.5, 900, '#ffb340', 0.3 * gAll * (0.9 + 0.1 * Math.sin(t * 2.3)), 0.08); g.globalCompositeOperation = 'source-over'; }
    const nb = bandsShown(h);
    for (let k = 0; k < nb; k++) {
      const yb = GROUND - bandBottom(k), yt = Math.max(GROUND - h, GROUND - BAND_TOP[k]);
      const hb = halfAt(yb), ht = halfAt(yt), gk = bandGild(st, t, k);
      g.beginPath(); g.moveTo(CX - hb, yb); g.lineTo(CX + hb, yb); g.lineTo(CX + ht, yt); g.lineTo(CX - ht, yt); g.closePath();
      const soil = SOIL[k % 2], gold = GOLD[k % 2];
      const gr = g.createLinearGradient(0, yt, 0, yb);
      gr.addColorStop(0, U.mix(U.mix(soil, '#8a6d5c', 0.35), U.mix(gold, '#fff6cf', 0.45), gk));
      gr.addColorStop(0.3, U.mix(soil, gold, gk));
      gr.addColorStop(1, U.mix(U.mix(soil, '#2a1c20', 0.45), U.mix(gold, '#b06f12', 0.55), gk));
      g.fillStyle = gr; g.fill();
      // 왼쪽은 달빛, 오른쪽은 그늘
      const side = g.createLinearGradient(CX - hb, 0, CX + hb, 0);
      side.addColorStop(0, `rgba(255,255,255,${0.10 + 0.12 * gk})`); side.addColorStop(0.35, 'rgba(255,255,255,0)'); side.addColorStop(1, `rgba(10,8,30,${0.30 - 0.12 * gk})`);
      g.fillStyle = side; g.fill();
      // 금으로 바뀌는 순간 띠를 훑는 빛
      if (gk > 0 && gk < 1) { g.fillStyle = `rgba(255,255,255,${0.75 * Math.sin(Math.PI * gk)})`; g.fill(); }
      const fl = REWIND ? 0 : bandFlash(st, t, k);
      if (fl > 0.01) { g.fillStyle = `rgba(255,250,225,${0.7 * fl})`; g.fill(); }
      g.strokeStyle = gk > 0.5 ? 'rgba(120,70,0,0.55)' : 'rgba(22,12,16,0.7)'; g.lineWidth = 2.5;
      g.beginPath(); g.moveTo(CX - hb, yb); g.lineTo(CX + hb, yb); g.stroke();
    }
    // 윤곽
    const yTop = GROUND - h, hT = halfAt(yTop);
    g.strokeStyle = gAll > 0.5 ? 'rgba(255,240,190,0.9)' : 'rgba(20,14,34,0.85)'; g.lineWidth = 3; g.lineJoin = 'round';
    g.beginPath(); g.moveTo(CX - BASE_HALF, GROUND); g.lineTo(CX - hT, yTop); g.lineTo(CX + hT, yTop); g.lineTo(CX + BASE_HALF, GROUND); g.stroke();
    // 맨 위에 쌓이는 눈(삽질이 끝난 뒤부터)
    const cap = digging ? 0 : U.prog(t - (st.dig.t + st.dig.D), 0.3, 2.5) * (st.snow ? 1 : 0);
    if (cap > 0.01) {
      g.fillStyle = '#f2f6ff'; g.globalAlpha = Math.min(1, cap * 1.4);
      g.beginPath(); g.moveTo(CX - hT - 3, yTop + 3);
      const segs = 7;
      for (let i = 0; i <= segs; i++) { const x = CX - hT - 3 + (2 * hT + 6) * i / segs; g.lineTo(x, yTop - 4 - 5 * cap * (0.6 + 0.4 * Math.sin(i * 2.1 + 0.5))); }
      g.lineTo(CX + hT + 3, yTop + 3);
      for (let i = segs; i >= 0; i--) { const x = CX - hT - 3 + (2 * hT + 6) * i / segs; g.lineTo(x, yTop + 4 + (i % 2 ? 5 : 1) * cap); }
      g.closePath(); g.fill(); g.globalAlpha = 1;
    }
    // 금빛 반짝임
    if (gAll > 0.05) {
      g.globalCompositeOperation = 'lighter';
      for (let i = 0; i < 26; i++) {
        const v = U.hash(i, 91), yy = GROUND - 8 - v * (h - 16), hh = halfAt(yy) - 10, xx = CX + (U.hash(i, 92) * 2 - 1) * hh;
        if (Math.abs(xx - LABEL_X) < 88) continue;            // 이름표 글자 위에는 뿌리지 않는다
        const a = Math.pow(Math.max(0, Math.sin(t * (1.6 + 2.4 * U.hash(i, 93)) + U.hash(i, 94) * TAU)), 3) * gAll;
        U.dot(g, xx, yy, 22, '#ffffff', 0.9 * a, 0.25);
        if (a > 0.3) { g.globalAlpha = a * 0.8; g.strokeStyle = '#fffbe6'; g.lineWidth = 1.4; const l = 12 * a; g.beginPath(); g.moveTo(xx - l, yy); g.lineTo(xx + l, yy); g.moveTo(xx, yy - l); g.lineTo(xx, yy + l); g.stroke(); }
      }
    }
    g.restore(); g.globalAlpha = 1;
  }
  // 달 이름표(두 세상 공통). plate: 글자 흙더미 위에서는 어두운 바탕을 깔아 읽히게 한다(0..1)
  const LABEL_X = CX - 34;                               // 이름표 가운데(삽질러와 삽이 오른쪽에 서므로 왼쪽으로 비켜 둔다)
  function drawMoundLabels(g, t, st, plate) {
    if (!st.dig) return;
    const h = fillH(st, t); if (h <= 0.5) return;
    for (let k = 0; k < st.dig.labeled; k++) {
      const born = st.dig.bandT[k]; if (t < born) continue;
      const gk = bandGild(st, t, k);
      // 붙는 순간 크게 '톡' 하고 나타났다가 제자리 크기로 줄어든다(전화 화면에서도 읽히게)
      const pop = 1 + 0.8 * (1 - U.easeOutCubic(U.prog(t - born, 0, 0.24)));
      const cy = GROUND - (bandBottom(k) + BAND_TOP[k]) / 2 + 1, month = (k + 1) + '월', note = MONTH_NOTES[k];
      g.save(); g.translate(LABEL_X, cy); g.scale(pop, pop); g.globalAlpha = U.prog(t - born, 0, 0.05);
      g.textBaseline = 'middle';
      const fMonth = '700 22px "Pretendard", sans-serif', fNote = '800 27px "Pretendard", sans-serif';   // 달은 작게, 그 달의 한마디는 크게
      g.font = fMonth; const wm = g.measureText(month).width;
      g.font = fNote; const wn = g.measureText(note).width;
      const total = wm + 9 + wn; let x = -total / 2;
      if (plate > 0.01) {
        const a0 = g.globalAlpha; g.globalAlpha = a0 * plate;
        U.roundRect(g, -total / 2 - 11, -15, total + 22, 30, 9); g.fillStyle = U.mix('#1c1520', '#2a1f06', gk); g.fill();
        g.globalAlpha = a0;
      }
      g.textAlign = 'left';
      g.font = fMonth; g.fillStyle = U.mix(U.mix('#c9b196', '#7a4d06', gk), U.mix('#bfa98f', '#ffd15e', gk), plate); g.fillText(month, x, 1); x += wm + 9;
      g.font = fNote; g.fillStyle = U.mix(U.mix('#fff1d6', '#3d2200', gk), U.mix('#fff4e0', '#ffe9a8', gk), plate); g.fillText(note, x, 0);
      g.restore(); g.globalAlpha = 1;
    }
  }

  // 치수선: 도면처럼 높이를 적는다 (H = 365삽)
  function drawDimension(g, t, st) {
    if (!st.dig) return;
    const tau = t - (st.dig.t + st.dig.D); if (tau < 0) return;
    const p = U.easeOutCubic(U.prog(tau, 0.05, 0.6)); const h = st.dig.h;
    const x = 46, yb = GROUND, yt = GROUND - h * p;
    const gilded = st.gildT != null && t > st.gildT + 0.5;
    g.save(); g.globalAlpha = 0.85 * U.prog(tau, 0, 0.15); g.strokeStyle = gilded ? '#ffe9a8' : '#cfe0ff'; g.fillStyle = g.strokeStyle; g.lineWidth = 1.6;
    g.beginPath(); g.moveTo(x, yb); g.lineTo(x, yt);
    g.moveTo(x - 9, yb); g.lineTo(CX - BASE_HALF - 4, yb);
    g.moveTo(x - 9, yt); g.lineTo(CX - halfAt(yt) - 8, yt); g.stroke();
    const arrow = (y, dir) => { g.beginPath(); g.moveTo(x, y); g.lineTo(x - 5, y + dir * 12); g.lineTo(x + 5, y + dir * 12); g.closePath(); g.fill(); };
    arrow(yb, -1); arrow(yt, 1);
    if (p > 0.6) {
      g.globalAlpha *= U.prog(p, 0.6, 1);
      g.translate(x - 14, (yb + yt) / 2); g.rotate(-Math.PI / 2);
      g.font = '800 28px "JetBrains Mono", "Pretendard", monospace'; g.textAlign = 'center'; g.textBaseline = 'alphabetic';
      g.fillText(`H = ${st.dig.n}삽`, 0, 0);
    }
    g.restore(); g.globalAlpha = 1;
  }

  // ───────────── 날아가는 흙덩이 ─────────────
  function drawClods(g, t, st, wx) {
    if (!st.dig) return;
    const d = st.dig, tau = t - d.t; if (tau < 0 || tau > d.D + 0.6) return;
    g.save();
    d.clods.forEach((c, j) => {
      const age = tau - c.born; if (age < 0 || age > c.fl + 0.25) return;
      const q = Math.min(1, age / c.fl);
      const h0 = digCountAt(d, c.born) / YEAR_DAYS * FULL_H, h1 = digCountAt(d, c.born + c.fl) / YEAR_DAYS * FULL_H;
      const sx = wx + 70 * WORKER_SCALE, sy = GROUND - h0 - 112 * WORKER_SCALE;
      const side = U.hash(j, 41) * 2 - 1;
      const ex = CX + side * (halfAt(GROUND - h1) - 14), ey = GROUND - h1;
      const x = U.lerp(sx, ex, q), y = U.lerp(sy, ey, q) - 70 * Math.sin(Math.PI * q) * (0.6 + 0.6 * U.hash(j, 42));
      if (age < c.fl) {
        const r = 6 + 4 * U.hash(j, 43);
        g.fillStyle = SOIL[j % 2]; g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
        g.strokeStyle = 'rgba(20,14,34,0.8)'; g.lineWidth = 1.6; g.stroke();
        g.fillStyle = 'rgba(255,255,255,0.8)'; g.beginPath(); g.arc(x - r * 0.25, y - r * 0.3, r * 0.42, 0, TAU); g.fill();
      } else {                                               // 떨어진 자리의 먼지
        const pa = (age - c.fl) / 0.25;
        g.globalAlpha = 0.5 * (1 - pa); g.fillStyle = '#e9dcd0';
        g.beginPath(); g.ellipse(ex, ey - 4 - 6 * pa, 10 + 16 * pa, 5 + 6 * pa, 0, 0, TAU); g.fill(); g.globalAlpha = 1;
      }
    });
    g.restore(); g.globalAlpha = 1;
  }

  // ───────────── 삽질러 ─────────────
  function workerState(t, st) {
    if (!st.spawn) return null;
    const tau = t - st.spawn.t; if (tau < 0) return null;
    const h = fillH(st, t);
    const o = { x: CX + 22, y: GROUND - h, scale: WORKER_SCALE, sx: 1, sy: 1, pose: Worker.POSES.idle, face: 'smile', look: 0, lookY: 0, blink: 0, snowCap: 0, ghost: null, clod: null, blush: 0.55, mark: null, drops: 0 };
    // 숨쉬기·눈 깜박임
    const idle = Object.assign({}, Worker.POSES.idle, { bob: 1.2 * Math.sin(t * 2.4) });
    o.pose = idle;
    const bl = ((t + 0.35) % 2.9); o.blink = bl < 0.12 ? Math.sin(Math.PI * bl / 0.12) : 0;
    // 하늘에서 '쿵' 하고 착지
    if (tau < DROP) { const q = tau / DROP; o.y = U.lerp(-140, GROUND - h, q * q); o.face = 'wow'; o.sy = 1.08; o.sx = 0.94; }
    else if (tau < DROP + 0.5) {
      const q = (tau - DROP) / 0.5;
      const sq = 1 - 0.24 * Math.exp(-7 * q) * Math.cos(q * 15);
      o.sy = sq; o.sx = 1 + (1 - sq) * 0.7; o.face = q < 0.35 ? 'o' : 'smile';
    }
    o.landT = st.spawn.t + DROP;
    // 착지한 뒤 화면을 보고 손 인사(삽질 전까지 심심하지 않게)
    const digT = st.dig ? st.dig.t : Infinity;
    const wv = tau - DROP - 0.35;
    if (wv > 0 && wv < 1.0 && t < digT - 0.15) {
      const up = U.smooth(U.prog(wv, 0, 0.18)) * (1 - U.smooth(U.prog(wv, 0.8, 1.0)));
      o.pose = Object.assign({}, idle, { h2x: U.lerp(17, -40, up), h2y: U.lerp(-37, -112 + 9 * Math.sin(wv * 26), up) });
      o.face = 'grin';
    }
    // 눈이 오기 시작하면 하늘을 올려다본다
    if (st.snow) {
      const sq = t - st.snow.t;
      if (sq > 0 && sq < 0.9 && t < digT - 0.1) { o.lookY = -1 * U.bump(sq, 0, 0.15, 0.7, 0.9); o.face = 'o'; }
      o.snowCap = 0.95 * U.prog(sq, 3, 9);
    }
    // 삽질: 삽 한 번이 한 달
    if (st.dig) {
      const d = st.dig, dt = t - d.t;
      if (dt >= -0.12 && dt < 0) o.pose = Worker.mixPose(idle, Worker.digPose(0), U.smooth((dt + 0.12) / 0.12));
      else if (dt >= 0 && dt < d.D) {
        const b = digBand(dt);
        o.pose = Worker.digPose(b.ph); o.face = b.ph > 0.12 && b.ph < 0.5 ? 'o' : 'smile';
        o.clod = b.ph > 0.42 && b.ph < 0.76 ? SOIL[0] : null;
        if (b.dur < 0.2) {                                    // 빨라지면 잔상과 땀방울
          o.ghost = [0.25, 0.5].map((dp, i) => ({ pose: Worker.digPose(b.ph + dp), alpha: 0.3 - i * 0.1 }));
          o.x += Math.sin(dt * 61) * 1.6; o.drops = 1; o.face = 'o';
        }
        o.snowCap = 0;
      } else if (dt >= d.D && dt < d.D + 0.7) {               // 휴 — 한숨 돌리기
        const q = dt - d.D;
        o.pose = Worker.mixPose(Worker.digPose(0), Worker.POSES.rest, U.smooth(q / 0.2)); o.face = q < 0.5 ? 'o' : 'smile';
        if (q > 0.45) o.pose = Worker.mixPose(Worker.POSES.rest, idle, U.smooth((q - 0.45) / 0.25));
        o.snowCap = 0;
      }
      if (dt >= d.D && st.snow) o.snowCap = 0.95 * U.prog(dt - d.D, 0.6, 4.5);
    }
    // 카운트다운: 숫자마다 폴짝, 위를 본다
    if (st.count) {
      const ct = t - st.count.t;
      if (ct >= -0.2 && ct < st.count.n * COUNT_STEP + 0.05) {
        o.lookY = -1 * U.prog(ct, -0.2, 0.1);
        if (ct >= 0) { const lt = ct % COUNT_STEP; o.y -= 9 * Math.max(0, Math.sin(Math.PI * lt / 0.26)) * (lt < 0.26 ? 1 : 0); o.face = 'o'; }
      }
    }
    // 실패: 깜짝 → 시무룩
    if (st.yearFail && !REWIND) {
      const ft = t - st.yearFail.t;
      const until = st.say ? st.say.t : Infinity;
      if (ft >= 0 && t < until + 0.02) {
        if (ft < 0.5) { o.y -= 16 * Math.max(0, Math.sin(Math.PI * ft / 0.3)) * (ft < 0.3 ? 1 : 0); o.face = 'wow'; o.lookY = -1; }
        else { o.face = 'sad'; o.lookY = 0.7 * U.prog(ft, 0.5, 0.8); o.pose = Object.assign({}, idle, { bob: 4 * U.prog(ft, 0.5, 0.8), lean: 0.05 * U.prog(ft, 0.5, 0.8) }); }
        if (ft > 0.55) o.mark = { text: '?', a: U.prog(ft, 0.55, 0.7), pop: U.easeOutBack(U.prog(ft, 0.55, 0.85), 3) };
      }
    }
    // 수고했어: 말풍선 쪽을 보고 활짝
    if (st.say) {
      const sq = t - st.say.t;
      if (sq >= 0) {
        o.mark = null; o.lookY = -0.5 * (1 - U.prog(sq, 1.2, 1.6)); o.look = 0.9 * (1 - U.prog(sq, 1.2, 1.6));
        o.face = sq < 0.2 ? 'o' : 'grin'; o.blush = 0.55 + 0.4 * U.prog(sq, 0.1, 0.4);
        o.pose = Object.assign({}, idle, { bob: idle.bob - 2 * Math.abs(Math.sin(sq * 5)) * (1 - U.prog(sq, 0.4, 1.0)) });
        if (!st.say.thanked) { o.face = 'smile'; }
        else if (st.gildT != null) {
          const gq = t - st.gildT;                           // 발밑이 금빛으로 차오른다: 내려다보며 깜짝
          if (gq > 0.05 && gq < 0.95) { o.look = 0; o.lookY = 1; o.face = 'wow'; o.y -= 7 * Math.abs(Math.sin(gq * 9)) * (1 - U.prog(gq, 0.4, 0.95)); }
        }
      }
    }
    // 새해: 연도판이 넘어가는 동안 올려다보다가, 잠기는 순간 만세
    if (st.yearUp) {
      const ut = t - st.yearUp.lock;
      if (t >= st.yearUp.t && ut < 0) { o.look = 0; o.lookY = -1; o.face = 'o'; }
      if (ut >= 0) {
        o.pose = Worker.mixPose(idle, Worker.POSES.cheer, U.easeOutBack(U.prog(ut, 0, 0.3), 1.6));
        o.face = 'grin'; o.look = 0; o.lookY = -0.6; o.blush = 0.95;
        const hop = ut < 0.5 ? 30 * Math.sin(Math.PI * ut / 0.5) : 9 * Math.abs(Math.sin((ut - 0.5) * Math.PI / 0.5));   // 그 뒤로는 박자마다 폴짝
        o.y -= hop;
      }
    }
    return o;
  }
  function drawWorker(g, t, st) {
    const o = workerState(t, st); if (!o) return null;
    // 착지 먼지
    const la = t - o.landT;
    if (la >= 0 && la < 0.45) {
      g.save(); g.globalAlpha = 0.55 * (1 - la / 0.45); g.fillStyle = '#eef3ff';
      for (const s of [-1, 1]) { g.beginPath(); g.ellipse(o.x + s * (24 + 60 * U.easeOutCubic(la / 0.45)), GROUND - fillH(st, t) - 6 - 10 * la, 16 + 12 * la, 9, 0, 0, TAU); g.fill(); }
      g.restore(); g.globalAlpha = 1;
    }
    g.save(); g.translate(o.x, o.y); g.scale(o.sx, o.sy); g.translate(-o.x, -o.y);
    Worker.draw(g, o.x, o.y, o.scale, o);
    g.restore();
    return o;
  }
  // 머리 위 표시(?) — 글자로 바꾸지 않고 또렷하게 얹는다
  function drawWorkerMark(g, t, st) {
    const o = workerState(t, st); if (!o) return;
    if (o.mark) {
      g.save(); g.translate(o.x + 84, o.y - 108 * o.scale); g.scale(o.mark.pop, o.mark.pop); g.rotate(0.2);
      g.font = '400 54px "Black Han Sans", "Pretendard", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.lineWidth = 8; g.strokeStyle = '#141833'; g.lineJoin = 'round'; g.globalAlpha = o.mark.a; g.strokeText(o.mark.text, 0, 0);
      g.fillStyle = '#ffffff'; g.fillText(o.mark.text, 0, 0); g.restore(); g.globalAlpha = 1;
    }
  }
  function drawSweat(g, t, o) {
    // 땀방울
    if (o.drops) {
      g.save(); g.fillStyle = '#9fd8ff';
      for (let i = 0; i < 3; i++) {
        const q = ((t * 3.1 + i * 0.37) % 1);
        g.globalAlpha = 0.9 * (1 - q);
        g.beginPath(); g.ellipse(o.x - 40 * o.scale - 26 * q - i * 4, o.y - 112 * o.scale - 14 * Math.sin(Math.PI * q) + i * 9, 4.5, 7, -0.6, 0, TAU); g.fill();
      }
      g.restore(); g.globalAlpha = 1;
    }
    return o;
  }
  // 알약 모양 계수판 하나
  function drawPill(g, x, y, scale, alpha, label, value, o) {
    if (alpha <= 0.003) return;
    g.save(); g.globalAlpha = alpha; g.translate(x, y); g.scale(scale, scale);
    g.font = '800 29px "Pretendard", sans-serif'; const w1 = g.measureText(label + ' ').width;
    g.font = '800 34px "Pretendard", sans-serif'; const w2 = g.measureText(o.widest || value).width + 2;
    const w = w1 + w2 + 40;
    U.roundRect(g, -w / 2, -29, w, 58, 29); g.fillStyle = o.bg || 'rgba(10,14,44,0.88)'; g.fill();
    g.lineWidth = 2.6; g.strokeStyle = o.edge; g.stroke();
    g.textBaseline = 'middle'; g.textAlign = 'left';
    g.font = '800 29px "Pretendard", sans-serif'; g.fillStyle = o.labelColor || '#ffffff'; g.fillText(label + ' ', -w / 2 + 20, 1);
    g.font = '800 34px "Pretendard", sans-serif'; g.fillStyle = o.valueColor; g.fillText(value, -w / 2 + 20 + w1, 1);
    g.restore(); g.globalAlpha = 1;
  }
  // 계수판 둘은 흙더미 윗면 양옆에 떠서, 쌓이는 만큼 삽질러와 함께 올라간다
  const hudY = (st, t) => GROUND - fillH(st, t) - 46;
  // 삽질 횟수판(왼쪽) + 날짜: 삽 한 번이 하루. 새해로 넘어가면 1월 1일이 된다.
  const pad2 = (n) => (n < 10 ? '0' : '') + n;
  function drawCounter(g, t, st, o) {
    if (!st.dig || !o) return;
    const d = st.dig, tau = t - d.t; if (tau < 0) return;
    const c = Math.round(digCountAt(d, tau));
    const pop = 1 + 0.22 * U.bump(tau - d.D, 0, 0.08, 0.1, 0.35);
    const a = U.prog(tau, 0, 0.12), y = hudY(st, t);
    drawPill(g, 98, y, 0.92 * pop, a, '삽질', String(c), { edge: tau >= d.D ? '#ffd76a' : 'rgba(255,255,255,0.35)', valueColor: '#ffd76a', widest: String(d.n) });
    const year = st.yearSet ? st.yearSet.v : 2026;
    const newYear = st.yearUp && t >= st.yearUp.lock;
    let txt;
    if (newYear) txt = `${year + st.yearUp.by}.01.01`;
    else { let day = Math.max(1, Math.min(YEAR_DAYS, Math.ceil(digCountAt(d, tau)))), m = 0; while (day > MONTH_DAYS[m]) { day -= MONTH_DAYS[m]; m++; } txt = `${year}.${pad2(m + 1)}.${pad2(day)}`; }
    const dp = newYear ? 1 + 0.3 * U.bump(t - st.yearUp.lock, 0, 0.08, 0.1, 0.4) : 1;
    g.save(); g.globalAlpha = a; g.translate(98, y - 48); g.scale(dp, dp);
    g.font = '800 25px "Pretendard", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineJoin = 'round';
    g.lineWidth = 6; g.strokeStyle = 'rgba(8,10,34,0.85)'; g.strokeText(txt, 0, 0);
    g.fillStyle = newYear ? '#ffd76a' : '#bfd4ff'; g.fillText(txt, 0, 0);
    g.restore(); g.globalAlpha = 1;
  }
  /* 헛삽질 계수기: 달이 쌓일 때마다 빨갛게 1, 2, 3 … 올라가다가(올해도 헛삽질만 한 것 같아서),
     "수고했어" 뒤 금빛이 차오르는 만큼 도로 내려가 0이 된다. */
  function wasteAt(st, t) {
    const d = st.dig; let up = 0, down = 0;
    for (const bt of d.bandT) if (t >= bt) up++;
    if (st.gildT != null) for (let k = 0; k < d.labeled; k++) if (t >= st.gildT + k * GILD_STEP + 0.03) down++;
    return { v: up - down, up, down };
  }
  function drawWaste(g, t, st) {
    if (!st.dig || !st.dig.bandT.length) return;
    const d = st.dig; if (t < d.bandT[0]) return;
    const w = wasteAt(st, t);
    const cleared = w.down >= d.labeled && d.labeled > 0;
    // 숫자가 바뀔 때마다 톡
    let last = d.bandT[0];
    for (const bt of d.bandT) if (t >= bt) last = bt;
    if (st.gildT != null) for (let k = 0; k < d.labeled; k++) { const gt = st.gildT + k * GILD_STEP + 0.03; if (t >= gt) last = Math.max(last, gt); }
    const pop = 1 + (cleared ? 0.34 : 0.16) * U.bump(t - last, 0, 0.05, 0.07, cleared ? 0.5 : 0.2);
    const col = cleared ? '#ffd76a' : '#ff6b7d';
    drawPill(g, 442, hudY(st, t), 0.92 * pop, U.prog(t - d.bandT[0], 0, 0.1), '헛삽질', String(w.v), { edge: col, valueColor: col, labelColor: cleared ? '#fff3d1' : '#ffd3d9', widest: '12', bg: cleared ? 'rgba(44,30,4,0.9)' : 'rgba(44,8,20,0.9)' });
    if (cleared) {                                          // 0이 되는 순간 반짝
      const q = t - last;
      if (q < 0.7) { g.save(); g.globalCompositeOperation = 'lighter'; U.dot(g, 442, hudY(st, t), 120 + 260 * U.easeOutCubic(q / 0.7), '#ffd76a', 0.55 * Math.pow(1 - q / 0.7, 2), 0.1); g.restore(); g.globalAlpha = 1; }
    }
  }

  // ───────────── 연도판(공항 안내판처럼 한 칸씩 넘어간다) ─────────────
  const FONT_DIGIT = '400 112px "Black Han Sans", "Pretendard", sans-serif';
  function digitLayer(d, gold) {
    return Fx.glowText('bd' + d + (gold ? 'g' : 'w'), d, FONT_DIGIT, gold ? '#ffe08a' : '#eef3ff', gold ? '#ff9d1e' : '#5f8bff', gold ? 18 : 10, null);
  }
  function drawBoard(g, t, st) {
    if (!st.yearSet) return;
    const tau = t - st.yearSet.t; if (tau < 0) return;
    const from = String(st.yearSet.v), to = st.yearUp ? String(st.yearSet.v + st.yearUp.by) : from, next = String(st.yearSet.v + 1);
    const n = from.length, total = n * BOARD.cw + (n - 1) * BOARD.gap, x0 = CX - total / 2 + BOARD.cw / 2;
    const up = st.yearUp ? t - st.yearUp.t : -1;              // 넘어가기 시작한 뒤
    const ul = st.yearUp ? t - st.yearUp.lock : -1;           // '철컥' 잠긴 뒤
    const fail = st.yearFail ? t - st.yearFail.t : -1;
    const failing = !REWIND && fail >= 0 && fail < 0.95 && (up < 0);
    let sx = 0;
    if (failing && fail > 0.16 && fail < 0.56) sx = Math.sin(fail * 75) * 9 * (1 - U.prog(fail, 0.16, 0.56));
    if (ul >= 0) {                                           // 금빛 후광 + 잠기는 순간 퍼지는 고리
      g.save(); g.globalCompositeOperation = 'lighter';
      U.dot(g, CX, BOARD.cy, 760, '#ffb340', 0.3 * U.prog(ul, 0, 0.35) * (0.9 + 0.1 * Math.sin(t * 2.7)), 0.08);
      if (ul < 0.8) {
        g.strokeStyle = '#ffd76a';
        for (const k of [0, 0.18]) { const qq = U.clamp01(ul / 0.8 - k); if (qq <= 0) continue; g.globalAlpha = 0.75 * (1 - qq); g.lineWidth = 7 * (1 - qq) + 1; g.beginPath(); g.ellipse(CX, BOARD.cy, 230 + 330 * U.easeOutCubic(qq), 90 + 230 * U.easeOutCubic(qq), 0, 0, TAU); g.stroke(); }
      }
      g.restore(); g.globalAlpha = 1;
    }
    for (let i = 0; i < n; i++) {
      const cx = x0 + i * (BOARD.cw + BOARD.gap) + sx;
      // 등장: 위에서 떨어져 통통
      const dropT = tau - i * 0.03;
      if (dropT < 0) continue;
      const q = U.clamp01(dropT / DROP);
      const yOff = dropT < DROP ? -(1 - q * q) * 640 : -30 * Math.exp(-9 * (dropT - DROP)) * Math.abs(Math.cos((dropT - DROP) * 17));
      const cy = BOARD.cy + yOff;
      const goldMix = ul >= 0 ? U.prog(ul, i * 0.05, 0.2 + i * 0.05) : 0;
      const pop = ul >= 0 ? 1 + 0.13 * U.bump(ul, i * 0.05, 0.1 + i * 0.05, 0.12 + i * 0.05, 0.45 + i * 0.05) : 1;
      g.save(); g.translate(cx, cy); g.scale(pop, pop);
      // 판
      U.roundRect(g, -BOARD.cw / 2, -BOARD.ch / 2, BOARD.cw, BOARD.ch, 14);
      const pg = g.createLinearGradient(0, -BOARD.ch / 2, 0, BOARD.ch / 2);
      pg.addColorStop(0, U.mix('#222a55', '#4a3410', goldMix)); pg.addColorStop(0.5, U.mix('#161c40', '#2e2008', goldMix)); pg.addColorStop(1, U.mix('#0e1330', '#1c1304', goldMix));
      g.fillStyle = pg; g.fill();
      const red = failing ? U.bump(fail, 0.1, 0.2, 0.5, 0.95) * (0.6 + 0.4 * Math.sin(fail * 26)) : 0;
      if (red > 0.01) { g.fillStyle = `rgba(255,70,90,${0.42 * red})`; g.fill(); }
      g.lineWidth = 2.5; g.strokeStyle = red > 0.05 ? `rgba(255,107,125,${0.5 + 0.5 * red})` : U.mix('#48539a', '#ffd76a', goldMix); g.stroke();
      // 숫자(칸 안에서만 보이게)
      g.save(); U.roundRect(g, -BOARD.cw / 2 + 3, -BOARD.ch / 2 + 3, BOARD.cw - 6, BOARD.ch - 6, 11); g.clip();
      const settleT = DROP + 0.02 + i * 0.06;                            // 내려앉으며 숫자가 촤르륵 돌다가 멈춘다
      const changes = from[i] !== next[i];
      if (dropT < settleT) {
        const flick = Math.floor(dropT / 0.05);
        const dgt = String((Number(from[i]) + 10 - (Math.floor(settleT / 0.05) - flick)) % 10);
        const ph = (dropT % 0.05) / 0.05;
        g.scale(1, 0.35 + 0.65 * ph); Fx.drawCentered(g, digitLayer(dgt, false), 0, 4, 1, 0.9);
      } else if (from[i] !== to[i] && up >= 0 && up < ROLL) {            // 넘어가는 중: 옛 숫자는 위로, 새 숫자는 아래에서 천천히 … 끝에서 철컥
        const roll = U.easeInOutCubic(U.prog(up, 0, ROLL));
        Fx.drawCentered(g, digitLayer(from[i], false), 0, 4 - roll * BOARD.ch, 1, 1);
        Fx.drawCentered(g, digitLayer(to[i], false), 0, 4 + (1 - roll) * BOARD.ch, 1, 1);
      } else if (changes && failing) {                                   // 반쯤 넘어가다 걸려서 도로 떨어진다
        let roll;
        if (fail < 0.16) roll = 0.64 * U.easeOutCubic(fail / 0.16);
        else if (fail < 0.56) roll = 0.64 + 0.03 * Math.sin(fail * 60);
        else roll = 0.64 * (1 - U.easeOutBack(U.prog(fail, 0.56, 0.8), 2.2));
        Fx.drawCentered(g, digitLayer(from[i], false), 0, 4 - roll * BOARD.ch, 1, 1);
        Fx.drawCentered(g, digitLayer(next[i], false), 0, 4 + (1 - roll) * BOARD.ch, 1, 1);
      } else {
        const cur = up >= ROLL ? to[i] : from[i];
        const bounce = ul >= 0 && from[i] !== to[i] ? -10 * Math.exp(-10 * ul) * Math.cos(ul * 30) : 0;   // 잠기는 순간 살짝 튕김
        if (goldMix < 1) Fx.drawCentered(g, digitLayer(cur, false), 0, 4 + bounce, 1, 1 - goldMix);
        if (goldMix > 0) Fx.drawCentered(g, digitLayer(cur, true), 0, 4 + bounce, 1, goldMix);
      }
      g.restore();
      // 가운데 경첩선
      g.fillStyle = 'rgba(4,6,20,0.7)'; g.fillRect(-BOARD.cw / 2 + 2, -2, BOARD.cw - 4, 3.5);
      g.fillStyle = 'rgba(255,255,255,0.10)'; g.fillRect(-BOARD.cw / 2 + 2, 1.5, BOARD.cw - 4, 1);
      g.fillStyle = U.mix('#6c78bd', '#ffd76a', goldMix);
      g.beginPath(); g.arc(-BOARD.cw / 2 + 1, 0, 4.5, 0, TAU); g.fill(); g.beginPath(); g.arc(BOARD.cw / 2 - 1, 0, 4.5, 0, TAU); g.fill();
      g.restore();
    }
  }

  /* 연도판 밑의 확인란. 처음부터 비어 있다가(복선), 새해로 못 넘어갈 때 빨갛게 깜박이고,
     say("수고했어") 뒤에 금빛으로 체크된다 — 코드를 안 읽어도 왜 막혔는지 보이게. */
  function drawCheckTag(g, t, st) {
    if (!st.yearSet) return;
    const tau = t - st.yearSet.t - 0.12; if (tau < 0) return;
    const q = U.clamp01(tau / DROP);
    const yOff = tau < DROP ? -(1 - q * q) * 520 : -14 * Math.exp(-9 * (tau - DROP)) * Math.abs(Math.cos((tau - DROP) * 17));
    const fail = st.yearFail ? t - st.yearFail.t : -1;
    const done = st.say && st.say.thanked ? t - st.say.t - 0.1 : -1;
    const failing = !REWIND && fail >= 0 && done < 0;
    const blink = failing ? (fail < 1.0 ? 0.55 + 0.45 * Math.sin(fail * 22) : 0.8) : 0;
    let sx = 0; if (failing && fail > 0.16 && fail < 0.56) sx = Math.sin(fail * 75) * 9 * (1 - U.prog(fail, 0.16, 0.56));
    const gold = done >= 0 ? U.prog(done, 0, 0.25) : 0;
    const pop = 1 + (done >= 0 ? 0.3 * U.bump(done, 0, 0.1, 0.12, 0.4) : 0) + (failing ? 0.1 * U.bump(fail, 0.1, 0.2, 0.22, 0.5) : 0);
    const x = CX + sx, y = BOARD.cy + BOARD.ch / 2 + 34 + yOff;
    g.save(); g.translate(x, y); g.scale(pop, pop);
    g.font = '800 26px "Pretendard", sans-serif'; const tw = g.measureText('수고했어').width;
    const w = tw + 74, h = 46;
    U.roundRect(g, -w / 2, -h / 2, w, h, 23);
    g.fillStyle = gold > 0 ? U.mix('#141a3c', '#3a2a06', gold) : (failing ? `rgba(60,10,24,${0.75 + 0.2 * blink})` : 'rgba(16,22,56,0.85)'); g.fill();
    const edge = gold > 0 ? U.mix('#6c78bd', '#ffd76a', gold) : (failing ? U.rgba('#ff6b7d', 0.5 + 0.5 * blink) : 'rgba(150,165,225,0.55)');
    g.lineWidth = 2.4; g.strokeStyle = edge; g.stroke();
    const bx = -w / 2 + 28;                                 // 네모 칸
    U.roundRect(g, bx - 11, -11, 22, 22, 5); g.lineWidth = 2.4; g.strokeStyle = edge; g.stroke();
    if (gold > 0) {
      g.strokeStyle = '#ffe08a'; g.lineWidth = 4; g.lineCap = 'round'; g.lineJoin = 'round';
      const p1 = U.clamp01(gold / 0.4), p2 = U.clamp01((gold - 0.4) / 0.6);
      g.beginPath(); g.moveTo(bx - 7, 0); g.lineTo(U.lerp(bx - 7, bx - 2, p1), U.lerp(0, 6, p1));
      if (p2 > 0) g.lineTo(U.lerp(bx - 2, bx + 9, p2), U.lerp(6, -8, p2));
      g.stroke();
    }
    g.font = '800 26px "Pretendard", sans-serif'; g.textAlign = 'left'; g.textBaseline = 'middle';
    g.fillStyle = gold > 0 ? U.mix('#aeb9d6', '#ffe9a8', gold) : (failing ? '#ff9aa6' : '#aeb9d6');
    g.fillText('수고했어', bx + 20, 1);
    g.restore();
    if (done >= 0 && done < 0.6) { g.save(); g.globalCompositeOperation = 'lighter'; U.dot(g, x, y, 90 + 240 * U.easeOutCubic(done / 0.6), '#ffd76a', 0.5 * Math.pow(1 - done / 0.6, 2), 0.1); g.restore(); g.globalAlpha = 1; }
  }

  // ───────────── 카운트다운 ─────────────
  const FONT_COUNT = '400 168px "Black Han Sans", "Pretendard", sans-serif';
  function drawCount(g, t, st) {
    if (!st.count) return;
    const n = st.count.n, tau = t - st.count.t;
    if (tau < 0 || tau > n * COUNT_STEP + 0.12) return;
    const i = Math.min(n - 1, Math.floor(tau / COUNT_STEP)), lt = tau - i * COUNT_STEP;
    const num = String(n - i);
    const sc = 1.35 - 0.35 * U.easeOutCubic(U.prog(lt, 0, 0.16)) - 0.06 * U.prog(lt, 0.2, COUNT_STEP);
    const a = U.prog(lt, 0, 0.05) * (1 - U.prog(lt, COUNT_STEP - 0.09, COUNT_STEP));
    Fx.drawCentered(g, Fx.glowText('cnt' + num, num, FONT_COUNT, '#ffffff', '#ff86c1', 30, { w: 10, color: '#141833' }), CX, COUNT_Y, sc, a);
    g.save(); g.globalCompositeOperation = 'lighter';
    g.globalAlpha = 0.7 * (1 - U.prog(lt, 0, 0.4)); g.strokeStyle = '#ffd1e6'; g.lineWidth = 6 * (1 - U.prog(lt, 0, 0.4)) + 1;
    g.beginPath(); g.arc(CX, COUNT_Y, 80 + 150 * U.easeOutCubic(U.prog(lt, 0, 0.4)), 0, TAU); g.stroke();
    g.restore(); g.globalAlpha = 1;
  }

  // ───────────── 실패 도장 ─────────────
  function drawStamp(g, t, st) {
    if (!st.yearFail) return;
    const tau = t - st.yearFail.t - 0.25; if (tau < 0) return;
    const fx = st.say && st.say.thanked ? t - st.say.fireT : -1;          // 고치는 줄의 Enter부터
    const gone = st.gildT != null ? U.prog(t - st.gildT, 0, 0.22) : (fx > 1.2 ? 1 : 0);
    if (fx >= 0 && gone >= 1) return;
    const hit = U.prog(tau, 0, 0.11);
    const sc0 = (1.9 - 0.9 * U.easeOutCubic(hit)) * (1 + 0.05 * U.bump(tau, 0.11, 0.15, 0.16, 0.3));
    const flip = fx >= 0 ? U.prog(fx, 0, 0.12) : 0;                        // 0→0.5 빨간 면이 접히고, 0.5→1 민트 면이 펴진다
    const fixed = flip >= 0.5;
    const sqY = fx >= 0 ? Math.max(0.02, Math.abs(Math.cos(Math.PI * flip))) : 1;
    const dock = fx >= 0 ? U.easeInOutCubic(U.prog(fx, 0.12, 0.3)) : 0;    // 뒤집힌 뒤에는 작아져 왼쪽에 비켜 선다(말풍선 자리 비우기)
    const l1 = '새해 진입 실패', l2 = `사유: ${st.yearFail.message}`;
    const x = U.lerp(CX, 132, dock), y = U.lerp(COUNT_Y + 4, COUNT_Y + 30, dock), sc = sc0 * U.lerp(1, 0.56, dock);
    g.save(); g.translate(x, y); g.rotate(fixed ? -0.05 * dock : -0.07); g.scale(sc, sc * sqY); g.globalAlpha = hit * (1 - gone);
    g.font = '700 32px "Pretendard", sans-serif'; const w1 = g.measureText(l1).width;
    g.font = '800 42px "Pretendard", sans-serif'; const w2 = g.measureText(l2).width;
    const w = Math.max(w1, w2) + 56, h = 142;
    const edge = fixed ? '#6ee7b7' : '#ff5a70';
    U.roundRect(g, -w / 2, -h / 2, w, h, 16); g.fillStyle = fixed ? 'rgba(6,40,32,0.94)' : 'rgba(52,6,20,0.92)'; g.fill();
    g.lineWidth = 5; g.strokeStyle = edge; g.stroke();
    U.roundRect(g, -w / 2 + 8, -h / 2 + 8, w - 16, h - 16, 10); g.lineWidth = 1.6; g.strokeStyle = U.rgba(edge, 0.7); g.stroke();
    g.textAlign = 'center'; g.textBaseline = 'middle';
    if (fixed) {
      g.font = '400 76px "Black Han Sans", "Pretendard", sans-serif'; const tw = g.measureText('보완 완료').width;
      g.fillStyle = '#6ee7b7'; g.fillText('보완 완료', 30, 4);
      g.strokeStyle = '#6ee7b7'; g.lineWidth = 10; g.lineCap = 'round'; g.lineJoin = 'round';
      const bx = -tw / 2 - 22; g.beginPath(); g.moveTo(bx - 20, 2); g.lineTo(bx - 5, 18); g.lineTo(bx + 22, -20); g.stroke();
    } else {
      g.font = '700 32px "Pretendard", sans-serif'; g.fillStyle = '#ff8794'; g.fillText(l1, 0, -34);   // 무슨 일인지는 작게
      g.font = '800 42px "Pretendard", sans-serif'; g.fillStyle = '#ffffff'; g.fillText(l2, 0, 20);      // 왜인지는 크게
    }
    g.restore(); g.globalAlpha = 1;
    // 도장 찍히는 순간의 먼지 고리
    if (tau > 0.09 && tau < 0.45) {
      g.save(); g.globalCompositeOperation = 'lighter'; const f = 1 - (tau - 0.09) / 0.36;
      g.globalAlpha = 0.5 * f; g.strokeStyle = '#ff7083'; g.lineWidth = 4 * f + 0.5;
      g.beginPath(); g.ellipse(CX, COUNT_Y + 4, 240 + 60 * (1 - f), 84 + 30 * (1 - f), -0.07, 0, TAU); g.stroke(); g.restore(); g.globalAlpha = 1;
    }
  }

  // ───────────── 말풍선 ─────────────
  const sayGlyphDelay = (i) => i * 0.125;               // 글자 하나에 16분음표 하나
  function drawBubble(g, t, st) {
    if (!st.say) return;
    const tau = t - st.say.t; if (tau < 0) return;
    const out = st.yearUp ? U.prog(t - st.yearUp.t, 0.0, 0.28) : 0; if (out >= 1) return;
    const text = st.say.text;
    const h = st.dig ? st.dig.h : 0;
    let px = 48; const mk = (p) => `800 ${p}px "Pretendard", sans-serif`;
    g.save(); g.font = mk(px);
    while (g.measureText(text).width > 232 && px > 24) { px -= 2; g.font = mk(px); }
    const tw = g.measureText(text).width, bw = tw + 56, bh = px + 50;
    const bx = Math.min(W - 14 - bw / 2, CX + 122), by = GROUND - h - 137 * WORKER_SCALE - 66;
    const pop = U.easeOutBack(U.prog(tau, 0, 0.3), 2.4) * (1 - out);
    const float = 3 * Math.sin(t * 2.6);
    g.translate(bx, by + float); g.scale(pop, pop); g.globalAlpha = Math.min(1, pop * 1.4);
    // 꼬리(삽질러 머리 쪽으로)
    g.beginPath(); g.moveTo(-bw / 2 + 34, bh / 2 - 6); g.lineTo(-bw / 2 + 10, bh / 2 + 34); g.lineTo(-bw / 2 + 70, bh / 2 - 6); g.closePath();
    g.fillStyle = '#fffaf0'; g.fill(); g.lineWidth = 3.5; g.strokeStyle = '#141833'; g.lineJoin = 'round'; g.stroke();
    U.roundRect(g, -bw / 2, -bh / 2, bw, bh, 30); g.fillStyle = '#fffaf0'; g.fill(); g.stroke();
    g.fillStyle = '#fffaf0'; g.fillRect(-bw / 2 + 32, bh / 2 - 8, 40, 8);
    g.font = mk(px); g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#1b2350';
    const chars = Array.from(text), cw = chars.map(c => g.measureText(c).width);
    let cx = -tw / 2;
    chars.forEach((c, i) => {                                // 한 자씩 톡톡
      const q = U.prog(tau - sayGlyphDelay(i), 0, 0.16);
      if (q > 0 && c !== ' ') {
        const sc = U.easeOutBack(q, 3.2);
        g.save(); g.translate(cx + cw[i] / 2, 2); g.scale(sc, sc); g.fillText(c, 0, 0); g.restore();
      }
      cx += cw[i];
    });
    g.restore(); g.globalAlpha = 1;
    // 풍선 둘레 반짝이
    if (st.say.thanked && out < 1) {
      g.save(); g.globalCompositeOperation = 'lighter';
      for (let i = 0; i < 6; i++) {
        const a = Math.pow(Math.max(0, Math.sin(t * 3 + i * 1.7)), 2) * U.prog(tau, 0.2, 0.5) * (1 - out);
        const ang = i / 6 * TAU + 0.4, xx = bx + Math.cos(ang) * (bw / 2 + 14), yy = by + Math.sin(ang) * (bh / 2 + 14);
        U.dot(g, xx, yy, 26, '#ffe08a', a, 0.25);
      }
      g.restore(); g.globalAlpha = 1;
    }
  }

  // 눈의 시계: 새해로 못 넘어간 동안은 느리게, 넘어가는 순간엔 잠깐 멈춘다(소리를 꺼도 박자가 보이게)
  function snowClock(st, t) {
    let c = t;
    if (st.yearFail) { const a = st.yearFail.t + 0.15, b = st.say ? st.say.t : Infinity; if (t > a) c -= 0.72 * (Math.min(t, b) - a); }
    if (st.yearUp) { const a = st.yearUp.t; if (t > a) c -= Math.min(t, st.yearUp.lock) - a; }
    return c;
  }
  // 실패한 동안 무대가 식는 정도(0..1)
  function chill(st, t) {
    if (!st.yearFail || REWIND) return 0;
    const until = st.say ? st.say.t : Infinity;
    return U.prog(t - st.yearFail.t, 0.1, 0.5) * (1 - U.prog(t - until, 0, 0.4));
  }

  /* 무대는 두 겹으로 그린다.
     drawScene  — 그림(하늘·산·눈·흙더미·삽질러·연도판·불꽃). main.js가 이것을 newyear.js의 ascii()로 글자로 바꿔 찍는다.
     drawOverlay — 읽어야 하는 글자(달 이름표·계수판·확인란·카운트다운·도장·말풍선). 글자로 바꾸지 않고 또렷하게 얹는다.
     opts.rewind: 되감는 중(불꽃·도장처럼 번쩍이는 것은 빼고 큰 움직임만) */
  function drawScene(g, t, st, opts) {
    const rewind = REWIND = !!(opts && opts.rewind);
    g.save(); g.beginPath(); g.rect(0, 0, W, H); g.clip();
    let lift = 0, amb = { a: 0, color: '#ffd479', y: 600 };
    if (!rewind) for (const b of st.bursts) {
      const f = Fx.fireworkFlash(t, b);
      if (f > 0) { lift += f * 0.3; if (f > amb.a) amb = { a: f, color: b.color, y: b.y }; }
    }
    if (st.yearUp) { const u = t - st.yearUp.lock; if (u >= 0) { const f = Math.pow(1 - U.prog(u, 0, 1.0), 2); lift += f * 0.6; if (f > amb.a) amb = { a: f, color: '#ffd479', y: BOARD.cy }; } }
    if (st.gildT != null) { const u = t - st.gildT; if (u >= 0) { const f = Math.pow(1 - U.prog(u, 0, 1.4), 2) * 0.7; lift += f * 0.4; if (f > amb.a) amb = { a: f, color: '#ffc45a', y: GROUND - 260 }; } }
    const cold = chill(st, t);
    if (cold > 0) { const u = t - st.yearFail.t; const f = U.bump(u, 0, 0.1, 0.3, 0.9) * 0.6; if (f > amb.a) amb = { a: f, color: '#ff5a70', y: BOARD.cy }; }
    lift = rewind ? 0 : Math.min(0.5, lift);
    if (rewind) amb = { a: 0, color: '#ffd479', y: 600 };
    const goldAmt = st.gildT == null ? 0 : U.prog(t - st.gildT, 0.1, 1.1);
    const dawn = st.yearUp ? U.prog(t - st.yearUp.lock, 0, 1.6) : 0;
    const sT = opts && opts.snowT != null ? opts.snowT : snowClock(st, t);
    const snowN = st.snow ? st.snow.n : 0;
    const pile = st.snow ? U.clamp01((t - st.snow.t - 2) / 9) * Math.min(1, snowN / 200) : 0;
    const ws = workerState(t, st), wx = ws ? ws.x : CX;

    Fx.sky(g, 0, W, H, lift);
    drawStars(g, t, Math.min(1, lift * 0.6 + dawn * 0.35));
    drawFar(g, t, lift, dawn);
    if (!rewind) for (const b of st.bursts) { if (b.type === 'shape') drawShapeBurst(g, t, b); else Fx.firework(g, t, b); }
    if (st.snow) Fx.snow(g, sT, st.snow.t, snowN, 0, W, H, { layerLo: 0, layerHi: 0.78, gold: snowN - 1 });
    drawGround(g, t, st, lift, goldAmt, pile);
    drawMound(g, t, st, lift);
    if (!rewind) drawClods(g, t, st, wx);
    const o = drawWorker(g, t, st);
    if (o) drawSweat(g, t, o);
    drawBoard(g, t, st);
    if (st.snow) Fx.snow(g, sT, st.snow.t, snowN, 0, W, H, { layerLo: 0.78, layerHi: 1, gold: snowN - 1 });
    if (cold > 0.01) {                                        // 실패한 동안은 색이 빠지고 어두워진다
      g.fillStyle = `rgba(4,6,20,${0.34 * cold})`; g.fillRect(0, 0, W, H);
      g.globalCompositeOperation = 'saturation'; g.fillStyle = `rgba(128,128,128,${0.6 * cold})`; g.fillRect(0, 0, W, H);
      g.globalCompositeOperation = 'source-over';
    }
    g.restore();
    REWIND = false;
    return { ambient: amb, lift };
  }
  function drawOverlay(g, t, st, opts) {
    const rewind = REWIND = !!(opts && opts.rewind);
    g.save(); g.beginPath(); g.rect(0, 0, W, H); g.clip();
    drawMoundLabels(g, t, st, 1);
    drawDimension(g, t, st);
    drawWorkerMark(g, t, st);
    drawCheckTag(g, t, st);
    drawCounter(g, t, st, workerState(t, st));
    drawWaste(g, t, st);
    if (!rewind) { drawCount(g, t, st); drawStamp(g, t, st); drawBubble(g, t, st); }
    g.restore();
    REWIND = false;
  }

  // 소리 합성용: 무대에서 일어나는 일의 시각
  function soundEvents(st) {
    const ev = [];
    if (st.yearSet) ev.push({ t: st.yearSet.t, type: 'board_drop' }, { t: st.yearSet.t + DROP, type: 'board_land' }, { t: st.yearSet.t + DROP + 0.2, type: 'board_settle' });
    if (st.snow) ev.push({ t: st.snow.t, type: 'snow_start', n: st.snow.n });
    if (st.spawn) ev.push({ t: st.spawn.t, type: 'worker_fall' }, { t: st.spawn.t + DROP, type: 'worker_land' });
    if (st.dig) {
      const d = st.dig;
      ev.push({ t: d.t, type: 'dig_start', dur: d.D, n: d.n }, { t: d.t + d.D, type: 'dig_end' });
      for (let k = 0; k < 12; k++) {                          // 삽 한 번 = 한 달: 찌르는 순간(dig_hit)과 그 달이 닫히는 순간(band)
        const t0 = k ? DIG_GRID[k - 1] : 0, dur = DIG_GRID[k] - t0;
        if (t0 >= d.D) break;
        ev.push({ t: d.t + t0 + dur * 0.3, type: 'dig_hit', i: k });
      }
      d.bandT.forEach((bt, k) => ev.push({ t: bt, type: 'band', k }));
    }
    if (st.count) for (let i = 0; i < st.count.n; i++) ev.push({ t: st.count.t + i * COUNT_STEP, type: 'count', left: st.count.n - i });
    if (st.yearFail) ev.push({ t: st.yearFail.t, type: 'jam' }, { t: st.yearFail.t + 0.25, type: 'stamp' }, { t: st.yearFail.t + 0.56, type: 'jam_drop' });
    if (st.say) {
      if (st.say.thanked && st.yearFail) ev.push({ t: st.say.fireT, type: 'fix_stamp' });
      ev.push({ t: st.say.t, type: 'bubble', thanked: st.say.thanked });
      Array.from(st.say.text).forEach((c, i) => { if (c !== ' ') ev.push({ t: st.say.t + sayGlyphDelay(i), type: 'say_glyph', i }); });
    }
    if (st.say && st.say.thanked) ev.push({ t: st.say.t + 0.1, type: 'check' });
    if (st.gildT != null) {
      for (let k = 0; k < st.dig.bands; k++) ev.push({ t: st.gildT + k * GILD_STEP, type: 'gild', k });
      if (st.dig.labeled) ev.push({ t: st.gildT + (st.dig.labeled - 1) * GILD_STEP + 0.03, type: 'waste_zero' });
    }
    if (st.yearUp) ev.push({ t: st.yearUp.t, type: 'year_roll', dur: ROLL }, { t: st.yearUp.lock, type: 'year_gold' });
    for (const b of st.bursts) ev.push({ t: b.t0, type: 'fw_launch', x: b.x / W, rise: b.rise, band: b.band }, { t: b.t0 + b.rise, type: 'fw_burst', x: b.x / W, size: b.R, kind: b.type });
    return ev;
  }

  // 검증 스크립트가 화면에서 찾아볼 자리(숫자를 파이썬 쪽에 따로 적어 두지 않도록 여기서 내보낸다)
  const LAYOUT = { W, H, CX, GROUND, BANDS, BAND_H, FULL_H, BASE_HALF, TOP_HALF, BOARD, COUNT_Y, WORKER_SCALE, YEAR_DAYS, SOIL, GOLD, MONTH_DAYS, BAND_TOP };
  window.Stage = { REGISTRY, META, NY, collect, drawScene, drawOverlay, soundEvents, dayAt, W, H, CX, GROUND, BOARD, COURIER, COUNT_STEP, ROLL, GILD_STEP, DROP, fillH, LAYOUT };
})();
