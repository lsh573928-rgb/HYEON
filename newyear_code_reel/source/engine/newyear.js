function newyear() {
  /* newyear.js — 영상 오른쪽 가운데 창에 뜨는 바로 그 코드.
     위: 2026.py가 부르는 이름들(한 줄씩 실행된다)
     아래: 왼쪽 그림을 매 프레임 글자로 찍는 부분 */

  // ── 1. 대본이 부르는 이름들 ──
  const C = {};

  C['year ='] = (env, y) => {
    env.year = env.year0 = y;
  };

  C['= 삽질러'] = (env) => {
    env.days = [];
    return { type: '삽질러' };
  };

  C['snow.fall'] = (env, n) => {
    env.snow = n;
  };

  C['삽질러.삽질'] = (env, n) => {
    if (env.days.length + n > 365)
      throw RangeError('1년은 365일');
    for (let d = 1; d <= n; d++)
      env.days.push(d);  // 하루에 한 삽
  };

  C.countdown = (env, n) => {
    env.beats = [];
    for (let k = n; k > 0; k--)
      env.beats.push(k);
  };

  C['year +='] = (env, by) => {
    if (!env.thanked)
      throw Error('"수고했어" 누락');
    env.year += by;
  };

  C.say = (env, text) => {
    if (text.includes('수고'))
      env.thanked = true;
  };

  C.fireworks = (env, n) => {
    env.shells = [];
    for (let i = 0; i < n; i++)
      env.shells.push(i % 12);  // 그 달에서
  };

  // ── 2. 그림을 글자로 ──
  const RAMP = ' .:-=+*#%@';  // 어두움 → 밝음
  const EDGE = '-\\|/';        // 선의 방향

  function ascii(img, env, out) {
    // 새해가 되면 칸이 작아진다(해상도 업)
    const cell = env.year > env.year0 ? 5 : 8;
    const cols = img.width / cell | 0;
    const rows = img.height / cell / 1.8 | 0;
    const px = shrink(img, cols, rows);
    const edge = sobel(px.luma, cols, rows);
    out.begin(cols, rows, cell);
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const i = y * cols + x;
        const line = edge.mag[i] > 0.5
          && px.luma[i] > 0.3;
        const ch = line
          ? EDGE[edge.dir[i]]
          : RAMP[px.luma[i] * 9.99 | 0];
        out.put(i, ch, px.rgb(i));
      }
    }
    return out.end();
  }

  // 그림을 칸 수만큼 줄인다 → 칸마다 평균 색
  function shrink(img, cols, rows) {
    const c = scratch(cols, rows);
    c.drawImage(img, 0, 0, cols, rows);
    const d = c.getImageData(0, 0, cols, rows)
      .data;
    const luma = new Float32Array(cols * rows);
    for (let i = 0; i < luma.length; i++) {
      const r = d[4 * i], g = d[4 * i + 1];
      const b = d[4 * i + 2];
      const l = (.21 * r + .72 * g + .07 * b)
        / 255;
      // 밤하늘은 비우고, 어두운 것도 보이게
      luma[i] = Math.max(0, l - 0.1) ** 0.6;
    }
    // 글자는 칸의 일부만 칠하므로 색을 밝힌다
    const rgb = (i) => {
      const m = Math.max(d[4 * i],
        d[4 * i + 1], d[4 * i + 2], 1);
      const k = (90 + 165 * luma[i] ** .5) / m;
      return [d[4 * i] * k, d[4 * i + 1] * k,
        d[4 * i + 2] * k];
    };
    return { luma, rgb };
  }

  // 밝기가 갑자기 바뀌는 곳은 선 글자로
  function sobel(L, w, h) {
    const mag = new Float32Array(w * h);
    const dir = new Uint8Array(w * h);
    for (let y = 1; y < h - 1; y++) {
      for (let x = 1; x < w - 1; x++) {
        const i = y * w + x;
        const gx = L[i + 1] - L[i - 1];
        const gy = L[i + w] - L[i - w];
        mag[i] = Math.hypot(gx, gy);
        const a = Math.atan2(gy, gx);
        dir[i] = Math.round(a / (Math.PI / 4)
          + 6) % 4;
      }
    }
    return { mag, dir };
  }

  // 칸마다 글자를 찍는다
  function writer(ctx, font) {
    let cols, rows, cell, idx, tint;
    const glyphs = RAMP + EDGE;
    return {
      begin(c, r, s) {
        cols = c; rows = r; cell = s;
        idx = new Uint8Array(c * r);
        tint = new ImageData(c, r);
      },
      put(i, ch, rgb) {
        idx[i] = glyphs.indexOf(ch);
        tint.data.set([...rgb, 255], 4 * i);
      },
      end() {
        const a = atlas(glyphs, cell, font);
        const pane = layer('glyph', ctx);
        const ch = cell * 1.8;
        let n = 0;
        for (let i = 0; i < idx.length; i++) {
          if (idx[i] === 0) continue;  // ' '
          pane.drawImage(a, idx[i] * cell, 0,
            cell, ch, (i % cols) * cell,
            (i / cols | 0) * ch, cell, ch);
          n++;
        }
        // 흰 글자 위에 칸의 색을 입힌다
        paint(pane, tint, cols * cell, rows * ch);
        // 칸 바탕에도 같은 색을 옅게(형체가 보이게)
        backdrop(ctx, tint, cols * cell, rows * ch);
        ctx.drawImage(pane.canvas, 0, 0);
        return n;
      },
    };
  }

  return { C, ascii, writer, RAMP, EDGE };
}

/* ── 아래는 화면에 띄우지 않는 잔손질(그림판 재사용, 글자판 만들기, 색 입히기) ── */
const NY_CACHE = new Map();
function nyCanvas(key, w, h) {
  let c = NY_CACHE.get(key);
  if (!c || c.canvas.width !== w || c.canvas.height !== h) {
    const el = document.createElement('canvas'); el.width = w; el.height = h;
    c = el.getContext('2d', { willReadFrequently: key.startsWith('scratch') });
    NY_CACHE.set(key, c);
  }
  return c;
}
// 칸 수만큼 줄이는 그림판: 크게 한 번에 줄이면 거칠어지므로 반씩 줄여 평균을 낸다
function scratch(w, h) {
  const c = nyCanvas('scratch', w, h);
  return {
    drawImage(img, x, y, dw, dh) {
      let src = img, sw = img.width, sh = img.height, k = 0;
      while (sw / 2 >= dw && sh / 2 >= dh) {
        const nw = Math.max(dw, sw / 2 | 0), nh = Math.max(dh, sh / 2 | 0);
        const half = nyCanvas('half' + (k++ % 2), nw, nh);
        half.imageSmoothingEnabled = true; half.imageSmoothingQuality = 'high';
        half.clearRect(0, 0, nw, nh); half.drawImage(src, 0, 0, sw, sh, 0, 0, nw, nh);
        src = half.canvas; sw = nw; sh = nh;
      }
      c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high';
      c.clearRect(0, 0, w, h);
      c.drawImage(src, 0, 0, sw, sh, x, y, dw, dh);
    },
    getImageData: (...a) => c.getImageData(...a),
  };
}
// 글자판: 글자를 흰색으로 한 줄에 미리 그려 둔다(칸 크기마다 한 번)
function atlas(glyphs, cell, font) {
  const key = 'atlas' + cell;
  const ch = cell * 1.8;
  const c = nyCanvas(key, glyphs.length * cell, Math.ceil(ch));
  if (!c.done) {
    c.font = `700 ${cell * 1.62}px ${font}`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillStyle = '#fff';
    Array.from(glyphs).forEach((g, i) => c.fillText(g, i * cell + cell / 2, ch / 2 + cell * 0.08));
    c.done = true;
  }
  return c.canvas;
}
function layer(key, like) {
  const c = nyCanvas(key, like.canvas.width, like.canvas.height);
  c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
  c.clearRect(0, 0, c.canvas.width, c.canvas.height);
  return c;
}
// 칸 색(작은 그림)을 칸 크기로 늘려 글자 모양 안에만 칠한다
function paint(pane, tint, w, h) {
  const t = nyCanvas('tint', tint.width, tint.height);
  t.putImageData(tint, 0, 0);
  pane.globalCompositeOperation = 'source-in';
  pane.imageSmoothingEnabled = false;
  pane.drawImage(t.canvas, 0, 0, tint.width, tint.height, 0, 0, w, h);
  pane.globalCompositeOperation = 'source-over';
}

function backdrop(ctx, tint, w, h) {
  const t = nyCanvas('tint', tint.width, tint.height);
  ctx.save(); ctx.globalAlpha = 0.16; ctx.imageSmoothingEnabled = false;
  ctx.drawImage(t.canvas, 0, 0, tint.width, tint.height, 0, 0, w, h);
  ctx.restore();
}

window.NEWYEAR = newyear;
