/* 시각표 — 대본 글자(script.js)와 박자(timing.js)를 받아
   ① 글쇠 하나하나가 찍히는 시각 ② 줄이 실행되는(Enter) 시각 ③ 그 줄이 부르는 효과와 값을 만든다.
   오른쪽 편집기·왼쪽 무대·소리 합성(audio.py)이 모두 이 표 하나를 본다. */
'use strict';
(function () {
  const U = window.U, Interp = window.Interp;

  // 한글 한 자를 글쇠 순서대로: ㅅ → 수 → (받침 있으면) 숙
  const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';
  function hangulSteps(ch) {
    const code = ch.codePointAt(0);
    if (code < 0xAC00 || code > 0xD7A3) return null;
    const idx = code - 0xAC00, cho = Math.floor(idx / 588), jung = Math.floor((idx % 588) / 28), jong = idx % 28;
    const steps = [CHO[cho], String.fromCodePoint(0xAC00 + cho * 588 + jung * 28)];
    if (jong) steps.push(ch);
    return steps;
  }

  /* registry: 이름 → { check(args, kwargs, env) 던지면 오류, apply(...) 변수 갱신, make(...) 객체 만들기, log(...) 한 줄 설명 }
       이름 꼴: 'snow.fall'(호출) · 'year ='/'year +='(대입) · '= 삽질러'(생성해서 대입) · '삽질러.dig'(변수에 담긴 객체의 메서드)
     timing: { start, cps, enterDelay, gap, duration, lines: [{before, cps, hold, fireAt, fireAfter}] } */
  function build(scriptText, timing, registry) {
    const rawLines = scriptText.replace(/\r/g, '').split('\n');
    while (rawLines.length && rawLines[rawLines.length - 1].trim() === '') rawLines.pop();
    const env = {};
    const lines = [], fires = [], keys = [], errorRows = [];
    let clock = timing.start || 0;

    function resolve(parsed) {
      // 돌려주는 것: {key, args, kwargs, target} — 없으면 오류를 던진다
      const err = (type, msg) => { const e = new Error(msg); e.pyType = type; return e; };
      if (parsed.kind === 'call') {
        if (registry[parsed.name]) return { key: parsed.name, args: parsed.args, kwargs: parsed.kwargs };
        const parts = parsed.name.split('.');
        if (parts.length === 2 && env[parts[0]] && env[parts[0]].type) {
          const key = env[parts[0]].type + '.' + parts[1];
          if (registry[key]) return { key, args: parsed.args, kwargs: parsed.kwargs, self: parts[0] };
          throw err('AttributeError', `'${env[parts[0]].type}'에는 '${parts[1]}'이(가) 없습니다`);
        }
        throw err('NameError', `name '${parts[0]}' is not defined`);
      }
      if (parsed.kind === 'assign') {
        const v = parsed.value;
        if (v && typeof v === 'object' && v.call) {
          const key = '= ' + v.call;
          if (!registry[key] || parsed.op !== '=') throw err('NameError', `name '${v.call}' is not defined`);
          return { key, args: v.args, kwargs: v.kwargs, target: parsed.target };
        }
        const key = parsed.target + ' ' + parsed.op;
        if (!registry[key]) {
          if (parsed.op === '=') return { key: null, args: [v], kwargs: {}, target: parsed.target, plain: true };   // 그냥 변수 저장
          throw err('NameError', `name '${parsed.target}' is not defined`);
        }
        return { key, args: [v], kwargs: {}, target: parsed.target };
      }
      if (parsed.kind === 'del') {
        const key = 'del ' + parsed.target;
        if (!registry[key]) throw err('NameError', `name '${parsed.target}' is not defined`);
        return { key, args: [], kwargs: {} };
      }
      throw err('SyntaxError', 'invalid syntax');
    }

    rawLines.forEach((text, idx) => {
      const tm = (timing.lines && timing.lines[idx]) || {};
      const cps = tm.cps || timing.cps || 18;
      const line = { idx, text, strokes: [], fires: [], typeStart: 0, typeEnd: 0 };
      const enterDelay = timing.enterDelay != null ? timing.enterDelay : 0.12;

      // 글쇠 간격을 먼저 만든다(시작 시각은 아래에서 정한다)
      let n = 0, rel = 0; const pending = [];
      const stroke = (op, ch) => {
        // 사람 손처럼 들쭉날쭉하게(씨앗 고정). 빈칸·괄호·따옴표 앞에서는 조금 더 쉰다.
        let d = (1 / cps) * (0.66 + 0.68 * U.hash(idx * 131 + 7, n++));
        if (ch === '(' || ch === ' ' || ch === '"') d *= 1.2;
        rel += d;
        pending.push({ rel, op, ch });
      };
      for (const ch of Array.from(text)) {
        const steps = hangulSteps(ch);
        if (!steps) { stroke('ins', ch); continue; }
        steps.forEach((s, k) => stroke(k === 0 ? 'ins' : 'rep', s));
      }
      // 시작 시각: 보통은 앞줄 뒤 before초. fireAt(절대 시각)이나 fireAfter("몇 번째 줄 실행 + delay초")가 있으면 Enter가 거기 떨어지도록 거꾸로 잡는다.
      let base;
      if (tm.fireAt != null) base = Math.max(clock + 0.03, tm.fireAt - enterDelay - rel);          // Enter가 정확히 그 시각(박자)에 떨어지게
      else if (tm.fireAfter && fires[tm.fireAfter.line]) base = Math.max(clock + 0.05, fires[tm.fireAfter.line].t + tm.fireAfter.delay - enterDelay - rel);
      else base = clock + (tm.before != null ? tm.before : (idx === 0 ? 0 : (timing.gap != null ? timing.gap : 0.35)));
      line.typeStart = base;
      for (const q of pending) {
        line.strokes.push({ t: base + q.rel, op: q.op, ch: q.ch });
        keys.push({ t: base + q.rel, kind: q.ch === ' ' ? 'space' : 'key', line: idx });
      }
      clock = base + rel;
      line.typeEnd = clock;

      clock += enterDelay;
      const parsed = Interp.parseLine(text, env);
      const f = { t: clock, line: idx, text, parsed, ok: true, error: null, key: null, tryKey: null, args: [], kwargs: {}, log: null };
      if (parsed.kind === 'blank' || parsed.kind === 'comment') { f.silent = true; }
      else if (parsed.kind === 'error') { f.ok = false; f.error = { type: parsed.errorType, message: parsed.message }; }
      else {
        try {
          const r = resolve(parsed);
          f.tryKey = r.key; f.args = r.args; f.kwargs = r.kwargs;
          if (r.plain) { env[r.target] = r.args[0]; f.silent = true; }
          else {
            const entry = registry[r.key];
            if (entry.check) entry.check(r.args, r.kwargs, env);
            if (entry.make) env[r.target] = entry.make(r.args, r.kwargs, env);
            if (entry.apply) entry.apply(r.args, r.kwargs, env);
            f.key = r.key;
            f.log = entry.log ? entry.log(r.args, r.kwargs, env) : null;
          }
        } catch (e) {
          f.ok = false; f.error = { type: e.pyType || 'Error', message: e.message };
        }
      }
      if (!f.ok) errorRows.push({ afterLine: idx, t: f.t, text: `${f.error.type}: ${f.error.message}` });
      keys.push({ t: clock, kind: 'enter', line: idx, ok: f.ok });
      line.fires.push(f); fires.push(f);
      line.fireAt = f.t;
      clock += tm.hold || 0;
      lines.push(line);
    });

    // 화면에서 몇 번째 칸에 놓이는지(오류 줄이 한 칸씩 밀어낸다)
    for (const ln of lines) ln.row = ln.idx + errorRows.filter(e => e.afterLine < ln.idx).length;
    for (const e of errorRows) e.row = lines[e.afterLine].row + 1;

    return { lines, fires, keys, env, errorRows, scriptEnd: clock, rows: lines.length + errorRows.length };
  }

  // 시각 t에 그 줄에 보이는 글자
  function visibleText(line, t) {
    const out = [];
    for (const s of line.strokes) {
      if (s.t > t) break;
      if (s.op === 'ins') out.push(s.ch); else if (s.op === 'rep') out[out.length - 1] = s.ch; else out.pop();
    }
    return out.join('');
  }
  // 시각 t의 줄 상태: 'idle'(아직) | 'typing' | 'ok' | 'error' | 'silent'(주석)
  function lineState(line, t) {
    if (t < line.typeStart) return { state: 'idle' };
    const f = line.fires[0];
    if (!f || t < f.t) return { state: 'typing' };
    if (f.silent) return { state: 'silent', fire: f };
    return { state: f.ok ? 'ok' : 'error', fire: f };
  }

  window.Timeline = { build, visibleText, lineState };
})();
