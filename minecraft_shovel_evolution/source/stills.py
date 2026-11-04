#!/usr/bin/env python3
"""preview.png(네 삽 비교)와 thumbnail.png(다이아 삽 중심) 만들기.

    python3 stills.py            # ../preview.png, ../thumbnail.png
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pixelart as pa  # noqa: E402
from render import CYAN, LIGHT, Textures  # noqa: E402
from scene import (Coarse, blend_rect, draw_sparkle, draw_sprite, draw_text,  # noqa: E402
                   falloff, rays, text_width)

BG_TEXEL = 8


def cave_bg(W, H, light_xy, light_rgb, light_I, ambient=0.17, halo=None, seed=11):
    gw, gh = math.ceil(W / BG_TEXEL), math.ceil(H / BG_TEXEL)
    lx, ly = light_xy
    alb = pa.cave_albedo(gw, gh, (lx / BG_TEXEL / 16, ly / BG_TEXEL / 16), seed=seed)
    jj, ii = np.meshgrid(np.arange(gw), np.arange(gh))
    wx, wy = (jj + 0.5) * BG_TEXEL, (ii + 0.5) * BG_TEXEL
    d = np.hypot(wx - lx, wy - ly)
    rn = np.hypot((wx - W / 2) / (W / 2), (wy - H / 2) / (H / 2)) / math.sqrt(2)
    vign = (0.18 + 0.82 * np.exp(-(rn / 0.75) ** 3))[..., None]
    L = (ambient + np.asarray(light_rgb) * (light_I * falloff(d, 950, 1.6))[..., None]) * vign
    lit = alb * L
    if halo is not None:
        lit = lit + np.asarray(light_rgb) * (halo * falloff(d, 520, 2.2))[..., None]
    big = np.repeat(np.repeat(lit, BG_TEXEL, 0), BG_TEXEL, 1)[:H, :W]
    return big.astype(np.float32)


def save(canvas, path):
    Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path, optimize=True)
    print(path)


def make_preview(texs: Textures, path: Path):
    W, H = 1920, 720
    canvas = cave_bg(W, H, (W / 2, H / 2), (0.85, 0.88, 0.95), 0.22, ambient=0.15, seed=3)
    draw_text(canvas, "SHOVEL EVOLUTION", W // 2, 50, 8, (1.0, 1.0, 1.0), align="center")
    texel = 22
    slot = 400
    label_col = {n: tuple(int(pa.MATERIALS[n]["L"][i:i + 2], 16) / 255 for i in (1, 3, 5))
                 for n in pa.ORDER}
    label_col["stone"] = (0.80, 0.80, 0.80)
    for i, name in enumerate(pa.ORDER):
        cx, cy = 240 + i * 480, 380
        x0, y0 = cx - slot // 2, cy - slot // 2
        blend_rect(canvas, x0, y0, slot, slot, (0.02, 0.02, 0.03), 0.55)       # 칸 바탕
        for (bx, by, bw, bh, col) in ((x0, y0, slot, 6, (0.35, 0.35, 0.38)),
                                      (x0, y0, 6, slot, (0.35, 0.35, 0.38)),
                                      (x0, y0 + slot - 6, slot, 6, (0.0, 0.0, 0.0)),
                                      (x0 + slot - 6, y0, 6, slot, (0.0, 0.0, 0.0))):
            blend_rect(canvas, bx, by, bw, bh, col, 0.9)
        glow = LIGHT[name]
        g = Coarse(slot - 12, slot - 12, (slot - 12) / 2, (slot - 12) / 2, 8)
        lay = g.up(np.clip(1 - g.r / 190, 0, 1) ** 2 * 0.22)[..., None] * glow
        canvas[y0 + 6:y0 + slot - 6, x0 + 6:x0 + slot - 6] += lay
        draw_sprite(canvas, texs.rgba[name], cx + 10, cy + 12, texel, 0, texs.anchor, 0.45,
                    solid=(0, 0, 0))
        draw_sprite(canvas, texs.rgba[name], cx, cy, texel, 0, texs.anchor)
        draw_text(canvas, pa.LABELS[name], cx, 612, 6, label_col[name], align="center")
        if i < 3:
            draw_text(canvas, ">", cx + 240 - text_width(">", 6) // 2, 380 - 21, 6, (0.9, 0.9, 0.9))
    save(canvas, path)


def make_thumbnail(texs: Textures, path: Path):
    W, H = 1920, 1080
    sx, sy = 1390, 560
    canvas = cave_bg(W, H, (sx, sy), LIGHT["diamond"], 0.55, ambient=0.15, halo=0.30, seed=19)
    g = Coarse(W, H, sx, sy, 20)
    canvas += g.up(rays(g, 10, 0.12, 0.30, 90, 1000))[..., None] * CYAN
    draw_sprite(canvas, texs.rgba["diamond"], sx + 18, sy + 22, 58, 0, texs.anchor, 0.5,
                solid=(0, 0, 0))
    draw_sprite(canvas, texs.rgba["diamond"], sx, sy, 58, 0, texs.anchor)
    rng = np.random.default_rng(8)
    for _ in range(12):
        r, a = rng.uniform(300, 520), rng.uniform(0, 2 * math.pi)
        draw_sparkle(canvas, sx + r * math.cos(a), sy + r * math.sin(a) * 0.8,
                     int(rng.choice([8, 10, 12])), int(rng.choice([2, 3])), tuple(CYAN))
    for c, rr in ((8, 3), (11, 2)):                       # 삽날 위 반짝임
        x = sx + (c + 0.5 - texs.anchor[0]) * 58
        y = sy + (rr + 0.5 - texs.anchor[1]) * 58
        draw_sparkle(canvas, x, y, 10, 3, (0.85, 1.0, 1.0))
    draw_text(canvas, "SHOVEL", 90, 150, 18, (1.0, 1.0, 1.0))
    draw_text(canvas, "EVOLUTION", 90, 310, 13, tuple(CYAN))
    # 아래 진화 줄: 나무 > 돌 > 철 > 다이아
    x, box, gap, cy = 90, 160, 70, 830
    for i, name in enumerate(pa.ORDER):
        blend_rect(canvas, x, cy - box // 2, box, box, (0.0, 0.0, 0.0), 0.45)
        draw_sprite(canvas, texs.rgba[name], x + box // 2, cy, 10, 0, texs.anchor)
        if i < 3:
            draw_text(canvas, ">", x + box + (gap - 29) // 2, cy - 21, 6, (0.9, 0.9, 0.9))
        x += box + gap
    save(canvas, path)


def main():
    texs = Textures(sys.argv[1] if len(sys.argv) > 1 else None)
    out = HERE.parent
    make_preview(texs, out / "preview.png")
    make_thumbnail(texs, out / "thumbnail.png")


if __name__ == "__main__":
    main()
