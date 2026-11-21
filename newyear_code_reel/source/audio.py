#!/usr/bin/env python3
"""새해 코드 릴스 소리 — 소리 파일 없이 전부 NumPy로 합성한다(48kHz 스테레오 16비트).

    python3 audio.py            → ../audio/soundtrack.wav
                                  → ../newyear_code_reel_silent.mp4(무음 영상) + soundtrack.wav
                                  → ../newyear_code_reel.mp4 (영상은 다시 인코딩하지 않고 복사, 소리는 AAC 256k)
    python3 audio.py --no-mux   → wav만

시각은 build/events.json(시각표)에서만 읽는다. 대본(script.js)·박자표(timing.js)·엔진이 시각표보다 새것이면
`node render.js --events`로 먼저 다시 만든다 → 대본을 고쳐도 소리가 화면과 어긋나지 않는다.
시각표에 없는 사건은 소리도 없다(불꽃 줄을 지우면 불꽃 소리도, "수고했어"가 없으면 음악도 없다).

소리 겹(무대 소리는 왼쪽, 타자는 오른쪽, 음악은 가운데 · 타자에는 잔향을 넣지 않는다)
    불꽃    올라가는 휘파람 → 터지는 '펑'(클수록 낮고 길고 크게) + 타닥타닥, 좌우 자리는 화면 그대로
    반전    연도판이 걸리는 '철컥' + 낮고 짧은 '삐—' → 도장 '쿵' → 다음 줄 타자만 남는 정적
    머리글  0초 낚는 말 '쾅' · 되감기 '쮸르륵' · 맺는 말이 뜰 때 종
    음악    "수고했어" 말풍선부터 오르골 〈석별의 정〉(Auld Lang Syne — 저작권이 없는 옛 가락) + 포근한 화음,
            그 전에 흙더미가 한 달씩 쌓일 때마다 같은 조(F장조)의 음계가 한 음씩 올라간다(12번째 = 으뜸음)
    무대    코드에서 무대로 날아가는 빛 · 연도판(휙·딱·차르륵) · 눈 · 삽질러 등장 · 카운트다운(삑 + 쿵)
    삽질    삽 '칙' 세 번 → 점점 빨라지는 삽질
    타자    글쇠마다 '틱'(음높이·세기 제각각) · Enter '톡' · 오류 Enter '둑'
    바탕    아주 작은 밤공기(정적 구간에서는 이것도 사라진다)

영상은 끝이 처음으로 이어진다(첫머리에 완성 장면이 잠깐 계속된다). 그래서 영상 끝을 넘는 울림은 잘라 버리지 않고
첫머리에 겹치고, 되감기는 동안 사라지게 했다 → 반복 재생해도 이음매에서 소리가 끊기지 않는다.
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

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVENTS = HERE / "build" / "events.json"
SILENT = ROOT / "newyear_code_reel_silent.mp4"
FINAL = ROOT / "newyear_code_reel.mp4"
WAV = ROOT / "audio" / "soundtrack.wav"

SR = 48000
SEED = 20262027
TAIL = 3.0                          # 영상 끝을 넘겨 울리는 꼬리(초) — 첫머리에 겹친다
REVERB = 0.5                        # 잔향 크기
TARGET_LUFS = -14.0                 # 통합 음량 목표
CEILING = 10 ** (-1.4 / 20)         # 트루 피크 한도(-1.0 dBTP)보다 조금 아래
EDGE = 0.004                        # 파일 양 끝 여닫기(초)

LAYERS = {                          # 겹 이름 → 표에 적을 설명(큰 소리부터)
    "불꽃": "올라가는 휘파람 · 펑 · 타닥타닥",
    "반전": "연도판 철컥 + 삐— · 도장 쿵",
    "머리글": "0초 쾅 · 되감기 · 맺는 말 종",
    "음악": "오르골 〈석별의 정〉 + 화음 · 달마다 오르는 음계 · 금빛 종",
    "무대": "날아가는 빛 · 연도판 · 눈 · 삽질러 · 카운트다운",
    "삽질": "삽 칙 세 번 → 빨라지는 삽질",
    "타자": "글쇠 틱 · Enter 톡",
    "바탕": "밤공기",
}

# ── 음악: F장조 〈석별의 정〉 첫 가락 ──
TONIC = 698.456                     # 으뜸음 F5(Hz)
MAJOR = (0, 2, 4, 5, 7, 9, 11)      # 장음계(반음 수)
PICKUP = -3                         # 못갖춘마디 '도'(C5): 음계에서 으뜸음 세 칸 아래
MELODY = (                          # (첫 마디 첫 박부터 센 박, 음계 칸 — 으뜸음 = 0)
    (0, 0), (1.5, 0), (2, 0), (3, 2),
    (4, 1), (5.5, 0), (6, 1), (7, 2),
    (8, 0), (9.5, 0), (10, 2), (11, 4),
    (12, 5), (15, 5),
    (16, 4), (17.5, 2), (18, 2), (19, 0),
    (20, 1), (21.5, 0), (22, 1), (23, 2),
    (24, 0), (25.5, -2), (26, -2), (27, -3),
    (28, 0),
)
ENDINGS = (28, 12, 8)               # 가락을 맺을 수 있는 자리(박) — 영상 길이에 들어가는 가장 긴 것을 고른다
CHORDS = "F F C C F F Bb Bb F F C C Bb C F F".split()               # 반 마디마다의 화음
BROKEN = {"F": ("F3", "C4", "A4", "C4"), "C": ("E3", "C4", "Bb4", "G4"), "Bb": ("F3", "D4", "Bb4", "D4")}
PAD = {"F": ("F3", "A3", "C4"), "C": ("E3", "G3", "Bb3", "C4"), "Bb": ("F3", "Bb3", "D4")}
BEAT_PREF, BEAT_MIN, BEAT_MAX = 0.52, 0.44, 0.66                    # 한 박 길이(초): 약 115 BPM, 91~136 BPM 안에서만
PICKUP_MIN = 0.08                   # 못갖춘마디가 이보다 짧으면 안 들린다(초)
HOLD_MIN = 0.5                      # 끝음이 영상 끝까지 적어도 이만큼은 울려야 한다(초)

STAMP_LAND = 0.07                   # 도장이 내려와 찍히기까지(초) — 화면에서는 커다랗게 나타나 줄어들며 찍힌다
HUSH_FADE = 0.2                     # 정적으로 들어가는 시간(초)
HUSH_ENDS = ("bubble", "year_roll", "fw_launch", "fw_burst")        # 정적을 깨는 무대 사건


# ======================================================================== 시각표
def load_events() -> dict:
    """시각표를 읽는다. 없거나 대본·박자표·엔진보다 오래됐으면 render.js로 다시 만든다."""
    sources = [HERE / "script.js", HERE / "timing.js", *(HERE / "engine").glob("*.js")]
    if not EVENTS.exists() or EVENTS.stat().st_mtime < max(p.stat().st_mtime for p in sources):
        subprocess.run(["node", "render.js", "--events"], cwd=HERE, check=True)
    return json.loads(EVENTS.read_text(encoding="utf-8"))


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

    def all(self, kind):
        return self.by.get(kind, [])

    def time(self, kind):
        """그 종류의 첫 사건 시각(없으면 None)."""
        return self.by[kind][0]["t"] if kind in self.by else None

    def pan(self, x):
        """화면 가로 자리(px) → 좌우 자리(-1 왼쪽 ~ +1 오른쪽). 무대는 왼쪽, 코드는 오른쪽으로 기운다."""
        return float(np.clip((x / self.width - 0.5) * 1.8, -1, 1))


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


def bell(freq, dur, tau=0.6, partials=((1, 1.0, 1.0), (2.0, 0.45, 0.6), (3.01, 0.25, 0.4), (4.17, 0.12, 0.3))):
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


def degree(d, octave=0):
    """F장조 음계에서 으뜸음(F5)보다 d칸 위(음수면 아래)의 주파수."""
    return TONIC * 2 ** (d // 7 + octave + MAJOR[d % 7] / 12)


def musicbox(freq, dur, ring=1.0):
    """오르골 빗살 한 번: 순음에 가까운 몸통 + 한 옥타브 위 조금 + 튕기는 순간의 높은 '팅'. 높은 음일수록 빨리 사그라든다."""
    t = tt(dur)
    tau = 0.95 * ring * (TONIC / freq) ** 0.5
    out = np.sin(2 * np.pi * freq * t) * np.exp(-t / tau)
    out += 0.30 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / (0.5 * tau))
    out += 0.07 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / (0.25 * tau))
    if 6.27 * freq < 16000:                                            # 한쪽이 고정된 쇠막대의 둘째 떨림
        out += 0.16 * np.sin(2 * np.pi * 6.27 * freq * t) * np.exp(-t / 0.03)
    return out * np.clip(t / 0.0015, 0, 1)


def pad_tone(freq, dur, attack=0.3, release=0.6):
    """포근한 깔개음: 살짝 어긋난 사인 두 개 + 한 옥타브 위 조금. 천천히 열리고 dur 뒤에 천천히 닫힌다."""
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
        """sig를 t0초에 놓는다. pan은 숫자 하나 또는 표본마다의 값(움직이는 소리), rev는 잔향으로 보내는 양."""
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


# ======================================================================== 장면별 소리
def headline(m: Mix, tl: Timeline):
    """머리글: 0초 낚는 말이 떨어지는 '쾅' · 되감기 '쮸르륵' · 맺는 말이 뜰 때 종."""
    rng = seeded("머리글")
    for e in tl.all("hook_slam"):
        m.put("머리글", osc(glide(150, 42, 0.6, 0.6)) * env(0.6, 0.004, 0.15), e["t"], 0.50, 0.0, rev=0.2)
        m.put("머리글", burst(rng, 0.25, 70, 900, 0.002, 0.045), e["t"], 0.34, 0.0, rev=0.3)
        m.put("머리글", burst(rng, 0.04, 1500, 6000, 0.0005, 0.005), e["t"], 0.10, 0.0, rev=0.3)
    for e in tl.all("rewind"):
        q = tt(e["dur"]) / e["dur"]
        speed = np.sin(np.pi * q)                                       # 가운데서 가장 빠르다
        cut = (np.cumsum(14 + 26 * speed) / SR) % 1                     # 테이프 토막: 0→1을 되풀이, 빠를수록 잘게
        squeal = osc(520 * 2 ** (2.2 * speed + 0.5 * cut)) * cut ** 1.5 * (1 - cut ** 10)   # 거꾸로 감긴 소리처럼 커지다 뚝
        whirr = moving_noise(rng, 900 * 2 ** (2.0 * speed), 0.5)
        m.put("머리글", fade((squeal + 0.6 * whirr) * (0.35 + 0.65 * speed), 0.03, 0.04), e["t"], 0.13, 0.0, rev=0.15)
    for e in tl.all("final_message"):
        for octave, gain in ((0, 0.06), (1, 0.03)):                     # C6·C7 — 어느 화음 위에서도 어울리는 음
            m.put("머리글", bell(degree(4, octave), 1.6, tau=0.7), e["t"], gain, 0.0, rev=0.6)
        m.put("머리글", burst(rng, 0.9, 6500, 13000, 0.12, 0.3), e["t"], 0.03, 0.0, rev=0.5)


KEY_TONES = {       # 글쇠 종류 → (틱 대역 Hz, 틱 길이, 몸통 Hz, 몸통 길이, 몸통 비율, 세기)
    "key": ((1900, 5200), 0.0022, 190, 0.010, 0.45, 0.070),
    "space": ((1100, 3200), 0.0035, 135, 0.016, 0.65, 0.080),
    "select_all": ((1100, 3200), 0.0035, 135, 0.016, 0.65, 0.080),      # 첫머리의 전체 선택도 글쇠 한 번
    "enter": ((800, 2400), 0.0060, 98, 0.032, 0.90, 0.130),
    "enter_error": ((250, 900), 0.0120, 72, 0.050, 1.10, 0.150),
}


def key_click(rng, band, tick_tau, body_f, body_tau, body_mix):
    """글쇠 한 번: 대역 잡음 '틱' + 작은 몸통 울림. 부를 때마다 음높이가 조금씩 다르다."""
    j = rng.uniform(0.86, 1.16)
    dur = 0.03 + 4 * body_tau
    body = osc(glide(1.3 * body_f * j, body_f * j, dur, 0.5)) * env(dur, 0.001, body_tau)
    return burst(rng, dur, band[0] * j, band[1] * j, 0.0003, tick_tau) + body_mix * body


def typing(m: Mix, tl: Timeline):
    """타자: 글쇠마다 음높이·세기·자리가 조금씩 달라 기계음처럼 들리지 않는다. 떼는 소리도 작게 따라온다."""
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
    새해로 넘어갈 때는 '차르륵 철컥', 금빛으로 바뀔 때는 반짝이며 부푸는 소리."""
    rng = seeded("연도판")
    pan = tl.pan_stage
    drop, land, settle = tl.time("board_drop"), tl.time("board_land"), tl.time("board_settle")
    if drop is not None and land is not None and land > drop:
        q = tt(land - drop) / (land - drop)
        whoosh = moving_noise(rng, glide(2800, 600, land - drop), 0.6) * q ** 1.5
        m.put("무대", fade(whoosh, 0, 0.02), drop, 0.10, pan, rev=0.3)
    if land is not None:
        m.put("무대", burst(rng, 0.05, 900, 4200, 0.0005, 0.007), land, 0.17, pan, rev=0.3)
        m.put("무대", osc(glide(170, 80, 0.16)) * env(0.16, 0.002, 0.035), land, 0.20, pan, rev=0.3)
        m.put("무대", bell(degree(4), 0.9, tau=0.3), land, 0.06, pan, rev=0.6)
    if drop is not None and settle is not None and settle > drop:
        flaps = max(1, round((settle - drop) / 0.05))
        for i in range(1, flaps + 1):                                   # 촘촘하다가 점점 성기게 → 멈춘다
            when = drop + (settle - drop) * (i / flaps) ** 1.3
            m.put("무대", flap_tick(rng), when, 0.05 + 0.04 * i / flaps, pan + rng.uniform(-0.1, 0.1), rev=0.2)
    for e in tl.all("year_roll"):
        for i, dt in enumerate((0.0, 0.03, 0.065, 0.11, 0.17)):
            m.put("무대", flap_tick(rng), e["t"] + dt, 0.10 * 0.8 ** i, pan, rev=0.25)
        m.put("무대", osc(glide(170, 75, 0.2)) * env(0.2, 0.002, 0.045), e["t"], 0.22, pan, rev=0.3)
        m.put("무대", burst(rng, 0.05, 700, 3800, 0.0005, 0.008), e["t"], 0.15, pan, rev=0.3)
    for e in tl.all("year_gold"):
        for side in (-0.3, 0.3):
            m.put("무대", burst(rng, 1.6, 5000, 13000, 0.18, 0.4), e["t"], 0.035, pan + side, rev=0.5)
        for i, (d, octave) in enumerate(((4, 0), (2, 1), (4, 1))):      # C6·A6·C7 — 으뜸화음 위에서 금빛으로
            t = tt(1.8)
            glow = bell(degree(d, octave), 1.8, tau=0.6) * np.clip(t / 0.08, 0, 1) * (1 + 0.3 * np.sin(2 * np.pi * (6 + i) * t))
            m.put("무대", glow, e["t"] + 0.03 * i, 0.035, pan + 0.2 * (i - 1), rev=0.7)


def snow(m: Mix, tl: Timeline):
    """눈: 높은 바람결 '사아—' + 유리알 같은 '딩' 세 번(내려오는 음)."""
    rng = seeded("눈")
    glass = ((1, 1.0, 1.0), (2.76, 0.3, 0.45), (5.4, 0.12, 0.2))
    for e in tl.all("snow_start"):
        for side in (-0.85, -0.05):
            m.put("무대", burst(rng, 2.4, 5500, 12500, 0.35, 0.65), e["t"], 0.035, side, rev=0.5)
        for d, dt, side in ((11, 0.0, -0.7), (9, 0.17, -0.2), (7, 0.41, -0.5)):         # C7 → A6 → F6
            m.put("무대", bell(degree(d), 0.9, tau=0.3, partials=glass), e["t"] + dt, 0.05, side, rev=0.8)


def night_air(m: Mix, tl: Timeline):
    """바탕: 아주 작은 밤공기. 영상 길이에 꼭 맞는 주기 잡음이라 반복 재생에도 이음매가 없다."""
    rng = seeded("바탕")
    breath = 1 + 0.25 * np.sin(2 * np.pi * 3 * np.arange(tl.n) / tl.n)
    for side in (-0.6, 0.6):
        air = fft_filter(rng.normal(size=tl.n), lo=180, hi=1300, order=2)
        m.put("바탕", air / np.sqrt(np.mean(air ** 2)) * breath, 0.0, 0.0035, side)


def worker(m: Mix, tl: Timeline):
    """삽질러: 떨어지는 휘파람 → 내려앉는 '툭' + 귀여운 '뿅'. 말풍선이 뜰 때는 '뽁'."""
    rng = seeded("삽질러")
    pan = tl.pan_stage
    fall, land = tl.time("worker_fall"), tl.time("worker_land")
    if fall is not None and land is not None and land > fall:
        t = tt(land - fall)
        whistle = osc(glide(1900, 620, land - fall) * (1 + 0.012 * np.sin(2 * np.pi * 9 * t)))
        m.put("무대", fade(whistle, 0.03, 0.02), fall, 0.06, pan, rev=0.3)
    if land is not None:
        m.put("무대", osc(glide(125, 52, 0.25, 0.6)) * env(0.25, 0.003, 0.06), land, 0.24, pan, rev=0.25)
        m.put("무대", burst(rng, 0.25, 200, 1800, 0.004, 0.05), land, 0.09, pan, rev=0.3)
        for d, dt, length in ((0, 0.07, 0.05), (4, 0.125, 0.09)):       # 뿅: 파 → 도
            blip = (sine(degree(d), length) + 0.25 * sine(2 * degree(d), length)) * env(length, 0.003, 0.03)
            m.put("무대", blip, land + dt, 0.07, pan, rev=0.4)
    for e in tl.all("bubble"):
        m.put("무대", osc(glide(380, 1000, 0.06)) * env(0.06, 0.003, 0.018), e["t"], 0.10, pan + 0.15, rev=0.3)


def shovel_hit(rng, bright=1.0):
    """삽이 흙에 박히는 '칙': 거친 흙 소리 + 삽날 쇳소리 조금 + 낮은 '퍽'."""
    grit = burst(rng, 0.09, 450 * bright, 3600 * bright, 0.001, 0.016)
    blade = sum(a * sine(f * bright * rng.uniform(0.96, 1.04), 0.09) for f, a in ((2150, 1.0), (3380, 0.6), (5270, 0.35)))
    thud = osc(glide(150, 70, 0.09)) * env(0.09, 0.002, 0.022)
    return 0.8 * grit + 0.12 * blade * env(0.09, 0.0005, 0.012) + 0.5 * thud


def dig(m: Mix, tl: Timeline):
    """삽질: 또박또박 세 번 → 점점 빨라졌다가 끝에서 숨을 고르는 삽질. 한 달치가 쌓일 때마다 오르골 음계가 한 음씩 오른다."""
    rng = seeded("삽질")
    pan = tl.pan_stage
    hits = tl.all("dig_hit")
    for e in hits:
        m.put("삽질", shovel_hit(rng), e["t"], 0.24, pan + rng.uniform(-0.08, 0.08), rev=0.25)
        m.put("삽질", burst(rng, 0.16, 900, 3000, 0.03, 0.04), e["t"] + 0.07, 0.05, pan - 0.15, rev=0.3)   # 흙 던지는 소리
    start, end = tl.all("dig_start"), tl.time("dig_end")
    if start and end is not None:
        t0 = hits[-1]["t"] if hits else start[0]["t"]
        count = int(min(start[0]["n"] - len(hits), 18 * (end - t0)))
        u = np.linspace(0, 1, 2001)
        ease = (u * u * (3 - 2 * u)) ** 1.2                             # 삽질 횟수가 늘어나는 꼴(0→1)
        for j in range(1, count + 1):
            uj = float(np.interp(j / count, ease, u))
            rush = math.sin(math.pi * uj)                               # 가장 빠른 대목에서 1
            m.put("삽질", shovel_hit(rng, 1 + 0.35 * rush), t0 + (end - t0) * uj, 0.14 * rng.uniform(0.7, 1.0),
                  pan + rng.uniform(-0.12, 0.12), rev=0.25)
    for e in tl.all("band"):
        d = e["k"] - (tl.bands - 1) + 7                                 # 마지막 달 = 으뜸음 F6에 도착
        m.put("음악", musicbox(degree(d), 1.2), e["t"], 0.11 + 0.004 * e["k"], pan, rev=0.5)
        if e["k"] == tl.bands - 1:                                      # 도착: 아래 옥타브와 5음을 곁들인다
            m.put("음악", musicbox(degree(d - 7), 1.4), e["t"], 0.07, pan, rev=0.5)
            m.put("음악", musicbox(degree(d - 3), 1.4), e["t"], 0.05, pan, rev=0.5)


def countdown(m: Mix, tl: Timeline):
    """카운트다운: 숫자마다 '삑' + 낮은 '쿵'. 숫자가 줄수록 음이 오르고 세지며, 밑에서 차오르던 바람 소리는 끝나는 순간 뚝 끊긴다."""
    rng = seeded("카운트다운")
    counts = tl.all("count")
    pan = tl.pan_stage
    for i, e in enumerate(counts):
        last = i == len(counts) - 1
        f = degree(4 + i - (len(counts) - 1))                           # 마지막 숫자 = 딸림음 C6 → 으뜸음을 기다리게 한다
        length = 0.16 if last else 0.09
        beep = (sine(f, length + 0.1) + 0.25 * sine(2 * f, length + 0.1) + 0.12 * sine(3 * f, length + 0.1))
        m.put("무대", beep * env(length + 0.1, 0.003, 0.02, hold=length), e["t"], 0.10 + 0.02 * i, pan, rev=0.3)
        m.put("무대", osc(glide(150, 46, 0.32, 0.6)) * env(0.32, 0.003, 0.085), e["t"], 0.20 + 0.05 * i, 0.6 * pan, rev=0.25)
        m.put("무대", burst(rng, 0.03, 1000, 4000, 0.0005, 0.004), e["t"], 0.05, pan, rev=0.2)
    if len(counts) > 1:
        t0 = counts[0]["t"]
        span = (counts[-1]["t"] - t0) * len(counts) / (len(counts) - 1)     # 마지막 숫자가 사라지는 순간까지
        riser = moving_noise(rng, glide(500, 5200, span), 0.5) * (tt(span) / span) ** 2.2
        m.put("무대", fade(riser, 0, 0.012), t0, 0.07, pan, rev=0.25)


def twist(m: Mix, tl: Timeline):
    """반전: 연도판이 걸리는 '철컥' + 낮고 짧은 '삐—'(오답 소리) → 도장 '쿵' → 숫자가 도로 떨어지는 '톡'. 그 뒤는 정적."""
    rng = seeded("반전")
    pan = 0.6 * tl.pan_stage
    for e in tl.all("jam"):
        clack = sum(a * sine(f, 0.12) for f, a in ((1180, 1.0), (1870, 0.7), (2930, 0.5), (4410, 0.3))) * env(0.12, 0.0005, 0.03)
        m.put("반전", unit(clack), e["t"], 0.16, pan, rev=0.25)
        m.put("반전", burst(rng, 0.03, 2000, 7000, 0.0003, 0.003), e["t"], 0.13, pan, rev=0.25)
        q = tt(0.27) / 0.27
        droop = 1 - 0.04 * q                                            # 끝으로 갈수록 살짝 처진다
        buzz = square(note("B2") * droop, 3200) + 0.7 * square(note("F3") * droop, 3200)    # 증4도 — 틀렸다는 소리
        buzz *= 1 - 0.18 * np.sin(2 * np.pi * 31 * 0.27 * q) ** 2
        m.put("반전", fade(buzz, 0.004, 0.03), e["t"], 0.27, pan, rev=0.12)
    for e in tl.all("stamp"):
        land = e["t"] + STAMP_LAND
        swish = moving_noise(rng, glide(1600, 500, STAMP_LAND), 0.5) * tt(STAMP_LAND) / STAMP_LAND
        m.put("반전", swish, e["t"], 0.05, pan)
        m.put("반전", osc(glide(115, 44, 0.45, 0.6)) * env(0.45, 0.003, 0.085), land, 0.60, pan, rev=0.15)
        m.put("반전", burst(rng, 0.22, 80, 700, 0.002, 0.035), land, 0.42, pan, rev=0.2)
        m.put("반전", burst(rng, 0.05, 900, 2800, 0.0005, 0.007), land, 0.14, pan, rev=0.2)
    for e in tl.all("jam_drop"):
        m.put("반전", osc(glide(260, 150, 0.08)) * env(0.08, 0.002, 0.018), e["t"], 0.09, pan, rev=0.1)
        m.put("반전", flap_tick(rng), e["t"], 0.05, pan)


def ending(beat, pickup, room):
    """가락을 맺을 자리(박). 끝음이 HOLD_MIN 넘게 울릴 수 있는 가장 긴 것, 없으면 None."""
    return next((p for p in ENDINGS if pickup + p * beat + HOLD_MIN <= room), None)


def tempo_candidates(anchors):
    """(박 길이, 못갖춘마디 길이) 후보. 강박 번호(마디 첫 박 0, 셋째 박 2, 다음 마디 첫 박 4 …)를 하나씩 대 본다."""
    if not anchors:
        yield BEAT_PREF, BEAT_PREF
    for r in range(0, 9, 2):
        if len(anchors) == 2:
            for s in range(r + 2, r + 17, 2):
                beat = (anchors[1] - anchors[0]) / (s - r)
                yield beat, anchors[0] - r * beat
        elif anchors:
            yield anchors[0] / (r + 1), anchors[0] / (r + 1)            # 못갖춘마디가 딱 한 박
            yield BEAT_PREF, anchors[0] - r * BEAT_PREF


def fit_tempo(anchors, room):
    """말풍선 시각을 0으로 놓고, 강박(마디의 1·3박)이 anchors(연도판 넘김·첫 불꽃까지의 초)에 떨어지도록
    박 길이와 못갖춘마디 길이를 고른다. room = 영상 끝까지 남은 시간.
    둘 다 맞출 수 없으면 앞의 것만 맞추고, 그것도 안 되면 기본 빠르기로 간다."""
    def cost(c):                                                        # 빠르기는 115 BPM 근처, 못갖춘마디는 한 박에 가깝게
        return abs(math.log(c[0] / BEAT_PREF)) + 0.2 * abs(math.log(c[1] / c[0]))
    for k in range(len(anchors), -1, -1):
        fits = [(beat, pickup) for beat, pickup in tempo_candidates(anchors[:k])
                if BEAT_MIN <= beat <= BEAT_MAX and PICKUP_MIN <= pickup <= 2.5 * beat
                and ending(beat, pickup, room) is not None]
        if fits:
            return min(fits, key=cost)
    return BEAT_PREF, BEAT_PREF


def music(m: Mix, tl: Timeline):
    """음악: "수고했어" 말풍선에서 못갖춘마디 '도'로 시작하는 오르골 〈석별의 정〉 + 펼친 화음 + 포근한 깔개음.
    흙더미가 금빛으로 바뀔 때는 쌓인 순서대로 작은 종이 음계를 타고 오른다. 고마움이 없으면 음악도 없다.
    돌려주는 것: 요약 표에 적을 박자 정보(음악이 없으면 None)."""
    for e in tl.all("gild"):
        d = e["k"] - (tl.bands - 1) + 7
        m.put("음악", musicbox(degree(d, 1), 0.5, ring=0.3), e["t"], 0.04, tl.pan_stage, rev=0.6)
    bubble = next((e for e in tl.all("bubble") if e.get("thanked")), None)
    if bubble is None:
        return None
    t0, room = bubble["t"], tl.duration - bubble["t"]
    marks = sorted((tl.time(kind), name) for name, kind in (("연도판 넘김", "year_roll"), ("첫 불꽃", "fw_burst"))
                   if tl.time(kind) is not None and tl.time(kind) > t0)
    beat, pickup = fit_tempo([t - t0 for t, _ in marks], room)
    last = ending(beat, pickup, room)

    def at(pos):
        return t0 + pickup + pos * beat

    notes = [(p, d) for p, d in MELODY if (p <= last if last is not None else at(p) < tl.duration - 0.2)]
    end_pos = notes[-1][0] if notes else 0
    chord = CHORDS[int(end_pos // 2) % len(CHORDS)]

    # 가락(가운데) — 강박은 조금 세게, 끝음은 길게. 한 옥타브 위 빗살이 작게 따라 울린다.
    m.put("음악", musicbox(degree(PICKUP), 1.6), t0, 0.20, 0.0, rev=0.45)
    for pos, d in notes:
        final = pos == end_pos
        accent = 1.0 if pos % 2 == 0 else 0.85
        m.put("음악", musicbox(degree(d), 3.0 if final else 1.6, ring=1.8 if final else 1.0), at(pos), 0.25 * accent, 0.0, rev=0.45)
        m.put("음악", musicbox(degree(d, 1), 1.0, ring=0.6), at(pos), 0.05 * accent, 0.0, rev=0.6)

    # 왼손: 반 마디마다 펼친 화음(여덟분음표), 첫 음(강박)이 가장 세다
    for half in range(int(end_pos // 2)):
        for i, name in enumerate(BROKEN[CHORDS[half % len(CHORDS)]]):
            m.put("음악", musicbox(note(name), 1.4), at(2 * half + 0.5 * i), 0.11 if i == 0 else 0.06, 0.15 * (-1) ** i, rev=0.4)

    # 맺음: 끝음 바로 앞에서 화음을 아래부터 굴려 올리고, 끝음 뒤에는 높은 음 셋이 한 박 간격으로 반짝인다
    roll = [note(name) * octave for octave in (1, 2) for name in PAD[chord]]
    for i, f in enumerate(roll):
        m.put("음악", musicbox(f, 2.4, ring=1.5), at(end_pos) - 0.032 * (len(roll) - i), 0.07, 0.0, rev=0.5)
    for i, name in enumerate(PAD[chord][:3]):
        when = at(end_pos + 0.5 * (i + 1))
        if when < tl.duration - 0.1:
            m.put("음악", musicbox(note(name) * 8, 1.0, ring=0.7), when, 0.05, 0.0, rev=0.7)

    # 깔개음: 화음이 바뀔 때마다 겹쳐 넘어가고, 마지막 화음은 영상 끝을 넘어 첫머리까지 이어진다
    spans = [(t0, at(0), "F")] + [(at(2 * h), at(2 * h + 2), CHORDS[h % len(CHORDS)]) for h in range(int(end_pos // 2))]
    spans.append((at(end_pos), tl.duration, chord))
    merged = []
    for a, b, c in spans:
        if merged and merged[-1][2] == c:
            merged[-1] = (merged[-1][0], b, c)
        else:
            merged.append((a, b, c))
    for a, b, c in merged:
        for name in PAD[c]:
            m.put("음악", pad_tone(note(name), b - a), a, 0.022, 0.0, rev=0.5)

    landed = []
    for t, name in marks:                                               # 강박이 실제로 어디에 떨어졌는지
        pos = (t - at(0)) / beat
        strong = 2 * round(pos / 2)
        landed.append((name, t, strong // 4 + 1, strong % 4 + 1, (strong - pos) * beat))
    return dict(start=t0, beat=beat, pickup=pickup, landed=landed, end=at(end_pos),
                end_bar=int(end_pos // 4) + 1, end_beat=int(end_pos % 4) + 1, chord=chord, cut=last is None)


def fireworks(m: Mix, tl: Timeline):
    """불꽃: 올라가는 휘파람(길이 = rise) → '펑' + 타닥타닥. 클수록 낮고 길고 크다. 좌우 자리는 화면의 x를 따른다."""
    rng = seeded("불꽃")

    def pan_of(e):
        return tl.pan(e["x"] * tl.stage_w)

    def pop(t, s, level, pan):
        """한 번 터지는 '펑': 낮은 울림 + 몸통 + 날카로운 첫소리. s(0~1)가 클수록 낮고 길다."""
        tau = 0.07 + 0.2 * s ** 1.5
        low = 62 / s ** 0.9
        m.put("불꽃", osc(glide(2.2 * low, 0.8 * low, 5 * tau, 0.5)) * env(5 * tau, 0.003, tau), t, 0.9 * level, 0.7 * pan, rev=0.4)
        m.put("불꽃", burst(rng, 4 * tau, 45, 520 / s, 0.002, 0.6 * tau), t, 0.7 * level, pan, rev=0.6)
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
        s = max(e["size"] / biggest, 0.2)                               # 가장 큰 불꽃 = 1
        level, pan, kind = 0.8 * s ** 1.6, pan_of(e), e.get("kind")
        pop(e["t"], s, level, pan)
        if kind == "double":                                            # 두 겹 불꽃: 작게 한 번 더
            pop(e["t"] + 0.09, 0.7 * s, 0.45 * level, pan)
        span = (0.35 + 0.6 * s) * (1.6 if kind == "willow" else 1.0)    # 버들 불꽃은 오래 흘러내린다
        for u in rng.uniform(0, 1, int(10 + 50 * s ** 2)) ** 1.5:       # 타닥타닥 — 앞쪽에 몰려 있다
            grain = burst(rng, 0.008, 2600, 9500, 0.0002, rng.uniform(0.0006, 0.002))
            m.put("불꽃", grain, e["t"] + 0.07 + span * u, 0.05 * s * (1 - u) ** 1.2 * rng.uniform(0.4, 1.0),
                  pan + 0.3 * s * rng.uniform(-1, 1), rev=0.3)
        if kind == "willow":
            m.put("불꽃", burst(rng, 1.4, 3000, 9000, 0.05, 0.4), e["t"] + 0.05, 0.03 * s, pan, rev=0.5)


# ======================================================================== 정적 · 반복 이음 · 마스터
def hush_window(tl: Timeline):
    """반전 뒤 정적 구간 (시작, 끝). 도장이 찍히고 숫자가 도로 떨어진 직후부터, 무대에서 다음 일이 벌어질 때(보통 말풍선)까지."""
    fail = [e["t"] for kind in ("jam", "stamp", "jam_drop") for e in tl.all(kind)]
    if not fail:
        return None
    t0 = max(fail) + 0.15 + HUSH_FADE
    t1 = min((e["t"] for e in tl.events if e["type"] in HUSH_ENDS and e["t"] > t0), default=tl.duration)
    return (t0, t1) if t1 - t0 > 0.1 else None


def arrange(layers: dict, tl: Timeline):
    """겹마다 ① 정적 구간을 비우고(타자만 남긴다 — 이 침묵이 웃음 포인트) ② 영상 끝을 넘긴 꼬리를 첫머리에 겹친다.
    꼬리는 완성 장면이 보이는 동안은 그대로 울리고, 되감기는 동안 사라진다."""
    t = np.arange(len(next(iter(layers.values())))) / SR
    hush = np.ones_like(t)
    window = hush_window(tl)
    if window:
        hush = np.interp(t, [window[0] - HUSH_FADE, window[0], window[1] - 0.010, window[1] - 0.001], [1.0, 0.0, 0.0, 1.0])
    rewind = tl.all("rewind")
    gone = (rewind[0]["t"], rewind[0]["t"] + rewind[0]["dur"]) if rewind else (0.0, 0.4)
    carry = np.interp(t[:len(t) - tl.n], gone, [1.0, 0.0])
    out = {}
    for name, x in layers.items():
        if name != "타자":
            x = x * hush[:, None]
        out[name] = x[:tl.n].copy()
        out[name][:len(carry)] += x[tl.n:] * carry[:, None]
    return out


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
    돌려주는 것: (완성 소리, 제한기 앞에서 곱한 배율)."""
    gain = 1.0
    for _ in range(4):
        gain *= 10 ** ((TARGET_LUFS - loudness(limit(x * gain))) / 20)
    y = limit(x * gain)
    edge = np.minimum(np.arange(len(y)), np.arange(len(y))[::-1]) / (EDGE * SR)
    return y * np.clip(edge, 0, 1)[:, None], gain


# ======================================================================== 파일 · 측정 · 요약
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


def cell(text, width):
    """한글은 두 칸을 차지하므로 화면 너비 기준으로 채운다."""
    return text + " " * max(width - sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text), 0)


def report(tl: Timeline, layers, out, gain, tune, muxed):
    print(f"소리 합성 완료 — {len(out) / SR:.3f}초 · {SR}Hz 스테레오 16비트 · 표본 {len(out)}개")
    print()
    print(cell("겹", 8) + cell("최대(dBFS)", 12) + "내용")
    for name, what in LAYERS.items():
        peak = db(float(np.max(np.abs(layers[name]))) * gain)
        print(cell(name, 8) + cell(f"{peak:6.1f}" if math.isfinite(peak) else "  없음", 12) + what)
    lufs, peak = measure(WAV)
    print()
    print(f"통합 음량 {lufs:.1f} LUFS (목표 {TARGET_LUFS:.0f} ±1) · 트루 피크 {peak:.1f} dBTP (한도 -1.0) — ffmpeg ebur128로 잰 값")
    if tune:
        print(f"음악  F장조 · {60 / tune['beat']:.1f} BPM · 가락은 말풍선({tune['start']:.3f}초)에서 시작, 못갖춘마디 {tune['pickup']:.3f}초")
        for name, t, bar, beat, err in tune["landed"]:
            print(f"      {name} {t:.3f}초 → {bar}마디 {beat}박 (강박, 어긋남 {err * 1000:+.0f}ms)")
        tail = "영상 길이에 맞는 맺음 자리가 없어 가락 도중에 끝난다" if tune["cut"] else f"{tune['chord']} 화음으로 맺는다"
        print(f"      끝음 {tune['end']:.3f}초({tune['end_bar']}마디 {tune['end_beat']}박)부터 영상 끝까지 {tl.duration - tune['end']:.2f}초 — {tail}")
    else:
        print('음악  없음 — 고마운 말("수고했어") 말풍선이 없다')
    window, jam = hush_window(tl), tl.time("jam")
    if window:
        depth = rms_db(out, *window) - rms_db(out, max(jam - 2, 0), jam)
        print(f"정적  {window[0]:.3f}~{window[1]:.3f}초(타자 소리만) — 반전 직전 2초보다 {depth:.1f} dB")
    print()
    print(f"{WAV}  {WAV.stat().st_size / 1e6:.2f} MB")
    if muxed:
        stale = SILENT.stat().st_mtime < EVENTS.stat().st_mtime
        print(f"{FINAL}  {FINAL.stat().st_size / 1e6:.2f} MB (영상 복사 + AAC 256k)")
        if stale:
            print("주의: 무음 영상이 시각표보다 오래됐습니다 — `node render.js`로 영상을 다시 만든 뒤 한 번 더 돌리세요.")
    elif not SILENT.exists():
        print(f"무음 영상이 없어 소리만 만들었습니다: {SILENT} — 먼저 `node render.js`")


def main():
    ap = argparse.ArgumentParser(description="새해 코드 릴스 소리 합성")
    ap.add_argument("--no-mux", action="store_true", help="wav만 만들고 영상에는 입히지 않는다")
    args = ap.parse_args()

    tl = Timeline(load_events())
    m = Mix(tl.n + int(TAIL * SR))
    for scene in (headline, typing, couriers, board, snow, night_air, worker, dig, countdown, twist, fireworks):
        scene(m, tl)
    tune = music(m, tl)
    layers = arrange(m.render(), tl)
    out, gain = master(sum(layers.values()))
    write_wav(WAV, out)
    muxed = not args.no_mux and SILENT.exists()
    if muxed:
        mux(SILENT, WAV, FINAL, tl.duration)
    report(tl, layers, out, gain, tune, muxed)


if __name__ == "__main__":
    main()
