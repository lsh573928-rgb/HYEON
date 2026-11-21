/* 박자표 — 대본 각 줄의 Enter가 언제 떨어지는지(이야기 시각, 초). 줄 순서는 script.js와 같다.
   영상 전체가 120bpm(한 박 0.5초, 첫 마디 첫 박 0.5초) 격자 위에 있다. 16초 = 8마디(석별의 정 한 절).
     fireAt: 이 줄의 Enter 시각 — 타자는 거기서 거꾸로 맞춰 시작한다. 효과는 한 8분음표(0.25초) 뒤 무대에 닿는다.
     before / cps: fireAt이 없는 줄에서 앞줄 뒤 쉬는 시간 / 초당 글쇠 수 */
window.TIMING = {
  fps: 30,
  duration: 16.0,
  music: { bpm: 120, firstDownbeat: 0.5, bars: 8, beatsPerBar: 4 },
  /* 영상 첫머리: 완성 장면(0~hold) → 코드 전체 선택(hold~select) → 삭제(select, 첫 박) → 장면이 거꾸로 풀린다.
     오른쪽 창은 rewindEnd에 비워진 채 첫 줄을 치기 시작하고, 왼쪽 무대는 stageRewindEnd까지 계속 풀린다(빈 무대로 오래 두지 않으려고). */
  coldOpen: { hold: 0.25, select: 0.5, rewindEnd: 0.9, stageRewindEnd: 1.4 },
  start: 0.9,
  cps: 22,
  enterDelay: 0.1,
  gap: 0.3,
  lines: [
    { fireAt: 1.50, cps: 27 },    // year = 2026        → 2.00 연도판이 내려앉는다
    { fireAt: 2.25, cps: 27 },    // me = 삽질러()       → 2.75 삽질러 착지
    { fireAt: 3.00, cps: 25 },    // snow.fall(300)     → 3.25 눈
    { fireAt: 4.00 },             // me.삽질(365)        → 4.25~7.00 삽질(한 달에 8분음표 하나, 끝의 두 달은 몰아서)
    { fireAt: 7.25 },             // countdown(3)       → 7.50 · 8.00 · 8.50
    { fireAt: 9.00 },             // year += 1          → 카운트다운이 끝나는 박에 Enter … 오류
    { fireAt: 10.25, cps: 20 },   // say("수고했어")    → 10.50 말풍선, 11.00부터 금빛
    { fireAt: 11.6667 },          // year += 1          → 12.00에 '철컥'
    { fireAt: 12.75 },            // fireworks(12)      → 13.00부터, 마지막 삽 모양은 14.50
    { before: 0.9, cps: 16 },     // # 수고한 친구에게
  ],
};
