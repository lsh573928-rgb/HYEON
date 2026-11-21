#!/usr/bin/env node
/* 릴스 렌더러 — index.html을 헤드리스 크로미움으로 열어 프레임을 한 장씩 그리게 하고 ffmpeg로 묶는다.

   node render.js                         # ../newyear_code_reel_silent.mp4 (무음 영상)
   node render.js --still 0 45 300        # 확인용 프레임만 PNG로 (--out-dir, 기본 ../frames/still)
   node render.js --events                # 소리 합성·검증용 시각표와 화면 배치를 build/events.json 으로(--out-dir로 위치 변경)
   node render.js --script other.js       # 다른 대본으로 렌더(대본을 바꾸면 영상이 바뀌는지 확인할 때)
   node render.js --no-cold-open --out ../newyear_code_reel_B_silent.mp4   # 첫머리(완성 장면 → 되감기) 없이 빈 무대에서 시작하는 비교판
   node render.js --raw --still 300       # 왼쪽을 글자로 바꾸기 전 그림 그대로(비교용)

   프레임은 시각 t의 순수 함수라서(난수는 씨앗 고정) 몇 번을 돌려도 같은 그림이 나온다.
*/
'use strict';
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

function loadPlaywright() {
  try { return require('playwright'); } catch (e) { /* 아래에서 안내 */ }
  try { return require('playwright-core'); } catch (e) { /* 아래에서 안내 */ }
  console.error('playwright가 없습니다. 이 폴더에서 `npm install` 후 `npx playwright install chromium`을 실행하세요.');
  process.exit(1);
}

function parseArgs(argv) {
  const a = { still: null, outDir: null, out: null, events: false, script: null, crf: 14, from: null, to: null, noCold: false };
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--still') { a.still = []; while (argv[i + 1] && /^\d+$/.test(argv[i + 1])) a.still.push(+argv[++i]); }
    else if (k === '--out-dir') a.outDir = argv[++i];
    else if (k === '--out') a.out = argv[++i];
    else if (k === '--events') a.events = true;
    else if (k === '--script') a.script = argv[++i];
    else if (k === '--crf') a.crf = +argv[++i];
    else if (k === '--no-cold-open') a.noCold = true;
    else if (k === '--raw') a.raw = true;
    else if (k === '--from') a.from = +argv[++i];
    else if (k === '--to') a.to = +argv[++i];
    else { console.error('모르는 옵션: ' + k); process.exit(1); }
  }
  return a;
}

(async () => {
  const args = parseArgs(process.argv);
  const HERE = __dirname;
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e && e.stack || e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  const url = 'file://' + path.join(HERE, 'index.html') + '?capture=1' + (args.noCold ? '&cold=0' : '') + (args.raw ? '&ascii=0' : '');
  if (args.script) {
    // 다른 대본 파일(window.SCRIPT_TEXT = `...`)을 기본 대본보다 먼저 넣는다.
    const txt = fs.readFileSync(path.resolve(args.script), 'utf8');
    await page.addInitScript(txt + '\n;window.SCRIPT_OVERRIDE = window.SCRIPT_TEXT;');
  }
  await page.goto(url);
  await page.evaluate(() => window.REEL.ready);
  const info = await page.evaluate(() => ({ fps: REEL.fps, frames: REEL.frames, duration: REEL.duration, w: REEL.width, h: REEL.height }));
  if (errors.length) { console.error('페이지 오류:\n' + errors.join('\n')); await browser.close(); process.exit(1); }

  const grab = async (i) => {
    const d = await page.evaluate((n) => { REEL.render(n); return REEL.canvas.toDataURL('image/png'); }, i);
    return Buffer.from(d.slice(d.indexOf(',') + 1), 'base64');
  };

  if (args.events) {
    const ev = await page.evaluate(() => REEL.events());
    const summary = await page.evaluate(() => REEL.summary());
    const dir = path.resolve(args.outDir || path.join(HERE, 'build'));
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'events.json'), JSON.stringify({ ...info, ...summary, events: ev }, null, 1));
    console.log(`시각표 ${ev.length}건 → ${path.join(dir, 'events.json')}`);
    await browser.close();
    return;
  }

  if (args.still) {
    const dir = path.resolve(args.outDir || path.join(HERE, '..', 'frames', 'still'));
    fs.mkdirSync(dir, { recursive: true });
    for (const i of args.still) {
      const f = path.join(dir, `f${String(i).padStart(4, '0')}.png`);
      fs.writeFileSync(f, await grab(i));
      console.log(f);
    }
    if (errors.length) { console.error('페이지 오류:\n' + errors.join('\n')); process.exitCode = 1; }
    await browser.close();
    return;
  }

  const out = path.resolve(args.out || path.join(HERE, '..', 'newyear_code_reel_silent.mp4'));
  const from = args.from == null ? 0 : args.from;
  const to = args.to == null ? info.frames : args.to;
  const ff = spawn('ffmpeg', [
    '-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(info.fps), '-c:v', 'png', '-i', '-',
    '-vf', 'scale=in_range=full:out_range=tv:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=yuv420p',
    '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'slow', '-crf', String(args.crf), '-tune', 'animation',
    '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
    '-r', String(info.fps), '-movflags', '+faststart', '-an', out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => ff.on('close', c => c === 0 ? res() : rej(new Error('ffmpeg 종료 코드 ' + c))));
  const t0 = Date.now();
  for (let i = from; i < to; i++) {
    const buf = await grab(i);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 30 === 0) process.stdout.write(`\r${i}/${to} 프레임`);
  }
  ff.stdin.end();
  await done;
  await browser.close();
  if (errors.length) { console.error('\n페이지 오류:\n' + errors.join('\n')); process.exit(1); }
  console.log(`\r${to - from} 프레임 → ${out} (${((Date.now() - t0) / 1000).toFixed(1)}초)`);
})().catch(e => { console.error(e); process.exit(1); });
