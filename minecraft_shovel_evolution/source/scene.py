"""그리기 도구 — 픽셀아트를 뭉개지 않게 그리는 것이 핵심.

* 스프라이트는 화면 픽셀마다 텍스처 좌표를 역계산해 가장 가까운 텍셀(nearest)을 그대로 가져온다.
  보간이 없으므로 텍셀 안은 한 가지 색으로 평평하다.
* 회전·확대가 있는 프레임에서만 2x2 초표본으로 텍셀 '경계'의 계단만 1픽셀 정리한다.
  축 정렬·정수 위치(대부분의 프레임)에서는 결과가 순수 nearest와 비트 단위로 같다.
* 빛·광선·충격파는 굵은 격자(8~20px)에서 계산해 nearest로 키운다 → 픽셀 느낌 유지.
"""
from __future__ import annotations

import math

import numpy as np

from pixelart import GLYPHS


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smoothstep(a: float, b: float, x: float) -> float:
    x = clamp01((x - a) / (b - a))
    return x * x * (3 - 2 * x)


def ease_out_back(x: float, c: float = 1.4) -> float:
    x -= 1.0
    return 1 + (c + 1) * x ** 3 + c * x ** 2


def falloff(d: np.ndarray, radius: float, power: float = 2.0) -> np.ndarray:
    return np.clip(1.0 - d / radius, 0.0, 1.0) ** power


def quant(x: np.ndarray, levels: int) -> np.ndarray:
    return np.floor(x * levels) / levels


# ---------------------------------------------------------------- 스프라이트
def tex_to_screen(u, v, cx, cy, texel, angle_deg, anchor):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    px, py = (u - anchor[0]) * texel, (v - anchor[1]) * texel
    return cx + ca * px - sa * py, cy + sa * px + ca * py


def draw_sprite(canvas, tex, cx, cy, texel, angle_deg=0.0, anchor=(8.0, 8.0),
                alpha=1.0, ss=2, solid=None):
    """canvas (H,W,3) float32 위에 tex (h,w,4) float(0~1)를 nearest로 그린다.

    solid=(r,g,b)이면 같은 실루엣을 단색으로(그림자용).
    """
    if alpha <= 0:
        return
    th, tw = tex.shape[:2]
    H, W = canvas.shape[:2]
    corners = [tex_to_screen(u, v, cx, cy, texel, angle_deg, anchor)
               for u, v in ((0, 0), (tw, 0), (tw, th), (0, th))]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    x0, x1 = max(0, math.floor(min(xs))), min(W, math.ceil(max(xs)))
    y0, y1 = max(0, math.floor(min(ys))), min(H, math.ceil(max(ys)))
    if x0 >= x1 or y0 >= y1:
        return
    gx = x0 + (np.arange((x1 - x0) * ss) + 0.5) / ss
    gy = y0 + (np.arange((y1 - y0) * ss) + 0.5) / ss
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    dx = (gx - cx)[None, :]
    dy = (gy - cy)[:, None]
    u = (ca * dx + sa * dy) / texel + anchor[0]
    v = (-sa * dx + ca * dy) / texel + anchor[1]
    iu = np.floor(u).astype(np.int32)
    iv = np.floor(v).astype(np.int32)
    valid = (iu >= 0) & (iu < tw) & (iv >= 0) & (iv < th)
    samp = tex[np.clip(iv, 0, th - 1), np.clip(iu, 0, tw - 1)]
    al = samp[..., 3] * valid * alpha
    if solid is None:
        rgb = samp[..., :3] * al[..., None]
    else:
        rgb = np.asarray(solid, np.float32)[None, None, :] * al[..., None]
    h, w = y1 - y0, x1 - x0
    al = al.reshape(h, ss, w, ss).mean(axis=(1, 3))
    rgb = rgb.reshape(h, ss, w, ss, 3).mean(axis=(1, 3))
    reg = canvas[y0:y1, x0:x1]
    reg *= (1.0 - al)[..., None]
    reg += rgb


# ---------------------------------------------------------------- 사각 픽셀
def blend_rect(canvas, x, y, w, h, color, alpha):
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1 or alpha <= 0:
        return
    reg = canvas[y0:y1, x0:x1]
    reg *= 1.0 - alpha
    reg += np.asarray(color, np.float32) * alpha


def draw_sparkle(canvas, x, y, unit, arm, arm_color, core=(1.0, 1.0, 1.0), alpha=1.0):
    """십자 반짝임: arm=0이면 점 하나, 1~3이면 팔 길이."""
    x, y = int(round(x - unit / 2)), int(round(y - unit / 2))
    for i in range(1, arm + 1):
        a = alpha * (1.0 - 0.22 * (i - 1))
        for ddx, ddy in ((i, 0), (-i, 0), (0, i), (0, -i)):
            blend_rect(canvas, x + ddx * unit, y + ddy * unit, unit, unit, arm_color, a)
    blend_rect(canvas, x, y, unit, unit, core, alpha if arm else alpha * 0.7)


# ---------------------------------------------------------------- 굵은 격자 층
class Coarse:
    """화면을 cell px 격자로 나눈 거리·각도표(중심 기준)."""

    def __init__(self, W, H, cx, cy, cell):
        self.W, self.H, self.cell = W, H, cell
        gw, gh = math.ceil(W / cell), math.ceil(H / cell)
        x = (np.arange(gw) + 0.5) * cell - cx
        y = (np.arange(gh) + 0.5) * cell - cy
        X, Y = np.meshgrid(x, y)
        self.r = np.hypot(X, Y).astype(np.float32)
        self.ang = np.arctan2(Y, X).astype(np.float32)

    def up(self, layer):
        c = self.cell
        big = np.repeat(np.repeat(layer, c, axis=0), c, axis=1)
        return big[:self.H, :self.W]


def rays(g: Coarse, n_rays, rot, intensity, r_inner, r_outer, r_lim=None, sharp=0.55):
    m = np.cos(n_rays * (g.ang - rot))
    v = np.round(np.clip((m - sharp) / (1 - sharp), 0, 1) * 2) / 2
    fall = np.clip(1 - g.r / r_outer, 0, 1) ** 1.3 * np.clip(g.r / r_inner, 0, 1)
    if r_lim is not None:
        fall = fall * (g.r < r_lim)
    return quant(v * fall * intensity, 14)


# ---------------------------------------------------------------- 글자
def text_width(text, unit):
    return (len(text) * 6 - 1) * unit


def draw_text(canvas, text, x, y, unit, color, shadow=(0.05, 0.05, 0.08), shadow_off=None,
              align="left"):
    if align == "center":
        x -= text_width(text, unit) // 2
    so = unit if shadow_off is None else shadow_off
    for pass_ in ((shadow, so), (color, 0)) if shadow is not None else ((color, 0),):
        col, off = pass_
        cx = x
        for ch in text:
            g = GLYPHS[ch]
            for r in range(7):
                for c in range(5):
                    if g[r, c]:
                        blend_rect(canvas, cx + c * unit + off, y + r * unit + off, unit, unit, col, 1.0)
            cx += 6 * unit
    return text_width(text, unit)
