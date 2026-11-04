#!/usr/bin/env python3
"""효과음 합성 + 영상에 입히기 — 소리 파일 없이 전부 코드로 만든다(48kHz 스테레오).

    python3 sfx.py
      → ../audio/sfx.wav
      → ../minecraft_shovel_evolution_silent.mp4(무음 영상) + sfx.wav
      → ../minecraft_shovel_evolution.mp4 (영상은 다시 인코딩하지 않고 복사, 소리는 AAC 192k)

소리 목록(시각은 render.py 상수를 그대로 읽는다 → 화면과 어긋나지 않음)
    바탕   동굴 저음·물방울 3번·횃불 타닥 소리
    0.0초  등장 휘익 + 뿅
    2/4/6초 직전 0.32초  상승 칩튠 음 + 바람 소리(기 모으기)
    2.0초  돌: 둔탁한 쿵 + 나무 부서짐 + 자갈 후두둑
    4.0초  철: 쿵 + 금속 '챙' + 빛 띠 '쉭' + 반짝 소리
    6.0초  다이아: 큰 붐 + 수정 화음 + 칩튠 팡파르 + 반짝 소리 여러 개
"""
from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from render import CX, DURATION, TRANS, W, Textures, build_sparkles  # noqa: E402

SR = 48000
N = int(round(SR * DURATION))
rng = np.random.default_rng(424242)


# ======================================================================== 기본 도구
def tt(dur):
    return np.arange(int(round(dur * SR))) / SR


def env(dur, attack=0.004, tau=0.2, hold=0.0):
    t = tt(dur)
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    d = np.exp(-np.clip(t - attack - hold, 0, None) / tau)
    return a * d


def phase_of(freq, dur):
    f = np.broadcast_to(np.asarray(freq, np.float64), (len(tt(dur)),))
    return 2 * np.pi * np.cumsum(f) / SR


def sine(freq, dur):
    return np.sin(phase_of(freq, dur))


def square(freq, dur, top=14000.0):
    """대역 제한 사각파(칩튠 소리, 앨리어싱 줄임)."""
    ph = phase_of(freq, dur)
    fmax = float(np.max(freq))
    out = np.zeros_like(ph)
    k = 1
    while k * fmax < top:
        out += np.sin(k * ph) / k
        k += 2
    return out * (4 / np.pi)


def sweep(f0, f1, dur):
    t = tt(dur)
    return f0 * (f1 / f0) ** (t / dur)


def fft_filter(x, lo=None, hi=None, order=4):
    """주파수 영역 대역 통과(lo~hi Hz), 버터워스형 경사(order차)."""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR) + 1e-9
    m = np.ones_like(f)
    if lo is not None:
        m /= np.sqrt(1 + (lo / f) ** (2 * order))
    if hi is not None:
        m /= np.sqrt(1 + (f / hi) ** (2 * order))
    return np.fft.irfft(X * m, n)


def noise(dur):
    return rng.normal(0, 1, len(tt(dur)))


def swept_noise(dur, f0, f1, width=0.6):
    """중심 주파수가 f0→f1로 움직이는 대역 잡음(바람·쉭 소리). 블록 겹쳐 더하기."""
    n = len(tt(dur))
    blk, hop = 2048, 512
    win = np.hanning(blk)
    out = np.zeros(n + blk)
    f = np.fft.rfftfreq(blk, 1 / SR) + 1e-9
    for s in range(0, n, hop):
        c = f0 * (f1 / f0) ** min(1.0, s / max(n - 1, 1))
        mask = np.exp(-0.5 * (np.log2(f / c) / width) ** 2)
        seg = np.fft.irfft(np.fft.rfft(rng.normal(0, 1, blk) * win) * mask, blk)
        out[s:s + blk] += seg * win
    out = out[:n]
    return out / (np.max(np.abs(out)) + 1e-9)


def bell(freq, dur, partials=((1, 1.0, 1.0), (2.0, 0.45, 0.6), (3.01, 0.25, 0.4), (4.17, 0.12, 0.3)),
         tau=0.6):
    t = tt(dur)
    out = np.zeros_like(t)
    for ratio, amp, tr in partials:
        out += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / (tau * tr))
    return out * np.clip(t / 0.002, 0, 1)


def note(name):
    names = {"C": -9, "C#": -8, "D": -7, "D#": -6, "E": -5, "F": -4, "F#": -3, "G": -2,
             "G#": -1, "A": 0, "A#": 1, "B": 2}
    return 440.0 * 2 ** ((names[name[:-1]] + 12 * (int(name[-1]) - 4)) / 12)


# ======================================================================== 믹스 버스
class Mix:
    def __init__(self):
        self.dry = np.zeros((N, 2))
        self.wet = np.zeros((N, 2))     # 동굴 잔향으로 보낼 소리

    def put(self, sig, t0, gain=1.0, pan=0.0, rev=0.25):
        i0 = int(round(t0 * SR))
        if i0 >= N:
            return
        s = np.asarray(sig, np.float64) * gain
        if i0 < 0:
            s, i0 = s[-i0:], 0
        s = s[:N - i0]
        th = (np.clip(pan, -1, 1) + 1) * np.pi / 4          # 같은 음량 패닝
        lr = np.array([math.cos(th), math.sin(th)]) * math.sqrt(2)
        self.dry[i0:i0 + len(s)] += s[:, None] * lr
        self.wet[i0:i0 + len(s)] += s[:, None] * lr * rev

    def render(self):
        ir_len = int(2.2 * SR)
        t = np.arange(ir_len) / SR
        out = self.dry.copy()
        for ch in range(2):                                  # 좌우 다른 잔향 → 넓은 동굴
            ir = rng.normal(0, 1, ir_len) * np.exp(-t / 0.42)   # RT60 약 2.9초
            ir[:int(0.018 * SR)] = 0                          # 18ms 지연(벽까지 거리)
            ir = fft_filter(ir, lo=120, hi=4200)
            ir /= np.sqrt(np.sum(ir ** 2))
            nfft = 1 << (N + ir_len - 1).bit_length()
            wet = np.fft.irfft(np.fft.rfft(self.wet[:, ch], nfft) * np.fft.rfft(ir, nfft), nfft)[:N]
            out[:, ch] += wet * 0.55
        return out


def pan_of_x(x):
    return float(np.clip((x - CX) / (W / 2), -1, 1)) * 0.8


# ======================================================================== 장면별 소리
def ambience(m: Mix):
    # 동굴 저음: 낮게 깔린 잡음 + 아주 작은 저음 두 개(천천히 일렁임)
    t = tt(DURATION)
    rumble = fft_filter(rng.normal(0, 1, N), lo=25, hi=180)
    rumble /= np.max(np.abs(rumble))
    drone = (np.sin(2 * np.pi * 55 * t) * 0.6 + np.sin(2 * np.pi * 82.4 * t) * 0.3) * (
        0.75 + 0.25 * np.sin(2 * np.pi * 0.23 * t))
    fade = np.clip(t / 0.4, 0, 1)
    bed = (rumble * 0.06 + drone * 0.018) * fade
    m.put(bed, 0.0, 1.0, 0.0, rev=0.0)
    # 물방울(위로 떨어지며 '똑' — 잔향 많이)
    for t0, pan in ((1.15, -0.55), (3.45, 0.6), (5.25, -0.3)):
        for k, g in ((0, 1.0), (0.085, 0.35)):
            d = sine(sweep(1500 if k == 0 else 1900, 700, 0.05), 0.05) * env(0.05, 0.001, 0.018)
            m.put(d, t0 + k, 0.10 * g, pan, rev=1.0)
    # 횃불 타닥(좌우 끝)
    for pan in (-0.85, 0.85):
        tc = 0.0
        while tc < DURATION:
            tc += rng.exponential(1 / 7.0)
            c = fft_filter(noise(0.006), lo=1800, hi=7000) * env(0.006, 0.0005, 0.0015)
            m.put(c, tc, 0.05 * rng.uniform(0.4, 1.0), pan, rev=0.15)


def intro(m: Mix):
    m.put(swept_noise(0.45, 250, 2200, 0.7) * np.hanning(int(0.45 * SR)), 0.0, 0.10, 0.0, rev=0.4)
    pop = square(sweep(420, 980, 0.07), 0.07) * env(0.07, 0.002, 0.035)
    m.put(pop, 0.36, 0.09, 0.05, rev=0.3)
    m.put(sine(sweep(840, 1960, 0.07), 0.07) * env(0.07, 0.002, 0.03), 0.36, 0.05, 0.05)


def charge(m: Mix, T, k):
    """변신 직전 0.32초: 반음씩 오르는 칩튠 + 바람 상승."""
    base = (note("A3"), note("C4"), note("E4"))[k]
    steps = 11
    step = 0.32 / steps
    for i in range(steps):
        f = base * 2 ** (i / 12 * (1.2 + 0.2 * k))
        s = square(f, step * 0.9, top=9000) * env(step * 0.9, 0.002, step * 0.6, hold=step * 0.3)
        m.put(s, T - 0.32 + i * step, 0.035 * (0.45 + 0.55 * i / steps), 0.0, rev=0.2)
    rise = swept_noise(0.32, 400, 5000, 0.5) * np.linspace(0, 1, int(0.32 * SR)) ** 2
    m.put(rise, T - 0.32, 0.08 + 0.03 * k, 0.0, rev=0.3)


def thump(m: Mix, T, f0, f1, tau, gain, crunch=0.0, crunch_hi=1500):
    m.put(sine(sweep(f0, f1, tau * 4), tau * 4) * env(tau * 4, 0.003, tau), T, gain, 0.0, rev=0.5)
    if crunch:
        c = fft_filter(noise(0.35), lo=60, hi=crunch_hi) * env(0.35, 0.002, 0.08)
        m.put(c / np.max(np.abs(c)), T, crunch, 0.0, rev=0.6)


def stone_transition(m: Mix):
    T = TRANS[0]
    thump(m, T, 130, 45, 0.14, 0.55, crunch=0.30)
    for dt, g in ((0.0, 1.0), (0.022, 0.7), (0.055, 0.55), (0.09, 0.35)):       # 나무 부서짐
        c = fft_filter(noise(0.03), lo=1200, hi=5000) * env(0.03, 0.0005, 0.008)
        m.put(c / np.max(np.abs(c)), T + dt, 0.18 * g, rng.uniform(-0.3, 0.3), rev=0.3)
    for _ in range(14):                                                         # 자갈 후두둑
        tk = T + 0.12 + rng.uniform(0, 0.75) ** 1.3
        c = fft_filter(noise(0.012), lo=900, hi=3500) * env(0.012, 0.0005, 0.003)
        m.put(c / np.max(np.abs(c)), tk, 0.06 * rng.uniform(0.4, 1), rng.uniform(-0.7, 0.7), rev=0.35)


def iron_transition(m: Mix, sparkles):
    T = TRANS[1]
    thump(m, T, 150, 55, 0.11, 0.42, crunch=0.15, crunch_hi=2500)
    # 금속 '챙': 맞지 않는 배음(비조화) 여러 개가 길게 울림
    clang = bell(640, 1.6, partials=((1, 1.0, 1.0), (2.32, 0.6, 0.7), (4.25, 0.4, 0.5),
                                     (6.63, 0.25, 0.35), (9.38, 0.15, 0.25)), tau=0.75)
    m.put(clang, T + 0.005, 0.16, 0.1, rev=0.5)
    m.put(swept_noise(0.45, 3000, 9500, 0.35) * np.hanning(int(0.45 * SR)), 4.25, 0.07, 0.2, rev=0.3)
    for t0, dur, pos, *_ in sparkles:
        if 4.0 <= t0 < 6.0:
            m.put(bell(note("E6") * rng.choice([1, 1.5, 2]), 0.5, tau=0.18), t0 + dur * 0.4, 0.05, 0.25)


def diamond_transition(m: Mix, sparkles):
    T = TRANS[2]
    thump(m, T, 110, 32, 0.30, 0.75, crunch=0.35, crunch_hi=1200)
    m.put(swept_noise(0.9, 1500, 220, 0.8) * env(0.9, 0.01, 0.3), T, 0.16, 0.0, rev=0.6)   # 퍼지는 바람
    for i, nm in enumerate(("E5", "G#5", "B5", "E6", "G#6")):                               # 수정 화음
        m.put(bell(note(nm), 2.0, tau=0.9), T + 0.02 + i * 0.035, 0.07, (-0.4, 0.4, -0.2, 0.2, 0.0)[i],
              rev=0.7)
    for i, nm in enumerate(("E5", "G#5", "B5", "E6")):                                      # 칩튠 팡파르
        d = 0.085 if i < 3 else 0.32
        s = square(note(nm), d, top=10000) * env(d, 0.003, 0.05 if i < 3 else 0.14, hold=0.03)
        m.put(s, T + 0.06 + i * 0.075, 0.045, 0.0, rev=0.35)
    pent = [note(n) for n in ("E6", "F#6", "G#6", "B6", "C#7", "E7")]
    for t0, dur, pos, *_ in sparkles:                                                       # 반짝 소리
        if t0 >= 6.0:
            x = pos[1] if pos[0] == "free" else CX + 200
            f = pent[rng.integers(len(pent))]
            m.put(bell(f, 0.6, tau=0.16), t0 + dur * 0.4, 0.035 * rng.uniform(0.6, 1.0), pan_of_x(x),
                  rev=0.6)
    for t0, g in ((6.40, 0.06), (7.00, 0.035)):                                            # 빛 띠 '쉭'
        m.put(swept_noise(0.45, 4000, 11000, 0.35) * np.hanning(int(0.45 * SR)), t0, g, 0.2, rev=0.3)


# ======================================================================== 마스터
def master(x):
    x = np.tanh(x * 1.4) / 1.4                     # 부드러운 포화(피크 깎기)
    t = np.arange(N) / SR
    x *= np.clip((DURATION - t) / 0.25, 0, 1)[:, None]    # 마지막 0.25초 페이드아웃(끊김 방지)
    x *= np.clip(t / 0.01, 0, 1)[:, None]
    peak = np.max(np.abs(x))
    return x * (10 ** (-1.0 / 20) / peak)          # 최대 -1 dBFS


def write_wav(path: Path, x):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def mux(video: Path, audio: Path, out: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", str(SR), "-t", f"{DURATION:.3f}", "-movflags", "+faststart", str(out)],
                   check=True)


def main():
    root = HERE.parent
    silent = root / "minecraft_shovel_evolution_silent.mp4"
    final = root / "minecraft_shovel_evolution.mp4"
    if not silent.exists():          # render.py 결과(무음)를 무음본 이름으로 보관
        final.replace(silent)
    sparkles = build_sparkles(Textures())
    m = Mix()
    ambience(m)
    intro(m)
    for k, T in enumerate(TRANS):
        charge(m, T, k)
    stone_transition(m)
    iron_transition(m, sparkles)
    diamond_transition(m, sparkles)
    x = master(m.render())
    wav = root / "audio" / "sfx.wav"
    write_wav(wav, x)
    mux(silent, wav, final)
    print(wav)
    print(final)


if __name__ == "__main__":
    main()
