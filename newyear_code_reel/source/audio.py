#!/usr/bin/env python3
"""새해 코드 릴스 소리 — 소리 파일 없이 전부 NumPy로 합성한다(48kHz 스테레오 16비트).

    python3 audio.py            → ../audio/soundtrack.wav       전체 믹스
                                  ../audio/soundtrack_fx.wav    가락·화음·방울을 뺀 효과음판(음원 자동 인식에 걸릴 때 쓴다)
                                → ../newyear_code_reel_silent.mp4(무음 영상)에 하나씩 입혀
                                  ../newyear_code_reel.mp4 · ../newyear_code_reel_fx.mp4 (영상은 복사, 소리는 AAC 256k)
    python3 audio.py --no-mux   → wav만
    python3 audio.py --events 다른/events.json --out-dir 폴더
                                → 다른 시각표로 wav만(대본을 바꿔 본 시험용 — 영상에는 입히지 않는다)

시각은 build/events.json(시각표)에서만 읽는다. 대본(script.js)·박자표(timing.js)·엔진이 시각표보다 새것이면
`node render.js --events`로 먼저 다시 만든다 → 대본을 고쳐도 소리가 화면과 어긋나지 않는다.
시각표에 없는 사건은 소리도 없다(불꽃 줄을 지우면 불꽃 소리도 없다).

음악 — 저작권이 없는 옛 가락 〈석별의 정〉(Auld Lang Syne) 한 절 8마디, F장조. 시각표의 박자 격자(music) 위에 그대로 놓는다.
영상이 반복되므로 8마디 넷째 박의 못갖춘마디 '도'가 파일 맨 앞(0초)에 오고, 끝음은 영상이 끝나기 전에 사그라든다.
    가 구간  0초 ~ 연도판이 걸릴 때(jam)   오르골 한 줄을 작게 + 마디마다 밑음만 아주 여리게 — 첫 줄부터 음악이 깔린다
    나 구간  jam ~ "수고했어" 말풍선        음악이 뚝 끊긴다. 버저 · 도장 · 다음 줄 타자 · '보완 완료' 팅만 남는다(이 정적이 웃음 포인트)
    다 구간  말풍선 ~ 끝                    격자의 그 자리에서 다시: 옥타브를 겹친 오르골 + 포근한 화음 + 썰매 방울 8분음표
jam이 없으면 가 구간이 끝까지 가고, jam 뒤에 고마운 말이 없으면 음악은 돌아오지 않는다.

효과음(무대 소리는 왼쪽, 타자는 오른쪽, 음악은 가운데 · 타자에는 잔향을 넣지 않는다)
    불꽃    올라가는 휘파람 → '펑' + 타닥타닥. 버들은 여리고 길게, 마지막 삽 모양이 가장 크고 길다. 가락이 울릴 때마다 살짝 비켜 준다
    버저    연도판이 걸리는 '철컥' + 낮고 짧은 '삐—'
    도장    '쿵' → 숫자가 도로 떨어지는 '툭' → '보완 완료' 팅
    머리글  0초 '쿵' · 전체 선택 '칙' · 되감기 '쮸욱' · 맺는 말이 뜰 때 반짝임
    무대    코드에서 무대로 날아가는 빛 · 연도판(휙·딱·차르륵) · 삽질러 · 눈 · 카운트다운(목탁 '똑' + '쿵') ·
            말풍선과 글자 넷(도 미 솔 도) · 금빛 종 · 연도판이 넘어가는 '드르륵 철컥' + 종 화음
    삽질    삽 '칙' 열두 번 + 한 달치가 쌓일 때마다 한 음씩 오르는 5음 음계(파 솔 라 도 레 — 가락과 부딪치지 않는다)
    타자    글쇠마다 '틱'(음높이·세기 제각각) · Enter '톡' · 오류 Enter '둑'
    바탕    아주 작은 밤공기
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import unicodedata
import wave
import zlib
from pathlib import Path
from typing import NamedTuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVENTS = HERE / "build" / "events.json"
SILENT = ROOT / "newyear_code_reel_silent.mp4"
OUTPUTS = {"soundtrack.wav": ROOT / "newyear_code_reel.mp4", "soundtrack_fx.wav": ROOT / "newyear_code_reel_fx.mp4"}

SR = 48000
SEED = 20262027
REVERB = 0.5                        # 잔향 크기
TARGET_LUFS = -14.0                 # 통합 음량 목표
CEILING = 10 ** (-1.4 / 20)         # 트루 피크 한도(-1.0 dBTP)보다 조금 아래
CHOP = 0.015                        # 음악이 뚝 끊기는 데 걸리는 시간(초)
CURTAIN = (0.8, 0.08)               # 영상 끝에서 이만큼 앞부터 닫기 시작해 이만큼 앞에서 다 닫는다(초) → 반복 첫머리가 깨끗하다
EDGE = 0.008                        # 파일 맨 끝 닫기(초)

LAYERS = {                          # 겹 이름 → 표에 적을 설명
    "가락": "오르골 〈석별의 정〉 — 처음엔 한 줄로 작게, 말풍선부터 옥타브를 겹쳐 크게",
    "화음": "마디 밑음(가 구간) · 포근한 화음(다 구간)",
    "방울": "썰매 방울 8분음표(다 구간)",
    "불꽃": "올라가는 휘파람 · 펑 · 타닥타닥",
    "버저": "연도판 철컥 + 낮은 삐—",
    "도장": "도장 쿵 · 숫자 툭 · 보완 완료 팅",
    "머리글": "0초 쿵 · 되감기 · 맺는 말 반짝임",
    "무대": "날아가는 빛 · 연도판 · 삽질러 · 눈 · 카운트다운 · 말풍선 · 금빛 종",
    "삽질": "삽 칙 · 달마다 오르는 음",
    "타자": "글쇠 틱 · Enter 톡",
    "바탕": "밤공기",
}
MUSIC = ("가락", "화음", "방울")    # 효과음판에서 빠지는 겹
QUIET = ("key", "space", "enter", "enter_error", "jam", "stamp", "jam_drop", "fix_stamp")   # 정적 속에서도 나는 소리

# ── 음악: F장조 〈석별의 정〉 한 절. 마디마다 (음이름, 박 수) — 옛 가락 그대로(5 | 1. 1 1 3 | 2. 1 2 3 | 1. 1 3 5 | 6 - - 6 | 5. 3 3 1 | 2. 1 2 3 | 1. 6 6 5 | 1) ──
PICKUP = ("C5", 1)
MELODY = (
    (("F5", 1.5), ("F5", 0.5), ("F5", 1), ("A5", 1)),
    (("G5", 1.5), ("F5", 0.5), ("G5", 1), ("A5", 1)),
    (("F5", 1.5), ("F5", 0.5), ("A5", 1), ("C6", 1)),
    (("D6", 3), ("D6", 1)),
    (("C6", 1.5), ("A5", 0.5), ("A5", 1), ("F5", 1)),
    (("G5", 1.5), ("F5", 0.5), ("G5", 1), ("A5", 1)),
    (("F5", 1.5), ("D5", 0.5), ("D5", 1), ("C5", 1)),
    (("F5", 3),),
)
HARMONY = "F F F F | C7 C7 C7 C7 | F F F F | Bb Bb Bb Bb | F F F F | C7 C7 C7 C7 | F F Bb C7 | F F F F"    # 박마다의 화음
VOICING = {"F": ("F3", "A3", "C4", "F4"), "C7": ("C3", "Bb3", "E4", "G4"), "Bb": ("Bb2", "Bb3", "D4", "F4")}   # 밑음 + 위 세 음
PENTA = (0, 2, 4, 7, 9)             # F장조 5음 음계(파 솔 라 도 레, 반음 수) — 어느 화음 위에서도 가락과 부딪치지 않는다
FULL = 0.26                         # 다 구간 가락의 크기
THIN = FULL * 10 ** (-11 / 20)      # 가 구간 가락 — 옥타브 겹침까지 치면 다 구간보다 약 12 dB 작다
DUCK = 1 - 10 ** (-5 / 20)          # 가락 음이 울리는 순간 불꽃이 비켜 주는 깊이(5 dB)

STAMP_LAND = 0.08                   # 도장이 내려와 찍히기까지(초) — 화면에서는 커다랗게 나타나 줄어들며 찍힌다
BUZZ = 0.25                         # 버저 길이(초)
SYNC = ("hook_slam", "board_land", "worker_land", "dig_hit", "count", "jam", "bubble", "year_gold", "fw_burst")    # 화면과 맞는지 재 볼 사건


# ======================================================================== 시각표
def load_events(path: Path | None) -> dict:
    """시각표를 읽는다. 기본 시각표는 없거나 대본·박자표·엔진보다 오래됐으면 render.js로 다시 만든다."""
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    if not EVENTS.exists() or EVENTS.stat().st_mtime < newest_source():
        subprocess.run(["node", "render.js", "--events"], cwd=HERE, check=True)
    return json.loads(EVENTS.read_text(encoding="utf-8"))


def newest_source() -> float:
    """대본·박자표·엔진 가운데 가장 늦게 고친 시각."""
    return max(p.stat().st_mtime for p in [*HERE.glob("*.js"), *(HERE / "engine").glob("*.js")])


class Timeline:
    """시각표를 종류별로 꺼내 쓰기 쉽게 감싼 것. 없는 종류는 빈 목록·None으로 돌려준다."""

    def __init__(self, data: dict):
        self.events = sorted(data["events"], key=lambda e: e["t"])
        self.duration = float(data["duration"])
        self.n = int(round(self.duration * SR))
        self.by: dict[str, list] = {}
        for e in self.events:
            self.by.setdefault(e["type"], []).append(e)
        stage, editor = data["layout"]["stage"], data["layout"]["editor"]
        self.width = data["w"]
        self.stage_w = stage["W"]
        self.bands = stage["BANDS"]
        self.code_x, self.cell_w, self.code_end = editor["codeX"], editor["cellW"], editor["x1"]
        self.pan_stage = self.pan(stage["CX"])
        self.pan_code = self.pan(self.code_x)

        grid = data["music"]                                            # 박자 격자
        self.beat = 60.0 / grid["bpm"]
        self.downbeat, self.bars, self.per_bar = grid["firstDownbeat"], grid["bars"], grid["beatsPerBar"]

        self.jam = self.time("jam")                                     # 음악이 끊기는 순간
        after = [e for e in self.events if self.jam is not None and e["t"] > self.jam]
        self.resume = next((e["t"] for e in after if e["type"] == "bubble" and e.get("thanked")), None)    # 음악이 돌아오는 순간
        self.reopen = next((e["t"] for e in after if e["type"] not in QUIET), self.duration)               # 무대 소리가 다시 나는 순간

    def all(self, kind):
        return self.by.get(kind, [])

    def time(self, kind):
        """그 종류의 첫 사건 시각(없으면 None)."""
        return self.by[kind][0]["t"] if kind in self.by else None

    def pan(self, x):
        """화면 가로 자리(px) → 좌우 자리(-1 왼쪽 ~ +1 오른쪽). 무대는 왼쪽, 코드는 오른쪽으로 기운다."""
        return float(np.clip((x / self.width - 0.5) * 1.8, -1, 1))

    def at(self, bar, beat=1.0):
        """bar마디 beat박이 시작하는 시각(초). 마디와 박은 1부터 센다."""
        return self.downbeat + ((bar - 1) * self.per_bar + (beat - 1)) * self.beat

    def section(self, t):
        """시각 t의 음악 구간: 'A' 가늘게 · 'B' 정적 · 'C' 크게."""
        if self.jam is None or t < self.jam - 1e-6:
            return "A"
        return "B" if self.resume is None or t < self.resume - 1e-6 else "C"


# ======================================================================== 기본 도구
def seeded(name):
    """소리 묶음마다 따로 쓰는 난수(씨앗 고정) — 한 묶음을 고쳐도 다른 묶음 소리는 그대로다."""
    return np.random.default_rng([SEED, zlib.crc32(name.encode())])


def tt(dur):
    return np.arange(int(round(dur * SR))) / SR


def env(dur, attack=0.004, tau=0.2, hold=0.0):
    """소리 크기 틀: attack초 동안 올라가 hold초 머문 뒤 tau초 간격으로 사그라든다."""
    t = tt(dur)
    return np.clip(t / max(attack, 1e-6), 0, 1) * np.exp(-np.clip(t - attack - hold, 0, None) / tau)


def fade(x, t_in=0.0, t_out=0.0):
    """앞뒤를 부드럽게 여닫는다(초) — 뚝 끊기는 소리를 막는다."""
    y = np.array(x, np.float64)
    a, b = min(int(t_in * SR), len(y)), min(int(t_out * SR), len(y))
    if a:
        y[:a] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    if b:
        y[-b:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(b) / b)
    return y


def ramp(t, t0, dur):
    """t0에서 0, dur초 뒤에 1이 되는 곧은 비탈."""
    return np.clip((t - t0) / dur, 0, 1)


def unit(x):
    return x / (np.max(np.abs(x)) + 1e-12)


def sine(freq, dur):
    return np.sin(2 * np.pi * freq * tt(dur))


def osc(freq):
    """표본마다의 주파수(Hz) → 사인파. 음높이가 움직이는 소리는 전부 이걸로 만든다."""
    return np.sin(2 * np.pi * np.cumsum(freq) / SR)


def glide(f0, f1, dur, curve=1.0):
    """f0에서 f1로 미끄러지는 주파수. curve가 1보다 작으면 처음에 빨리 움직인다."""
    return f0 * (f1 / f0) ** ((tt(dur) / dur) ** curve)


def square(freq, top):
    """대역 제한 사각파(홀수 배음을 top Hz까지만) — 버저 소리."""
    ph = 2 * np.pi * np.cumsum(freq) / SR
    out = np.zeros_like(ph)
    for k in range(1, int(top / np.max(freq)) + 1, 2):
        out += np.sin(k * ph) / k
    return out * 4 / np.pi


def fft_filter(x, lo=None, hi=None, order=4):
    """주파수 영역 대역 통과(lo~hi Hz), 버터워스형 경사(order차)."""
    f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-9
    mask = np.ones_like(f)
    if lo is not None:
        mask /= np.sqrt(1 + (lo / f) ** (2 * order))
    if hi is not None:
        mask /= np.sqrt(1 + (f / hi) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x) * mask, len(x))


def burst(rng, dur, lo, hi, attack, tau):
    """대역 잡음 한 줌(lo~hi Hz)에 크기 틀을 씌운 것 — 틱·칙·퍽 같은 소리의 재료. 최댓값 1."""
    n = len(tt(dur))
    return unit(fft_filter(rng.normal(size=n), lo, hi, order=2) * env(dur, attack, tau))


def moving_noise(rng, centre, width=0.5):
    """가운데 주파수가 centre(표본마다 Hz)를 따라 움직이는 대역 잡음(바람·휙 소리). 토막을 겹쳐 더한다."""
    n = len(centre)
    blk, hop = 2048, 512
    win = np.hanning(blk)
    f = np.fft.rfftfreq(blk, 1 / SR) + 1e-9
    out = np.zeros(n + blk)
    for s in range(0, n, hop):
        mask = np.exp(-0.5 * (np.log2(f / centre[min(s + blk // 2, n - 1)]) / width) ** 2)
        out[s:s + blk] += np.fft.irfft(np.fft.rfft(rng.normal(size=blk) * win) * mask, blk) * win
    return unit(out[:n])


BRASS = ((1, 1.0, 1.0), (2.0, 0.45, 0.6), (3.01, 0.25, 0.4), (4.17, 0.12, 0.3))     # 작은 놋쇠 종
GLASS = ((1, 1.0, 1.0), (2.76, 0.3, 0.45), (5.4, 0.12, 0.2))                        # 유리알
CELESTA = ((1, 1.0, 1.0), (2.0, 0.22, 0.5), (4.0, 0.08, 0.25))                      # 첼레스타


def bell(freq, dur, tau=0.6, partials=BRASS):
    """종·유리 소리: (배음 비율, 크기, 울림 길이 비율) 여러 개."""
    t = tt(dur)
    out = np.zeros_like(t)
    for ratio, amp, ring in partials:
        out += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / (tau * ring))
    return out * np.clip(t / 0.002, 0, 1)


def note(name):
    """음이름('F3', 'Bb4') → 주파수."""
    steps = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "Bb": 1, "B": 2}
    return 440.0 * 2 ** ((steps[name[:-1]] + 12 * (int(name[-1]) - 4)) / 12)


def penta(k, octave=4):
    """F{octave}에서 5음 음계로 k칸 위(음수면 아래)의 주파수."""
    return note(f"F{octave}") * 2 ** (k // 5 + PENTA[k % 5] / 12)


def musicbox(freq, dur, ring=1.0):
    """오르골 빗살 한 번: 순음에 가까운 몸통 + 한 옥타브 위 조금 + 튕기는 순간의 높은 '팅'. 높은 음일수록 빨리 사그라든다."""
    t = tt(dur)
    tau = 0.45 * ring * (note("F5") / freq) ** 0.5
    out = np.sin(2 * np.pi * freq * t) * np.exp(-t / tau)
    out += 0.30 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / (0.5 * tau))
    out += 0.07 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / (0.25 * tau))
    if 6.27 * freq < 16000:                                            # 한쪽이 고정된 쇠막대의 둘째 떨림
        out += 0.16 * np.sin(2 * np.pi * 6.27 * freq * t) * np.exp(-t / 0.03)
    return fade(out * np.clip(t / 0.0015, 0, 1), 0, 0.012)


def pad_tone(freq, dur, attack=0.09, release=0.35):
    """포근한 깔개음: 살짝 어긋난 사인 두 개 + 한 옥타브 위 조금. 부드럽게 열리고 dur 뒤에 천천히 닫힌다."""
    t = tt(dur + release)
    tone = np.sin(2 * np.pi * freq * 1.0015 * t) + np.sin(2 * np.pi * freq * 0.9985 * t + 1.0)
    tone += 0.35 * np.sin(2 * np.pi * 2 * freq * t + 2.0)
    return fade(tone, min(attack, dur), release)


# ======================================================================== 믹스 버스
class Mix:
    """겹마다 마른 소리와 잔향으로 보낼 소리를 따로 모은다."""

    def __init__(self, n):
        self.n = n
        self.dry = {name: np.zeros((n, 2), np.float32) for name in LAYERS}
        self.wet = {name: np.zeros((n, 2), np.float32) for name in LAYERS}

    def put(self, layer, sig, t0, gain=1.0, pan=0.0, rev=0.0):
        """sig를 t0초에 놓는다(영상 끝을 넘는 부분은 버린다). pan은 숫자 하나 또는 표본마다의 값, rev는 잔향으로 보내는 양."""
        i0 = int(round(t0 * SR))
        th = (np.clip(pan, -1, 1) + 1) * np.pi / 4                      # 같은 음량 패닝
        lr = np.stack([np.cos(th), np.sin(th)], axis=-1) * math.sqrt(2)
        s = (np.asarray(sig, np.float64)[:, None] * gain * lr)[:max(self.n - i0, 0)]
        self.dry[layer][i0:i0 + len(s)] += s
        self.wet[layer][i0:i0 + len(s)] += s * rev

    def render(self):
        """겹마다 (마른 소리 + 잔향)을 돌려준다. 잔향은 좌우가 다른 짧은 잡음 꼬리(RT60 약 1.4초, 15ms 뒤부터)."""
        rng = seeded("잔향")
        t = tt(1.5)
        ir = rng.normal(size=(len(t), 2)) * np.exp(-t / 0.2)[:, None]
        ir[:int(0.015 * SR)] = 0
        ir = np.stack([fft_filter(ir[:, c], lo=250, hi=5000, order=2) for c in range(2)], axis=1)
        ir /= np.sqrt((ir ** 2).sum(axis=0))
        nfft = 1 << (self.n + len(ir) - 1).bit_length()
        spec = np.fft.rfft(ir, nfft, axis=0)
        out = {}
        for name in LAYERS:
            wet = np.fft.irfft(np.fft.rfft(self.wet[name], nfft, axis=0) * spec, nfft, axis=0)[:self.n]
            out[name] = self.dry[name] + REVERB * wet
        return out


# ======================================================================== 음악
class Note(NamedTuple):
    t: float            # 격자 위의 시각(초)
    bar: int            # 마디(못갖춘마디는 0)
    beat: float         # 박(1부터)
    name: str           # 음이름
    beats: float        # 길이(박)
    section: str        # 'A' 가늘게 · 'B' 정적이라 울리지 않는다 · 'C' 크게


def score(tl: Timeline):
    """가락의 음을 격자 위에 놓는다. 못갖춘마디는 첫 마디 바로 앞(반복 재생에서는 8마디 넷째 박) = 파일 맨 앞."""
    name, beats = PICKUP
    lead = tl.at(1) - beats * tl.beat
    notes = [Note(lead, 0, tl.per_bar + 1 - beats, name, beats, tl.section(lead))] if lead >= 0 else []
    for bar, line in enumerate(MELODY, 1):
        beat = 1.0
        for name, beats in line:
            t = tl.at(bar, beat)
            if t < tl.duration:
                notes.append(Note(t, bar, beat, name, beats, tl.section(t)))
            beat += beats
    return notes


def chord_spans(tl: Timeline):
    """화음이 바뀌는 자리마다 (시작 시각, 끝 시각, 화음)."""
    spans = []
    for bar, line in enumerate(HARMONY.split("|"), 1):
        for beat, chord in enumerate(line.split(), 1):
            if spans and spans[-1][2] == chord:
                spans[-1] = (spans[-1][0], tl.at(bar, beat + 1), chord)
            else:
                spans.append((tl.at(bar, beat), tl.at(bar, beat + 1), chord))
    return spans


def sleigh(rng):
    """썰매 방울 한 번 흔들기: 서로 안 맞는 높은 쇳소리 여럿 + 짤랑이는 잡음."""
    dur = 0.16
    t = tt(dur)
    ring = sum(a * np.sin(2 * np.pi * f * rng.uniform(0.985, 1.015) * t + rng.uniform(0, 2 * np.pi))
               for f, a in ((2850, 1.0), (3640, 0.8), (4470, 0.7), (5320, 0.6), (6730, 0.45), (8110, 0.3)))
    return unit(ring) * env(dur, 0.002, 0.04) + 0.5 * burst(rng, dur, 5500, 12000, 0.004, 0.03)


def music(m: Mix, tl: Timeline):
    """〈석별의 정〉을 격자 위에 놓는다. 가 구간은 오르골 한 줄 + 밑음, 나 구간은 쉼, 다 구간은 옥타브 겹침 + 화음 + 방울.
    돌려주는 것: 악보의 음 전부(울리지 않는 음도 구간 'B'로 들어 있다)."""
    notes = score(tl)
    if not notes:
        return notes
    cut = math.inf if tl.jam is None else tl.jam                        # 가 구간 소리는 여기서 끊긴다
    sounding = [nt for nt in notes if nt.section != "B"]
    for i, nt in enumerate(sounding):
        f, final = note(nt.name), nt is notes[-1]
        again = next((o.t for o in sounding[i + 1:] if o.name == nt.name), math.inf)      # 같은 빗살을 다시 튕기면 앞의 울림은 멎는다
        ring = 2.0 if final else 1.0
        accent = 1.0 if nt.beat % 2 == 1 else 0.9 if nt.beat % 1 == 0 else 0.8          # 1·3박 > 2·4박 > 엇박
        if nt.section == "A":
            hold = min(again, cut + CHOP) - nt.t
            m.put("가락", musicbox(f, min(hold, 1.8 * ring), ring), nt.t, THIN * accent, 0.0, rev=0.35)
        else:
            hold = min(again - nt.t, 1.8 * ring)
            m.put("가락", musicbox(f, hold, ring), nt.t, FULL * accent, 0.0, rev=0.45)
            m.put("가락", musicbox(2 * f, hold, 0.7 * ring), nt.t, 0.4 * FULL * accent, 0.0, rev=0.6)

    for t0, t1, chord in chord_spans(tl):
        if tl.resume is not None and t0 < tl.resume < t1:               # 화음 도중에 돌아오면 거기서부터
            t0 = tl.resume
        section, t1 = tl.section(t0), min(t1, tl.duration)
        root, *upper = (note(name) for name in VOICING[chord])
        if section == "A" and t0 < min(t1, cut):                        # 밑음만 아주 여리게
            for f, gain in ((root, 0.014), (2 * root, 0.010)):
                m.put("화음", pad_tone(f, min(t1, cut) - t0, attack=0.15), t0, gain, 0.0, rev=0.4)
        elif section == "C" and t0 < t1:
            m.put("화음", pad_tone(root, t1 - t0), t0, 0.030, 0.0, rev=0.4)
            for i, f in enumerate(upper):
                m.put("화음", pad_tone(f, t1 - t0), t0, 0.022, 0.25 * (i - 1), rev=0.5)

    rng = seeded("방울")
    half = tl.beat / 2
    for i in range(int((notes[-1].t - tl.downbeat) / half + 1e-6) + 1):  # 끝음까지 8분음표마다, 정박이 조금 세다
        t = tl.downbeat + i * half
        if tl.section(t) == "C":
            m.put("방울", sleigh(rng), t, (0.034 if i % 2 == 0 else 0.019) * rng.uniform(0.85, 1.0), rng.uniform(-0.25, 0.25), rev=0.35)
    return notes


# ======================================================================== 장면별 소리
def headline(m: Mix, tl: Timeline):
    """머리글: 0초 낚는 말이 떨어지는 '쿵'(못갖춘마디 음과 함께) · 되감기 '쮸욱' · 맺는 말이 뜰 때 반짝임."""
    rng = seeded("머리글")
    for e in tl.all("hook_slam"):
        m.put("머리글", osc(glide(150, 42, 0.6, 0.6)) * env(0.6, 0.004, 0.15), e["t"], 0.16, 0.0, rev=0.2)
        m.put("머리글", burst(rng, 0.25, 70, 900, 0.002, 0.045), e["t"], 0.16, 0.0, rev=0.3)
        m.put("머리글", burst(rng, 0.04, 1500, 6000, 0.0005, 0.005), e["t"], 0.05, 0.0, rev=0.3)
    for e in tl.all("rewind"):
        q = tt(e["dur"]) / e["dur"]
        scrub = 0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(glide(42, 14, e["dur"])) / SR)     # 테이프를 문지르듯 잘게 끊긴다 — 뒤로 갈수록 느리게
        zip_ = osc(glide(2400, 300, e["dur"], 0.7)) * scrub ** 2
        air = moving_noise(rng, glide(5200, 700, e["dur"], 0.7), 0.5)
        m.put("머리글", fade((0.7 * zip_ + air) * (1 - 0.6 * q), 0.02, 0.06), e["t"], 0.06, 0.5 * tl.pan_stage, rev=0.2)
    for e in tl.all("final_message"):
        for side in (-0.4, 0.4):
            m.put("머리글", burst(rng, 1.2, 6500, 13000, 0.15, 0.35), e["t"], 0.03, side, rev=0.5)


KEY_TONES = {       # 글쇠 종류 → (틱 대역 Hz, 틱 길이, 몸통 Hz, 몸통 길이, 몸통 비율, 세기)
    "key": ((1900, 5200), 0.0022, 190, 0.010, 0.45, 0.042),
    "space": ((1100, 3200), 0.0035, 135, 0.016, 0.65, 0.048),
    "enter": ((800, 2400), 0.0060, 98, 0.032, 0.90, 0.070),
    "enter_error": ((250, 900), 0.0120, 72, 0.050, 1.10, 0.085),
}


def key_click(rng, band, tick_tau, body_f, body_tau, body_mix):
    """글쇠 한 번: 대역 잡음 '틱' + 작은 몸통 울림. 부를 때마다 음높이가 조금씩 다르다."""
    j = rng.uniform(0.86, 1.16)
    dur = 0.03 + 4 * body_tau
    body = osc(glide(1.3 * body_f * j, body_f * j, dur, 0.5)) * env(dur, 0.001, body_tau)
    return burst(rng, dur, band[0] * j, band[1] * j, 0.0003, tick_tau) + body_mix * body


def typing(m: Mix, tl: Timeline):
    """타자: 글쇠마다 음높이·세기·자리가 조금씩 달라 기계음처럼 들리지 않는다. 떼는 소리도 작게 따라온다.
    첫머리의 전체 선택은 글쇠 둘을 겹쳐 누르는 '칙'."""
    rng = seeded("타자")
    typed: dict[int, int] = {}                                          # 줄마다 지금까지 친 글쇠 수 → 커서 자리
    for e in tl.events:
        if e["type"] not in KEY_TONES:
            continue
        band, tick_tau, body_f, body_tau, body_mix, gain = KEY_TONES[e["type"]]
        col = typed.get(e.get("line"), 0)
        typed[e.get("line")] = col + 1
        pan = tl.pan(min(tl.code_x + tl.cell_w * col, tl.code_end)) + rng.uniform(-0.06, 0.06)
        m.put("타자", key_click(rng, band, tick_tau, body_f, body_tau, body_mix), e["t"], gain * rng.uniform(0.62, 1.0), pan)
        up = key_click(rng, (1.5 * band[0], 1.5 * band[1]), 0.7 * tick_tau, body_f, body_tau, 0.2 * body_mix)
        m.put("타자", up, e["t"] + rng.uniform(0.05, 0.085), 0.22 * gain * rng.uniform(0.5, 1.0), pan)
    band, tick_tau, body_f, body_tau, body_mix, gain = KEY_TONES["key"]
    for e in tl.all("select_all"):
        for dt, level in ((0.0, 1.0), (0.014, 0.8)):
            m.put("타자", key_click(rng, band, tick_tau, body_f, body_tau, body_mix), e["t"] + dt, gain * level, tl.pan_code + 0.2)


def couriers(m: Mix, tl: Timeline):
    """코드 줄에서 무대로 날아가는 빛: 오른쪽에서 왼쪽으로 옮겨 가며 치솟는 '슈욱', 도착하는 순간 딱 끝난다."""
    rng = seeded("빛")
    for e in tl.all("courier"):
        q = tt(e["dur"]) / e["dur"]
        zip_ = osc(glide(650, 3300, e["dur"], 1.6)) * q ** 2
        air = moving_noise(rng, glide(1500, 7500, e["dur"]), 0.45) * q ** 1.5
        pan = np.linspace(tl.pan_code, tl.pan_stage, len(q))
        m.put("무대", fade(zip_ + 0.8 * air, 0, 0.012), e["t"], 0.05, pan, rev=0.35)
        for q0 in (0.55, 0.8):                                          # 반짝 두 번
            twinkle = sine(rng.uniform(3600, 6200), 0.05) * env(0.05, 0.001, 0.012)
            m.put("무대", twinkle, e["t"] + q0 * e["dur"], 0.02, float(np.interp(q0, q, pan)), rev=0.5)


def flap_tick(rng):
    """접이식 숫자판 한 장이 넘어가는 '칙'."""
    j = rng.uniform(0.85, 1.2)
    return burst(rng, 0.02, 1800 * j, 6500 * j, 0.0003, 0.0018) + 0.4 * sine(1450 * j, 0.02) * env(0.02, 0.0005, 0.004)


def board(m: Mix, tl: Timeline):
    """연도판: 위에서 떨어지는 '휙' → 내려앉는 '딱' + 작은 종 → 숫자가 멈출 때까지 '차르륵'.
    새해로 넘어갈 때는 느린 '드르륵' 끝에 '철컥' + 박자에 딱 맞는 밝은 종 화음."""
    rng = seeded("연도판")
    pan = tl.pan_stage
    drop, land, settle = tl.time("board_drop"), tl.time("board_land"), tl.time("board_settle")
    if drop is not None and land is not None and land > drop:
        q = tt(land - drop) / (land - drop)
        whoosh = moving_noise(rng, glide(2800, 600, land - drop), 0.6) * q ** 1.5
        m.put("무대", fade(whoosh, 0, 0.02), drop, 0.06, pan, rev=0.3)
    if land is not None:
        m.put("무대", burst(rng, 0.05, 900, 4200, 0.0005, 0.007), land, 0.10, pan, rev=0.3)
        m.put("무대", osc(glide(170, 80, 0.16)) * env(0.16, 0.002, 0.035), land, 0.10, pan, rev=0.3)
        m.put("무대", bell(note("C6"), 0.9, tau=0.3), land, 0.05, pan, rev=0.6)
    if drop is not None and settle is not None and settle > drop:
        flaps = max(1, round((settle - drop) / 0.05))
        for i in range(1, flaps + 1):                                   # 촘촘하다가 점점 성기게 → 멈춘다
            when = drop + (settle - drop) * (i / flaps) ** 1.3
            m.put("무대", flap_tick(rng), when, 0.03 + 0.03 * i / flaps, pan + rng.uniform(-0.1, 0.1), rev=0.2)
    for e in tl.all("year_roll"):
        clicks = max(3, round(e["dur"] / 0.055))
        for i in range(clicks):                                         # 톱니가 점점 느리게 걸린다. 마지막 톱니가 '철컥'의 '철'
            u = i / (clicks - 1)
            tooth = flap_tick(rng) + 0.6 * osc(glide(900 - 250 * u, 600 - 250 * u, 0.02)) * env(0.02, 0.0005, 0.005)
            m.put("무대", tooth, e["t"] + 0.86 * e["dur"] * u ** 1.5, 0.04 + 0.05 * u, pan, rev=0.25)
    for e in tl.all("year_gold"):
        m.put("무대", osc(glide(170, 75, 0.2)) * env(0.2, 0.002, 0.045), e["t"], 0.11, pan, rev=0.3)
        m.put("무대", burst(rng, 0.05, 700, 3800, 0.0005, 0.008), e["t"], 0.09, pan, rev=0.3)
        for i, (name, gain, tau) in enumerate((("C6", 0.060, 0.55), ("G6", 0.050, 0.5), ("C7", 0.040, 0.45), ("E7", 0.022, 0.2))):
            m.put("무대", bell(note(name), 1.8, tau=tau), e["t"], gain, pan + 0.2 * (i - 1.5), rev=0.7)   # 딸림화음 '도 솔 도 미'
        for side in (-0.3, 0.3):
            m.put("무대", burst(rng, 1.6, 5000, 13000, 0.18, 0.4), e["t"], 0.03, pan + side, rev=0.5)


def snow(m: Mix, tl: Timeline):
    """눈: 높은 바람결 '사아—' + 유리알 같은 '딩' 세 번(내려오는 음)."""
    rng = seeded("눈")
    for e in tl.all("snow_start"):
        for side in (-0.85, -0.05):
            m.put("무대", burst(rng, 2.4, 5500, 12500, 0.35, 0.65), e["t"], 0.035, side, rev=0.5)
        for name, dt, side in (("C7", 0.0, -0.7), ("A6", 0.17, -0.2), ("F6", 0.41, -0.5)):
            m.put("무대", bell(note(name), 0.9, tau=0.3, partials=GLASS), e["t"] + dt, 0.05, side, rev=0.8)


def night_air(m: Mix, tl: Timeline):
    """바탕: 아주 작은 밤공기. 영상 길이에 꼭 맞는 주기 잡음이라 반복 재생에도 이음매가 없다."""
    rng = seeded("바탕")
    breath = 1 + 0.25 * np.sin(2 * np.pi * 3 * np.arange(tl.n) / tl.n)
    for side in (-0.6, 0.6):
        air = fft_filter(rng.normal(size=tl.n), lo=180, hi=1300, order=2)
        m.put("바탕", air / np.sqrt(np.mean(air ** 2)) * breath, 0.0, 0.0035, side)


def worker(m: Mix, tl: Timeline):
    """삽질러: 떨어지는 휘파람 → 내려앉는 '툭' + 귀여운 '뿅'. 말풍선은 '뽁', 글자는 하나씩 첼레스타 '도 미 솔 도',
    확인란 체크는 '틱', 흙더미가 금빛으로 바뀔 때는 작은 종이 5음 음계를 타고 오르고 헛삽질이 0이 되면 반짝."""
    rng = seeded("삽질러")
    pan = tl.pan_stage
    fall, land = tl.time("worker_fall"), tl.time("worker_land")
    if fall is not None and land is not None and land > fall:
        t = tt(land - fall)
        whistle = osc(glide(1900, 620, land - fall) * (1 + 0.012 * np.sin(2 * np.pi * 9 * t)))
        m.put("무대", fade(whistle, 0.03, 0.02), fall, 0.04, pan, rev=0.3)
    if land is not None:
        m.put("무대", osc(glide(125, 52, 0.25, 0.6)) * env(0.25, 0.003, 0.06), land, 0.12, pan, rev=0.25)
        m.put("무대", burst(rng, 0.25, 200, 1800, 0.004, 0.05), land, 0.07, pan, rev=0.3)
        for name, dt, length in (("G5", 0.07, 0.05), ("C6", 0.125, 0.09)):      # 뿅: 솔 → 도
            blip = (sine(note(name), length) + 0.25 * sine(2 * note(name), length)) * env(length, 0.003, 0.03)
            m.put("무대", blip, land + dt, 0.055, pan, rev=0.4)
    for e in tl.all("bubble"):
        m.put("무대", osc(glide(380, 1000, 0.06)) * env(0.06, 0.003, 0.018), e["t"], 0.12, pan + 0.15, rev=0.3)
    for e in tl.all("say_glyph"):                                       # 딸림화음을 타고 오른다: C6 E6 G6 C7 …
        f = note("C6") * 2 ** (e["i"] // 3 + (0, 4, 7)[e["i"] % 3] / 12)
        m.put("무대", bell(f, 0.7, tau=0.22, partials=CELESTA), e["t"], 0.075, pan + 0.1 * e["i"], rev=0.6)
    for e in tl.all("check"):
        m.put("무대", burst(rng, 0.02, 2500, 8000, 0.0003, 0.002), e["t"], 0.05, pan, rev=0.3)
        m.put("무대", sine(3136, 0.04) * env(0.04, 0.0005, 0.008), e["t"], 0.03, pan, rev=0.4)
    for e in tl.all("gild"):                                            # 흙더미가 쌓일 때와 같은 음을 한 옥타브 위에서 두 배 빠르게
        chime = musicbox(penta(e["k"] - (tl.bands - 1) + 10, 5), 0.35, ring=0.3)
        m.put("무대", chime, e["t"], 0.035, pan + 0.03 * (e["k"] - tl.bands / 2), rev=0.6)
    for e in tl.all("waste_zero"):
        for dt in (0.0, 0.03, 0.07):
            m.put("무대", sine(rng.uniform(3800, 6200), 0.06) * env(0.06, 0.001, 0.014), e["t"] + dt, 0.025, pan + rng.uniform(0.1, 0.4), rev=0.6)
        m.put("무대", burst(rng, 0.25, 6000, 12000, 0.01, 0.06), e["t"], 0.02, pan + 0.25, rev=0.5)


def shovel_hit(rng, bright=1.0):
    """삽이 흙에 박히는 '칙': 거친 흙 소리 + 삽날 쇳소리 조금 + 낮은 '퍽'."""
    grit = burst(rng, 0.09, 450 * bright, 3600 * bright, 0.001, 0.016)
    blade = sum(a * sine(f * bright * rng.uniform(0.96, 1.04), 0.09) for f, a in ((2150, 1.0), (3380, 0.6), (5270, 0.35)))
    thud = osc(glide(150, 70, 0.09)) * env(0.09, 0.002, 0.022)
    return 0.8 * grit + 0.12 * blade * env(0.09, 0.0005, 0.012) + 0.5 * thud


def dig(m: Mix, tl: Timeline):
    """삽질: 삽 한 번에 '칙'(8분음표 둘 → 16분음표 열 — 이 장면의 타악기), 한 달치가 쌓일 때마다 5음 음계가 한 음씩 오른다.
    마지막 달(12월)이 으뜸음 F6에 닿는다."""
    rng = seeded("삽질")
    pan = tl.pan_stage
    hits = tl.all("dig_hit")
    for e in hits:
        swell = 0.8 + 0.2 * e["i"] / max(len(hits) - 1, 1)             # 뒤로 갈수록 조금씩 세게
        m.put("삽질", shovel_hit(rng, 1 + 0.02 * e["i"]), e["t"], 0.14 * swell, pan + rng.uniform(-0.08, 0.08), rev=0.25)
    for e in tl.all("band"):
        tick = musicbox(penta(e["k"] - (tl.bands - 1) + 10), 0.5, ring=0.35)
        m.put("삽질", tick, e["t"], 0.050 + 0.002 * e["k"], pan, rev=0.4)
        m.put("삽질", burst(rng, 0.08, 700, 2600, 0.004, 0.02), e["t"], 0.02, pan - 0.1, rev=0.3)     # 흙이 얹히는 '폭'


def countdown(m: Mix, tl: Timeline):
    """카운트다운: 숫자마다 목탁 같은 '똑' + 초침 '틱' + 낮은 '쿵'. 숫자가 줄수록 음이 오르고 세지며,
    마지막 숫자 밑에서는 바람 소리가 차올랐다가 한 박 뒤에 뚝 끊긴다."""
    rng = seeded("카운트다운")
    counts = tl.all("count")
    pan = tl.pan_stage
    for i, e in enumerate(counts):
        f = penta(7 + i - (len(counts) - 1))                            # … 파 솔 라(A5)로 끝난다
        block = sine(f, 0.12) * env(0.12, 0.0008, 0.022) + 0.5 * sine(2.76 * f, 0.12) * env(0.12, 0.0005, 0.009)
        m.put("무대", block, e["t"], 0.075 + 0.012 * i, pan, rev=0.3)
        m.put("무대", burst(rng, 0.03, 1800, 6000, 0.0004, 0.003), e["t"], 0.035, pan, rev=0.2)
        m.put("무대", osc(glide(150, 46, 0.32, 0.6)) * env(0.32, 0.003, 0.085), e["t"], 0.07 + 0.02 * i, 0.6 * pan, rev=0.25)
        m.put("무대", burst(rng, 0.12, 120, 800, 0.002, 0.03), e["t"], 0.05 + 0.012 * i, 0.6 * pan, rev=0.25)
    if counts:
        span = counts[1]["t"] - counts[0]["t"] if len(counts) > 1 else tl.beat
        riser = moving_noise(rng, glide(500, 5200, span), 0.5) * (tt(span) / span) ** 2.2
        m.put("무대", fade(riser, 0, 0.012), counts[-1]["t"], 0.05, pan, rev=0.25)


def twist(m: Mix, tl: Timeline):
    """반전: 연도판이 걸리는 '철컥' + 낮고 짧은 '삐—'(오답 소리) → 도장 '쿵' → 숫자가 도로 떨어지는 '툭'.
    고치는 줄이 실행되면 도장이 뒤집히는 작고 밝은 '팅'."""
    rng = seeded("반전")
    pan = 0.6 * tl.pan_stage
    for e in tl.all("jam"):
        clack = sum(a * sine(f, 0.12) for f, a in ((1180, 1.0), (1870, 0.7), (2930, 0.5), (4410, 0.3))) * env(0.12, 0.0005, 0.03)
        m.put("버저", unit(clack), e["t"], 0.055, pan, rev=0.25)
        m.put("버저", burst(rng, 0.03, 2000, 7000, 0.0003, 0.003), e["t"], 0.05, pan, rev=0.25)
        q = tt(BUZZ) / BUZZ
        droop = 1 - 0.04 * q                                            # 끝으로 갈수록 살짝 처진다
        buzz = square(note("B2") * droop, 3200) + 0.7 * square(note("F3") * droop, 3200)    # 증4도 — 틀렸다는 소리
        buzz *= 1 - 0.18 * np.sin(2 * np.pi * 31 * BUZZ * q) ** 2
        m.put("버저", fade(buzz, 0.004, 0.03), e["t"], 0.06, pan, rev=0.12)
    for e in tl.all("stamp"):
        land = e["t"] + STAMP_LAND
        swish = moving_noise(rng, glide(1600, 500, STAMP_LAND), 0.5) * tt(STAMP_LAND) / STAMP_LAND
        m.put("도장", swish, e["t"], 0.03, pan)
        m.put("도장", osc(glide(115, 44, 0.45, 0.6)) * env(0.45, 0.003, 0.085), land, 0.20, pan, rev=0.1)
        m.put("도장", burst(rng, 0.22, 80, 700, 0.002, 0.035), land, 0.19, pan, rev=0.1)
        m.put("도장", burst(rng, 0.05, 900, 2800, 0.0005, 0.007), land, 0.07, pan, rev=0.1)
    for e in tl.all("jam_drop"):
        m.put("도장", osc(glide(260, 150, 0.08)) * env(0.08, 0.002, 0.018), e["t"], 0.045, pan, rev=0.1)
        m.put("도장", flap_tick(rng), e["t"], 0.03, pan)
    for e in tl.all("fix_stamp"):
        m.put("도장", bell(note("C7"), 0.5, tau=0.12), e["t"], 0.05, pan, rev=0.3)
        m.put("도장", burst(rng, 0.02, 3000, 9000, 0.0003, 0.002), e["t"], 0.03, pan)


def fireworks(m: Mix, tl: Timeline):
    """불꽃: 올라가는 휘파람(길이 = rise) → '펑' + 타닥타닥. 클수록 낮고 길고 크다. 좌우 자리는 화면의 x를 따른다.
    버들(willow)은 여린 '펑'에 긴 '치이—', 삽 모양(shape)은 크기와 상관없이 가장 큰 '펑'에 가장 긴 꼬리."""
    rng = seeded("불꽃")

    def pan_of(e):
        return tl.pan(e["x"] * tl.stage_w)

    def pop(t, s, level, pan, tail=1.0):
        """한 번 터지는 '펑': 낮은 울림 + 몸통 + 날카로운 첫소리. s(0~1)가 클수록 낮고 길다."""
        tau = (0.07 + 0.2 * s ** 1.5) * tail
        low = 62 / s ** 0.9
        m.put("불꽃", osc(glide(2.2 * low, 0.8 * low, 5 * tau, 0.5)) * env(5 * tau, 0.003, tau), t, 0.5 * level, 0.7 * pan, rev=0.4)
        m.put("불꽃", burst(rng, 4 * tau, 60, 600 / s, 0.002, 0.6 * tau), t, 0.8 * level, pan, rev=0.6)
        m.put("불꽃", burst(rng, 0.04, 1400, 6500, 0.0004, 0.005), t, 0.35 * level, pan, rev=0.5)

    for e in tl.all("fw_launch"):
        q = tt(e["rise"]) / e["rise"]
        j = rng.uniform(0.8, 1.25)
        whistle = osc(glide(650 * j, 1700 * j, e["rise"], 0.8) * (1 + 0.012 * np.sin(2 * np.pi * 17 * e["rise"] * q)))
        air = moving_noise(rng, glide(1800, 5200, e["rise"]), 0.4)
        m.put("불꽃", (whistle + 0.6 * air) * np.sin(np.pi * q) ** 0.8 * (1 - 0.6 * q), e["t"], 0.016, pan_of(e), rev=0.5)

    bursts = tl.all("fw_burst")
    biggest = max((e["size"] for e in bursts), default=1.0)
    for e in bursts:
        kind, pan = e.get("kind"), pan_of(e)
        s = 1.0 if kind == "shape" else max(e["size"] / biggest, 0.2)
        level = {"shape": 0.50, "willow": 0.16}.get(kind, 0.26) * s ** 1.5
        pop(e["t"], s, level, pan, tail=1.5 if kind == "shape" else 1.0)
        if kind == "double":                                            # 두 겹 불꽃: 작게 한 번 더
            pop(e["t"] + 0.09, 0.7 * s, 0.45 * level, pan)
        span = (0.35 + 0.6 * s) * (1.6 if kind in ("willow", "shape") else 1.0)
        for u in rng.uniform(0, 1, int(10 + 50 * s ** 2)) ** 1.5:       # 타닥타닥 — 앞쪽에 몰려 있다
            grain = burst(rng, 0.008, 2600, 9500, 0.0002, rng.uniform(0.0006, 0.002))
            m.put("불꽃", grain, e["t"] + 0.07 + span * u, 0.05 * s * (1 - u) ** 1.2 * rng.uniform(0.4, 1.0),
                  pan + 0.3 * s * rng.uniform(-1, 1), rev=0.3)
        if kind in ("willow", "shape"):                                 # 흘러내리는 불티
            m.put("불꽃", burst(rng, 1.4, 3000, 9000, 0.05, 0.4), e["t"] + 0.05, 0.03 * s, pan, rev=0.5)


# ======================================================================== 구간 나누기 · 마스터
def arrange(layers: dict, tl: Timeline):
    """겹마다 ① 연도판이 걸리는 순간 음악·무대의 울림을 뚝 끊고(나 구간 — 타자·버저·도장만 남는다)
    ② 영상 끝에서 천천히 닫는다(반복 재생의 첫 음이 앞 바퀴의 꼬리에 묻히지 않게). 밤공기는 주기 잡음이라 닫지 않는다."""
    t = np.arange(tl.n) / SR
    tune = stage = air = np.ones(tl.n)
    if tl.jam is not None:
        back = 0.0 if tl.resume is None else ramp(t, tl.resume - 0.003, 0.003)
        tune = 1 - ramp(t, tl.jam, CHOP) + back
        stage = 1 - ramp(t, tl.jam, CHOP) + ramp(t, tl.reopen - 0.003, 0.003)
        air = 1 - ramp(t, tl.jam, 0.06) + ramp(t, tl.reopen, 0.3)
    start, end = tl.duration - CURTAIN[0], tl.duration - CURTAIN[1]
    curtain = 0.5 + 0.5 * np.cos(np.pi * ramp(t, start, end - start))
    gates = {**{name: tune * curtain for name in MUSIC}, "바탕": air, "타자": 1.0, "버저": curtain, "도장": curtain}
    return {name: x * np.reshape(gates.get(name, stage * curtain), (-1, 1)) for name, x in layers.items()}


def duck(tl: Timeline, notes):
    """다 구간의 가락 음이 울리는 순간마다 불꽃이 살짝 비켜 주는 크기 곡선(5ms에 내려갔다가 0.18초 간격으로 돌아온다)."""
    gain = np.ones(tl.n)
    t = tt(1.0)
    dip = 1 - DUCK * ramp(t, 0, 0.005) * np.exp(-np.clip(t - 0.005, 0, None) / 0.18)
    for nt in notes:
        if nt.section == "C":
            i0 = int(round(nt.t * SR))
            part = dip[:max(tl.n - i0, 0)]
            gain[i0:i0 + len(part)] = np.minimum(gain[i0:i0 + len(part)], part)
    return gain


def k_weighted(x):
    """ITU-R BS.1770 청감 보정(높은 음 선반 + 저음 거르개, 48kHz 계수). 주파수 영역에서 한 번에 건다."""
    z = np.exp(-2j * np.pi * np.fft.rfftfreq(len(x)))
    shelf = (1.53512485958697 - 2.69169618940638 * z + 1.19839281085285 * z ** 2) / (1 - 1.69065929318241 * z + 0.73248077421585 * z ** 2)
    highpass = (1 - 2 * z + z ** 2) / (1 - 1.99004745483398 * z + 0.99007225036621 * z ** 2)
    return np.fft.irfft(np.fft.rfft(x, axis=0) * (shelf * highpass)[:, None], len(x), axis=0)


def loudness(x):
    """통합 음량(LUFS): 0.4초 토막을 0.1초씩 옮겨 가며 재고, 조용한 토막(-70 LUFS 아래 · 평균보다 10 LU 아래)은 뺀다."""
    power = np.cumsum(np.vstack([np.zeros((1, 2)), k_weighted(x) ** 2]), axis=0)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    starts = np.arange(0, len(x) - blk + 1, hop)
    z = ((power[starts + blk] - power[starts]) / blk).sum(axis=1)

    def lufs(z):
        return -0.691 + 10 * np.log10(np.mean(z))

    z = z[z > 10 ** ((-70 + 0.691) / 10)]
    z = z[z > 10 ** ((lufs(z) - 10 + 0.691) / 10)]
    return lufs(z)


def true_peak(x):
    """표본 사이 봉우리까지 본 크기(4배로 촘촘히 되살려 표본마다 최댓값 하나)."""
    up = np.fft.irfft(np.fft.rfft(x, axis=0), 4 * len(x), axis=0) * 4
    return np.abs(up).max(axis=1).reshape(len(x), 4).max(axis=1)


def limit(x):
    """트루 피크 제한기: 넘치는 곳만 앞뒤 11ms에 걸쳐 살짝 눌렀다 놓는다. 영상이 반복되므로 양 끝도 이어서 계산한다."""
    gain = np.minimum(1.0, CEILING / np.maximum(true_peak(x), 1e-9))
    for shift in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512):
        gain = np.minimum(gain, np.roll(gain, shift))                   # 지난 1024표본 가운데 가장 작은 값
    gain = np.roll(gain, -512)                                          # → 앞뒤 512표본
    win = np.hanning(1025)[1:-1]
    gain = np.convolve(np.concatenate([gain[-511:], gain, gain[:511]]), win / win.sum(), mode="valid")
    return x * gain[:, None]


def master(x):
    """-14 LUFS에 맞추고 트루 피크를 한도 아래로. 제한기가 음량을 조금 깎으므로 몇 번 되풀이해 맞춘다.
    돌려주는 것: (완성 소리, 제한기 앞에서 곱한 배율, 제한기가 가장 많이 누른 양 dB)."""
    gain = 1.0
    for _ in range(4):
        gain *= 10 ** ((TARGET_LUFS - loudness(limit(x * gain))) / 20)
    y = limit(x * gain)
    y[-int(EDGE * SR):] *= np.linspace(1, 0, int(EDGE * SR))[:, None]   # 글쇠 소리가 파일 끝에 걸려도 뚝 끊기지 않게
    return y, gain, max(db(float(true_peak(x * gain).max()) / CEILING), 0.0)


# ======================================================================== 파일 · 측정
def write_wav(path: Path, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.round(np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def mux(video: Path, audio: Path, out: Path, duration):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                    "-ar", str(SR), "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out)], check=True)


def measure(path: Path):
    """ffmpeg ebur128로 잰 (통합 음량 LUFS, 트루 피크 dBTP)."""
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = log[log.rindex("Summary:"):]
    return (float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1)),
            float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary).group(1)))


def db(v):
    return 20 * math.log10(v) if v > 0 else -math.inf


def rms_db(x, t0, t1):
    return db(float(np.sqrt(np.mean(x[int(t0 * SR):int(t1 * SR)] ** 2))))


def pitch(x, t0, t1):
    """t0~t1초에서 가장 센 음의 주파수(Hz) — 창을 씌운 FFT의 봉우리를 포물선으로 다듬는다."""
    part = x[int(t0 * SR):int(t1 * SR)]
    size = 1 << 18
    spec = np.abs(np.fft.rfft(part * np.hanning(len(part)), size))
    lo, hi = (int(f * size / SR) for f in (200, 4000))
    k = lo + int(np.argmax(spec[lo:hi]))
    a, b, c = np.log(spec[k - 1:k + 2] + 1e-30)
    return (k + 0.5 * (a - c) / (a - 2 * b + c)) * SR / size


def onset(x, t, before=0.04, after=0.06):
    """t초 근처(-before ~ +after)에서 소리가 가장 가파르게 커지는 시각(초). 3ms 평균 크기의 앞뒤 차이로 찾는다."""
    w = int(0.003 * SR)
    i0 = int(round((t - before) * SR)) - w
    i1 = min(int(round((t + after) * SR)) + w, len(x))
    part = np.concatenate([np.zeros(max(-i0, 0)), x[max(i0, 0):i1]])   # 파일 앞쪽 바깥은 무음
    power = np.cumsum(np.concatenate([[0.0], part ** 2]))
    level = np.sqrt((power[w:] - power[:-w]) / w)                       # level[i] = part[i : i+w]의 크기
    return (i0 + w + int(np.argmax(level[w:] - level[:-w]))) / SR


# ======================================================================== 요약
def cell(text, width):
    """한글은 두 칸을 차지하므로 화면 너비 기준으로 채운다."""
    return text + " " * max(width - sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text), 0)


def row(*cells):
    print("  " + "".join(cell(text, width) for text, width in cells).rstrip())


def level_text(v):
    return f"{v:6.1f}" if math.isfinite(v) else "  없음"


def report_layers(layers, gain):
    row(("겹", 8), ("최대(dBFS)", 12), ("내용", 0))
    for name, what in LAYERS.items():
        row((name, 8), (level_text(db(float(np.max(np.abs(layers[name]))) * gain)), 12), (what, 0))


def report_tune(tl: Timeline, notes, voice):
    """가락의 음마다 악보(격자)의 시각·음높이와 소리에서 잰 값을 나란히 적는다. voice = 가락 겹(한 줄기)."""
    print(f"가락  〈석별의 정〉 F장조 · {60 / tl.beat:.0f} BPM · 첫 마디 첫 박 {tl.downbeat:.3f}초 · 구간 A 가늘게 / B 정적(쉼) / C 크게")
    row(("마디.박", 9), ("음", 5), ("구간", 6), ("악보(초)", 10), ("소리(초)", 10), ("어긋남", 9), ("악보(Hz)", 10), ("소리(Hz)", 10), ("차이", 0))
    sounding = [nt for nt in notes if nt.section != "B"]
    worst_ms = worst_pct = 0.0
    for nt in notes:
        head = [("못갖춘" if nt.bar == 0 else f"{nt.bar}.{nt.beat:g}", 9), (nt.name, 5), (nt.section, 6), (f"{nt.t:.3f}", 10)]
        if nt.section == "B":
            row(*head, ("쉼", 0))
            continue
        later = [o.t for o in sounding if o.t > nt.t]
        stop = min([nt.t + nt.beats * tl.beat, tl.duration] + later[:1] + ([tl.jam] if nt.section == "A" and tl.jam else []))
        heard, hz, want = onset(voice, nt.t), pitch(voice, nt.t + 0.005, stop), note(nt.name)
        worst_ms, worst_pct = max(worst_ms, abs(heard - nt.t) * 1000), max(worst_pct, abs(hz / want - 1) * 100)
        row(*head, (f"{heard:.3f}", 10), (f"{(heard - nt.t) * 1000:+.0f}ms", 9), (f"{want:.1f}", 10), (f"{hz:.1f}", 10), (f"{(hz / want - 1) * 100:+.2f}%", 0))
    if sounding:
        verdict = "기준 안" if worst_ms <= 20 and worst_pct <= 1 else "기준을 벗어남"
        print(f"  울린 음 {len(sounding)}개 · 쉰 음 {len(notes) - len(sounding)}개 — 가장 큰 어긋남 {worst_ms:.0f}ms · {worst_pct:.2f}% ({verdict}: 20ms · 1%)")


def report_sections(tl: Timeline, layers, out, gain):
    """가·다 구간 가락의 크기 차이와, 연도판이 걸린 뒤의 정적이 얼마나 깊은지."""
    voice = layers["가락"].mean(axis=1)
    if tl.jam is None:
        print("구간  연도판이 걸리지 않는다 — 가 구간(가는 편곡)이 끝까지 간다")
        return
    if tl.resume is None:
        print(f"구간  {tl.jam:.3f}초에 음악이 끊기고, 고마운 말이 없어 돌아오지 않는다")
    else:
        thin, full = (float(np.max(np.abs(voice[a:b]))) for a, b in ((0, int(tl.jam * SR)), (int(tl.resume * SR), tl.n)))
        print(f"구간  가락 최대: 가 구간이 다 구간보다 {db(thin / full):.1f} dB · 음악은 {tl.jam:.3f}초에 끊겨 {tl.resume:.3f}초에 돌아온다")
    tune = sum(layers[name] for name in MUSIC)
    print(f"      음악 겹(가락·화음·방울) {tl.jam + 0.1:.3f}~{tl.resume or tl.duration:.3f}초: {level_text(rms_db(tune, tl.jam + 0.1, tl.resume or tl.duration)).strip()} dB(RMS)")

    stamp = tl.time("stamp")
    failed = next((e.get("line") for e in tl.all("enter_error")), None)
    nxt = [e for e in tl.events if e["type"] in KEY_TONES and failed is not None and e.get("line") == failed + 1]
    if stamp is None or not nxt:
        return
    before = rms_db(out, max(tl.jam - 2, 0), tl.jam)
    hush, first_key, enter = stamp + 0.35, nxt[0]["t"], nxt[-1]["t"]
    print(f"정적  반전 직전 2초 {before:.1f} dB(RMS, 완성 믹스)")
    if first_key > hush:
        print(f"      도장+0.35초({hush:.3f}) → 다음 줄 첫 글쇠({first_key:.3f}): {rms_db(out, hush, first_key):.1f} dB — 차이 {before - rms_db(out, hush, first_key):.1f} dB")
    else:
        print(f"      도장+0.35초({hush:.3f}) → 다음 줄 첫 글쇠({first_key:.3f}): 글쇠가 먼저라 빈 구간이 없다 — 타자 소리가 정적을 채운다")
    if enter > hush:
        rest = sum(x for name, x in layers.items() if name != "타자") * gain
        print(f"      도장+0.35초({hush:.3f}) → 다음 줄 Enter({enter:.3f}): 타자까지 {rms_db(out, hush, enter):.1f} dB(차이 {before - rms_db(out, hush, enter):.1f} dB)"
              f" · 타자를 빼면 {level_text(rms_db(rest, hush, enter)).strip()} dB")


def report_sync(tl: Timeline, out):
    """화면의 사건 시각과 완성 믹스에서 소리가 솟는 시각을 나란히 적는다(종류마다 첫 사건 하나)."""
    mono = out.mean(axis=1)
    print("맞물림  사건 시각 ↔ 완성 믹스에서 소리가 솟는 시각")
    row(("사건", 14), ("시각표(초)", 12), ("소리(초)", 10), ("어긋남", 0))
    for kind in SYNC:
        if tl.time(kind) is not None:
            heard = onset(mono, tl.time(kind))
            row((kind, 14), (f"{tl.time(kind):.3f}", 12), (f"{heard:.3f}", 10), (f"{(heard - tl.time(kind)) * 1000:+.0f}ms", 0))


def main():
    ap = argparse.ArgumentParser(description="새해 코드 릴스 소리 합성")
    ap.add_argument("--no-mux", action="store_true", help="wav만 만들고 영상에는 입히지 않는다")
    ap.add_argument("--events", type=Path, help="다른 시각표(events.json)로 합성한다 — 영상에는 입히지 않는다")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "audio", help="wav를 둘 폴더(기본 ../audio)")
    args = ap.parse_args()

    data = load_events(args.events)
    tl = Timeline(data)
    m = Mix(tl.n)
    for scene in (headline, typing, couriers, board, snow, night_air, worker, dig, countdown, twist, fireworks):
        scene(m, tl)
    notes = music(m, tl)
    layers = arrange(m.render(), tl)
    fx, _, fx_pressed = master(sum(x for name, x in layers.items() if name not in MUSIC))      # 효과음판의 불꽃은 비켜 줄 가락이 없다
    layers["불꽃"] = layers["불꽃"] * duck(tl, notes)[:, None]
    full, gain, pressed = master(sum(layers.values()))

    wavs = {name: args.out_dir / name for name in OUTPUTS}
    for name, x in zip(wavs, (full, fx)):
        write_wav(wavs[name], x)
    muxed = not args.no_mux and args.events is None and SILENT.exists()
    if muxed:
        for name, out in OUTPUTS.items():
            mux(SILENT, wavs[name], out, tl.duration)

    print(f"소리 합성 완료 — {tl.n / SR:.3f}초 · {SR}Hz 스테레오 16비트 · 표본 {len(full)}개(전체) · {len(fx)}개(효과음판)")
    print()
    report_layers(layers, gain)
    print()
    for (name, path), squeezed, what in zip(wavs.items(), (pressed, fx_pressed), ("전체 믹스", "효과음판(가락·화음·방울 없음)")):
        lufs, peak = measure(path)
        print(f"{cell(what, 30)} 통합 음량 {lufs:.1f} LUFS (목표 {TARGET_LUFS:.0f} ±1) · 트루 피크 {peak:.1f} dBTP (한도 -1.0) · 제한기가 누른 최대 {squeezed:.1f} dB")
    print()
    report_tune(tl, notes, layers["가락"].mean(axis=1))
    print()
    report_sections(tl, layers, full, gain)
    print()
    report_sync(tl, full)
    print()
    for path in wavs.values():
        print(f"{path}  {path.stat().st_size / 1e6:.2f} MB")
    if muxed:
        for out in OUTPUTS.values():
            print(f"{out}  {out.stat().st_size / 1e6:.2f} MB (영상 복사 + AAC 256k)")
        if SILENT.stat().st_mtime < newest_source():
            print("주의: 무음 영상이 대본·엔진보다 오래됐습니다 — 화면이 달라졌다면 `node render.js`로 다시 만든 뒤 한 번 더 돌리세요.")
    elif args.events is not None:
        print("다른 시각표로 만든 소리라 영상에는 입히지 않았습니다.")
    elif not args.no_mux:
        print(f"무음 영상이 없어 소리만 만들었습니다: {SILENT} — 먼저 `node render.js`")


if __name__ == "__main__":
    main()
