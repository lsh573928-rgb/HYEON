/* 삽질러 — 노란 안전모를 쓴 작은 일꾼. 전부 도형으로 그린 창작 캐릭터(그림 파일 없음).
   발밑 가운데가 기준점(0,0), 키는 약 120px(scale 1). 삽은 자루의 손 잡는 점 G와 기울기 θ로 정한다. */
'use strict';
(function () {
  const U = window.U;
  const TAU = Math.PI * 2;
  const C = {
    hat: '#ffc93c', hatDark: '#e2a51d', hatLight: '#ffe58a',
    skin: '#ffd9b5', skinShade: '#f2bd94', cheek: '#ff9d8a',
    vest: '#ff8a3d', vestDark: '#e06a22', stripe: '#e6ff7a',
    jacket: '#2b3a6e', pants: '#243059', boot: '#161a2c', glove: '#fff3d1',
    wood: '#c28a55', woodDark: '#9a6a3d', steel: '#cfd9ee', steelDark: '#8d9bbd', steelLight: '#ffffff',
    line: '#141833',
  };

  // 삽질 한 번(0..1)의 손 위치·삽 기울기. θ=0이면 자루가 곧게 서고 삽날이 아래.
  const DIG_KEYS = [
    { p: 0.00, gx: 29, gy: -50, th: 0.10, bob: 0, lean: 0 },
    { p: 0.30, gx: 33, gy: -35, th: 0.30, bob: 7, lean: 0.10 },     // 푹 찌르기
    { p: 0.52, gx: 35, gy: -43, th: -0.92, bob: 3, lean: 0.03 },    // 떠 올리기(자루가 턱 아래로 지나가게)
    { p: 0.78, gx: 12, gy: -80, th: -2.05, bob: -4, lean: -0.10 },  // 어깨 너머로 퍼 던지기
    { p: 0.90, gx: 30, gy: -44, th: -0.50, bob: 1, lean: -0.02 },   // 되돌아오기(자루가 얼굴을 가리지 않게 낮게)
    { p: 1.00, gx: 29, gy: -50, th: 0.10, bob: 0, lean: 0 },
  ];
  function digPose(p) {
    p = ((p % 1) + 1) % 1;
    let a = DIG_KEYS[0], b = DIG_KEYS[1];
    for (let i = 0; i < DIG_KEYS.length - 1; i++) if (p >= DIG_KEYS[i].p && p <= DIG_KEYS[i + 1].p) { a = DIG_KEYS[i]; b = DIG_KEYS[i + 1]; break; }
    const q = U.smooth((p - a.p) / (b.p - a.p));
    const L = (k) => U.lerp(a[k], b[k], q);
    return { gx: L('gx'), gy: L('gy'), th: L('th'), bob: L('bob'), lean: L('lean') };
  }
  const POSES = {
    idle: { gx: 30, gy: -50, th: 0.06, bob: 0, lean: 0 },             // 삽을 옆에 짚고 서 있기
    cheer: { gx: 31, gy: -94, th: Math.PI - 0.16, bob: -3, lean: 0, h2x: -36, h2y: -122 },   // 삽날을 하늘로 번쩍 + 만세
    rest: { gx: 31, gy: -46, th: 0.16, bob: 2, lean: 0.04 },
  };
  function mixPose(a, b, q) {
    const o = {}; for (const k of ['gx', 'gy', 'th', 'bob', 'lean']) o[k] = U.lerp(a[k], b[k], q);
    // 한 손을 삽에서 떼는 자세(만세)는 삽 위의 손 자리에서 서서히 옮겨 간다
    if (a.h2x != null || b.h2x != null) {
      const sa = shovelPoints(a), sb = shovelPoints(b);
      const ax = a.h2x != null ? a.h2x : sa.hand2.x, ay = a.h2y != null ? a.h2y : sa.hand2.y;
      const bx = b.h2x != null ? b.h2x : sb.hand2.x, by = b.h2y != null ? b.h2y : sb.hand2.y;
      o.h2x = U.lerp(ax, bx, q); o.h2y = U.lerp(ay, by, q);
    }
    return o;
  }

  const SHAFT_UP = 34, SHAFT_DOWN = 40, BLADE = 26;
  function shovelPoints(pose) {
    const ux = Math.sin(pose.th), uy = -Math.cos(pose.th);          // 손잡이 쪽 방향
    const top = { x: pose.gx + ux * SHAFT_UP, y: pose.gy + uy * SHAFT_UP };
    const neck = { x: pose.gx - ux * SHAFT_DOWN, y: pose.gy - uy * SHAFT_DOWN };
    const tip = { x: neck.x - ux * BLADE, y: neck.y - uy * BLADE };
    const hand2 = pose.h2x != null ? { x: pose.h2x, y: pose.h2y } : { x: pose.gx - ux * 13, y: pose.gy - uy * 13 };
    return { ux, uy, top, neck, tip, hand1: { x: pose.gx + ux * 15, y: pose.gy + uy * 15 }, hand2 };
  }

  function drawShovel(g, pose, alpha, clod) {
    const s = shovelPoints(pose);
    g.save(); g.globalAlpha *= alpha; g.lineCap = 'round'; g.lineJoin = 'round';
    // 자루
    g.strokeStyle = C.woodDark; g.lineWidth = 8; g.beginPath(); g.moveTo(s.top.x, s.top.y); g.lineTo(s.neck.x, s.neck.y); g.stroke();
    g.strokeStyle = C.wood; g.lineWidth = 5; g.beginPath(); g.moveTo(s.top.x, s.top.y); g.lineTo(s.neck.x, s.neck.y); g.stroke();
    // 손잡이(T자)
    g.strokeStyle = C.woodDark; g.lineWidth = 8;
    g.beginPath(); g.moveTo(s.top.x - s.uy * 9, s.top.y + s.ux * 9); g.lineTo(s.top.x + s.uy * 9, s.top.y - s.ux * 9); g.stroke();
    g.strokeStyle = C.wood; g.lineWidth = 5;
    g.beginPath(); g.moveTo(s.top.x - s.uy * 9, s.top.y + s.ux * 9); g.lineTo(s.top.x + s.uy * 9, s.top.y - s.ux * 9); g.stroke();
    // 삽날
    g.save(); g.translate(s.neck.x, s.neck.y); g.rotate(Math.atan2(-s.uy, -s.ux) - Math.PI / 2);
    g.beginPath(); g.moveTo(-13, -3); g.lineTo(13, -3); g.lineTo(13, 12); g.quadraticCurveTo(11, 24, 0, 31); g.quadraticCurveTo(-11, 24, -13, 12); g.closePath();
    const sg = g.createLinearGradient(-13, 0, 13, 0); sg.addColorStop(0, C.steelDark); sg.addColorStop(0.45, C.steel); sg.addColorStop(1, C.steelLight);
    g.fillStyle = sg; g.fill(); g.strokeStyle = C.line; g.lineWidth = 2.2; g.stroke();
    g.strokeStyle = 'rgba(20,24,51,0.35)'; g.lineWidth = 2; g.beginPath(); g.moveTo(0, 0); g.lineTo(0, 18); g.stroke();
    if (clod) {                                                    // 삽 위의 흙 한 덩이
      g.fillStyle = clod; g.beginPath(); g.ellipse(0, 14, 12, 9, 0, 0, TAU); g.fill();
      g.fillStyle = 'rgba(255,255,255,0.75)'; g.beginPath(); g.ellipse(-2, 9, 9, 4, 0, Math.PI, TAU); g.fill();
    }
    g.restore();
    g.restore();
    return s;
  }

  /* o: {pose, face:'smile'|'o'|'grin'|'wow', blink:0..1, snowCap:0..1, look:-1..1, ghost:[{pose,alpha}], clod:color|null, glow:0..1} */
  function draw(g, x, y, scale, o) {
    o = o || {};
    const pose = o.pose || POSES.idle;
    g.save(); g.translate(x, y); g.scale(scale, scale);
    g.lineJoin = 'round'; g.lineCap = 'round';
    // 그림자
    g.fillStyle = 'rgba(8,10,30,0.35)'; g.beginPath(); g.ellipse(2, 3, 36, 8, 0, 0, TAU); g.fill();

    const bob = pose.bob || 0, lean = pose.lean || 0;
    // 빠른 삽질의 잔상
    if (o.ghost) for (const gh of o.ghost) drawShovel(g, gh.pose, gh.alpha, null);

    // 다리·장화
    g.fillStyle = C.pants; U.roundRect(g, -17, -30 + bob * 0.4, 14, 26 - bob * 0.4, 5); g.fill(); U.roundRect(g, 3, -30 + bob * 0.4, 14, 26 - bob * 0.4, 5); g.fill();
    g.fillStyle = C.boot; U.roundRect(g, -21, -9, 20, 11, 5); g.fill(); U.roundRect(g, 1, -9, 20, 11, 5); g.fill();

    g.save(); g.translate(0, bob); g.rotate(lean);
    // 몸통(남색 웃옷 + 주황 조끼 + 형광 띠)
    g.fillStyle = C.jacket; U.roundRect(g, -25, -76, 50, 50, 14); g.fill();
    g.fillStyle = C.vest; U.roundRect(g, -21, -75, 42, 46, 11); g.fill();
    g.fillStyle = C.vestDark; g.fillRect(-2, -75, 4, 46);
    g.fillStyle = C.stripe; g.fillRect(-21, -48, 42, 7); g.fillRect(-14, -75, 6, 28); g.fillRect(8, -75, 6, 28);
    g.strokeStyle = C.line; g.lineWidth = 2.4; U.roundRect(g, -25, -76, 50, 50, 14); g.stroke();

    // 머리
    const hy = -96;
    g.fillStyle = C.skin; g.beginPath(); g.arc(0, hy, 25, 0, TAU); g.fill();
    g.fillStyle = C.skinShade; g.beginPath(); g.arc(0, hy, 25, 0.25, Math.PI - 0.25); g.fill();
    g.fillStyle = C.skin; g.beginPath(); g.ellipse(0, hy - 2, 25, 22, 0, 0, TAU); g.fill();
    g.strokeStyle = C.line; g.lineWidth = 2.4; g.beginPath(); g.arc(0, hy, 25, 0, TAU); g.stroke();
    // 얼굴
    const look = (o.look || 0) * 3, lookY = (o.lookY || 0) * 3;
    const blink = o.blink || 0;
    const ey = hy + 3 + lookY;
    g.fillStyle = C.line;
    if (o.face === 'grin' || o.face === 'cheer') {
      g.strokeStyle = C.line; g.lineWidth = 2.8;
      g.beginPath(); g.arc(-9 + look, ey + 1, 4.8, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
      g.beginPath(); g.arc(9 + look, ey + 1, 4.8, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
    } else {
      const eh = 4.8 * (1 - 0.85 * blink);
      g.beginPath(); g.ellipse(-9 + look, ey, 3.5, eh, 0, 0, TAU); g.fill();
      g.beginPath(); g.ellipse(9 + look, ey, 3.5, eh, 0, 0, TAU); g.fill();
      if (blink < 0.5) { g.fillStyle = '#fff'; g.beginPath(); g.arc(-8 + look, ey - 1.6, 1.3, 0, TAU); g.fill(); g.beginPath(); g.arc(10 + look, ey - 1.6, 1.3, 0, TAU); g.fill(); }
      if (o.face === 'sad') {                             // 처진 눈썹
        g.strokeStyle = C.line; g.lineWidth = 2.4;
        g.beginPath(); g.moveTo(-15 + look, ey - 9); g.lineTo(-6 + look, ey - 12); g.moveTo(15 + look, ey - 9); g.lineTo(6 + look, ey - 12); g.stroke();
      }
    }
    const blush = o.blush == null ? 0.55 : o.blush;
    g.save(); g.fillStyle = C.cheek; g.globalAlpha *= Math.min(1, blush);
    g.beginPath(); g.ellipse(-16, hy + 11, 5.5, 3.4, 0, 0, TAU); g.fill(); g.beginPath(); g.ellipse(16, hy + 11, 5.5, 3.4, 0, 0, TAU); g.fill();
    g.restore();
    g.strokeStyle = C.line; g.lineWidth = 2.4; g.fillStyle = '#7a2f2f';
    const my = hy + 9 + lookY * 0.5;
    if (o.face === 'o' || o.face === 'wow') { g.beginPath(); g.ellipse(look, my + 4, o.face === 'wow' ? 5 : 3.4, o.face === 'wow' ? 6 : 4, 0, 0, TAU); g.fill(); }
    else if (o.face === 'grin' || o.face === 'cheer') { g.beginPath(); g.arc(look, my, 8, 0.1, Math.PI - 0.1); g.closePath(); g.fill(); }
    else if (o.face === 'sad') { g.beginPath(); g.arc(look, my + 9, 6, Math.PI + 0.35, TAU - 0.35); g.stroke(); }
    else { g.beginPath(); g.arc(look, my, 6, 0.25, Math.PI - 0.25); g.stroke(); }

    // 안전모
    g.fillStyle = C.hat;
    g.beginPath(); g.moveTo(-27, hy - 6); g.bezierCurveTo(-27, hy - 44, 27, hy - 44, 27, hy - 6); g.closePath(); g.fill();
    g.strokeStyle = C.line; g.lineWidth = 2.4; g.stroke();
    g.fillStyle = C.hatDark; U.roundRect(g, -33, hy - 10, 66, 9, 4.5); g.fill(); g.stroke();
    g.fillStyle = C.hatLight; g.beginPath(); g.ellipse(-10, hy - 26, 7, 4, -0.5, 0, TAU); g.fill();
    g.fillStyle = C.hatDark; g.fillRect(-3, hy - 36, 6, 26);
    if (o.snowCap > 0.01) {                               // 안전모 위에 쌓인 눈
      g.fillStyle = '#f4f8ff'; g.globalAlpha *= Math.min(1, o.snowCap * 1.5);
      const hh = 9 * o.snowCap;
      g.beginPath(); g.moveTo(-20, hy - 28); g.bezierCurveTo(-18, hy - 40 - hh, 18, hy - 40 - hh, 20, hy - 28);
      g.quadraticCurveTo(12, hy - 31, 6, hy - 27); g.quadraticCurveTo(-2, hy - 32, -9, hy - 27); g.quadraticCurveTo(-15, hy - 31, -20, hy - 28); g.closePath(); g.fill();
      g.globalAlpha = 1;
    }
    g.restore();

    // 삽 + 팔(몸 위에)
    const tilt = (px, py) => { const c = Math.cos(lean), s = Math.sin(lean); return { x: px * c - py * s, y: px * s + py * c + bob }; };
    const sh1 = tilt(19, -66), sh2 = tilt(-19, -66);
    const s = drawShovel(g, pose, 1, o.clod || null);
    g.strokeStyle = C.line; g.lineWidth = 13;
    g.beginPath(); g.moveTo(sh1.x, sh1.y); g.lineTo(s.hand1.x, s.hand1.y); g.moveTo(sh2.x, sh2.y); g.lineTo(s.hand2.x, s.hand2.y); g.stroke();
    g.strokeStyle = C.jacket; g.lineWidth = 9;
    g.beginPath(); g.moveTo(sh1.x, sh1.y); g.lineTo(s.hand1.x, s.hand1.y); g.moveTo(sh2.x, sh2.y); g.lineTo(s.hand2.x, s.hand2.y); g.stroke();
    g.fillStyle = C.glove; g.strokeStyle = C.line; g.lineWidth = 2;
    g.beginPath(); g.arc(s.hand1.x, s.hand1.y, 6.5, 0, TAU); g.fill(); g.stroke();
    g.beginPath(); g.arc(s.hand2.x, s.hand2.y, 6.5, 0, TAU); g.fill(); g.stroke();
    g.restore();
    // 삽날 끝의 화면 좌표(흙이 튀는 자리)
    return { tipX: x + s.tip.x * scale, tipY: y + s.tip.y * scale, topX: x + s.top.x * scale, topY: y + s.top.y * scale };
  }

  window.Worker = { draw, digPose, mixPose, POSES, C };
})();
