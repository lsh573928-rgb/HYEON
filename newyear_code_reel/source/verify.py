#!/usr/bin/env python3
"""완성 릴스 자동 검수 — 규격·줄거리·이음매·결정성·대본 연동·안전 구역·소리.

    python3 verify.py [--skip-script-tests] [--video 영상.mp4]

영상을 정하지 않으면 ../newyear_code_reel.mp4(소리 포함)가 있을 때 그것을, 없으면 무음본을 본다.
시각과 화면 자리는 전부 build/events.json(node render.js --events)에서 읽는다. 이 파일에 적어 둔 숫자는
인스타그램 규격, 앱 화면이 덮는 자리, 대본 머리말의 약속, 판정 기준뿐이다. 시각표에 없는 사건의 검사는 건너뛴다.

  A 컨테이너   ffprobe 규격, 프레임 수, bt709 꼬리표, moov가 mdat 앞(faststart), 소리 규격
  B 줄거리     MP4를 다시 풀어 낸 프레임에서 잰다 — 연도판 색과 걸림, 확인란(기본 → 빨강 → 금), 흙더미 높이와 색,
               실패한 동안 빠지는 색, 편집기 실행 표시와 오류 줄, 제목(낚는 말이 빨개짐 · 맺는 말로 교체), 불꽃 수와 밝기.
               새해 전의 무대는 사물을 글자('삽질'·'눈'·'별')로 그리고 새해 뒤에는 진짜 그림이 되므로,
               흙더미는 두 그림에서 다 통하는 잣대(따뜻한 화소의 몫, 파랑이 빠진 정도)로 잰다
  C 이음매     마지막 프레임 → 첫 프레임 차이(제목 띠 제외)를 이웃 프레임 차이와 견준다
  D 결정성     같은 프레임을 node로 두 번 따로 그려 화소가 완전히 같은지, 시각표·영상이 지금 소스와 맞는지
  E 대본 연동  대본을 바꿔 그리면 영상이 바뀌는지(삽질 수, "수고했어" 삭제, 없는 이름, 불꽃 수, 눈송이 수)
               — node를 여러 번 띄운다. --skip-script-tests로 생략
  F 안전 구역  앱 단추 자리(오른쪽 아래)·화면 맨 위·피드(4:5)로 잘리는 자리에 글자가 걸리지 않는지
  G 소리       통합 음량·트루 피크(ebur128), 도장 뒤 침묵 구간 (소리가 있을 때만)

결과: 검사마다 한 줄(통과/실패 + 잰 값), ../frames/verify_report.json,
      ../frames/representative_sheet.png · loop_check.png · rep_*.png (전부 MP4에서 푼 프레임)
하나라도 실패하면 종료 코드 1.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVENTS = HERE / "build" / "events.json"
TMP = HERE / "build" / "tmp_verify"          # 대본을 바꿔 그려 보는 임시 폴더(끝나면 지운다)
FRAMES_DIR = ROOT / "frames"
LABEL_FONT = HERE / "fonts" / "BlackHanSans-Regular.ttf"

# ── 엔진이 내보내지 않는 숫자: 인스타그램 릴스 규격과 앱 화면이 덮는 자리 ──
SPEC = dict(w=1080, h=1920, fps=30, codec="h264", profile="High", pix_fmt="yuv420p", audio=("aac", "48000", 2))
SAFE_RIGHT_X = 940                 # 이보다 오른쪽,
SAFE_RIGHT_Y = (1000, 1700)        # 이 높이에는 좋아요·댓글 단추가 얹힌다
SAFE_TOP_Y = 220                   # 이보다 위에는 앱 머리띠가 얹힌다
FEED_RATIO = (4, 5)                # 프로필 격자·피드에서는 가운데 4:5만 보인다(1080×1920이면 y 285~1635)

# ── 대본을 바꿔 그려 볼 때 넣는 값(앞의 값이 대본에 이미 적혀 있으면 다음 값) ──
DIG_TRIES = ((100, "04.10"), (200, "07.19"))   # 삽질 수 → 날짜판이 멈추는 날. script.js 머리말의 약속: 100번이면 4월 10일
FW_TRIES = (3, 5)                              # 불꽃 수
SNOW_TRIES = (30, 300)                         # 눈송이 수
UNKNOWN_LINE = "tree.grow(7)"                  # 엔진에 없는 이름

# ── 판정 기준. 괄호 안은 기본 대본으로 잰 값(2026-11-21) — 화면을 조금 다듬어도 넘지 않게 여유를 뒀다 ──
LIM = dict(
    board_ice=-10.0,      # 연도판 칸의 R−B 평균: 얼음빛이면 이보다 작다 (−45)
    board_gold=30.0,      #                       금빛이면 이보다 크다 (+105)
    jam_red=15.0,         # 걸린 뒤 연도판의 붉은 정도 R−(G+B)/2 가 이만큼 넘게 는다 (+39)
    ink=120,              # 색을 읽을 글자·테두리로 치는 밝기(휘도): 확인란과 제목 글자. 바탕은 40 아래
    tag_px=200,           # 확인란으로 치는 최소 밝은 화소 수 (930~2100)
    tag_tint=40.0,        # 빨강: R−max(G,B), 금: min(R,G)−B 가 이보다 크다 (빨강 +103, 금 +74 · 서로 반대쪽은 +24 아래)
    tag_cool=15.0,        # 기본(회청색): B−R 이 이보다 크다 (+36)
    mound_px=6,           # 흙더미 윗변 오차(px) (+1~2)
    warm=15,              # 흙더미로 치는 화소의 따뜻한 정도 R−B (글자 '삽질' +40, 밤하늘 −26)
    warm_share=0.05,      # 한 줄에서 따뜻한 화소가 이 몫을 넘으면 흙더미 줄 (글자 줄 0.3~0.8, 이름표 줄 0.12, 하늘 0.0)
    chill_ratio=0.75,     # 실패한 동안 무대 배경 채도 ÷ 걸리기 전 1초 채도의 상한 (0.39)
    mark_px=30,           # 실행 표시(✓·✕)로 치는 최소 화소 수 (155~160)
    mark_tint=12,         # 초록·빨강으로 치는 색 우세: 한 채널이 나머지보다 이만큼 큼 (흐려진 ✕ 39, 창 바탕 −26)
    head_change=0.02,     # 제목이 바뀌면 글자 띠의 이 비율 넘게 화소가 크게 달라진다 (13.8%)
    head_same=0.005,      # 제목이 그대로면 이 비율 아래 (0.0%)
    hook_red=60.0,        # 낚는 말 둘째 줄 글자의 R−G 가 오류 순간 이만큼 넘게 는다 (노랑 +28 → 빨강 +142)
    fw_glow=3.0,          # 첫 불꽃이 터진 기둥의 하늘 밝기가 이만큼 넘게 는다 (+6.2, 불꽃 줄을 지우면 +0.3)
    loop_ratio=2.0,       # 이음매 차이 ≤ 이웃 프레임 차이 × loop_ratio + 여유 (평균 3.0 대 3.6, 가장 큰 칸 22 대 19)
    loop_floor=0.5,       #   평균 차이에 주는 여유
    loop_block_floor=5.0, #   가장 큰 칸 차이에 주는 여유
    fresh_block=12.0,     # 지금 그린 화면과 MP4의 칸별 차이 상한: 압축 손실뿐이면 3.5~5.4, 옛 렌더면 68~142
    snow_ratio=0.5,       # 눈송이를 줄인 쪽의 밝은 화소 수 ÷ 많은 쪽 (30송이 254 ÷ 300송이 1010 = 0.25 — 별빛이 함께 세어진다)
    bright=90,            # 편집기·제목 글자로 치는 밝기(휘도 0..255). 창 바탕은 25쯤, 가장 흐린 글자가 105쯤
    solid=160,            # '밝은 덩어리'(눈송이·별·글자 속)로 치는 밝기
    solid_run=20,         # 맨 위에 가만히 있는 밝은 가로 줄의 최대 길이(px). 별·불꽃 잔불은 6 이하, 제목 글자면 30 이상
    card_margin=16,       # 코드 글자 끝과 창 오른쪽 끝 사이 최소 여백(px) (127)
    lufs=(-16.0, -12.0),  # 통합 음량 범위
    true_peak=-1.0,       # 트루 피크 상한(dBTP)
    silence_db=15.0,      # 침묵 구간은 걸리기 직전 2초보다 이만큼 조용해야 한다
)
BLOCK = 120                        # 차이를 견줄 때 화면을 나누는 칸 크기(px)
WINDOW_SHOTS = 5                   # 구간 평균을 낼 때 그 구간에서 고르게 뽑는 프레임 수

GROUPS = dict(A="컨테이너", B="줄거리", C="이음매", D="결정성", E="대본 연동", F="안전 구역", G="소리")


# ======================================================================== 기본 도구
def hex_rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def warmth(px: np.ndarray) -> np.ndarray:
    """따뜻한 정도 R−B. 밤하늘·얼음빛은 음수, 흙은 +30쯤, 금은 +150쯤."""
    return px[..., 0].astype(np.int16) - px[..., 2]


def luma(px: np.ndarray) -> np.ndarray:
    return px[..., 0] * 0.2126 + px[..., 1] * 0.7152 + px[..., 2] * 0.0722


def ink(patch: np.ndarray, level: float) -> tuple[int, np.ndarray]:
    """밝기가 level을 넘는 화소(글자·선)의 수와 평균 색(R, G, B). 하나도 없으면 (0, 검정)."""
    px = patch.reshape(-1, 3)
    lit = px[luma(px) > level]
    return len(lit), lit.mean(0) if len(lit) else np.zeros(3)


def tint_counts(px: np.ndarray) -> tuple[int, int]:
    """(초록이 우세한 화소 수, 빨강이 우세한 화소 수)"""
    p = px.astype(np.int16)
    r, g, b = p[..., 0], p[..., 1], p[..., 2]
    green = g - np.maximum(r, b) >= LIM["mark_tint"]
    red = r - np.maximum(g, b) >= LIM["mark_tint"]
    return int(green.sum()), int(red.sum())


def longest_run(mask: np.ndarray) -> tuple[int, int, int]:
    """가로로 이어진 True 중 가장 긴 것 → (길이, 시작 x, y). 없으면 (0, 0, 0)."""
    edge = np.diff(np.pad(mask, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    start, end = np.argwhere(edge == 1), np.argwhere(edge == -1)      # 줄 순서대로 짝이 맞는다
    if not len(start):
        return 0, 0, 0
    i = int(np.argmax(end[:, 1] - start[:, 1]))
    return int(end[i, 1] - start[i, 1]), int(start[i, 1]), int(start[i, 0])


def diff_stats(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """두 그림의 (평균 절대 차이, BLOCK px 칸마다 평균 낸 차이 가운데 가장 큰 값).
    평균은 화면 전체가 달라졌는지를, 가장 큰 칸은 한 군데만 튀는지를 본다."""
    d = np.abs(a.astype(np.int16) - b).mean(axis=2)
    rows, cols = d.shape[0] // BLOCK, d.shape[1] // BLOCK
    cells = d[:rows * BLOCK, :cols * BLOCK].reshape(rows, BLOCK, cols, BLOCK).mean(axis=(1, 3))
    return float(d.mean()), float(cells.max())


def swap_number(text: str, n: int) -> str | None:
    """줄의 첫 괄호 속 숫자를 n으로 바꾼다. 괄호 속이 숫자가 아니면 None."""
    new = re.sub(r"\(\s*\d+\s*\)", f"({n})", text, count=1)
    return None if new == text else new


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, **kw)


class Report:
    """검사 결과 모음 — 한 줄씩 바로 찍고, 끝에 묶음별 표를 낸다."""

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, group: str, name: str, ok: bool, text: str, **data):
        self.rows.append(dict(group=group, name=name, ok=bool(ok), measured=text, **data))
        print(f"  [{'통과' if ok else '실패'}] {group} {name} — {text}", flush=True)

    def skip(self, group: str, name: str, why: str):
        self.rows.append(dict(group=group, name=name, ok=None, measured=why))
        print(f"  [생략] {group} {name} — {why}", flush=True)

    def failed(self) -> list[dict]:
        return [r for r in self.rows if r["ok"] is False]

    def table(self):
        print("\n묶음            통과  실패  생략")
        for g, title in GROUPS.items():
            rows = [r for r in self.rows if r["group"] == g]
            n = [sum(r["ok"] is v for r in rows) for v in (True, False, None)]
            print(f"{g} {title:<10}{n[0]:>6}{n[1]:>6}{n[2]:>6}")


# ======================================================================== 시각표(events.json) 읽기
class Reel:
    """events.json 한 벌. 시각·배치는 여기서만 꺼내 쓰고, 화면에서 재는 법도 여기 모았다."""

    def __init__(self, data: dict):
        self.d = data
        self.fps, self.frames = data["fps"], data["frames"]
        self.w, self.h = data["w"], data["h"]
        self.lines, self.error_rows, self.state = data["lines"], data["errorRows"], data["state"]
        lay = data["layout"]
        self.split, self.head, self.ed, self.stage = lay["split"], lay["head"], lay["editor"], lay["stage"]
        self.last = self.frames - 1

    @classmethod
    def load(cls, path: Path) -> "Reel":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    # ── 사건과 시각 ──
    def events(self, typ: str) -> list[dict]:
        return [e for e in self.d["events"] if e["type"] == typ]

    def t(self, typ: str, which: int = 0) -> float | None:
        """그 종류 사건의 시각 — 첫 번째(which=0) 또는 마지막(which=-1). 없으면 None."""
        found = self.events(typ)
        return found[which]["t"] if found else None

    def at(self, t: float | None, shift: float = 0.0) -> int | None:
        """시각 t+shift에 가장 가까운 프레임 번호."""
        if t is None:
            return None
        return int(min(self.last, max(0, round((t + shift) * self.fps))))

    def after(self, t: float | None) -> int | None:
        """시각 t이거나 그 직후인 첫 프레임 번호."""
        if t is None:
            return None
        return int(min(self.last, max(0, math.ceil(t * self.fps - 1e-6))))

    def spread(self, t0: float, t1: float) -> list[int]:
        """t0~t1 구간에서 고르게 뽑은 프레임 번호들."""
        step = (t1 - t0) / (WINDOW_SHOTS - 1)
        return sorted({self.at(t0 + step * i) for i in range(WINDOW_SHOTS)})

    def sec(self, frame: int) -> float:
        return frame / self.fps

    def hook_frame(self) -> int:
        """첫머리에서 코드가 지워지고 첫 줄을 치기 시작하는 프레임 — 위에는 낚는 말이 그대로 떠 있다."""
        return self.after(self.d["coldOpen"]["rewindEnd"])

    def snow_frame(self) -> int | None:
        """눈만 내리는 순간: 하늘이 번쩍이는 일(걸림·금빛·새해·불꽃)이 처음 생기기 직전. 그런 일이 없으면 마지막 프레임."""
        start = self.t("snow_start")
        if start is None:
            return None
        flashes = [t for t in map(self.t, ("jam", "gild", "year_roll", "fw_launch")) if t is not None and t > start]
        return self.at(min(flashes), -0.3) if flashes else self.last

    # ── 줄 ──
    def failed_lines(self) -> list[dict]:
        return [ln for ln in self.lines if not ln["ok"]]

    def line_for(self, t: float | None) -> dict | None:
        """시각 t의 효과를 부른 대본 줄: Enter(fireAt)가 t였거나, 그 줄에서 날아간 빛(courier)이 t에 무대에 닿은 줄.
        효과 이름(key)은 엔진을 고치면 바뀔 수 있으므로 시각으로 찾는다."""
        if t is None:
            return None
        for ln in self.lines:
            hits = [ln["fireAt"]] + [e["t"] + e["dur"] for e in self.events("courier") if abs(e["t"] - ln["fireAt"]) < 1e-3]
            if any(abs(h - t) < 1e-3 for h in hits):
                return ln
        return None

    def hook_number(self) -> int | None:
        """낚는 말 둘째 줄에 적힌 줄 번호('6번째 줄에서 …'의 6). 숫자가 없으면 None."""
        found = re.search(r"\d+", self.d["copy"]["hook"][1])
        return int(found.group()) if found else None

    # ── 달력(날짜판과 같은 셈) ──
    def date_of(self, day: int) -> str:
        """그해 day번째 날의 '월.일'."""
        month = 0
        while day > self.stage["MONTH_DAYS"][month]:
            day -= self.stage["MONTH_DAYS"][month]
            month += 1
        return f"{month + 1:02d}.{day:02d}"

    def full_months(self, days: int) -> int:
        """days일 동안 끝까지 채운 달 수(그 달들에만 이름표가 붙는다)."""
        return int((np.cumsum(self.stage["MONTH_DAYS"]) <= days).sum())

    # ── 연도판 ──
    def board_pixels(self, img: np.ndarray) -> np.ndarray:
        """연도판 숫자 칸 안쪽 화소(칸 가장자리 12%는 뺀다 — 걸려서 떨 때도 칸 안에 남게).
        칸 x 자리는 엔진과 같은 규칙(무대 가운데 CX에 n칸을 가운데 정렬)으로 BOARD 치수에서 계산한다."""
        b, n = self.stage["BOARD"], len(str(self.state["yearSet"]["v"]))
        left = self.stage["CX"] - (n * b["cw"] + (n - 1) * b["gap"]) / 2
        inset_x, inset_y = b["cw"] * 0.12, b["ch"] * 0.12
        y0, y1 = round(b["cy"] - b["ch"] / 2 + inset_y), round(b["cy"] + b["ch"] / 2 - inset_y)
        cells = []
        for i in range(n):
            x0 = left + i * (b["cw"] + b["gap"])
            cells.append(img[y0:y1, round(x0 + inset_x):round(x0 + b["cw"] - inset_x)].reshape(-1, 3))
        return np.concatenate(cells)

    def board_warmth(self, img: np.ndarray) -> float:
        return float(warmth(self.board_pixels(img)).mean())

    def board_redness(self, img: np.ndarray) -> float:
        r, g, b = self.board_pixels(img).astype(np.float64).mean(0)
        return float(r - (g + b) / 2)

    def tag_state(self, img: np.ndarray) -> tuple[str, int, np.ndarray]:
        """연도판 바로 밑 확인란('수고했어')의 상태 → ('기본'|'빨강'|'금'|'없음'|'?', 밝은 화소 수, 그 평균 색).
        자리는 연도판 치수에서 잡는다: 판 아랫변(칸 간격의 절반은 띄운다)부터 칸 높이의 절반 아래까지,
        가운데에서 좌우로 칸 폭의 0.9배. 글자·테두리·체크 같은 밝은 화소의 평균 색으로 가른다."""
        b, cx = self.stage["BOARD"], self.stage["CX"]
        bottom = b["cy"] + b["ch"] / 2
        patch = img[round(bottom + b["gap"] / 2):round(bottom + b["ch"] / 2), round(cx - b["cw"] * 0.9):round(cx + b["cw"] * 0.9)]
        n, (r, g, bl) = ink(patch, LIM["ink"])
        if n < LIM["tag_px"]:
            kind = "없음"
        elif r - max(g, bl) >= LIM["tag_tint"]:
            kind = "빨강"
        elif min(r, g) - bl >= LIM["tag_tint"]:
            kind = "금"
        else:
            kind = "기본" if bl - r >= LIM["tag_cool"] else "?"
        return kind, n, np.array([r, g, bl])

    # ── 흙더미 ──
    def mound_half(self, y: float) -> float:
        """높이 y에서 흙더미 반폭(사다리꼴)."""
        s = self.stage
        return s["BASE_HALF"] - (s["BASE_HALF"] - s["TOP_HALF"]) * (s["GROUND"] - y) / s["FULL_H"]

    def mound_top(self, img: np.ndarray) -> int | None:
        """흙더미 윗변의 y. 가운데 띠(윗변 폭의 0.9배)를 바닥선에서 위로 훑어, 따뜻한 색(흙·금)이 끊기는 줄을 찾는다.
        새해 전의 흙더미는 '삽질' 글자로 짜여 있고 가운데에는 어두운 달 이름표가 놓이므로, 그 줄 화소의 일부만
        따뜻해도 흙으로 친다. 윗변 위는 밤하늘과 장화(둘 다 차가운 색)다. 흙더미가 없으면 None."""
        s = self.stage
        half = round(s["TOP_HALF"] * 0.9)
        strip = warmth(img[:s["GROUND"], s["CX"] - half:s["CX"] + half + 1])
        warm = (strip > LIM["warm"]).mean(axis=1) >= LIM["warm_share"]
        top, gap = None, 0
        for y in range(s["GROUND"] - 1, -1, -1):
            if warm[y]:
                top, gap = y, 0
            else:
                gap += 1
                if gap > 4:                      # 띠·글자 줄 사이 틈(2~3px)은 건너뛰고, 그보다 길게 끊기면 끝
                    break
        return top

    def band_spans(self) -> list[tuple[float, float]]:
        """쌓인 달 띠마다 (아래 높이, 위 높이) px. 달마다 두께가 다르다(BAND_TOP = 그 달이 끝나는 높이)."""
        h, spans, bottom = self.state["dig"]["h"], [], 0.0
        for top in self.stage["BAND_TOP"]:
            if bottom < h - 0.5:
                spans.append((bottom, min(top, h)))
            bottom = top
        return spans

    def band_tints(self, img: np.ndarray) -> list[float]:
        """달 띠마다 '파랑이 빠진 정도' (R−B)/R 의 중앙값: 흙은 0.3쯤, 금은 0.6~0.7. 밝기와 무관해서 '삽질' 글자로 짠
        흙더미(새해 전)와 진짜 그림(새해 뒤)을 같은 잣대로 잰다. 가운데 달 이름표를 피해 양옆(반폭의 0.7~0.92배)에서,
        눈이 덮는 위쪽 30%와 아래 3px은 빼고 본다. 중앙값이라 반짝이는 걸러진다. 너무 얇은 띠는 뺀다."""
        s, tints = self.stage, []
        for bottom, top in self.band_spans():
            y0, y1 = round(s["GROUND"] - top + (top - bottom) * 0.3), round(s["GROUND"] - bottom) - 3
            if y1 - y0 < 4:
                continue
            half = self.mound_half(s["GROUND"] - top)
            near, far = round(half * 0.7), round(half * 0.92)
            sides = np.concatenate([img[y0:y1, s["CX"] - far:s["CX"] - near], img[y0:y1, s["CX"] + near:s["CX"] + far]], axis=1)
            red = np.maximum(sides[..., 0].astype(np.float64), 1.0)
            tints.append(float(np.median((red - sides[..., 2]) / red)))
        return tints

    def band_kinds(self, img: np.ndarray) -> list[str]:
        """달 띠마다 '흙' 또는 '금': 파랑이 빠진 정도가 흙·금 색표의 중간보다 크면 금이다."""
        soil, gold = (np.mean([(c[0] - c[2]) / c[0] for c in map(hex_rgb, self.stage[k])]) for k in ("SOIL", "GOLD"))
        return ["금" if tint > (soil + gold) / 2 else "흙" for tint in self.band_tints(img)]

    # ── 무대 전체 ──
    def scenery_chroma(self, img: np.ndarray) -> float:
        """무대 배경(흙더미 윗변 아래: 흙더미와 눈밭)의 평균 채도 max(R,G,B)−min(R,G,B) — 캔버스의 'saturation' 합성이
        쓰는 바로 그 정의. 그 위쪽은 일부러 선명하게 얹는 연도판·도장·계수판이 있어서 뺀다."""
        top = round(self.stage["GROUND"] - (self.state["dig"]["h"] if self.state["dig"] else 0))
        px = img[top:, :self.split].astype(np.int16)
        return float((px.max(axis=2) - px.min(axis=2)).mean())

    def sky_luma(self, img: np.ndarray, x: float, half: float) -> float:
        """무대 하늘(바닥선 위, 제목 띠 제외)에서 가로 x±half 기둥의 평균 밝기."""
        y0, y1 = self.head_rows()
        cols = slice(max(0, round(x - half)), min(self.split, round(x + half)))
        return float(luma(img[np.r_[0:y0, y1:self.stage["GROUND"]], cols]).mean())

    def flake_pixels(self, img: np.ndarray) -> int:
        """제목 위 하늘(별과 눈뿐인 자리)의 밝은 화소 수 — 눈송이가 많을수록 는다."""
        return int((luma(img[:self.head_rows()[0], :self.split]) > LIM["solid"]).sum())

    # ── 편집기 ──
    def row_box(self, row: int) -> tuple[int, int]:
        """그 칸 글자가 놓이는 높이(y0, y1): 밑선에서 글자 크기의 0.9배 위 ~ 0.3배 아래."""
        y = self.ed["codeTop"] + row * self.ed["lineH"]
        return round(y - self.ed["fontPx"] * 0.9), round(y + self.ed["fontPx"] * 0.3)

    def gutter_mark(self, img: np.ndarray, row: int) -> str | None:
        """줄 번호 자리(창 왼쪽 끝과 코드 사이)의 실행 표시: 'ok'(초록 ✓), 'error'(빨강 ✕), 없으면 None."""
        y0, y1 = self.row_box(row)
        green, red = tint_counts(img[y0:y1, self.ed["cardX"] + 10:self.ed["gutterX"] + 3])
        if max(green, red) < LIM["mark_px"]:
            return None
        return "ok" if green > red else "error"

    def error_bar(self, img: np.ndarray, row: int) -> bool:
        """오류 줄이면 창 왼쪽 끝에 빨간 세로 막대가 붙는다."""
        y0, y1 = self.row_box(row)
        r, g, b = img[y0:y1, self.ed["cardX"] + 1:self.ed["cardX"] + 5].reshape(-1, 3).astype(np.float64).mean(0)
        return bool(r - max(g, b) >= LIM["mark_tint"])

    def editor_rows(self, img: np.ndarray, frame: int) -> dict:
        """그 프레임에서 줄마다 기대한 실행 표시와 화면에서 읽은 표시, 오류 줄(빨간 막대)이 낀 칸.
        주석·빈 줄·그냥 변수 저장(silent)과 아직 Enter가 안 떨어진 줄에는 표시가 없어야 한다."""
        now = self.sec(frame)
        marks = []
        for ln in self.lines:
            want = None if ln["silent"] or ln["fireAt"] > now else ("ok" if ln["ok"] else "error")
            marks.append(dict(line=ln["idx"] + 1, text=ln["text"], row=ln["row"], want=want,
                              seen=self.gutter_mark(img, ln["row"])))
        n_rows = len(self.lines) + len(self.error_rows)
        return dict(marks=marks,
                    bars_seen=[r for r in range(n_rows) if self.error_bar(img, r)],
                    bars_want=[e["row"] for e in self.error_rows if e["t"] <= now])

    def text_right(self, img: np.ndarray, y0: int, y1: int) -> int | None:
        """편집기 쪽(x ≥ split)에서 y0..y1 사이 밝은 글자가 닿는 가장 오른쪽 x. 없으면 None."""
        cols = (luma(img[y0:y1, self.split:]) > LIM["bright"]).sum(axis=0) >= 2
        return int(self.split + np.flatnonzero(cols)[-1]) if cols.any() else None

    # ── 제목 ──
    def head_rows(self) -> tuple[int, int]:
        """위쪽 큰 글자 두 줄이 차지하는 높이(테두리·그림자까지 넉넉히 글자 크기의 1.2배)."""
        pad = self.head["px"] * 1.2
        return round(self.head["y1"] - pad), round(self.head["y2"] + pad)

    def head_patch(self, img: np.ndarray) -> np.ndarray:
        """제목 띠의 편집기 쪽 절반, 코드 창 위까지(제목은 화면 가운데 정렬이고, 이쪽에는 눈·불꽃이 없다)."""
        y0, y1 = self.head_rows()
        return img[y0:min(y1, self.ed["cardY"]), self.split:]

    def head_change(self, a: np.ndarray, b: np.ndarray) -> float:
        """제목 띠에서 크게 달라진 화소의 비율."""
        diff = np.abs(self.head_patch(a).astype(np.int16) - self.head_patch(b)).max(axis=2)
        return float((diff > 96).mean())

    def head_extent(self, img: np.ndarray) -> tuple[int, int] | None:
        """제목 글자(밝은 속)가 차지하는 높이 (맨 윗줄 y, 맨 아랫줄 y). 글자가 없으면 None."""
        lit = (luma(img[:self.ed["cardY"], self.split:]) > LIM["bright"]).sum(axis=1) >= 3
        rows = np.flatnonzero(lit)
        return (int(rows[0]), int(rows[-1])) if len(rows) else None

    def hook2_redness(self, img: np.ndarray) -> float:
        """제목 둘째 줄 글자 색의 R−G: 노랑이면 +30쯤, 빨강이면 +140쯤."""
        y0, y1 = round(self.head["y2"] - self.head["px"] / 2), round(self.head["y2"] + self.head["px"] / 2)
        _, (r, g, _) = ink(img[y0:y1, self.split:], LIM["ink"])
        return float(r - g)

    def scene_diff(self, a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
        """제목 띠를 뺀 화면의 (평균 절대 차이, 가장 큰 칸 차이)."""
        y0, y1 = self.head_rows()
        keep = np.r_[0:y0, y1:self.h]
        return diff_stats(a[keep], b[keep])


# ======================================================================== 영상·정지 화면 꺼내기
def probe(mp4: Path) -> tuple[dict, dict | None] | None:
    """ffprobe로 읽은 (영상 줄기, 소리 줄기 또는 None). 읽지 못하는 파일(렌더가 덜 끝났거나 깨짐)이면 None."""
    r = run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
             "stream=codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_read_frames,"
             "duration,color_range,color_space,color_primaries,color_transfer,sample_rate,channels"
             ":format=duration,size", "-of", "json", mp4], text=True)
    if r.returncode != 0:
        return None
    j = json.loads(r.stdout)
    video = next(s for s in j["streams"] if s["codec_type"] == "video")
    audio = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    video["format"] = j["format"]
    return video, audio


def top_level_atoms(mp4: Path) -> list[str]:
    """MP4 최상위 상자 이름을 파일에 놓인 순서대로."""
    names, pos, total = [], 0, mp4.stat().st_size
    with open(mp4, "rb") as f:
        while pos + 8 <= total:
            f.seek(pos)
            size, name = struct.unpack(">I4s", f.read(8))
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = total - pos
            names.append(name.decode("latin1"))
            if size < 8:
                break
            pos += size
    return names


def decode(mp4: Path, wanted: set[int], w: int, h: int) -> dict[int, np.ndarray]:
    """MP4에서 고른 프레임만 RGB로 푼다(bt709·TV 범위 → 0..255) → {프레임 번호: 그림}."""
    nums = sorted(wanted)
    pick = "+".join(f"eq(n\\,{n})" for n in nums)
    raw = run(["ffmpeg", "-v", "error", "-i", mp4, "-map", "0:v:0", "-vf",
               f"select={pick},scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,"
               "format=rgb24", "-fps_mode", "passthrough", "-f", "rawvideo", "-"], check=True).stdout
    return dict(zip(nums, np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)))


def render_js(*args) -> subprocess.CompletedProcess:
    return run(["node", "render.js", *args], cwd=HERE, text=True)


def render_events(folder: Path, script: Path | None = None) -> tuple[Reel | None, str]:
    """node render.js --events 를 돌려 시각표를 읽는다 → (Reel 또는 None, 오류 글)."""
    r = render_js(*(["--script", script] if script else []), "--events", "--out-dir", folder)
    if r.returncode != 0 or not (folder / "events.json").exists():
        return None, (r.stderr or r.stdout).strip()[-300:]
    return Reel.load(folder / "events.json"), ""


def render_stills(folder: Path, frames: list[int], script: Path | None = None) -> list[np.ndarray] | None:
    """node render.js --still 로 고른 프레임을 그려 읽는다(준 순서대로). 실패하면 None."""
    r = render_js(*(["--script", script] if script else []), "--still", *frames, "--out-dir", folder)
    pngs = [folder / f"f{n:04d}.png" for n in frames]
    if r.returncode != 0 or not all(p.exists() for p in pngs):
        return None
    return [np.asarray(Image.open(p).convert("RGB")) for p in pngs]


def try_script(name: str, lines: list[str]) -> tuple[Path, Reel | None, str]:
    """바꾼 대본을 render.js --script가 읽는 꼴(window.SCRIPT_TEXT = "...")로 적고 시각표를 만든다
    → (대본 파일, Reel 또는 None, 오류 글)."""
    folder = TMP / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "script.js"
    path.write_text("window.SCRIPT_TEXT = " + json.dumps("\n".join(lines), ensure_ascii=False) + ";\n", encoding="utf-8")
    return (path, *render_events(folder, path))


# ======================================================================== 볼 프레임 고르기
def representative(reel: Reel) -> list[tuple[str, str, int]]:
    """대표 장면 8개 → [(파일 이름 꼬리, 설명, 프레임)]. 대본에 없는 장면은 빠진다."""
    st, at, t = reel.state, reel.at, reel.t
    year = st["yearSet"]["v"] if st["yearSet"] else None
    new_year = year + st["yearUp"]["by"] if st["yearSet"] and st["yearUp"] else None
    dig_mid = t("dig_start") + 0.6 * st["dig"]["D"] if st["dig"] else None
    picks = [
        ("hook", "첫 장면(낚는 말)", 0),
        ("board", f"연도판 {year}과 확인란", at(t("board_settle"), 0.2)),
        ("worker", "삽질러 착지", at(t("worker_land"), 0.1)),
        ("dig", "삽질 한창", at(dig_mid)),
        ("jam", "걸림과 실패 도장", at(t("stamp"), 0.3)),
        ("thanks", "말풍선과 금빛", at(t("gild"), 0.45)),
        ("newyear", f"{new_year} 잠김", at(t("year_gold"), 0.4)),
        ("final", "마지막 프레임", reel.last),
    ]
    return [p for p in picks if p[2] is not None]


def moments(reel: Reel) -> dict[str, int | None]:
    """검사에 쓰는 순간 → 프레임 번호(그 장면이 없는 대본이면 None)."""
    at, t = reel.at, reel.t
    m = dict(first=0, first3=3, first6=6, last=reel.last, last1=reel.last - 1, last3=reel.last - 3, last6=reel.last - 6,
             mid=reel.frames // 2, mid1=reel.frames // 2 + 1)
    # 연도판: 넘어가기 직전 / 금빛이 된 뒤 / 걸리기 전후(빨간 빛이 깜박이므로 0.3초 뒤 앞뒤 한 프레임까지 본다)
    m["ice"] = at(t("year_roll"), -0.1) if t("year_roll") is not None else reel.last
    m["gold"] = at(t("year_gold"), 0.6)
    jam, stamp, fix = t("jam"), t("stamp"), t("fix_stamp")
    m["jam_before"] = at(jam, -0.3)
    for name, shift in (("jam_after_a", 0.3 - 1 / reel.fps), ("jam_after_b", 0.3), ("jam_after_c", 0.3 + 1 / reel.fps)):
        m[name] = at(jam, shift)
    # 확인란: 처음 바뀌기 전 / 도장과 '보완 완료' 사이 한가운데(고치지 않는 대본이면 도장 0.5초 뒤) / 체크 0.4초 뒤
    changes = [x for x in (jam, t("check")) if x is not None]
    m["tag_plain"] = at(min(changes), -0.3) if changes else reel.last
    m["tag_red"] = at(stamp, 0.5 if fix is None else (fix - stamp) / 2) if stamp is not None else None
    m["tag_gold"] = at(t("check"), 0.4)
    # 색 빠짐: 걸리기 전 1초 / 도장 0.3초 뒤부터 고치는 줄의 Enter까지(고치지 않으면 1초 동안)
    if jam is not None and stamp is not None:
        for i, f in enumerate(reel.spread(jam - 1.0, jam - 1 / reel.fps)):
            m[f"warm{i}"] = f
        for i, f in enumerate(reel.spread(stamp + 0.3, fix if fix is not None else stamp + 1.3)):
            m[f"cold{i}"] = f
    # 흙더미: 삽질이 끝난 순간 / 금빛이 오르기 직전 / 마지막 띠가 바뀌고 0.6초 뒤
    m["dug"] = reel.after(t("dig_end"))
    m["soil"] = at(t("gild"), -0.1) if t("gild") is not None else reel.last
    m["gilded"] = at(t("gild", -1), 0.6)
    # 제목: 맺는 말로 바뀌기 전후 / 첫 오류 전후
    swap = reel.d["swapT"]
    m["head_before"], m["head_after"] = at(swap, -0.4), at(swap, 0.8)
    m["hook_before"], m["hook_red"] = at(t("enter_error"), -0.3), at(t("enter_error"), 0.3)
    # 불꽃: 첫 발을 쏘기 0.5초 전 / 첫 발이 터지고 0.1초 뒤
    m["fw_before"], m["fw_after"] = at(t("fw_launch"), -0.5), at(t("fw_burst"), 0.1)
    for ln in reel.lines:
        m[f"typed{ln['idx']}"] = reel.after(ln["typeEnd"])
    return m


# ======================================================================== A. 컨테이너
def check_container(rep: Report, mp4: Path, reel: Reel, v: dict, a: dict | None):
    dur, want = float(v["duration"]), reel.frames / SPEC["fps"]
    rep.add("A", "영상 코덱", (v["codec_name"], v.get("profile"), v["pix_fmt"]) == (SPEC["codec"], SPEC["profile"], SPEC["pix_fmt"]),
            f"{v['codec_name']} {v.get('profile')} · {v['pix_fmt']}")
    rep.add("A", "화면 크기", (v["width"], v["height"]) == (SPEC["w"], SPEC["h"]) == (reel.w, reel.h), f"{v['width']}x{v['height']}")
    rate = f"{SPEC['fps']}/1"
    rep.add("A", "프레임 속도", v["r_frame_rate"] == v["avg_frame_rate"] == rate and reel.fps == SPEC["fps"],
            f"{v['r_frame_rate']} (평균 {v['avg_frame_rate']})")
    rep.add("A", "프레임 수", int(v["nb_read_frames"]) == reel.frames, f"{v['nb_read_frames']}장 (시각표 {reel.frames}장)")
    rep.add("A", "길이", abs(dur - want) <= 0.02, f"{dur:.3f}초 (기대 {want:.3f}±0.02)")
    tags = [v.get(k) for k in ("color_space", "color_primaries", "color_transfer")]
    rep.add("A", "색 꼬리표", tags == ["bt709"] * 3, " / ".join(str(t) for t in tags) + f" · 범위 {v.get('color_range')}")
    atoms = top_level_atoms(mp4)
    rep.add("A", "faststart", "moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat"),
            "상자 순서 " + " → ".join(atoms))
    if a is None:
        rep.skip("A", "소리 규격", "소리 줄기 없음(무음 영상)")
    else:
        rep.add("A", "소리 규격", (a["codec_name"], a["sample_rate"], a["channels"]) == SPEC["audio"],
                f"{a['codec_name']} {a['sample_rate']}Hz {a['channels']}ch")
        rep.add("A", "소리 길이", abs(float(a["duration"]) - dur) <= 0.05, f"{float(a['duration']):.3f}초 (영상 {dur:.3f}±0.05)")


# ======================================================================== B. 줄거리
def check_board(rep: Report, group: str, reel: Reel, ice: np.ndarray, gold: np.ndarray | None):
    """연도판: 넘어가기 전엔 얼음빛, 넘어간 뒤엔 금빛. 끝내 못 넘어가는 대본이면 ice에 마지막 화면을 받는다."""
    if not reel.state["yearSet"]:
        rep.skip(group, "연도판 색", "대본에 year = … 줄이 없음")
        return
    w_ice = reel.board_warmth(ice)
    if gold is None:
        rep.add(group, "연도판 색", w_ice < LIM["board_ice"],
                f"새해로 넘어가지 않음 → 끝까지 얼음빛 R−B {w_ice:+.1f} (기준 < {LIM['board_ice']})", ice=w_ice)
        return
    w_gold = reel.board_warmth(gold)
    rep.add(group, "연도판 색", w_ice < LIM["board_ice"] and w_gold > LIM["board_gold"],
            f"넘어가기 전 R−B {w_ice:+.1f} (얼음빛 < {LIM['board_ice']}) → 잠기고 0.6초 뒤 {w_gold:+.1f} (금빛 > {LIM['board_gold']})",
            ice=w_ice, gold=w_gold)


def check_jam(rep: Report, reel: Reel, pic):
    """새해로 넘기다 걸리면 연도판이 빨갛게 달아오른다."""
    if reel.t("jam") is None or not reel.state["yearSet"]:
        rep.skip("B", "연도판 걸림", "대본에 새해로 넘기다 걸리는 줄이 없음")
        return
    before = reel.board_redness(pic("jam_before"))
    after = max(reel.board_redness(pic(k)) for k in ("jam_after_a", "jam_after_b", "jam_after_c"))
    rep.add("B", "연도판 걸림", after - before >= LIM["jam_red"],
            f"붉은 정도 0.3초 전 {before:+.1f} → 0.3초 뒤 {after:+.1f} (늘어난 양 {after - before:+.1f}, 기준 ≥ {LIM['jam_red']})",
            before=before, after=after)


def check_tag(rep: Report, reel: Reel, pic):
    """연도판 밑 확인란: 처음엔 기본색, 실패 도장이 찍힌 동안 빨강, 체크된 뒤 금."""
    if not reel.state["yearSet"]:
        rep.skip("B", "확인란", "대본에 year = … 줄이 없음")
        return
    steps = [("기본", "tag_plain", "처음"), ("빨강", "tag_red", "도장이 찍힌 동안"), ("금", "tag_gold", "체크 0.4초 뒤")]
    seen = [(want, when, *reel.tag_state(pic(key))) for want, key, when in steps if pic(key) is not None]
    rep.add("B", "확인란", all(want == kind for want, _, kind, _, _ in seen),
            " → ".join(f"{when} {kind}({n}화소, R−B {rgb[0] - rgb[2]:+.0f} · R−G {rgb[0] - rgb[1]:+.0f})" for _, when, kind, n, rgb in seen)
            + " (기대 " + " → ".join(want for want, *_ in seen) + ")",
            states=[dict(want=want, seen=kind, pixels=n, rgb=rgb.round(1).tolist()) for want, _, kind, n, rgb in seen])


def check_mound_top(rep: Report, group: str, reel: Reel, img: np.ndarray):
    """삽질이 끝난 순간 흙더미 윗변이 GROUND − h 에 있는가."""
    want = reel.stage["GROUND"] - reel.state["dig"]["h"]
    top = reel.mound_top(img)
    rep.add(group, "흙더미 높이", top is not None and abs(top - want) <= LIM["mound_px"],
            f"윗변 y={top} (기대 {want:.1f}±{LIM['mound_px']}, 삽질 {reel.state['dig']['n']}번)", top=top, want=want)


def check_bands(rep: Report, group: str, reel: Reel, soil: np.ndarray, gilded: np.ndarray | None):
    """달 띠 색: 금빛으로 바뀌기 전엔 전부 흙, 바뀐 뒤엔 전부 금. 안 바뀌는 대본이면 soil에 마지막 화면을 받는다."""
    if not reel.state["dig"]:
        rep.skip(group, "흙더미 색", "대본에 삽질 줄이 없음")
        return
    before = reel.band_kinds(soil)
    if gilded is None:
        rep.add(group, "흙더미 색", bool(before) and set(before) == {"흙"},
                f"금빛으로 바뀌지 않음 → 끝까지 흙 {before.count('흙')}/{len(before)}띠", before=before)
        return
    after = reel.band_kinds(gilded)
    rep.add(group, "흙더미 색", bool(before) and set(before) == {"흙"} and set(after) == {"금"},
            f"바뀌기 전 흙 {before.count('흙')}/{len(before)}띠 → 마지막 띠가 바뀌고 0.6초 뒤 금 {after.count('금')}/{len(after)}띠",
            before=before, after=after)


def check_chill(rep: Report, reel: Reel, pic, plan: dict):
    """실패한 동안에는 무대에서 색이 빠진다."""
    warm = [reel.scenery_chroma(pic(k)) for k in plan if k.startswith("warm")]
    cold = [reel.scenery_chroma(pic(k)) for k in plan if k.startswith("cold")]
    if not warm or not cold:
        rep.skip("B", "실패한 동안 색 빠짐", "대본에 새해로 넘기다 걸리는 줄이 없음")
        return
    before, during = float(np.mean(warm)), float(np.mean(cold))
    rep.add("B", "실패한 동안 색 빠짐", during <= before * LIM["chill_ratio"],
            f"무대 배경(흙더미·눈밭) 평균 채도 — 걸리기 전 1초 {before:.1f} → 도장 0.3초 뒤부터 고칠 때까지 {during:.1f} "
            f"(비율 {during / before:.2f}, 기준 ≤ {LIM['chill_ratio']} · 프레임 {len(warm)}장 대 {len(cold)}장)",
            before=before, during=during)


def check_editor(rep: Report, group: str, reel: Reel, img: np.ndarray, frame: int):
    """그 프레임의 편집기: 성공한 줄은 초록 ✓, 실패한 줄은 빨강 ✕, 주석은 표시 없음, 실패한 줄 바로 아래에만 오류 줄."""
    rows = reel.editor_rows(img, frame)
    wrong = [m for m in rows["marks"] if m["seen"] != m["want"]]
    count = {k: sum(m["seen"] == k for m in rows["marks"]) for k in ("ok", "error", None)}
    text = f"✓ {count['ok']}줄 · ✕ {count['error']}줄 · 표시 없음 {count[None]}줄"
    if wrong:
        text += " — 어긋남: " + ", ".join(f"{m['line']}번째 줄({m['text']}) 기대 {m['want']} 읽음 {m['seen']}" for m in wrong)
    rep.add(group, "편집기 실행 표시", not wrong, text, marks=rows["marks"])
    rep.add(group, "오류 줄", rows["bars_seen"] == rows["bars_want"],
            f"실패한 줄 {len(reel.failed_lines())}개 · 빨간 막대가 보이는 칸 {rows['bars_seen']} (기대 {rows['bars_want']})",
            bars_seen=rows["bars_seen"], bars_want=rows["bars_want"])


def check_headline(rep: Report, reel: Reel, pic):
    """위쪽 큰 글자: 예고한 줄에서 오류가 나는 순간 둘째 줄이 빨개지고, 새해로 넘어가면 맺는 말로 바뀐다."""
    if pic("hook_red") is None:
        rep.skip("B", "낚는 말 빨강", "대본에 오류가 나는 줄이 없음")
    else:
        before, after = reel.hook2_redness(pic("hook_before")), reel.hook2_redness(pic("hook_red"))
        rep.add("B", "낚는 말 빨강", after - before >= LIM["hook_red"],
                f"둘째 줄 '{reel.d['copy']['hook'][1]}' 글자의 R−G — 첫 오류 0.3초 전 {before:+.1f} → 0.3초 뒤 {after:+.1f} "
                f"(늘어난 양 {after - before:+.1f}, 기준 ≥ {LIM['hook_red']})", before=before, after=after)
    if reel.d["swapT"] is None:
        rep.skip("B", "제목 교체", "맺는 말로 바뀌지 않는 대본(swapT 없음)")
    else:
        changed = reel.head_change(pic("head_before"), pic("head_after"))
        rep.add("B", "제목 교체", changed >= LIM["head_change"],
                f"바뀌기 0.4초 전과 0.8초 뒤 사이 제목 띠에서 달라진 화소 {changed:.1%} (기준 ≥ {LIM['head_change']:.0%})",
                changed=changed)


def check_fireworks(rep: Report, reel: Reel, pic):
    """불꽃: 대본에 적은 수만큼 터지고, 그중 한 발만 삽 모양이고, 첫 발이 터진 자리의 하늘이 밝아진다."""
    fw = reel.state["fw"]
    if not fw:
        rep.skip("B", "불꽃", "대본에 불꽃 줄이 없음")
        return
    line, bursts = reel.line_for(fw["t"]), reel.events("fw_burst")
    want = line["args"][0] if line and line["args"] else fw["n"]
    shapes = sum(b.get("kind") == "shape" for b in bursts)
    rep.add("B", "불꽃 수", len(bursts) == want and shapes == 1,
            f"fw_burst {len(bursts)}건 (대본 '{line['text'] if line else '?'}' → {want}발) · 삽 모양(kind 'shape') {shapes}발 (기대 1발)",
            bursts=len(bursts), want=want, shapes=shapes)
    if not bursts or pic("fw_before") is None:
        rep.add("B", "불꽃 밝기", False, "영상 안에서 쏘거나 터지는 불꽃이 없음")
        return
    x, half = bursts[0]["x"] * reel.stage["W"], bursts[0]["size"]
    before, after = reel.sky_luma(pic("fw_before"), x, half), reel.sky_luma(pic("fw_after"), x, half)
    rep.add("B", "불꽃 밝기", after - before >= LIM["fw_glow"],
            f"첫 불꽃이 터진 기둥(x {x:.0f}±{half:.0f})의 하늘 밝기 — 쏘기 0.5초 전 {before:.1f} → 터지고 0.1초 뒤 {after:.1f} "
            f"(늘어난 양 {after - before:+.1f}, 기준 ≥ {LIM['fw_glow']})", before=before, after=after)


def check_story(rep: Report, reel: Reel, pic, plan: dict):
    check_board(rep, "B", reel, pic("ice"), pic("gold") if reel.t("year_roll") is not None else None)
    check_jam(rep, reel, pic)
    check_tag(rep, reel, pic)
    if reel.t("dig_end") is None:
        rep.skip("B", "흙더미 높이", "대본에 삽질 줄이 없음")
    else:
        check_mound_top(rep, "B", reel, pic("dug"))
    check_bands(rep, "B", reel, pic("soil"), pic("gilded"))
    check_chill(rep, reel, pic, plan)
    check_editor(rep, "B", reel, pic("last"), reel.last)
    check_headline(rep, reel, pic)
    check_fireworks(rep, reel, pic)


# ======================================================================== C. 이음매
def check_loop(rep: Report, reel: Reel, pic):
    """마지막 프레임 → 첫 프레임이 여느 프레임 넘김만큼만 달라야 한다(제목은 끝에서 맺는 말 → 낚는 말로 바뀌는 중이라 뺀다).
    평균 차이는 영상 한가운데의 이웃 프레임과, 한 군데만 튀는지는 바로 앞 이웃 프레임(같은 불꽃이 떠 있는 장면)과 견준다."""
    seam, seam_block = reel.scene_diff(pic("last"), pic("first"))
    near, near_block = reel.scene_diff(pic("last1"), pic("last"))
    mid, mid_block = reel.scene_diff(pic("mid"), pic("mid1"))
    limit = mid * LIM["loop_ratio"] + LIM["loop_floor"]
    limit_block = near_block * LIM["loop_ratio"] + LIM["loop_block_floor"]
    y0, y1 = reel.head_rows()
    head = reel.head_change(pic("last"), pic("first"))
    rep.add("C", "마지막 → 첫 프레임", seam <= limit and seam_block <= limit_block,
            f"평균 차이 {seam:.2f} (기준 ≤ {limit:.2f} = 영상 가운데 이웃 프레임 {reel.frames // 2}→{reel.frames // 2 + 1}의 {mid:.2f} × {LIM['loop_ratio']} + 여유) · "
            f"가장 큰 {BLOCK}px 칸 {seam_block:.1f} (기준 ≤ {limit_block:.1f} = 바로 앞 이웃 프레임 {reel.last - 1}→{reel.last}의 {near_block:.1f} × {LIM['loop_ratio']} + 여유) — "
            f"참고: 바로 앞 이웃의 평균 {near:.2f}, 가운데 이웃의 가장 큰 칸 {mid_block:.1f} · 제목 띠 y {y0}~{y1}은 빼고 쟀고, "
            f"그 띠에서 크게 달라진 화소는 {head:.1%}",
            seam=seam, seam_block=seam_block, near=near, near_block=near_block, middle=mid, middle_block=mid_block,
            limit=limit, limit_block=limit_block, head_changed=head)


# ======================================================================== D. 결정성
def check_determinism(rep: Report, reel: Reel, from_mp4: np.ndarray | None):
    """같은 프레임을 따로 두 번 그려 화소가 같은지, 그리고 지금 소스가 build/events.json과 MP4를 만든 그 소스인지.
    from_mp4: MP4에서 푼 마지막 프레임(못 풀었으면 None)."""
    a, b = render_stills(TMP / "still_a", [reel.last]), render_stills(TMP / "still_b", [reel.last])
    if a is None or b is None:
        rep.add("D", "두 번 그리기", False, f"node render.js --still {reel.last} 실패")
    else:
        n_diff = int((a[0] != b[0]).any(axis=2).sum()) if a[0].shape == b[0].shape else -1
        rep.add("D", "두 번 그리기", n_diff == 0, f"프레임 {reel.last}을 따로 두 번 그려 다른 화소 {n_diff}개", different_pixels=n_diff)
    now, err = render_events(TMP / "events_now")
    if now is None:
        rep.add("D", "시각표가 지금 소스와 같음", False, f"node render.js --events 실패 {err}")
    else:
        stale = sorted(k for k in reel.d.keys() | now.d.keys() if now.d.get(k) != reel.d.get(k))
        rep.add("D", "시각표가 지금 소스와 같음", not stale,
                "build/events.json이 지금 소스와 다름(" + ", ".join(stale) + ") — node render.js --events 와 렌더를 다시" if stale
                else "build/events.json = 지금 엔진이 내보내는 시각표", stale_keys=stale)
    if a is not None and from_mp4 is not None:
        mad, block = diff_stats(a[0], from_mp4) if a[0].shape == from_mp4.shape else (float("inf"), float("inf"))
        rep.add("D", "영상이 지금 소스와 같음", block <= LIM["fresh_block"],
                f"프레임 {reel.last}: 지금 그린 화면과 MP4의 차이 — 평균 {mad:.2f}, 가장 큰 {BLOCK}px 칸 {block:.1f} "
                f"(기준 ≤ {LIM['fresh_block']}, 압축 손실만 있어야 한다)", mad=mad, block=block)


# ======================================================================== E. 대본 연동
def try_dig(rep: Report, reel: Reel):
    """① 삽질 수를 바꾸면 흙더미 높이·멈추는 날짜·이름표 수가 그만큼 바뀐다."""
    dig = reel.line_for(reel.t("dig_start"))
    n, date = next(p for p in DIG_TRIES if dig is None or dig["args"] != [p[0]])
    text = swap_number(dig["text"], n) if dig else None
    if text is None:
        rep.skip("E", "삽질 수", "대본에 삽질 줄이 없거나 횟수가 숫자로 적혀 있지 않음")
        return
    path, var, err = try_script("dig", [text if ln is dig else ln["text"] for ln in reel.lines])
    if var is None or not var.state["dig"]:
        rep.add("E", "삽질 수 → 시각표", False, f"'{text}' 대본을 그리지 못함 {err}")
        return
    s, d, labels = reel.stage, var.state["dig"], len(var.events("band"))
    want_h, full = n / s["YEAR_DAYS"] * s["FULL_H"], var.full_months(n)
    rep.add("E", "삽질 수 → 시각표", abs(d["h"] - want_h) < 0.01 and var.date_of(n) == date and d["labeled"] == labels == full,
            f"'{text}' → 높이 {d['h']:.2f}px (기대 {n}/{s['YEAR_DAYS']} × {s['FULL_H']} = {want_h:.2f}) · {n}번째 날 = {var.date_of(n)} "
            f"(기대 {date}) · 이름표가 붙는 달 {d['labeled']}개 · band 사건 {labels}건 (기대 {full}개: 끝까지 채운 달만)",
            h=d["h"], want_h=want_h, date=var.date_of(n), labeled=d["labeled"], band_events=labels)
    stills = render_stills(TMP / "dig", [var.after(var.t("dig_end"))], path)
    if stills is None:
        rep.add("E", "흙더미 높이", False, "정지 화면을 그리지 못함")
    else:
        check_mound_top(rep, "E", var, stills[0])


def try_without_say(rep: Report, reel: Reel):
    """② "수고했어" 줄을 지우면 새해로 못 넘어간다: 연도판은 얼음빛 그대로, 흙더미는 흙 그대로, 낚는 말도 그대로."""
    say, rolled = reel.line_for(reel.t("bubble")), reel.line_for(reel.t("year_roll"))
    if say is None or not reel.state["say"]["thanked"] or rolled is None:
        rep.skip("E", "수고했어 삭제", "대본에 \"수고했어\" 한마디나 새해로 넘어가는 줄이 없음")
        return
    path, var, err = try_script("nosay", [ln["text"] for ln in reel.lines if ln["key"] != say["key"]])
    if var is None:
        rep.add("E", "수고했어 삭제 → 시각표", False, f"대본을 그리지 못함 {err}")
        return
    # 그 한마디가 없으면, 새해로 넘기던 줄(과 같은 효과를 부르는 줄)은 전부 실패한다
    want = len(reel.failed_lines()) + sum(ln["key"] == rolled["key"] for ln in reel.lines)
    failed = len(var.failed_lines())
    rep.add("E", "수고했어 삭제 → 시각표",
            var.d["success"] is False and failed == want and var.t("year_roll") is None and var.d["swapT"] is None,
            f"success={var.d['success']} · 실패한 줄 {failed}개 (기대 {want}개) · year_roll {len(var.events('year_roll'))}건 · "
            f"맺는 말로 바뀌는 시각 {var.d['swapT']}", failed=failed, want=want)
    stills = render_stills(TMP / "nosay", [var.hook_frame(), var.last], path)
    if stills is None:
        rep.add("E", "수고했어 삭제 → 마지막 화면", False, "정지 화면을 그리지 못함")
        return
    hook, end = stills
    check_board(rep, "E", var, end, None)
    check_bands(rep, "E", var, end, None)
    changed = var.head_change(hook, end)
    rep.add("E", "낚는 말 유지", changed <= LIM["head_same"],
            f"프레임 {var.hook_frame()}(낚는 말)과 마지막 프레임 사이 제목 띠에서 달라진 화소 {changed:.1%} (기준 ≤ {LIM['head_same']:.1%})",
            changed=changed)
    check_editor(rep, "E", var, end, var.last)


def try_unknown_name(rep: Report, reel: Reel):
    """③ 없는 이름을 맨 앞줄에 넣으면 렌더가 죽지 않고 그 줄에서 NameError가 나며, 낚는 말의 줄 번호가 그 줄로 바뀐다."""
    path, var, err = try_script("unknown", [UNKNOWN_LINE] + [ln["text"] for ln in reel.lines])
    if var is None:
        rep.add("E", "없는 이름 → 시각표", False, f"렌더가 죽음: {err}")
        return
    error = var.lines[0]["error"] or {}
    first_bad = next((ln["idx"] + 1 for ln in reel.lines if not ln["ok"]), None)
    # copy.js에 낚는 말 둘째 줄을 직접 적어 두었으면(줄 번호가 없으면) 번호는 따지지 않는다
    custom = first_bad is not None and reel.hook_number() is None
    follows = custom or (reel.hook_number() == first_bad and var.hook_number() == 1)
    rep.add("E", "없는 이름 → 시각표", error.get("type") == "NameError" and follows,
            f"맨 앞줄 '{UNKNOWN_LINE}' → {error.get('type')}: {error.get('message')} · 낚는 말 '{reel.d['copy']['hook'][1]}' → "
            f"'{var.d['copy']['hook'][1]}' (처음 오류가 나는 줄: {first_bad}번째 → 1번째)", error=error, hook=var.d["copy"]["hook"])
    frame = var.at(var.lines[0]["fireAt"], 0.5)
    stills = render_stills(TMP / "unknown", [var.hook_frame(), frame], path)
    if stills is None:
        rep.add("E", "없는 이름 → 화면", False, "정지 화면을 그리지 못함")
        return
    hook, shot = stills
    mark, bar = var.gutter_mark(shot, var.lines[0]["row"]), var.error_bar(shot, var.lines[0]["row"] + 1)
    redder = var.hook2_redness(shot) - var.hook2_redness(hook)
    rep.add("E", "없는 이름 → 화면", mark == "error" and bar and redder >= LIM["hook_red"],
            f"Enter 0.5초 뒤(프레임 {frame}): 첫 줄 표시 {mark} (기대 error) · 바로 아래 오류 줄 {'있음' if bar else '없음'} · "
            f"낚는 말 둘째 줄 R−G {redder:+.1f} 늘어남 (기준 ≥ {LIM['hook_red']})", mark=mark, error_row=bar, hook_redder=redder)


def try_fireworks(rep: Report, reel: Reel):
    """④ 불꽃 수를 바꾸면 터지는 수가 그만큼 바뀐다."""
    line = reel.line_for(reel.state["fw"]["t"]) if reel.state["fw"] else None
    n = next(k for k in FW_TRIES if line is None or line["args"] != [k])
    text = swap_number(line["text"], n) if line else None
    if text is None:
        rep.skip("E", "불꽃 수", "대본에 불꽃 줄이 없거나 수가 숫자로 적혀 있지 않음")
        return
    _, var, err = try_script("fireworks", [text if ln is line else ln["text"] for ln in reel.lines])
    bursts = len(var.events("fw_burst")) if var else None
    rep.add("E", "불꽃 수", bursts == n, f"'{text}' → fw_burst {bursts}건 (기대 {n}건) {err}".rstrip(), bursts=bursts, want=n)


def try_snow(rep: Report, reel: Reel):
    """⑤ 눈송이 수를 바꾸면 같은 프레임의 하늘에 보이는 눈이 그만큼 달라진다."""
    line, frame = reel.line_for(reel.t("snow_start")), reel.snow_frame()
    n = next(k for k in SNOW_TRIES if line is None or line["args"] != [k])
    text = swap_number(line["text"], n) if line else None
    if text is None:
        rep.skip("E", "눈송이 수", "대본에 눈 줄이 없거나 수가 숫자로 적혀 있지 않음")
        return
    path, var, err = try_script("snow", [text if ln is line else ln["text"] for ln in reel.lines])
    base = render_stills(TMP / "snow_base", [frame])
    changed = render_stills(TMP / "snow", [frame], path) if var else None
    if base is None or changed is None:
        rep.add("E", "눈송이 수", False, f"'{text}' 대본이나 기본 대본을 그리지 못함 {err}")
        return
    counts = {line["args"][0]: reel.flake_pixels(base[0]), n: var.flake_pixels(changed[0])}
    few, many = sorted(counts)
    rep.add("E", "눈송이 수", counts[few] <= counts[many] * LIM["snow_ratio"],
            f"프레임 {frame}의 제목 위 하늘에서 밝은 화소 — '{line['text']}' {counts[line['args'][0]]}개 · '{text}' {counts[n]}개 "
            f"(적은 쪽 ÷ 많은 쪽 {counts[few] / max(counts[many], 1):.2f}, 기준 ≤ {LIM['snow_ratio']})", counts=counts)


def check_script_drives(rep: Report, reel: Reel):
    try_dig(rep, reel)
    try_without_say(rep, reel)
    try_unknown_name(rep, reel)
    try_fireworks(rep, reel)
    try_snow(rep, reel)


# ======================================================================== F. 안전 구역
def check_safe_zones(rep: Report, reel: Reel, pic, plan: dict):
    ed = reel.ed
    typed = [ln for ln in reel.lines if plan[f"typed{ln['idx']}"] is not None]
    shots = [("마지막 프레임", pic("last"))] + [(f"{ln['idx'] + 1}번째 줄을 다 친 프레임", pic(f"typed{ln['idx']}")) for ln in typed]

    # 가장 긴 코드 줄: 다 친 순간(커서 포함) 그 줄 글자의 오른쪽 끝을 화면에서 잰다
    ends = [(reel.text_right(pic(f"typed{ln['idx']}"), *reel.row_box(ln["row"])) or 0, ln) for ln in typed]
    end, longest = max(ends, key=lambda e: e[0])
    card_right = ed["cardX"] + ed["cardW"]
    body = (ed["cardY"] + ed["tabH"], ed["cardY"] + ed["cardH"])
    worst = max((reel.text_right(img, *body) or 0, name) for name, img in shots)
    rep.add("F", "코드 글자 오른쪽 끝", worst[0] <= card_right - LIM["card_margin"],
            f"가장 긴 줄은 {longest['idx'] + 1}번째 '{longest['text']}' (프레임 {plan['typed%d' % longest['idx']]}, 끝 x={end}) · "
            f"창 안 글자 전체의 끝 x={worst[0]} ({worst[1]}) · 창 오른쪽 끝 {card_right}까지 {card_right - worst[0]}px "
            f"(기준 ≥ {LIM['card_margin']})", longest_line=longest["text"], longest_end=end, text_end=worst[0], card_right=card_right)

    reach = max((reel.text_right(img, *SAFE_RIGHT_Y) or 0, name) for name, img in shots)
    rep.add("F", "앱 단추 자리", reach[0] <= SAFE_RIGHT_X,
            f"y {SAFE_RIGHT_Y[0]}~{SAFE_RIGHT_Y[1]}에서 밝은 글자가 닿는 가장 오른쪽 x={reach[0]} ({reach[1]}, 기준 ≤ {SAFE_RIGHT_X} · "
            f"마지막 프레임과 줄마다 다 친 프레임 {len(shots)}장)", rightmost=reach[0])

    # 맨 위: 배치로 본 가장 높은 요소와, 화면에서 잰 가장 밝은 것·가장 큰 밝은 덩어리
    tops = {"제목 윗변": reel.head["y1"] - reel.head["px"] / 2, "코드 창 윗변": ed["cardY"]}
    if reel.state["yearSet"]:
        tops["연도판 윗변"] = reel.stage["BOARD"]["cy"] - reel.stage["BOARD"]["ch"] / 2
    name, y = min(tops.items(), key=lambda kv: kv[1])
    rep.add("F", "맨 위 구역(배치)", y >= SAFE_TOP_Y, f"가장 높이 놓인 요소는 {name} y={y:.0f} (기준 ≥ {SAFE_TOP_Y})", tops=tops)
    # 화면에서: 눈·불꽃처럼 움직이는 것은 3프레임 간격 세 장의 최솟값으로 지우고, 가만히 있는 밝은 것만 남겨 가장 긴 가로 줄을 잰다
    found = []
    for shot, keys in (("첫 장면", ("first", "first3", "first6")), ("끝 장면", ("last6", "last3", "last"))):
        zones = [luma(pic(k)[:SAFE_TOP_Y]) for k in keys]
        length, x, yy = longest_run(np.minimum.reduce(zones) > LIM["solid"])
        py, px = np.unravel_index(int(zones[-1].argmax()), zones[-1].shape)
        found.append(dict(shot=shot, still_run=length, still_x=x, still_y=yy,
                          peak=float(zones[-1].max()), peak_x=int(px), peak_y=int(py)))
    big, peak = max(found, key=lambda f: f["still_run"]), max(found, key=lambda f: f["peak"])
    rep.add("F", "맨 위 구역(화면)", big["still_run"] <= LIM["solid_run"],
            f"y<{SAFE_TOP_Y}에서 가장 밝은 것은 {peak['shot']} ({peak['peak_x']},{peak['peak_y']}) 밝기 {peak['peak']:.0f} · "
            f"가만히 있는 밝은 것의 가장 긴 가로 줄 {big['still_run']}px"
            + (f" ({big['still_x']},{big['still_y']}) {big['shot']}" if big["still_run"] else "")
            + f" (기준 ≤ {LIM['solid_run']}px — 별·눈·불꽃은 통과, 글자·판이면 걸린다)", zones=found)

    # 피드·프로필 격자에서는 가운데 4:5만 보인다: 제목 글자(화면에서 잰 높이)와 연도판(배치)이 그 안에 있는가
    crop_h = reel.w * FEED_RATIO[1] / FEED_RATIO[0]
    feed = ((reel.h - crop_h) / 2, (reel.h + crop_h) / 2)
    spans = {"첫 프레임 제목": reel.head_extent(pic("first")), "마지막 프레임 제목": reel.head_extent(pic("last"))}
    if reel.state["yearSet"]:
        b = reel.stage["BOARD"]
        spans["연도판"] = (b["cy"] - b["ch"] / 2, b["cy"] + b["ch"] / 2)
    inside = all(v is not None and feed[0] <= v[0] and v[1] <= feed[1] for v in spans.values())
    rep.add("F", "피드 4:5 화면", inside,
            " · ".join(f"{k} y " + (f"{v[0]:.0f}~{v[1]:.0f}" if v else "안 보임") for k, v in spans.items())
            + f" — 보이는 범위 y {feed[0]:.0f}~{feed[1]:.0f}", spans=spans, feed=feed)


# ======================================================================== G. 소리
def loudness(mp4: Path) -> tuple[float, float]:
    """ffmpeg ebur128로 (통합 음량 LUFS, 트루 피크 dBTP)."""
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-map", "0:a:0", "-af", "ebur128=peak=true",
               "-f", "null", "-"], text=True).stderr
    summary = log[log.rindex("Summary:"):]
    return (float(re.search(r"I:\s*(-?[\d.]+) LUFS", summary).group(1)),
            float(re.search(r"Peak:\s*(-?[\d.]+) dBFS", summary).group(1)))


def rms_db(pcm: np.ndarray, rate: int, t0: float, t1: float) -> float:
    part = pcm[int(t0 * rate):int(t1 * rate)].astype(np.float64)
    return 20 * math.log10(max(math.sqrt(float(np.mean(part ** 2))), 1e-9))


def check_audio(rep: Report, mp4: Path, reel: Reel, audio: dict | None):
    if audio is None:
        rep.skip("G", "음량·침묵 구간", "소리 줄기 없음(무음 영상)")
        return
    lufs, peak = loudness(mp4)
    lo, hi = LIM["lufs"]
    rep.add("G", "통합 음량", lo <= lufs <= hi, f"{lufs:.1f} LUFS (기준 {lo}~{hi})", lufs=lufs)
    rep.add("G", "트루 피크", peak <= LIM["true_peak"], f"{peak:.1f} dBTP (기준 ≤ {LIM['true_peak']})", true_peak=peak)

    # 침묵 구간: 실패 도장이 찍히고 0.35초 뒤부터 걸린 줄 다음 줄의 첫 글쇠까지. 그 글쇠가 더 먼저 찍히는 박자표라면
    # (음악은 끊기고 타자 소리만 남는 정적) 그 줄의 Enter까지를 잰다 — 타자 소리까지 넣고도 조용해야 한다.
    jam, stamp, failed = reel.t("jam"), reel.t("stamp"), reel.line_for(reel.t("jam"))
    typed = [e["t"] for e in reel.d["events"]
             if failed and e.get("line") == failed["idx"] + 1 and e["type"] in ("key", "space", "enter", "enter_error")]
    start = None if stamp is None else stamp + 0.35
    if not typed or max(typed) <= start:
        rep.skip("G", "도장 뒤 침묵", "걸리는 장면이나 그 뒤에 치는 줄이 없음")
        return
    end, what = (typed[0], "다음 줄 첫 글쇠") if typed[0] > start else (typed[-1], f"다음 줄 Enter(첫 글쇠가 {typed[0]:.2f}초로 더 먼저라 타자 소리 포함)")
    rate = int(SPEC["audio"][1])
    raw = run(["ffmpeg", "-v", "error", "-i", mp4, "-map", "0:a:0", "-ac", "2", "-ar", rate, "-f", "f32le", "-"], check=True).stdout
    pcm = np.frombuffer(raw, np.float32).reshape(-1, 2)
    quiet = rms_db(pcm, rate, start, end)
    loud = rms_db(pcm, rate, max(0.0, jam - 2.0), jam)
    rep.add("G", "도장 뒤 침묵", loud - quiet >= LIM["silence_db"],
            f"도장 0.35초 뒤 {start:.2f}초 ~ {what} {end:.2f}초 RMS {quiet:.1f} dB · 걸리기 전 2초 {loud:.1f} dB → 차이 {loud - quiet:.1f} dB "
            f"(기준 ≥ {LIM['silence_db']})", quiet_db=quiet, loud_db=loud, window=(start, end))


# ======================================================================== 확인용 그림
def label_font(px: int) -> tuple[ImageFont.ImageFont, bool]:
    """(글꼴, 한글을 쓸 수 있는가)"""
    try:
        return ImageFont.truetype(str(LABEL_FONT), px), True
    except OSError:
        return ImageFont.load_default(), False


def tiles(shots: list[tuple[str, np.ndarray]], tile_w: int, out: Path):
    """그림을 옆으로 나란히 붙이고 위에 이름을 적는다."""
    tile_h, band = round(tile_w * shots[0][1].shape[0] / shots[0][1].shape[1]), 46
    font, _ = label_font(26)
    sheet = Image.new("RGB", (tile_w * len(shots), tile_h + band), (12, 16, 34))
    draw = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(shots):
        sheet.paste(Image.fromarray(img).resize((tile_w, tile_h), Image.LANCZOS), (i * tile_w, band))
        draw.text((i * tile_w + 10, 9), label, font=font, fill=(238, 243, 255))
    sheet.save(out, optimize=True)


def write_review_images(reel: Reel, frames: dict[int, np.ndarray]) -> list[str]:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    for old in FRAMES_DIR.glob("rep_*.png"):
        old.unlink()
    korean = label_font(26)[1]
    shots, written = [], []
    for i, (slug, text, n) in enumerate(representative(reel), 1):
        path = FRAMES_DIR / f"rep_{i}_{slug}.png"
        Image.fromarray(frames[n]).save(path, optimize=True)
        written.append(path.name)
        shots.append((f"{reel.sec(n):.2f}초 {text}" if korean else f"{reel.sec(n):.2f}s {slug}", frames[n]))
    tiles(shots, 360, FRAMES_DIR / "representative_sheet.png")
    tiles([(f"마지막 프레임 {reel.last}" if korean else f"last {reel.last}", frames[reel.last]),
           ("첫 프레임 0" if korean else "first 0", frames[0])], 540, FRAMES_DIR / "loop_check.png")
    return written + ["representative_sheet.png", "loop_check.png"]


# ======================================================================== 실행
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="새해 코드 릴스 자동 검수")
    ap.add_argument("--skip-script-tests", action="store_true", help="대본을 바꿔 그려 보는 E 검사를 건너뛴다(node를 여러 번 띄운다)")
    ap.add_argument("--video", type=Path, help="검사할 영상(기본: ../newyear_code_reel.mp4, 없으면 무음본)")
    args = ap.parse_args(argv)
    mp4 = args.video or next((p for p in (ROOT / "newyear_code_reel.mp4", ROOT / "newyear_code_reel_silent.mp4") if p.exists()), None)
    if mp4 is None or not mp4.exists():
        print("검사할 영상이 없습니다. 먼저 node render.js 로 만드세요.")
        return 1
    if not EVENTS.exists():
        print(f"{EVENTS} 가 없습니다. 먼저 node render.js --events 를 돌리세요.")
        return 1
    missing = [tool for tool in ("ffmpeg", "ffprobe", "node") if shutil.which(tool) is None]
    if missing:
        print("필요한 프로그램이 없습니다: " + ", ".join(missing))
        return 1
    probed = probe(mp4)
    if probed is None:
        print(f"{mp4} 를 읽을 수 없습니다(렌더가 덜 끝났거나 깨진 파일). 렌더가 끝난 뒤 다시 돌리세요.")
        return 1
    video, audio = probed
    reel = Reel.load(EVENTS)
    shutil.rmtree(TMP, ignore_errors=True)
    rep = Report()
    print(f"영상: {mp4} ({mp4.stat().st_size / 1e6:.2f} MB) · 시각표: {EVENTS}")

    check_container(rep, mp4, reel, video, audio)
    plan = moments(reel)
    wanted = {n for n in plan.values() if n is not None} | {n for _, _, n in representative(reel)}
    readable = (video["width"], video["height"]) == (reel.w, reel.h) and int(video["nb_read_frames"]) > max(wanted)
    frames = decode(mp4, wanted, reel.w, reel.h) if readable else {}

    def pic(name: str) -> np.ndarray | None:
        return frames.get(plan.get(name))

    if frames:
        print(f"  MP4에서 프레임 {len(frames)}장을 풀어 잽니다.", flush=True)
        check_story(rep, reel, pic, plan)
        check_loop(rep, reel, pic)
    else:
        rep.add("B", "프레임 풀기", False, "화면 크기나 프레임 수가 시각표와 달라 화면 검사(B·C·F)를 할 수 없음")
    check_determinism(rep, reel, pic("last"))
    if args.skip_script_tests:
        rep.skip("E", "대본 바꿔 그리기", "--skip-script-tests")
    else:
        check_script_drives(rep, reel)
    images = []
    if frames:
        check_safe_zones(rep, reel, pic, plan)
        images = write_review_images(reel, frames)
    check_audio(rep, mp4, reel, audio)
    shutil.rmtree(TMP, ignore_errors=True)

    failed = rep.failed()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / "verify_report.json").write_text(json.dumps(dict(
        file=mp4.name, events=str(EVENTS.relative_to(ROOT)), script=reel.d["script"], video=video, audio=audio,
        frames={k: v for k, v in plan.items() if v is not None}, limits=LIM, checks=rep.rows, images=images,
        all_ok=not failed), ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    rep.table()
    done = sum(r["ok"] is not None for r in rep.rows)
    print(f"전체: {'통과' if not failed else '실패'} — 검사 {done}개 중 {done - len(failed)}개 통과, {len(failed)}개 실패"
          f" · 보고서 {FRAMES_DIR / 'verify_report.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
