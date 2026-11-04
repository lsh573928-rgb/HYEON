#!/usr/bin/env python3
"""삽 진화 영상 렌더러 — 1920x1080 · 30fps · 8초 · H.264(MP4).

    python3 render.py                        # 무음 영상 렌더(../minecraft_shovel_evolution_silent.mp4)
    python3 sfx.py                           # 효과음 합성 → ../minecraft_shovel_evolution.mp4
    python3 render.py --still 60 61 --out-dir /tmp/x   # 확인용 프레임만 PNG로
    python3 render.py --textures DIR         # 본인 PC의 정식 리소스팩 PNG로 바꿔 끼우기(선택)

타임라인
    0.0~2.0  나무 삽 등장(살짝 커지며 떠오름) + 미세한 흔들림
    2.0      돌 삽: 빛남 → 픽셀 파편 → 교체 → 충격파·화면 흔들림
    4.0      철 삽: 흰 픽셀 섬광(광선) → 교체 → 금속 반짝임(빛 띠·반짝이)
    6.0      다이아 삽: 청록 빛 퍼짐·회전 광선·파편 대량·반짝이
    6.0~8.0  반짝임이 서서히 사라지고 마지막 프레임은 정지·축 정렬 상태로 선명하게
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pixelart as pa  # noqa: E402
from scene import (Coarse, blend_rect, clamp01, draw_sparkle, draw_sprite,  # noqa: E402
                   draw_text, ease_out_back, falloff, quant, rays, smoothstep, tex_to_screen)

W, H = 1920, 1080
FPS = 30
DURATION = 8.0
NFRAMES = round(FPS * DURATION)            # 240
CX, CY = W // 2, H // 2
TEXEL = 52                                  # 텍스처 1픽셀 = 화면 52px (모양 13칸 = 676px)
BG_TEXEL = 8                                # 벽 1텍셀 = 8px (블록 16텍셀 = 128px)
MARGIN = 32                                 # 화면 흔들림 여유
TRANS = (2.0, 4.0, 6.0)
ORDER = pa.ORDER
TORCH_XY = ((200, 330), (1704, 330))        # 횃불 불꽃 맨 윗칸의 화면 좌표
LABELS_ON = False                            # 세로판: 위 제목 + 아래 단계 이름


def configure_vertical():
    """세로판(1080x1920, 9:16) 배치로 바꾼다. Context를 만들기 전에 불러야 한다.

    삽은 화면 폭의 72%(텍셀 60px), 중심은 조금 위(y=920). 위아래 빈 곳에 제목·단계 이름을 넣고,
    아래쪽 20%는 앱 화면의 자막·버튼에 가려질 수 있어 비워 둔다.
    """
    global W, H, CX, CY, TEXEL, TORCH_XY, LABELS_ON
    W, H = 1080, 1920
    CX, CY = W // 2, 920
    TEXEL = 60
    TORCH_XY = ((96, 1460), (968, 1460))
    LABELS_ON = True

WHITE = np.array([1.0, 1.0, 1.0], np.float32)
CYAN = np.array([0.30, 1.0, 0.88], np.float32)
LIGHT = {
    "wooden": np.array([1.00, 0.80, 0.58], np.float32),
    "stone": np.array([0.78, 0.82, 0.88], np.float32),
    "iron": np.array([0.95, 0.97, 1.00], np.float32),
    "diamond": np.array([0.25, 1.00, 0.88], np.float32),
}
WALL_LIGHT = {"wooden": 0.24, "stone": 0.26, "iron": 0.28, "diamond": 0.42}
HALO_LEVEL = {"wooden": 0.07, "stone": 0.08, "iron": 0.10, "diamond": 0.20}
PUNCH = (0.07, 0.08, 0.13)                 # 교체 직후 크기 출렁임
SHAKE = (6, 8, 14)                          # 교체 직후 화면 흔들림(px)
SHADOW_OFF = (16, 20)
TORCH_COLOR = np.array([1.0, 0.62, 0.30], np.float32)

_rng = np.random.default_rng(20261104)
NOISE = _rng.uniform(-1, 1, (NFRAMES + 2, 4))


# ======================================================================== 텍스처
class Textures:
    def __init__(self, tex_dir: str | None = None):
        if tex_dir:
            raw = {}
            for name in ORDER:
                im = Image.open(Path(tex_dir) / f"{name}_shovel.png").convert("RGBA")
                raw[name] = np.asarray(im)
        else:
            raw = pa.make_shovels()
        self.rgba = {k: v.astype(np.float32) / 255.0 for k, v in raw.items()}
        alphas = np.stack([self.rgba[k][..., 3] > 0 for k in ORDER])
        self.same_silhouette = bool(all(np.array_equal(alphas[0], a) for a in alphas[1:]))
        union = alphas.any(0)
        ys, xs = np.nonzero(union)
        # 모양 외곽 상자의 중심 = 회전·확대·배치의 기준점(네 삽 공통)
        self.anchor = ((xs.min() + xs.max() + 1) / 2.0, (ys.min() + ys.max() + 1) / 2.0)
        # 네 삽에서 색이 같은 칸 = 손잡이, 나머지 = 삽날
        rgb = np.stack([self.rgba[k][..., :3] for k in ORDER])
        same = np.all(np.abs(rgb - rgb[0]).max(-1) < 1e-6, axis=0)
        self.handle = union & same
        self.head = union & ~same
        th, tw = union.shape
        yy, xx = np.mgrid[0:th, 0:tw]
        self.q = (xx - yy).astype(np.float32)          # 손잡이→삽날 방향 좌표(빛 띠용)
        self.cells = {k: np.argwhere(self.rgba[k][..., 3] > 0) for k in ORDER}
        self.head_cells = np.argwhere(self.head)

    def head_colors(self, name):
        cells = self.head_cells
        cols = self.rgba[name][cells[:, 0], cells[:, 1], :3]
        return np.unique(np.round(cols, 4), axis=0)


def apply_fx(texs: Textures, name, tint, sweep):
    out = texs.rgba[name].copy()
    if sweep is not None:
        p, strength = sweep
        q0 = -15.0 + 28.0 * p
        d = np.abs(texs.q - q0)
        band = np.where(d < 0.75, 0.8, np.where(d < 1.75, 0.36, 0.0)) * strength
        band = band * np.where(texs.head, 1.0, 0.3)
        out[..., :3] += (1.0 - out[..., :3]) * band[..., None]
    if tint > 0:
        out[..., :3] += (1.0 - out[..., :3]) * tint
    return out


# ======================================================================== 프레임 상태
def frame_state(n: int, anchor=(7.5, 8.5)) -> dict:
    """프레임 n의 삽 위치·크기·각도·효과 값(검증 스크립트도 이 함수를 쓴다)."""
    t = n / FPS
    idx = sum(t >= T - 1e-9 for T in TRANS)
    mat = ORDER[idx]
    env = 1.0 - smoothstep(6.9, 7.6, t)               # 끝에서 움직임을 멈춤
    angle = 2.5 * math.sin(math.pi * t) * env          # 정수 초마다 0°
    bob = int(round(-10.0 * math.cos(math.pi * t) * env))
    scale = 0.82 + 0.18 * ease_out_back(clamp01(t / 0.6))
    alpha = clamp01(t / 0.3)
    jx = jy = dx = dy = 0
    tint = 0.0
    for k, T in enumerate(TRANS):
        before = T - t
        if 0 < before <= 0.3:                          # 변신 직전: 하얗게 달아오르며 떨림
            x = 1.0 - before / 0.3
            tint = max(tint, 0.95 * x * x)
            amp = 4.0 * x
            jx, jy = int(round(amp * NOISE[n, 0])), int(round(amp * NOISE[n, 1]))
        dt = t - T
        if 0 <= dt < 0.5:                              # 변신 직후: 흰색에서 원래 색으로
            tint = max(tint, math.exp(-dt / 0.075))
            scale *= 1 + PUNCH[k] * math.exp(-dt * 9) * math.cos(dt * 26)
        if 0 <= dt < 0.4:
            amp = SHAKE[k] * math.exp(-dt / 0.09)
            dx, dy = int(round(amp * NOISE[n, 2])), int(round(amp * NOISE[n, 3]))
    sweep = None
    if mat == "iron" and 4.25 <= t < 4.70:
        sweep = ((t - 4.25) / 0.45, 1.0)
    if mat == "diamond":
        if 6.40 <= t < 6.85:
            sweep = ((t - 6.40) / 0.45, 1.0)
        elif 7.00 <= t < 7.40:
            sweep = ((t - 7.00) / 0.40, 0.55)
    return dict(n=n, t=t, idx=idx, mat=mat, angle=angle, cx=CX + jx + dx, cy=CY + bob + jy + dy,
                texel=TEXEL * scale, alpha=alpha, tint=tint, sweep=sweep, shake=(dx, dy),
                anchor=anchor)


def light_levels(t: float, mat: str):
    wall, halo, white = WALL_LIGHT[mat], HALO_LEVEL[mat], 0.0
    if mat == "diamond":
        halo += 0.04 * math.sin(2 * math.pi * (t - 6.0) / 1.3)
    for k, T in enumerate(TRANS):
        before = T - t
        if 0 < before <= 0.3:
            x = 1.0 - before / 0.3
            white += 0.45 * x * x
        dt = t - T
        if 0 <= dt < 2.0:
            white += 0.8 * math.exp(-dt / 0.12)
            wall += (1.5 if k == 2 else 0.6) * math.exp(-dt / 0.35)
            halo += (0.5 if k == 2 else 0.25) * math.exp(-dt / 0.30)
    return wall, halo, white


# ======================================================================== 배경(동굴)
class Cave:
    def __init__(self):
        self.gw = (W + 2 * MARGIN) // BG_TEXEL
        self.gh = (H + 2 * MARGIN) // BG_TEXEL
        cb = ((CX + MARGIN) / BG_TEXEL / 16, (CY + MARGIN) / BG_TEXEL / 16)
        self.alb = pa.cave_albedo(self.gw, self.gh, cb)
        jj, ii = np.meshgrid(np.arange(self.gw), np.arange(self.gh))
        wx = (jj + 0.5) * BG_TEXEL - MARGIN
        wy = (ii + 0.5) * BG_TEXEL - MARGIN
        self.dc = np.hypot(wx - CX, wy - CY).astype(np.float32)
        rn = np.hypot((wx - CX) / (W * 0.5), (wy - CY) / (H * 0.5)) / math.sqrt(2)
        # 경계가 생기지 않는 매끈한 비네팅(가운데 1.0 → 모서리 약 0.25)
        self.vign = (0.18 + 0.82 * np.exp(-(rn / 0.75) ** 3)).astype(np.float32)[..., None]
        self.torches = [((x + MARGIN) // BG_TEXEL, (y + MARGIN) // BG_TEXEL) for x, y in TORCH_XY]
        self.torch_fall = []
        for c, r in self.torches:
            tx, ty = (c + 1) * BG_TEXEL - MARGIN, (r + 2) * BG_TEXEL - MARGIN
            self.torch_fall.append(falloff(np.hypot(wx - tx, wy - ty), 340, 1.8)[..., None]
                                   .astype(np.float32))

    def render(self, t, mat, wall_I, halo_I, white_I):
        d = self.dc
        # 빛은 벽 텍셀(8px) 단위로 계산 → 그 자체로 픽셀 느낌. 단계 양자화는 하지 않는다(동심원 띠 방지).
        L = (0.17 + LIGHT[mat] * (wall_I * falloff(d, 950, 1.6))[..., None]
             + WHITE * (white_I * falloff(d, 700, 1.6))[..., None])
        L = L * self.vign
        for k, tf in enumerate(self.torch_fall):
            flick = 1 + 0.08 * math.sin(11.0 * t + 2.1 * k) + 0.05 * math.sin(17.3 * t + 1.3 + k)
            L = L + TORCH_COLOR * (0.50 * flick) * tf
        lit = self.alb * L
        halo = (LIGHT[mat] * (halo_I * falloff(d, 470, 2.2))[..., None]
                + WHITE * (0.35 * white_I * falloff(d, 420, 2.2))[..., None])
        lit = lit + halo
        for k, (c, r) in enumerate(self.torches):
            variant = int(t * 9 + 1.7 * k + (0.6 if math.sin(t * 5 + k) > 0.7 else 0))
            for rr, cc, col, emit in pa.torch_cells(variant):
                lit[r + rr, c + cc] = col if emit else col * 0.85
        world = np.repeat(np.repeat(lit, BG_TEXEL, axis=0), BG_TEXEL, axis=1)
        return world.astype(np.float32)


# ======================================================================== 파티클·반짝이
class Particle:
    __slots__ = ("t0", "x0", "y0", "vx", "vy", "g", "k", "life", "size", "color", "tw", "ph")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def build_particles(texs: Textures, anchor):
    rng = np.random.default_rng(2026)
    specs = (   # 시각, 이전 재질, 새 재질, 파편 수, 불꽃 수, 떠오르는 수, 속도배율
        (2.0, "wooden", "stone", 34, 26, 0, 1.0),
        (4.0, "stone", "iron", 30, 46, 0, 1.1),
        (6.0, "iron", "diamond", 30, 96, 48, 1.3),
    )
    parts = []
    for T, old, new, nd, ns, nf, sp in specs:
        bobT = int(round(-10.0 * math.cos(math.pi * T)))
        cx, cy = CX, CY + bobT
        old_cols = texs.head_colors(old)
        new_cols = np.vstack([texs.head_colors(new), [[1, 1, 1]] * 3])
        if new == "diamond":
            new_cols = np.vstack([new_cols, [CYAN, [0.55, 0.85, 1.0], [0.35, 0.65, 1.0]]])
        for kind, cnt in (("debris", nd), ("spark", ns), ("float", nf)):
            cells = texs.head_cells if kind == "debris" else texs.cells[new]
            for _ in range(cnt):
                r, c = cells[rng.integers(len(cells))]
                x0, y0 = tex_to_screen(c + rng.uniform(0, 1), r + rng.uniform(0, 1),
                                       cx, cy, TEXEL, 0.0, anchor)
                ang = math.atan2(y0 - cy, x0 - cx) + rng.normal(0, 0.5)
                if kind == "debris":
                    spd, g, k, life = rng.uniform(350, 900), 1500, 1.0, rng.uniform(0.55, 1.0)
                    size = int(rng.choice([8, 10, 12, 14, 16]))
                    col = old_cols[rng.integers(len(old_cols))]
                    vb = -250
                elif kind == "spark":
                    spd, g, k, life = rng.uniform(500, 1300), 350, 3.0, rng.uniform(0.35, 0.8)
                    size = int(rng.choice([6, 8, 10] if new != "diamond" else [6, 8, 10, 12]))
                    col = new_cols[rng.integers(len(new_cols))]
                    vb = -60
                else:
                    spd, g, k, life = rng.uniform(150, 520), -120, 1.5, rng.uniform(0.9, 1.4)
                    size = int(rng.choice([6, 8, 10, 12]))
                    col = new_cols[rng.integers(len(new_cols))]
                    vb = -40
                spd *= sp
                parts.append(Particle(t0=T + rng.uniform(0, 0.04), x0=x0, y0=y0,
                                      vx=math.cos(ang) * spd, vy=math.sin(ang) * spd + vb,
                                      g=g, k=k, life=life, size=size,
                                      color=np.asarray(col, np.float32),
                                      tw=kind != "debris", ph=rng.uniform(0, 6.28)))
    return parts


def draw_particles(canvas, parts, t, dx, dy):
    for p in parts:
        a = t - p.t0
        if a < 0 or a >= p.life:
            continue
        e = (1 - math.exp(-p.k * a)) / p.k
        x = p.x0 + p.vx * e + dx
        y = p.y0 + p.vy * e + 0.5 * p.g * a * a + dy
        f = a / p.life
        s = p.size if f < 0.6 else p.size * (1 - 0.7 * (f - 0.6) / 0.4)
        s = max(2, int(round(s / 2)) * 2)
        al = 1.0 if f < 0.7 else (1 - f) / 0.3
        if p.tw:
            al *= 0.6 + 0.4 * abs(math.sin(25 * a + p.ph))
        blend_rect(canvas, int(round(x - s / 2)), int(round(y - s / 2)), s, s, p.color, al)


def build_sparkles(texs: Textures):
    """(시작, 길이, ('tex', u, v) | ('free', x, y), 단위px, 팔 색)."""
    rng = np.random.default_rng(77)
    warm = (1.0, 0.85, 0.55)
    silver = (0.85, 0.92, 1.0)
    sp = [(0.45, 0.40, ("free", CX + 200, CY - 210), 6, warm),
          (0.55, 0.35, ("free", CX - 260, CY - 120), 6, warm)]
    head = texs.head_cells
    for t0 in (4.45, 4.58, 4.70):                       # 철: 삽날 위 금속 반짝임
        r, c = head[rng.integers(len(head))]
        sp.append((t0, 0.28, ("tex", c + 0.5, r + 0.5), 8, silver))
    for i in range(30):                                  # 다이아: 많고, 점점 줄어듦
        t0 = 6.05 + 1.2 * rng.uniform() ** 1.7
        dur = min(rng.uniform(0.3, 0.5), 7.62 - t0)
        if i % 3 == 0:
            r, c = head[rng.integers(len(head))]
            pos = ("tex", c + 0.5, r + 0.5)
        else:
            rad, ang = rng.uniform(140, 470), rng.uniform(0, 2 * math.pi)
            pos = ("free", CX + rad * math.cos(ang), CY + rad * math.sin(ang) * 0.85)
        sp.append((t0, dur, pos, int(rng.choice([6, 8, 8, 10])), tuple(CYAN)))
    return sp


def draw_sparkles(canvas, sparkles, st):
    t = st["t"]
    dx, dy = st["shake"]
    for t0, dur, pos, unit, col in sparkles:
        p = (t - t0) / dur
        if not 0 <= p < 1:
            continue
        if pos[0] == "tex":
            x, y = tex_to_screen(pos[1], pos[2], st["cx"], st["cy"], st["texel"], st["angle"],
                                 st["anchor"])
        else:
            x, y = pos[1] + dx, pos[2] + dy
        arm = int(round(math.sin(math.pi * p) * 3))
        draw_sparkle(canvas, x, y, unit, arm, col)


def build_dust():
    rng = np.random.default_rng(5)
    n = 50
    return dict(x0=rng.uniform(0, W, n), y0=rng.uniform(0, H, n), vy=rng.uniform(-20, -6, n),
                amp=rng.uniform(6, 18, n), fr=rng.uniform(0.3, 0.8, n), ph=rng.uniform(0, 6.28, n),
                ph2=rng.uniform(0, 6.28, n), size=rng.choice([4, 6], n),
                al=rng.uniform(0.10, 0.30, n))


def draw_dust(canvas, d, t):
    col = (1.0, 0.86, 0.66)
    for i in range(len(d["x0"])):
        x = int(round(d["x0"][i] + d["amp"][i] * math.sin(d["fr"][i] * t + d["ph"][i])))
        y = int(round((d["y0"][i] + d["vy"][i] * t) % H))
        a = d["al"][i] * (0.65 + 0.35 * math.sin(2.3 * t + d["ph2"][i]))
        s = int(d["size"][i])
        blend_rect(canvas, x, y, s, s, col, a)


# ======================================================================== 한 프레임
RINGS = (   # 시각, 수명, 시작반지름, 속도, 두께, 색
    (2.00, 0.40, 140, 2100, 28, np.array([0.85, 0.85, 0.85], np.float32)),
    (4.00, 0.40, 140, 2300, 28, WHITE),
    (6.00, 0.55, 160, 2400, 40, CYAN),
    (6.09, 0.50, 120, 1700, 24, np.array([0.75, 1.0, 0.97], np.float32)),
)
FLASH = (   # 시각, 색, 최대 불투명도, 감쇠 시간
    (2.0, WHITE, 0.45, 0.07),
    (4.0, WHITE, 0.60, 0.08),
    (6.0, np.array([0.6, 1.0, 0.94], np.float32), 0.60, 0.11),
)


class Context:
    def __init__(self, tex_dir=None):
        self.tex = Textures(tex_dir)
        self.cave = Cave()
        self.g12 = Coarse(W, H, CX, CY, 12)
        self.g20 = Coarse(W, H, CX, CY, 20)
        self.parts = build_particles(self.tex, self.tex.anchor)
        self.sparkles = build_sparkles(self.tex)
        self.dust = build_dust()


def render_frame(n: int, ctx: Context) -> np.ndarray:
    st = frame_state(n, ctx.tex.anchor)
    t, mat = st["t"], st["mat"]
    wall_I, halo_I, white_I = light_levels(t, mat)
    world = ctx.cave.render(t, mat, wall_I, halo_I, white_I)
    dx, dy = st["shake"]
    canvas = world[MARGIN - dy:MARGIN - dy + H, MARGIN - dx:MARGIN - dx + W].copy()
    draw_dust(canvas, ctx.dust, t)

    # 철: 흰색 픽셀 섬광(굵은 격자 광선이 순식간에 뻗었다 사라짐)
    dt = t - 4.0
    if 0 <= dt < 0.55:
        lay = rays(ctx.g20, 8, 0.15, 0.75 * math.exp(-dt / 0.16), 60, 1100,
                   r_lim=2600 * min(1.0, dt / 0.12 + 0.05))
        canvas += ctx.g20.up(lay)[..., None] * WHITE
    # 다이아: 회전하는 청록 광선 + 퍼지는 빛 물결
    if t >= 6.0:
        dt = t - 6.0
        env = smoothstep(0.0, 0.1, dt) * (1 - smoothstep(0.7, 1.5, dt))
        if env > 0:
            lay = rays(ctx.g20, 10, 0.35 * dt, 0.42 * env, 90, 1050)
            canvas += ctx.g20.up(lay)[..., None] * CYAN
        if dt < 0.7:
            R = 1900 * (1 - math.exp(-dt / 0.2)) + 1
            g = ctx.g12
            val = 0.55 * (1 - dt / 0.7) ** 2 * (g.r < R) * (0.25 + 0.75 * (g.r / R) ** 4)
            canvas += ctx.g12.up(quant(val, 10))[..., None] * CYAN
    # 충격파 고리
    for T, life, r0, v, th, col in RINGS:
        dt = t - T
        if 0 <= dt < life:
            R = r0 + v * dt
            a = 0.85 * (1 - dt / life) ** 1.5
            m = ctx.g12.up(np.abs(ctx.g12.r - R) < th / 2)
            canvas[m] = canvas[m] * (1 - a) + col * a

    tex = apply_fx(ctx.tex, mat, st["tint"], st["sweep"])
    s = st["texel"] / TEXEL
    draw_sprite(canvas, tex, st["cx"] + round(SHADOW_OFF[0] * s), st["cy"] + round(SHADOW_OFF[1] * s),
                st["texel"], st["angle"], st["anchor"], alpha=0.45 * st["alpha"], solid=(0, 0, 0))
    draw_sprite(canvas, tex, st["cx"], st["cy"], st["texel"], st["angle"], st["anchor"],
                alpha=st["alpha"])
    draw_particles(canvas, ctx.parts, t, dx, dy)
    draw_sparkles(canvas, ctx.sparkles, st)
    if LABELS_ON:
        draw_labels(canvas, st)

    for T, col, peak, tau in FLASH:
        dt = t - T
        if 0 <= dt < 0.5:
            a = peak * math.exp(-dt / tau)
            canvas *= 1 - a
            canvas += col * a
    canvas *= smoothstep(0.0, 0.35, t) if t < 0.35 else 1.0
    return (np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)


LABEL_COLOR = {"wooden": (0.86, 0.67, 0.34), "stone": (0.80, 0.80, 0.80),
               "iron": (0.96, 0.96, 0.96), "diamond": (0.30, 0.94, 0.86)}


def draw_labels(canvas, st):
    """세로판 글자: 위 SHOVEL / EVOLUTION, 아래 지금 단계 이름(바뀔 때 잠깐 커짐)."""
    draw_text(canvas, "SHOVEL", CX, 250, 14, (1.0, 1.0, 1.0), align="center")
    draw_text(canvas, "EVOLUTION", CX, 382, 10, tuple(CYAN), align="center")
    unit = 10
    if st["idx"] > 0 and st["t"] - TRANS[st["idx"] - 1] < 0.18:
        unit = 12
    draw_text(canvas, pa.LABELS[st["mat"]], CX, 1420 - (unit - 10) * 7 // 2, unit,
              LABEL_COLOR[st["mat"]], align="center")


# ======================================================================== 인코딩
def encode(out_path: Path, ctx: Context, crf: int = 14):
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", str(FPS), "-i", "-",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd,format=yuv420p",
           "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-tune", "animation",
           "-profile:v", "high", "-level:v", "4.1",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv", "-movflags", "+faststart", "-r", str(FPS),
           "-frames:v", str(NFRAMES), str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for n in range(NFRAMES):
        proc.stdin.write(render_frame(n, ctx).tobytes())
        if n % 30 == 29:
            print(f"  {n + 1}/{NFRAMES} 프레임  ({time.time() - t0:.1f}s)", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg 인코딩 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None,
                    help="무음 영상(기본 ../minecraft_shovel_evolution[_vertical]_silent.mp4). "
                         "효과음은 sfx.py가 입힌다")
    ap.add_argument("--vertical", action="store_true", help="세로판 1080x1920(9:16)")
    ap.add_argument("--textures", default=None, help="<재질>_shovel.png 4장이 든 폴더(선택)")
    ap.add_argument("--still", type=int, nargs="*", help="이 프레임만 PNG로 저장")
    ap.add_argument("--out-dir", default=str(HERE.parent / "frames"))
    ap.add_argument("--crf", type=int, default=14)
    a = ap.parse_args()
    if a.vertical:
        configure_vertical()
    tag = "_vertical" if a.vertical else ""
    a.out = a.out or str(HERE.parent / f"minecraft_shovel_evolution{tag}_silent.mp4")
    ctx = Context(a.textures)
    if not ctx.tex.same_silhouette:
        print("주의: 바꿔 낀 텍스처 4장의 실루엣이 서로 다릅니다(기준점은 합친 모양의 중심).")
    if a.still is not None:
        Path(a.out_dir).mkdir(parents=True, exist_ok=True)
        for n in a.still:
            p = Path(a.out_dir) / f"still{tag}_{n:03d}.png"
            Image.fromarray(render_frame(n, ctx)).save(p)
            print(p)
        return
    print(f"렌더: {NFRAMES}프레임 {W}x{H} {FPS}fps → {a.out}")
    encode(Path(a.out), ctx, a.crf)
    print("완료:", a.out)


if __name__ == "__main__":
    main()
