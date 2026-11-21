/* 대본 해석기 — 화면 오른쪽에 찍히는 글자(파이썬 문법을 따온 장면 대본)를 그대로 읽어
   "어느 줄이 어떤 효과를 어떤 값으로 부르는지"로 바꾼다. 영상 엔진은 이 결과만 보고 그린다.
   → 대본의 숫자·글자를 바꾸면 영상이 바뀐다. 모르는 이름을 쓰면 실제로 오류가 난다. */
'use strict';
(function () {
  const KEYWORDS = new Set(['for', 'in', 'while', 'if', 'else', 'elif', 'import', 'from', 'as', 'def', 'del', 'return',
    'pass', 'try', 'except', 'finally', 'raise', 'not', 'and', 'or', 'is', 'True', 'False', 'None', 'with', 'lambda']);
  const IDENT_START = /[A-Za-z_ㄱ-ㆎ가-힣]/;
  const IDENT_PART = /[A-Za-z0-9_ㄱ-ㆎ가-힣]/;

  // 글자 폭: 한글·전각은 2칸
  function cellWidth(ch) {
    const c = ch.codePointAt(0);
    return (c >= 0x1100 && c <= 0x11FF) || (c >= 0x2E80 && c <= 0xA4CF) || (c >= 0xAC00 && c <= 0xD7A3) ||
      (c >= 0xF900 && c <= 0xFAFF) || (c >= 0xFF00 && c <= 0xFF60) ? 2 : 1;
  }
  function textCells(s) { let n = 0; for (const ch of s) n += cellWidth(ch); return n; }

  // 한 줄을 색칠용 토막으로 나눈다. [{text, type}]
  function tokenize(line) {
    const out = [];
    const chars = Array.from(line);
    let i = 0;
    const push = (text, type) => out.push({ text, type });
    while (i < chars.length) {
      const ch = chars[i];
      if (ch === '#') { push(chars.slice(i).join(''), 'comment'); break; }
      if (ch === ' ' || ch === '\t') { let j = i; while (j < chars.length && (chars[j] === ' ' || chars[j] === '\t')) j++; push(chars.slice(i, j).join(''), 'space'); i = j; continue; }
      if (ch === '"' || ch === "'") {
        let j = i + 1;
        while (j < chars.length && chars[j] !== ch) { if (chars[j] === '\\') j++; j++; }
        j = Math.min(j + 1, chars.length);
        push(chars.slice(i, j).join(''), 'string'); i = j; continue;
      }
      if (/[0-9]/.test(ch)) {
        let j = i; while (j < chars.length && /[0-9._]/.test(chars[j])) j++;
        push(chars.slice(i, j).join(''), 'number'); i = j; continue;
      }
      if (IDENT_START.test(ch)) {
        let j = i; while (j < chars.length && IDENT_PART.test(chars[j])) j++;
        const word = chars.slice(i, j).join('');
        let k = j; while (k < chars.length && chars[k] === ' ') k++;
        const next = chars[k];
        const prevTok = out.length ? out[out.length - 1] : null;
        let type = 'ident';
        if (KEYWORDS.has(word)) type = 'keyword';
        else if (next === '(') type = 'func';
        else if (next === '.') type = 'object';
        else if (prevTok && prevTok.text === '.') type = 'attr';
        else if (next === '=' && chars[k + 1] !== '=' && insideCall(out)) type = 'kwarg';
        push(word, type); i = j; continue;
      }
      // 연산자·구두점
      const two = ch + (chars[i + 1] || '');
      if (['+=', '-=', '*=', '/=', '==', '!=', '<=', '>=', '->', '**'].includes(two)) { push(two, 'op'); i += 2; continue; }
      push(ch, '=+-*/<>%'.includes(ch) ? 'op' : 'punct'); i++;
    }
    return out;
  }
  function insideCall(tokens) {
    let depth = 0;
    for (const t of tokens) { if (t.text === '(') depth++; else if (t.text === ')') depth--; }
    return depth > 0;
  }

  // ── 값 읽기 ──
  function splitArgs(s) {
    const parts = []; let cur = '', q = null, depth = 0;
    for (const ch of Array.from(s)) {
      if (q) { cur += ch; if (ch === q) q = null; continue; }
      if (ch === '"' || ch === "'") { q = ch; cur += ch; continue; }
      if (ch === '(' || ch === '[') depth++;
      if (ch === ')' || ch === ']') depth--;
      if (ch === ',' && depth === 0) { parts.push(cur.trim()); cur = ''; continue; }
      cur += ch;
    }
    if (cur.trim() !== '') parts.push(cur.trim());
    return parts;
  }
  function parseValue(s, env) {
    s = s.trim();
    if (s === '') throw new SyntaxError('값이 비었습니다');
    if (/^-?[0-9][0-9_]*(\.[0-9]+)?$/.test(s)) return Number(s.replace(/_/g, ''));
    if ((s[0] === '"' && s[s.length - 1] === '"') || (s[0] === "'" && s[s.length - 1] === "'")) return s.slice(1, -1);
    if (s === 'True') return true;
    if (s === 'False') return false;
    if (s === 'None') return null;
    // 간단한 덧셈·뺄셈(이름 ± 숫자)
    const m = s.match(/^(.+?)\s*([+\-])\s*([0-9.]+)$/);
    if (m) { const a = parseValue(m[1], env); const b = Number(m[3]); return m[2] === '+' ? a + b : a - b; }
    const call = s.match(RE_CALL_VALUE);
    if (call) { const a = parseArgs(call[2], env); return { call: call[1], args: a.args, kwargs: a.kwargs }; }
    if (new RegExp('^' + IDENT_START.source + IDENT_PART.source + '*$').test(s)) {
      if (env && Object.prototype.hasOwnProperty.call(env, s)) return env[s];
      const e = new Error(`name '${s}' is not defined`); e.pyType = 'NameError'; throw e;
    }
    const e = new Error('invalid syntax'); e.pyType = 'SyntaxError'; throw e;
  }
  function parseArgs(s, env) {
    const args = [], kwargs = {};
    for (const part of splitArgs(s)) {
      const m = part.match(/^([A-Za-z_ㄱ-ㆎ가-힣][A-Za-z0-9_ㄱ-ㆎ가-힣]*)\s*=(?!=)\s*(.+)$/);
      if (m) kwargs[m[1]] = parseValue(m[2], env); else args.push(parseValue(part, env));
    }
    return { args, kwargs };
  }

  const NAME = '[A-Za-z_\\u3131-\\u318E\\uAC00-\\uD7A3][A-Za-z0-9_\\u3131-\\u318E\\uAC00-\\uD7A3]*';
  const RE_CALL_VALUE = new RegExp('^(' + NAME + '(?:\\.' + NAME + ')*)\\s*\\((.*)\\)$');
  const RE_CALL = new RegExp('^(' + NAME + '(?:\\.' + NAME + ')*)\\s*\\((.*)\\)$');
  const RE_ASSIGN = new RegExp('^(' + NAME + '(?:\\.' + NAME + ')*)\\s*(=|\\+=|-=|\\*=)\\s*(.+)$');
  const RE_FOR = new RegExp('^for\\s+(' + NAME + ')\\s+in\\s+range\\((.+)\\)\\s*:\\s*(.+)$');
  const RE_DEL = new RegExp('^del\\s+(' + NAME + '(?:\\.' + NAME + ')*)$');

  /* 한 줄을 뜻으로 바꾼다.
     {kind:'blank'|'comment'|'call'|'assign'|'for'|'del'|'error', name, args, kwargs, target, op, value, error} */
  function parseLine(raw, env) {
    let line = raw;
    // 줄 끝 주석 떼기(따옴표 밖의 #)
    let q = null, cut = -1; const cs = Array.from(line);
    for (let i = 0; i < cs.length; i++) {
      const ch = cs[i];
      if (q) { if (ch === q) q = null; continue; }
      if (ch === '"' || ch === "'") { q = ch; continue; }
      if (ch === '#') { cut = i; break; }
    }
    const trailing = cut >= 0 ? cs.slice(cut + 1).join('').trim() : null;
    if (cut >= 0) line = cs.slice(0, cut).join('');
    line = line.trim();
    if (line === '') return trailing != null ? { kind: 'comment', text: trailing } : { kind: 'blank' };
    try {
      let m;
      if ((m = line.match(RE_FOR))) {
        const n = parseValue(m[2], env);
        const body = parseLine(m[3], Object.assign({}, env, { [m[1]]: 0 }));
        return { kind: 'for', varName: m[1], count: n, body, note: trailing };
      }
      if ((m = line.match(RE_DEL))) return { kind: 'del', target: m[1], note: trailing };
      if ((m = line.match(RE_CALL))) {
        const a = parseArgs(m[2], env);
        return { kind: 'call', name: m[1], args: a.args, kwargs: a.kwargs, note: trailing };
      }
      if ((m = line.match(RE_ASSIGN))) {
        return { kind: 'assign', target: m[1], op: m[2], value: parseValue(m[3], env), note: trailing };
      }
      const e = new Error('invalid syntax'); e.pyType = 'SyntaxError'; throw e;
    } catch (e) {
      return { kind: 'error', errorType: e.pyType || e.name || 'SyntaxError', message: e.message, note: trailing };
    }
  }

  window.Interp = { tokenize, parseLine, parseValue, textCells, cellWidth };
})();
