"""직접 그린 16x16 픽셀아트 원본과 배경·글꼴 데이터.

공식 텍스처 파일은 내려받거나 복사하지 않았다. 레퍼런스 그림을 보고
마인크래프트 삽의 실루엣과 색 계열을 따라 새로 찍은 팬아트 픽셀이다.

네 삽은 하나의 모양 틀(SHOVEL_TEMPLATE)에서 색표만 바꿔 만든다.
그래서 실루엣·중심축·크기가 픽셀 단위로 똑같다(make_shovels에서 검사).
"""
from __future__ import annotations

import math

import numpy as np

GRID = 16          # 텍스처 한 변 픽셀 수
OX, OY = 1, 2      # 13x13 모양을 16x16 안에 놓는 위치(왼쪽, 위)

# 기호
#   o / O : 삽날 외곽선(위·왼쪽 밝은 테 / 오른쪽·아래 어두운 테)
#   L M D : 삽날 밝음 · 중간 · 어두움,  S : 반사광(철·다이아만)
#   h H g k : 손잡이(왼쪽 그늘 / 밝은 나뭇결 / 중간 나뭇결 / 오른쪽 가장 어두움)
SHOVEL_TEMPLATE = (
    ".........ooO.",
    "........oLLMO",
    ".......oLMDLO",
    "......oLMDMLO",
    ".......hMMLO.",
    "......hHkLO..",
    ".....hHk.O...",
    "....hgk......",
    "...hHk.......",
    "..hgk........",
    "hhHk.........",
    "hHk..........",
    ".kk..........",
)

HANDLE = {"h": "#4a361a", "H": "#8a6a33", "g": "#6c5126", "k": "#291d0c"}

MATERIALS = {
    "wooden":  {"o": "#4b3519", "O": "#271b0a", "L": "#a7823f", "M": "#8e6d32", "D": "#765a28"},
    "stone":   {"o": "#525252", "O": "#1e1e1e", "L": "#ababab", "M": "#929292", "D": "#7a7a7a"},
    "iron":    {"o": "#5e5e5e", "O": "#2b2b2b", "L": "#e4e4e4", "M": "#c6c6c6", "D": "#a8a8a8",
                "S": "#ffffff"},
    "diamond": {"o": "#0f4c42", "O": "#0a2e28", "L": "#4cefdc", "M": "#2ccab0", "D": "#1fa691",
                "S": "#d2fff7"},
}
SPECULAR = {"iron": ((1, 9),), "diamond": ((1, 9),)}   # (행, 열) — 틀 좌표

ORDER = ("wooden", "stone", "iron", "diamond")
LABELS = {"wooden": "WOODEN", "stone": "STONE", "iron": "IRON", "diamond": "DIAMOND"}


def hex2rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def make_shovel(name: str) -> np.ndarray:
    """(16, 16, 4) uint8 RGBA."""
    pal = {**HANDLE, **MATERIALS[name]}
    spec = set(SPECULAR.get(name, ()))
    img = np.zeros((GRID, GRID, 4), np.uint8)
    for r, row in enumerate(SHOVEL_TEMPLATE):
        assert len(row) == 13, row
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            key = "S" if (r, c) in spec else ch
            img[OY + r, OX + c] = (*hex2rgb(pal[key]), 255)
    return img


def make_shovels() -> dict[str, np.ndarray]:
    tex = {name: make_shovel(name) for name in ORDER}
    masks = [tex[n][..., 3] > 0 for n in ORDER]
    for m in masks[1:]:
        assert np.array_equal(m, masks[0]), "네 삽의 실루엣이 달라졌다"
    return tex


# ---------------------------------------------------------------- 횃불(배경 소품)
TORCH_FLAMES = (          # 2칸 너비, 불꽃 4줄 — 깜박임 3가지
    (".y", "yY", "YW", "WY"),
    ("y.", "Yy", "WY", "YW"),
    ("..", "yY", "WY", "YW"),
)
TORCH_STICK_ROWS = 7
TORCH_COLORS = {"y": "#e8761c", "Y": "#ffc23a", "W": "#fff6c4", "h": "#5a4220", "H": "#8a6a33"}


def torch_cells(variant: int):
    """[(행, 열, rgb 0~1, 발광여부)]"""
    out = []
    for r, row in enumerate(TORCH_FLAMES[variant % 3]):
        for c, ch in enumerate(row):
            if ch != ".":
                out.append((r, c, np.array(hex2rgb(TORCH_COLORS[ch])) / 255.0, True))
    for r in range(TORCH_STICK_ROWS):
        out.append((4 + r, 0, np.array(hex2rgb(TORCH_COLORS["H"])) / 255.0, False))
        out.append((4 + r, 1, np.array(hex2rgb(TORCH_COLORS["h"])) / 255.0, False))
    return out


# ---------------------------------------------------------------- 동굴 벽(블록 16텍셀)
def _stone_tile(rng, base, tint):
    v = base + rng.normal(0, 0.045, (16, 16))
    yy, xx = np.mgrid[0:16, 0:16] + 0.5
    for _ in range(int(rng.integers(5, 9))):
        cy, cx = rng.uniform(0, 16, 2)
        r = rng.uniform(0.8, 2.4)
        m = (yy - cy) ** 2 + (xx - cx) ** 2 < r * r
        v[m] += rng.choice([-0.10, -0.06, 0.05, 0.07])
    v[-1, :] *= 0.86
    v[:, -1] *= 0.86
    v[0, :] *= 1.05
    v[:, 0] *= 1.05
    return np.clip(v, 0, 1)[..., None] * np.asarray(tint, np.float64)[None, None, :]


def _ore(tile, rng, c1, c2, clusters):
    cells = [(0, 0), (0, 1), (1, 0), (1, 1), (-1, 0), (0, -1), (1, -1)]
    for _ in range(clusters):
        cy, cx = rng.integers(2, 14, 2)
        k = int(rng.integers(3, 6))
        for i in rng.choice(len(cells), k, replace=False):
            dy, dx = cells[i]
            tile[cy + dy, cx + dx] = c1 if rng.random() < 0.6 else c2
    return tile


def cave_albedo(gw: int, gh: int, center_block: tuple[float, float], seed: int = 11) -> np.ndarray:
    """(gh, gw, 3) float32 — 텍셀 단위 벽 반사율. 광석은 중앙에서 먼 곳에만."""
    rng = np.random.default_rng(seed)
    nbx, nby = math.ceil(gw / 16), math.ceil(gh / 16)
    out = np.zeros((nby * 16, nbx * 16, 3))
    cbx, cby = center_block
    for by in range(nby):
        for bx in range(nbx):
            far = math.hypot(bx + 0.5 - cbx, by + 0.5 - cby)
            if rng.random() < 0.13:
                tile = _stone_tile(rng, 0.30, (0.92, 0.95, 1.06))     # 짙은 암석
            else:
                tile = _stone_tile(rng, 0.47, (0.93, 0.97, 1.05))     # 보통 돌(약간 푸른 회색)
            roll = rng.random()
            if roll < 0.08:
                _ore(tile, rng, (0.10, 0.10, 0.10), (0.20, 0.20, 0.21), 3)            # 석탄
            elif roll < 0.115 and far > 3.0:
                _ore(tile, rng, (0.86, 0.68, 0.55), (0.68, 0.50, 0.38), 3)            # 철
            elif roll < 0.135 and far > 4.5:
                _ore(tile, rng, (0.45, 0.93, 0.90), (0.22, 0.68, 0.68), 3)            # 다이아
            if far > 3.5 and rng.random() < 0.05:
                tile *= 0.55                                                          # 그늘진 블록
            out[by * 16:(by + 1) * 16, bx * 16:(bx + 1) * 16] = tile
    return out[:gh, :gw].astype(np.float32)


# ---------------------------------------------------------------- 5x7 비트맵 글꼴
_G = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    ">": (".....", "..#..", "...#.", "#####", "...#.", "..#..", "....."),
    " ": (".....",) * 7,
}
GLYPHS = {k: np.array([[ch == "#" for ch in row] for row in v]) for k, v in _G.items()}


def export_textures(out_dir, scale: int = 16) -> list[str]:
    """16x16 원본과 확대본(nearest)을 PNG로 저장."""
    from pathlib import Path

    from PIL import Image

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, img in make_shovels().items():
        im = Image.fromarray(img, "RGBA")
        p1 = out_dir / f"{name}_shovel.png"
        im.save(p1)
        p2 = out_dir / f"{name}_shovel_x{scale}.png"
        im.resize((GRID * scale, GRID * scale), Image.NEAREST).save(p2)
        written += [str(p1), str(p2)]
    return written


if __name__ == "__main__":
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent
    for p in export_textures(sys.argv[1] if len(sys.argv) > 1 else here / "textures"):
        print(p)
