#!/usr/bin/env python3
"""완성 릴스 자동 검수 — 규격·줄거리·이음매·결정성·대본 연동·안전 구역·소리.

    python3 verify.py [--skip-script-tests] [--video 영상.mp4]

영상을 정하지 않으면 ../newyear_code_reel.mp4(소리 포함)가 있을 때 그것을, 없으면 무음본을 본다.
시각과 화면 자리는 전부 build/events.json(node render.js --events)에서 읽는다. 이 파일에 적어 둔 숫자는
인스타그램 규격, 앱 화면이 덮는 자리, 대본 머리말의 약속, 판정 기준뿐이다. 시각표에 없는 사건의 검사는 건너뛴다.

이번 판의 화면 — 타자는 없다. 대본 줄은 박자표의 시각(fireAt)에 한 줄씩 실행된다.
  왼쪽 무대  그림판에 그린 장면을 매 프레임 색 글자(ASCII)로 바꿔 찍는다(새해 전 8px 칸, 삽질러 둘레 6px 칸,
             2027이 잠기면 연도판 가운데서 고리가 퍼지며 5px 칸 — 해상도 업). 연도판도 글자다.
             읽어야 하는 것(달 이름표·계수판·날짜·확인란·카운트다운·도장·말풍선·마지막 알약)만 또렷하게 얹는다.
             글자 화면은 칸 하나하나의 색이 고르지 않으므로, 색은 '밝은 글자 화소의 평균'이나 '칸 바탕까지 넣은 줄 평균'으로 잰다.
  오른쪽     디버거 세 칸 — A 2026.py(줄마다 ✓·✕, 실행 막대) · B newyear.js(막대가 도는 실제 코드, 머리 오른쪽에 지금 값) ·
             C 터미널(줄별 결과, 금색 상태 줄, 맨 아래 frame 줄). ✓는 그 줄이 '끝난' 뒤에 뜬다.

  A 컨테이너   ffprobe 규격, 프레임 수, bt709 꼬리표, moov가 mdat 앞(faststart), 소리 규격
  B 줄거리     MP4를 다시 풀어 낸 프레임에서 잰다 — 연도판 색(얼음빛 → 금빛)과 걸림, 확인란(기본 → 빨강 → 금),
               흙더미 높이와 색, 실패한 동안 빠지는 색, 해상도 업(글자 줄이 촘촘해짐), 2026.py의 ✓·✕와 실행 막대,
               ✓가 줄이 끝난 뒤에 뜨는지(오래 도는 줄의 한가운데·끝), 터미널 줄 차례(시각표로 만든 차례와 금색 줄 자리),
               newyear.js 창이 도는지, 제목(낚는 말이 빨개짐 · 맺는 말로 교체), 불꽃 수·순서·밝기
  C 이음매     마지막 프레임 → 첫 프레임 차이(제목 띠 제외)를 이웃 프레임 차이와 견준다(평균, 그리고 120px 칸마다 같은 칸끼리)
  D 결정성     같은 프레임을 node로 두 번 따로 그려 화소가 완전히 같은지, 시각표·영상이 지금 소스와 맞는지
  E 대본 연동  대본을 바꿔 그리면 영상이 바뀌는지(삽질 수, "수고했어" 삭제, 없는 이름, 불꽃 수, 눈송이 수)
               — node를 여러 번 띄운다. --skip-script-tests로 생략
  F 안전 구역  앱 단추 자리(오른쪽 아래)·화면 맨 위·피드(4:5)로 잘리는 자리에 글자가 걸리지 않는지, 창 글자가 창 안에 있는지
               — 0.5초마다와 줄마다 실행 직후 프레임에서. newyear.js 창 머리의 위치 글자와 지금 값이 겹치지 않는지 — 모든 프레임의
               머리 띠에서, 색이 아니라 자리로(값 없는 프레임을 위치 글자 기준으로 삼는다)
  G 소리       통합 음량·트루 피크(ebur128), 도장 뒤 침묵 구간, 효과음판(../newyear_code_reel_fx.mp4)의 규격·길이

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
FX_VIDEO = ROOT / "newyear_code_reel_fx.mp4"  # 가락을 뺀 효과음판(audio.py가 함께 만든다)
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

# ── 판정 기준. 괄호 안은 기본 대본으로 잰 값(2026-11-21, 글자 화면판) — 화면을 조금 다듬어도 넘지 않게 여유를 뒀다 ──
LIM = dict(
    lit=100,              # 글자 화면에서 '밝은 글자 화소'로 치는 밝기(휘도 0..255). 칸 바탕은 40 아래
    board_ice=-5.0,       # 연도판 상자 안 밝은 글자의 R−B 평균: 얼음빛이면 이보다 작다 (−15)
    board_gold=25.0,      #                                    금빛이면 이보다 크다 (+55)
    jam_red=5.0,          # 걸린 뒤 연도판 상자 전체(글자+칸 바탕)의 붉은 정도 R−(G+B)/2 가 이만큼 넘게 는다 (−8.6 → +3.2, +11.8)
    ink=120,              # 확인란·제목 글자로 치는 밝기
    tag_px=200,           # 확인란으로 치는 최소 밝은 화소 수 (820~1900) — 글자 상자를 못 찾았을 때만
    tag_label_px=60,      # 확인란 글자 '수고했어' 상자 위쪽 65%의 밝은 화소 수 하한 (기본 ~470 · 빨강 ~490 · 금 ~600, 도장만 남기면 0)
    tag_tint=40.0,        # 빨강: R−max(G,B), 금: min(R,G)−B 가 이보다 크다 (빨강 +104, 금 +74 · 서로 반대쪽은 +27 아래)
    tag_cool=15.0,        # 기본(회청색): B−R 이 이보다 크다 (+34~38)
    mound_px=10,          # 흙더미 윗변 오차(px) — 글자 한 줄이 14px이라 칸 경계만큼 넉넉히 (+2)
    mound_warm=0.0,       # 흙더미로 치는 줄: 글자와 칸 바탕까지 넣은 R−B 평균이 이보다 크다 (흙 +1~17, 밤하늘 −16)
    mound_run=6,          # 그런 줄이 위에서부터 이만큼(px) 이어지는 첫 자리가 윗변
    gold_tint=0.33,       # 달 띠 옆구리의 '파랑이 빠진 정도' (R−B)/R 중앙값: 흙 0.10~0.16, 금 0.49~0.65
    chill_ratio=0.75,     # 실패한 동안 무대 배경 채도 ÷ 걸리기 전 1초 채도의 상한 (0.58)
    res_gain=1.3,         # 해상도 업: 고리가 지나간 뒤 100px에 든 글자 줄 수 ÷ 그 전 (6.9줄 → 11.1줄 = 1.61)
    mark_px=30,           # 실행 표시(✓·✕)로 치는 최소 화소 수 (✓ 115, ✕ 152, 금빛 막대 위 주석 줄 0)
    mark_tint=12,         # 초록·빨강으로 치는 색 우세: 한 채널이 나머지보다 이만큼 큼
    bar_lit=60,           # 실행 막대(창 왼쪽 7px 띠)로 치는 밝기 (막대 136~206, 창 바탕 17)
    bar_tint=40.0,        # 막대·글자 색을 가르는 우세 (금 min(R,G)−B +87, 빨강 R−max(G,B) +126, 보라 B−R +108)
    gold_px=40,           # 터미널 한 줄을 금색 줄로 치는 금색 화소 수 (상태 줄 141, 다른 줄 0)
    pane_change=0.001,    # newyear.js 창: 0.25초 사이 크게 달라진 화소 비율의 하한 (막대가 한 줄 옮겨 가면 11%, 값만 바뀌어도 0.3%)
    head_change=0.02,     # 제목이 바뀌면 글자 띠의 이 비율 넘게 화소가 크게 달라진다 (13.8%)
    head_same=0.005,      # 제목이 그대로면 이 비율 아래 (0.0%)
    hook_red=60.0,        # 낚는 말 둘째 줄 글자의 R−G 가 오류 순간 이만큼 넘게 는다 (노랑 +28 → 빨강 +142)
    fw_glow=2.0,          # 첫 불꽃이 터진 기둥(x ± 크기/2)의 하늘 평균 밝기가 터지기 0.1초 전 → 0.1초 뒤 이만큼 넘게 는다 (+3.9)
    fw_focus=2.0,         #   그 기둥에서 크게 밝아진 화소가 기둥당 나머지 하늘의 이 배수 넘게 많다 (5.7배)
    loop_ratio=2.0,       # 이음매 차이 ≤ 이웃 프레임 차이 × loop_ratio + 여유
    loop_floor=0.5,       #   평균 차이에 주는 여유
    loop_block_floor=5.0, #   가장 큰 칸 차이에 주는 여유
    fresh_block=12.0,     # 지금 그린 화면과 MP4의 칸별 차이 상한: 압축 손실뿐이면 몇 안 되고, 옛 렌더면 수십
    snow_ratio=0.5,       # 눈송이를 줄인 쪽의 제목 위 하늘 밝은 글자 화소 수 ÷ 많은 쪽 (30송이 99 ÷ 300송이 372 = 0.27 — 별 글자가 함께 세어진다)
    bright=90,            # 편집기·제목 글자로 치는 밝기. 창 바탕은 17쯤
    text_contrast=60,     # 편집기 '글자': 그 가로줄의 가운데값(창 바탕이나 실행 막대 바탕)보다 이만큼 밝은 화소 — 막대 바탕은 빠진다
    solid=160,            # '밝은 덩어리'(눈송이·별·글자 속)로 치는 밝기
    solid_run=20,         # 맨 위에 가만히 있는 밝은 가로 줄의 최대 길이(px). 별·불꽃 잔불 글자는 짧고, 제목 글자면 30 이상
    card_margin=6,        # 창 글자 끝과 창 오른쪽 끝 사이 최소 여백(px) (newyear.js 접힌 줄 11, 머리 값 16)
    crumb_gap=8,          # newyear.js 창 머리: 위치 글자(C['…'])의 끝과 오른쪽 지금 값의 시작 사이 최소 틈(px) (겹치지 않는 값 18~213, 겹친 값 −30·−19)
    lufs=(-16.0, -12.0),  # 통합 음량 범위
    true_peak=-1.0,       # 트루 피크 상한(dBTP)
    silence_db=15.0,      # 침묵 구간은 걸리기 직전 2초보다 이만큼 조용해야 한다
)
BLOCK = 120                        # 차이를 견줄 때 화면을 나누는 칸 크기(px)
WINDOW_SHOTS = 5                   # 구간 평균을 낼 때 그 구간에서 고르게 뽑는 프레임 수
LOOP_PAIRS = 5                     # 이음매를 견주는 끝 쪽 이웃 프레임 쌍의 수(가장 큰 칸 차이의 중앙값을 쓴다)
SAMPLE_STEP = 0.5                  # 안전 구역은 이 간격(초)마다 + 줄마다 실행 직후 프레임에서 본다

GROUPS = dict(A="컨테이너", B="줄거리", C="이음매", D="결정성", E="대본 연동", F="안전 구역", G="소리")


# ======================================================================== 기본 도구
def warmth(px: np.ndarray) -> np.ndarray:
    """따뜻한 정도 R−B. 밤하늘·얼음빛은 음수, 흙은 양수, 금은 크게 양수."""
    return px[..., 0].astype(np.int16) - px[..., 2]


def luma(px: np.ndarray) -> np.ndarray:
    return px[..., 0] * 0.2126 + px[..., 1] * 0.7152 + px[..., 2] * 0.0722


def ink(patch: np.ndarray, level: float) -> tuple[int, np.ndarray]:
    """밝기가 level을 넘는 화소(글자·선)의 수와 평균 색(R, G, B). 하나도 없으면 (0, 검정)."""
    px = patch.reshape(-1, 3)
    lit = px[luma(px) > level]
    return len(lit), lit.mean(0) if len(lit) else np.zeros(3)


def tint_counts(px: np.ndarray, level: float) -> tuple[int, int]:
    """밝기 level을 넘는 화소 가운데 (초록이 우세한 수, 빨강이 우세한 수). 어두운 막대 바탕의 붉은 기는 세지 않는다."""
    p = px.astype(np.int16)
    r, g, b = p[..., 0], p[..., 1], p[..., 2]
    lit = luma(p) > level
    green = lit & (g - np.maximum(r, b) >= LIM["mark_tint"])
    red = lit & (r - np.maximum(g, b) >= LIM["mark_tint"])
    return int(green.sum()), int(red.sum())


def color_name(rgb) -> str:
    """막대·글자의 평균 색 → '금' | '빨강' | '초록' | '보라' | '?'."""
    r, g, b = (float(c) for c in rgb)
    if min(r, g) - b >= LIM["bar_tint"]:
        return "금"
    if r - max(g, b) >= LIM["bar_tint"]:
        return "빨강"
    if g - max(r, b) >= LIM["bar_tint"]:
        return "초록"
    if b - r >= LIM["bar_tint"]:
        return "보라"
    return "?"


def longest_run(mask: np.ndarray) -> tuple[int, int, int]:
    """가로로 이어진 True 중 가장 긴 것 → (길이, 시작 x, y). 없으면 (0, 0, 0)."""
    edge = np.diff(np.pad(mask, ((0, 0), (1, 1))).astype(np.int8), axis=1)
    start, end = np.argwhere(edge == 1), np.argwhere(edge == -1)      # 줄 순서대로 짝이 맞는다
    if not len(start):
        return 0, 0, 0
    i = int(np.argmax(end[:, 1] - start[:, 1]))
    return int(end[i, 1] - start[i, 1]), int(start[i, 1]), int(start[i, 0])


def cell_diff(a: np.ndarray, b: np.ndarray) -> tuple[float, np.ndarray]:
    """두 그림의 (평균 절대 차이, BLOCK px 칸마다 평균 낸 차이의 표)."""
    d = np.abs(a.astype(np.int16) - b).mean(axis=2)
    rows, cols = d.shape[0] // BLOCK, d.shape[1] // BLOCK
    return float(d.mean()), d[:rows * BLOCK, :cols * BLOCK].reshape(rows, BLOCK, cols, BLOCK).mean(axis=(1, 3))


def diff_stats(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """두 그림의 (평균 절대 차이, BLOCK px 칸마다 평균 낸 차이 가운데 가장 큰 값).
    평균은 화면 전체가 달라졌는지를, 가장 큰 칸은 한 군데만 튀는지를 본다."""
    mean, cells = cell_diff(a, b)
    return mean, float(cells.max())


def changed_share(a: np.ndarray, b: np.ndarray, level: int = 48) -> float:
    """두 조각에서 어느 채널이든 level 넘게 달라진 화소의 비율."""
    return float((np.abs(a.astype(np.int16) - b).max(axis=2) > level).mean())


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
        self.lines, self.state = data["lines"], data["state"]
        lay = data["layout"]
        self.split, self.head, self.ed, self.stage = lay["split"], lay["head"], lay["editor"], lay["stage"]
        self.row_a = lay["rowA"]                      # 2026.py에서 줄마다 글자 밑선 y
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
        """첫머리 되감기가 끝나고 대본이 처음부터 돌기 시작하는 프레임 — 위에는 낚는 말이 그대로 떠 있다."""
        cold = self.d["coldOpen"]
        return self.after(cold.get("stageRewindEnd", cold["rewindEnd"]))

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

    def fired_lines(self, now: float) -> list[dict]:
        """시각 now까지 실행된(Enter가 떨어진) 줄."""
        return [ln for ln in self.lines if ln["fireAt"] <= now + 1e-6]

    def line_for(self, t: float | None) -> dict | None:
        """시각 t의 효과를 부른 대본 줄: 실행 시각(fireAt)이 t였거나, 그 줄에서 날아간 빛(courier)이 t에 무대에 닿은 줄.
        효과 이름(key)은 엔진을 고치면 바뀔 수 있으므로 시각으로 찾는다."""
        if t is None:
            return None
        for ln in self.lines:
            hits = [ln["fireAt"]] + [e["t"] + e["dur"] for e in self.events("courier") if abs(e["t"] - ln["fireAt"]) < 1e-3]
            if any(abs(h - t) < 1e-3 for h in hits):
                return ln
        return None

    def done_t(self, ln: dict) -> float | None:
        """그 줄이 '끝나는' 시각 — 2026.py의 ✓와 터미널 결과 줄은 이때 찍힌다(엔진 editor.js의 doneT와 같은 셈을 시각표로).
        실패한 줄은 실행 시각(✕는 바로 뜬다). 성공한 줄은 효과가 끝나는 사건으로 정한다:
          삽질 → dig_end · 카운트다운 → 마지막 count + 한 박(count 사이 간격) · 새해 year += → 2027이 잠기는 때(state.yearUp.lock) ·
          불꽃 → 마지막으로 쏜 불꽃이 터지는 때(마지막 fw_launch의 t + rise) · 그 밖 → 실행 0.25초 뒤.
        주석·빈 줄(silent)은 표시가 없으므로 None. 끝나는 때를 시각표로 알 수 없으면(카운트다운 한 박뿐인 대본 등) None."""
        if ln["silent"]:
            return None
        t = ln["fireAt"]
        if not ln["ok"]:
            return t
        st, near = self.state, lambda e: e["t"] >= t - 1e-3
        if ln["key"] == "삽질러.삽질" and st["dig"]:
            return next((e["t"] for e in self.events("dig_end") if near(e)), None)
        if ln["key"] == "countdown" and st["count"]:
            beats = [e["t"] for e in self.events("count") if near(e)]
            if len(beats) < 2:
                return None
            return beats[0] + len(beats) * (beats[-1] - beats[0]) / (len(beats) - 1)
        if ln["key"] == "year +=" and st["yearUp"] and abs(st["yearUp"]["fireT"] - t) < 1e-3:
            return st["yearUp"]["lock"]
        if ln["key"] == "fireworks" and self.events("fw_launch"):
            last = max(self.events("fw_launch"), key=lambda e: e["t"])
            return last["t"] + last["rise"]
        return t + 0.25

    def term_rows(self, now: float) -> list[dict]:
        """시각 now에 터미널에 보여야 하는 결과 줄(위에서부터, 많아야 5줄) → [dict(t, kind, line)].
        엔진(editor.js)과 같은 차례로 시각표에서 만든다: 프롬프트(되감기 끝) · 줄마다 ✓(끝나는 때) 또는 ✕(+0.2초)와 'at …'(+0.28초) ·
        첫 예외 뒤 '⏸ 예외에서 멈춤'(+0.45초) · 고치는 "수고했어" 줄이 들어오면 '▶ 계속' · 새해가 잠기면 '↻ 파일 이름' ·
        금색 상태 줄(status.t). kind: prompt | ok | error | at | pause | resume | rename | status. 금색으로 찍히는 것은 pause와 status."""
        st, rows = self.state, []
        rows.append(dict(t=self.d["coldOpen"]["rewindEnd"], kind="prompt", line=None))
        for ln in self.lines:
            if ln["silent"]:
                continue
            if ln["ok"]:
                done = self.done_t(ln)
                rows.append(dict(t=done if done is not None else ln["fireAt"] + 0.25, kind="ok", line=ln["idx"]))
            else:
                rows += [dict(t=ln["fireAt"] + 0.2, kind="error", line=ln["idx"]), dict(t=ln["fireAt"] + 0.28, kind="at", line=ln["idx"])]
        first_fail = next((ln for ln in self.lines if not ln["ok"] and not ln["silent"]), None)
        if first_fail:
            rows.append(dict(t=first_fail["fireAt"] + 0.45, kind="pause", line=first_fail["idx"]))
            say = st["say"]
            if say and say["thanked"] and say["fireT"] > first_fail["fireAt"]:
                rows.append(dict(t=say["fireT"], kind="resume", line=None))
        if st["yearUp"]:
            rows.append(dict(t=st["yearUp"]["lock"] + 0.05, kind="rename", line=None))
        if self.d.get("status"):
            rows.append(dict(t=self.d["status"]["t"], kind="status", line=None))
        rows.sort(key=lambda r: r["t"])
        return [r for r in rows if r["t"] <= now][-5:]

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

    # ── 연도판(글자로 찍힌다) ──
    def board_box(self, img: np.ndarray) -> np.ndarray:
        """연도판 n칸을 통째로 덮는 상자 안의 화소(칸 사이 틈 포함). 칸 자리는 엔진과 같은 규칙
        (무대 가운데 CX에 n칸을 가운데 정렬)으로 BOARD 치수에서 계산한다. 판도 이제 글자로 찍히므로 상자 하나로 본다."""
        b, n = self.stage["BOARD"], len(str(self.state["yearSet"]["v"]))
        total = n * b["cw"] + (n - 1) * b["gap"]
        x0 = self.stage["CX"] - total / 2
        return img[round(b["cy"] - b["ch"] / 2):round(b["cy"] + b["ch"] / 2), round(x0):round(x0 + total)].reshape(-1, 3)

    def board_tone(self, img: np.ndarray) -> tuple[float, int]:
        """연도판 상자 안 밝은 글자 화소의 (R−B 평균, 그 화소 수): 얼음빛 −15쯤, 금빛 +55쯤."""
        n, (r, _, b) = ink(self.board_box(img), LIM["lit"])
        return float(r - b), n

    def board_redness(self, img: np.ndarray) -> float:
        """연도판 상자 전체(글자 + 칸 바탕)의 붉은 정도 R−(G+B)/2."""
        r, g, b = self.board_box(img).astype(np.float64).mean(0)
        return float(r - (g + b) / 2)

    def tag_area(self) -> tuple[int, int, int, int]:
        """확인란을 찾는 자리 (y0, y1, x0, x1): 연도판 아랫변에서 칸 간격만큼 띄운 곳부터 칸 높이의 0.4배 아래까지,
        가운데에서 좌우로 칸 폭의 0.75배."""
        b, cx = self.stage["BOARD"], self.stage["CX"]
        bottom = b["cy"] + b["ch"] / 2
        return round(bottom + b["gap"]), round(bottom + b["ch"] * 0.4), round(cx - b["cw"] * 0.75), round(cx + b["cw"] * 0.75)

    def tag_label(self, plain: np.ndarray) -> tuple[int, int, int, int] | None:
        """아무것도 가리지 않은 프레임(plain)에서 확인란 글자 '수고했어'가 차지하는 상자 (y0, y1, x0, x1).
        기본 상태에서는 테두리가 어둡고 글자만 밝다(휘도 > ink) — 그 밝은 화소의 범위다. 없으면 None."""
        y0, y1, x0, x1 = self.tag_area()
        lit = luma(plain[y0:y1, x0:x1].astype(np.float64)) > LIM["ink"]
        per_row = lit.sum(axis=1)
        rows = np.flatnonzero(per_row >= max(3, 0.15 * per_row.max()))       # 글자 줄만(네모 칸 모서리 같은 낱 화소는 빼고)
        if not len(rows):
            return None
        cols = np.flatnonzero(lit[rows[0]:rows[-1] + 1].sum(axis=0) >= 2)
        if not len(cols):
            return None
        return y0 + int(rows[0]), y0 + int(rows[-1]) + 1, x0 + int(cols[0]), x0 + int(cols[-1]) + 1

    def tag_state(self, img: np.ndarray, label: tuple[int, int, int, int] | None = None) -> tuple[str, int, np.ndarray]:
        """연도판 바로 밑 확인란('수고했어')의 상태 → ('기본'|'빨강'|'금'|'없음'|'?', 밝은 화소 수, 그 평균 색).
        확인란은 글자로 바꾸지 않고 얹으므로 밝은 화소의 평균 색으로 가른다. label(tag_label)을 주면 그 글자 상자의
        위쪽 65%만 본다 — 실패하는 동안 그 밑으로 빨간 도장 테두리가 지나가므로(도장 윗변은 글자 아랫변 언저리),
        도장만 남고 확인란이 사라져도 '빨강'으로 읽히지 않게. 상자 왼쪽의 네모 칸과 테두리도 빠진다."""
        if label is None:
            y0, y1, x0, x1 = self.tag_area()
            least = LIM["tag_px"]
        else:
            y0, y1, x0, x1 = label
            y1 = y0 + round((y1 - y0) * 0.65)
            least = LIM["tag_label_px"]
        n, (r, g, bl) = ink(img[y0:y1, x0:x1], LIM["ink"])
        if n < least:
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
        """흙더미 윗변의 y. 삽질러는 흙더미 윗면 가운데에서 오른쪽(CX+22 언저리)에 서므로, 윗변 왼쪽 띠
        (CX − 윗변 반폭의 0.9배 ~ 0.35배) 기둥들을 위에서 아래로 훑어 '따뜻한 줄'이 mound_run px 이어지는 첫 자리를 찾는다.
        글자 화면은 칸 바탕에도 그 칸의 색을 옅게 깔아서, 글자 사이 틈까지 흙(따뜻)과 밤하늘(차가움)이 갈린다.
        훑기는 가장 높이 쌓인 흙더미보다 60px 위에서 시작한다(그 위의 연도판·확인란은 보지 않는다). 흙더미가 없으면 None."""
        s = self.stage
        x0, x1 = round(s["CX"] - s["TOP_HALF"] * 0.9), round(s["CX"] - s["TOP_HALF"] * 0.35)
        y_from = max(0, round(s["GROUND"] - s["FULL_H"] - 60))
        warm = warmth(img[y_from:s["GROUND"], x0:x1]).mean(axis=1) > LIM["mound_warm"]
        n = LIM["mound_run"]
        for i in range(len(warm) - n + 1):
            if warm[i:i + n].all():
                return y_from + i
        return None

    def band_spans(self) -> list[tuple[float, float]]:
        """쌓인 달 띠마다 (아래 높이, 위 높이) px. 달마다 두께가 다르다(BAND_TOP = 그 달이 끝나는 높이)."""
        h, spans, bottom = self.state["dig"]["h"], [], 0.0
        for top in self.stage["BAND_TOP"]:
            if bottom < h - 0.5:
                spans.append((bottom, min(top, h)))
            bottom = top
        return spans

    def band_tints(self, img: np.ndarray) -> list[float]:
        """달 띠마다 '파랑이 빠진 정도' (R−B)/R 의 중앙값(글자와 칸 바탕 전부): 흙은 0.1쯤, 금은 0.5~0.65.
        밝기와 무관해서 글자 흙더미를 같은 잣대로 잰다. 달 이름표는 가운데에서 왼쪽으로 비켜 있으므로(윗띠에서는
        왼쪽 옆구리까지 덮는다) 오른쪽 옆구리(반폭의 0.55~0.92배)만, 눈이 덮는 위쪽 30%와 아래 3px은 빼고 본다."""
        s, tints = self.stage, []
        for bottom, top in self.band_spans():
            y0, y1 = round(s["GROUND"] - top + (top - bottom) * 0.3), round(s["GROUND"] - bottom) - 3
            if y1 - y0 < 4:
                continue
            half = self.mound_half(s["GROUND"] - top)
            side = img[y0:y1, s["CX"] + round(half * 0.55):s["CX"] + round(half * 0.92)].reshape(-1, 3).astype(np.float64)
            red = np.maximum(side[:, 0], 1.0)
            tints.append(float(np.median((red - side[:, 2]) / red)))
        return tints

    def band_kinds(self, img: np.ndarray) -> list[str]:
        """달 띠마다 '흙' 또는 '금'."""
        return ["금" if tint > LIM["gold_tint"] else "흙" for tint in self.band_tints(img)]

    # ── 무대 전체 ──
    def scenery_chroma(self, img: np.ndarray) -> float:
        """무대 배경(흙더미 윗변 아래의 흙더미·눈밭)의 평균 채도 max(R,G,B)−min(R,G,B) — 캔버스의 'saturation' 합성이
        쓰는 바로 그 정의. 또렷하게 얹는 달 이름표·치수선을 피해 가운데에서 윗변 반폭의 절반만큼 오른쪽부터 본다.
        그 위쪽은 일부러 선명하게 얹는 연도판·도장·계수판이 있어서 뺀다."""
        s = self.stage
        top = round(s["GROUND"] - (self.state["dig"]["h"] if self.state["dig"] else 0))
        px = img[top:, round(s["CX"] + s["TOP_HALF"] / 2):self.split].astype(np.int16)
        return float((px.max(axis=2) - px.min(axis=2)).mean())

    def glyph_rows(self, img: np.ndarray) -> tuple[float, float]:
        """글자 화면의 가로줄 촘촘함 → (줄 간격 px, 100px에 든 글자 줄 수). 흙더미 아래쪽 오른 옆구리 띠
        (높이 FULL_H의 25~50%, 가운데에서 윗변 반폭의 절반 ~ 그 높이의 반폭) — 글자가 빽빽하고 또렷하게 얹는 것이 없는 자리 —
        의 줄별 평균 밝기에서 가장 센 주기(밝기 봉우리 사이 간격)를 잰다."""
        s = self.stage
        y0, y1 = round(s["GROUND"] - s["FULL_H"] * 0.5), round(s["GROUND"] - s["FULL_H"] * 0.25)
        x0, x1 = round(s["CX"] + s["TOP_HALF"] / 2), round(s["CX"] + self.mound_half(y0) - 4)
        prof = luma(img[y0:y1, x0:x1].astype(np.float64)).mean(axis=1)
        prof = (prof - prof.mean()) * np.hanning(len(prof))
        n = 4096
        spec, freq = np.abs(np.fft.rfft(prof, n=n)), np.fft.rfftfreq(n)
        band = np.flatnonzero((freq >= 1 / 40) & (freq <= 1 / 4))      # 줄 간격 4~40px 사이에서
        period = 1 / freq[band[np.argmax(spec[band])]]
        return float(period), float(100 / period)

    def sky_glow(self, before: np.ndarray, after: np.ndarray, x: float, half: float) -> tuple[float, float, float]:
        """무대 하늘(흙더미 윗변 20px 위까지, 제목 띠 제외)에서 두 프레임 사이 밝아진 정도 →
        (x±half 기둥의 평균 밝기 증가, 그 기둥에서 크게(휘도 +60) 밝아진 화소의 기둥당 수 ÷ 나머지 하늘의 기둥당 수, 그 기둥의 화소 수).
        글자 화면은 눈·별 글자가 프레임마다 깜박이고 새해 빛이 하늘 전체를 밝히므로, 터진 자리에 모이는지를 함께 본다."""
        y0, y1 = self.head_rows()
        top = self.stage["GROUND"] - (self.state["dig"]["h"] if self.state["dig"] else 0) - 20
        rows = np.r_[0:y0, y1:round(top)]
        a, b = luma(before[rows, :self.split].astype(np.float64)), luma(after[rows, :self.split].astype(np.float64))
        lo, hi = max(0, round(x - half)), min(self.split, round(x + half))
        up = (b - a) > 60
        near = up[:, lo:hi].sum() / max(hi - lo, 1)
        rest = (up.sum() - up[:, lo:hi].sum()) / max(self.split - (hi - lo), 1)
        return float((b[:, lo:hi] - a[:, lo:hi]).mean()), float(near / max(rest, 0.5)), int(up[:, lo:hi].sum())

    def flake_pixels(self, img: np.ndarray) -> int:
        """제목 위 하늘(별과 눈 글자뿐인 자리)의 밝은 글자 화소 수 — 눈송이가 많을수록 는다."""
        return int((luma(img[:self.head_rows()[0], :self.split]) > LIM["lit"]).sum())

    # ── 편집기 A: 2026.py ──
    def mark_at(self, img: np.ndarray, i: int) -> str | None:
        """대본 i번째 줄 앞(markX)의 실행 표시: 'ok'(초록 ✓), 'error'(빨강 ✕), 없으면 None.
        자리는 그 줄 글자 칸(밑선에서 글자 크기만큼 위 ~ 0.2배 아래), 가로는 markX ± 글자 크기의 0.6배."""
        A, y = self.ed["A"], self.row_a[i]
        half = round(A["font"] * 0.6)
        patch = img[round(y - A["font"]):round(y + A["font"] * 0.2), A["markX"] - half:A["markX"] + half + 1]
        green, red = tint_counts(patch, LIM["bright"])
        if max(green, red) < LIM["mark_px"]:
            return None
        return "ok" if green > red else "error"

    def bar_lines(self, img: np.ndarray) -> list[tuple[int, str]]:
        """2026.py 창 왼쪽 끝 7px 띠(실행 막대의 진한 끝)가 켜진 줄 → [(줄 idx, 색 이름)].
        줄마다 밑선에서 줄 간격의 절반 위까지를 본다(막대는 밑선 조금 아래까지 한 줄 높이로 깔린다)."""
        A, x0, found = self.ed["A"], self.ed["cardX"], []
        for i, y in enumerate(self.row_a):
            p = img[round(y - A["pitch"] * 0.5):round(y), x0 + 2:x0 + 7].reshape(-1, 3).astype(np.float64)
            if luma(p).mean() > LIM["bar_lit"]:
                found.append((i, color_name(p.mean(0))))
        return found

    # ── 편집기 B: newyear.js ──
    def pane_b(self, img: np.ndarray) -> np.ndarray:
        B, x0 = self.ed["B"], self.ed["cardX"]
        return img[B["y"]:B["y"] + B["h"], x0:x0 + self.ed["cardW"]]

    def pane_b_bar(self, img: np.ndarray) -> int | None:
        """newyear.js 창 실행 막대(왼쪽 7px 띠)가 켜진 높이의 가운데 y. 없으면 None."""
        B, x0 = self.ed["B"], self.ed["cardX"]
        col = luma(img[B["y"] + B["head"]:B["y"] + B["h"], x0 + 2:x0 + 7].astype(np.float64)).mean(axis=1)
        ys = np.flatnonzero(col > LIM["bar_lit"])
        return int(B["y"] + B["head"] + np.median(ys)) if len(ys) else None

    def head_strip_box(self) -> tuple[int, int, int, int]:
        """newyear.js 창 머리 띠 (x, y, 폭, 높이) — 창 머리 위아래 4px 안쪽, 창 전체 폭."""
        B = self.ed["B"]
        return self.ed["cardX"], B["y"] + 4, self.ed["cardW"], B["head"] - 8

    def value_windows(self) -> list[tuple[float, float, str]]:
        """시각표로 보아 newyear.js 창 머리에 지금 값이 '반드시' 떠 있는 구간 → [(t0, t1, 까닭)].
        삽질하는 동안은 막대가 날짜 셈(dayAt) 줄을 돌며 'd = …'를 띄우고, 'ok'·'gold' 단계(수고했어 · 2027 잠김)는 값을 띄운다.
        단계가 바뀌면 창이 구르는 동안(0.16초의 절반) 앞 단계 값을 두므로 0.2초 뒤부터, 다음 단계 0.05초 전까지(길어야 0.5초)."""
        out = []
        dig0, dig1 = self.t("dig_start"), self.t("dig_end")
        if dig0 is not None and dig1 is not None:
            out.append((dig0 + 0.2, dig1 - 0.05, "삽질하는 동안 날짜 셈"))
        steps = self.events("step")
        for i, s in enumerate(steps):
            if s["kind"] in ("ok", "gold"):
                nxt = steps[i + 1]["t"] if i + 1 < len(steps) else math.inf
                out.append((s["t"] + 0.2, min(nxt - 0.05, s["t"] + 0.5), f"{s['t']:.2f}초 '{s['kind']}' 단계"))
        return [w for w in out if w[1] > w[0]]

    # ── 편집기 C: 터미널 ──
    def terminal_lines(self, img: np.ndarray) -> list[dict]:
        """터미널 창 안의 글자 줄(위에서부터) → [dict(y0, y1, gold, lit)]. 맨 아래 줄은 'frame NNN/480 · …' 줄이다.
        밝은 화소가 있는 가로줄을 4px 넘는 틈으로 끊어 한 줄씩 묶고, 줄마다 금색 화소(min(R,G)−B ≥ bar_tint)를 센다."""
        C, x0 = self.ed["C"], self.ed["cardX"]
        top = C["y"] + C["head"] + 2
        body = img[top:C["y"] + C["h"] - 2, x0 + 10:x0 + self.ed["cardW"] - 10].astype(np.int16)
        lit = luma(body) > LIM["bright"]
        bands: list[list[int]] = []
        for y in np.flatnonzero(lit.sum(axis=1) >= 3):
            if bands and y - bands[-1][1] <= 4:
                bands[-1][1] = int(y)
            else:
                bands.append([int(y), int(y)])
        out = []
        for a, b in bands:
            p = body[a:b + 1]
            gold = (np.minimum(p[..., 0], p[..., 1]) - p[..., 2] >= LIM["bar_tint"]) & (luma(p) > LIM["lit"])
            out.append(dict(y0=top + a, y1=top + b, gold=int(gold.sum()), lit=int(lit[a:b + 1].sum())))
        return out

    # ── 편집기 글자(막대 바탕은 빼고) ──
    def editor_text(self, img: np.ndarray) -> np.ndarray:
        """편집기 쪽 절반(x ≥ split)에서 글자 화소 표시: 그 가로줄 가운데값(창 바탕, 또는 줄 전체에 깔린 실행 막대 바탕)보다
        text_contrast 넘게 밝은 화소. 막대 바탕 같은 넓은 면은 빠지고 그 위의 글자만 남는다."""
        lum = luma(img[:, self.split:].astype(np.float64))
        return (lum - np.median(lum, axis=1, keepdims=True)) > LIM["text_contrast"]

    def text_right(self, mask: np.ndarray, y0: int, y1: int, x_from: int = 0) -> int | None:
        """글자 표시(editor_text)에서 y0..y1 사이 글자가 닿는 가장 오른쪽 화면 x(세로로 2화소 넘는 기둥만). 없으면 None."""
        cols = mask[y0:y1, max(0, x_from - self.split):].sum(axis=0) >= 2
        return int(max(x_from, self.split) + np.flatnonzero(cols)[-1]) if cols.any() else None

    def pane_of(self, y: float) -> str:
        """화면 높이 y가 놓인 편집기 칸 이름."""
        for name, title in (("A", "2026.py"), ("B", "newyear.js"), ("C", "터미널")):
            p = self.ed[name]
            if p["y"] <= y < p["y"] + p["h"]:
                return f"{name}({title})"
        return "창 밖"

    # ── 제목 ──
    def head_rows(self) -> tuple[int, int]:
        """위쪽 큰 글자 두 줄이 차지하는 높이(테두리·그림자까지 넉넉히 글자 크기의 1.2배)."""
        pad = self.head["px"] * 1.2
        return round(self.head["y1"] - pad), round(self.head["y2"] + pad)

    def head_patch(self, img: np.ndarray) -> np.ndarray:
        """제목 띠의 편집기 쪽 절반, 2026.py 창 위까지(제목은 화면 가운데 정렬이고, 이쪽에는 눈·불꽃·글자 무대가 없다)."""
        y0, y1 = self.head_rows()
        return img[y0:min(y1, self.ed["A"]["y"]), self.split:]

    def head_change(self, a: np.ndarray, b: np.ndarray) -> float:
        """제목 띠에서 크게 달라진 화소의 비율."""
        diff = np.abs(self.head_patch(a).astype(np.int16) - self.head_patch(b)).max(axis=2)
        return float((diff > 96).mean())

    def head_extent(self, img: np.ndarray) -> tuple[int, int] | None:
        """제목 글자(밝은 속)가 차지하는 높이 (맨 윗줄 y, 맨 아랫줄 y). 글자가 없으면 None."""
        lit = (luma(img[:self.ed["A"]["y"], self.split:]) > LIM["bright"]).sum(axis=1) >= 3
        rows = np.flatnonzero(lit)
        return (int(rows[0]), int(rows[-1])) if len(rows) else None

    def hook2_redness(self, img: np.ndarray) -> float:
        """제목 둘째 줄 글자 색의 R−G: 노랑이면 +30쯤, 빨강이면 +140쯤."""
        y0, y1 = round(self.head["y2"] - self.head["px"] / 2), round(self.head["y2"] + self.head["px"] / 2)
        _, (r, g, _) = ink(img[y0:y1, self.split:], LIM["ink"])
        return float(r - g)

    def scene_cells(self, a: np.ndarray, b: np.ndarray) -> tuple[float, np.ndarray]:
        """제목 띠를 뺀 화면의 (평균 절대 차이, BLOCK px 칸 차이 표)."""
        y0, y1 = self.head_rows()
        keep = np.r_[0:y0, y1:self.h]
        return cell_diff(a[keep], b[keep])

    def cell_place(self, row: int, col: int) -> tuple[int, int]:
        """scene_cells 표의 칸 (줄, 칸) → 화면 위 칸 왼쪽 위 (x, y). 제목 띠를 빼고 붙였으므로 그 아래는 띠 높이만큼 내린다."""
        y0, y1 = self.head_rows()
        y = row * BLOCK
        return col * BLOCK, y if y < y0 else y + (y1 - y0)

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
    video = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        return None
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


def decode_strip(mp4: Path, reel: Reel) -> np.ndarray | None:
    """MP4의 모든 프레임에서 newyear.js 창 머리 띠만 잘라 푼다 → (프레임 수, 높이, 폭, 3). 못 풀면 None."""
    x, y, w, h = reel.head_strip_box()
    r = run(["ffmpeg", "-v", "error", "-i", mp4, "-map", "0:v:0", "-vf",
             "scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,"
             f"crop={w}:{h}:{x}:{y},format=rgb24", "-fps_mode", "passthrough", "-f", "rawvideo", "-"])
    if r.returncode != 0 or not r.stdout or len(r.stdout) % (w * h * 3):
        return None
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w, 3)


def grow(mask: np.ndarray, r: int = 1) -> np.ndarray:
    """참인 화소를 사방 r화소만큼 넓힌다(압축으로 글자 가장자리가 1화소 흔들려도 같은 글자로 보게)."""
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def header_gaps(reel: Reel, strip: np.ndarray) -> dict:
    """newyear.js 창 머리: 왼쪽 위치 글자(파일 이름표 + '/ C['…']')의 끝과 오른쪽 정렬된 지금 값의 시작 사이 틈을 프레임마다 잰다.
    색은 쓰지 않고 자리로 가른다(색을 돌리거나 다시 압축해도 같은 값이 나오게):
      · 값이 떠 있는가 — 값은 창 오른쪽 끝에서 16px 안쪽(cardW − 16)에 오른쪽 맞춤으로 찍히므로, 그 끝 14px 기둥에 밝은 화소가 있으면 값이 있다.
      · 위치 글자 — 값이 없는 프레임(영상 전체에서)이 그대로 기준이 된다: 그 머리의 밝은 화소가 위치 글자이고, 가장 오른쪽 기둥이 끝이다.
        서로 다른 위치 글자마다 하나씩 모아 둔다.
      · 값이 있는 프레임마다, 기준 글자가 왼쪽부터 가장 멀리까지 (1화소 넓힌) 지금 화면에 그대로 남은(빠진 화소 3% 이하) 기준을 고른다 —
        값은 위치 글자 위에 덧칠되므로 진짜 기준이면 끝까지 남고, 엔진이 위치 글자를 잘라 그리면 잘린 데까지 남는다. 그 끝이 이 프레임의
        위치 글자 끝이다. 앞부분만 같은 다른 기준은 갈라지는 데서 멈추므로 덜 멀리 간다. 짧은 기준을 잘못 고르면 남는 위치 글자 꼬리가
        값으로 읽혀 틈이 0 언저리로 줄어든다 — 틀려도 '겹침'으로 기우니 겹친 것을 놓치지 않는다.
      · 값 시작 — 기준에 없던 새 화소의 기둥을 오른쪽 끝에서부터 20px 넘는 빈칸이 나올 때까지 이어 간 왼쪽 끝.
    → dict(rows={프레임: (틈, 위치 글자 끝 x, 값 시작 x) 또는 None(맞는 기준 없음)}, refs={기준 프레임: 위치 글자 끝 x}, has_value=[…])."""
    x0, w = reel.head_strip_box()[0], strip.shape[2]
    lit = luma(strip.astype(np.float32)) > 70
    end = w - 16
    has_value = lit[:, :, end - 14:end + 1].sum(axis=(1, 2)) >= 6
    rights = [int(np.flatnonzero(c)[-1]) if c.any() else -1 for c in lit.sum(axis=1) >= 2]
    refs: dict[int, int] = {}
    for i in np.flatnonzero(~has_value):
        if rights[i] < 60:                                   # 머리가 비었다(되감기 화면 등)
            continue
        if not any(rights[j] == rights[i] and (lit[j] ^ lit[i]).sum() < 0.02 * lit[i].sum() + 20 for j in refs):
            refs[int(i)] = rights[i]
    pill = min(refs.values()) // 2 if refs else 0             # 어느 기준이든 품는 앞부분(파일 이름표) — 이만큼은 맞아야 같은 머리로 본다
    rows: dict[int, tuple[int, int, int] | None] = {}
    for i in np.flatnonzero(has_value):
        now, now_g, best = lit[i], grow(lit[i]), None
        for j, r in refs.items():
            ref = lit[j][:, :r + 1]
            # 기준 글자가 앞에서부터 어디까지 지금 화면에 그대로 남았나(값은 덧칠될 뿐이라 진짜 기준이면 끝까지 남는다.
            # 엔진이 위치 글자를 잘라 그리면 잘린 데까지)
            # 글자 두어 자 폭(10px)씩 잘라 보아, 기준 화소의 4분의 1 넘게(+2) 빠진 첫 자리 바로 앞까지
            win, lost = np.ones(10), (ref & ~now_g[:, :r + 1]).sum(axis=0)
            miss, have = np.convolve(lost, win)[9:], np.convolve(ref.sum(axis=0), win)[9:]
            over = np.flatnonzero(miss > 0.25 * have + 2)
            c = r
            if len(over):
                j0 = int(over[0])
                c = j0 + int(np.flatnonzero(lost[j0:j0 + 10])[0]) - 1      # 그 칸에서 처음 빠진 기둥 바로 앞
            if c < pill:
                continue
            # 끝까지 남은 기준(c == r)을 먼저, 그중 가장 긴 것. 그런 것이 없을 때만(위치 글자를 잘라 그린 화면) 가장 멀리 남은 것.
            # 더 긴 다른 기준이 겹친 값 글자에 묻혀 조금 더 가는 일이 있어서 '끝까지'를 앞세운다.
            score = (c == r, c)
            if best is None or score > best[2]:
                best = (j, c, score)
        if best is None:
            rows[int(i)] = None
            continue
        j, c, _ = best
        kept = np.zeros_like(lit[j])
        kept[:, :c + 1] = lit[j][:, :c + 1]
        r = int(np.flatnonzero(kept.sum(axis=0) >= 1)[-1])   # 이 프레임에 남은 위치 글자의 끝
        cols = np.flatnonzero((now & ~grow(kept)).sum(axis=0) >= 2)
        k = len(cols) - 1
        while k > 0 and cols[k] - cols[k - 1] <= 20:
            k -= 1
        start = int(cols[k]) if len(cols) else end
        rows[int(i)] = (start - r, x0 + r, x0 + start)
    return dict(rows=rows, refs={j: x0 + r for j, r in refs.items()}, has_value=has_value.tolist())


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
        ("hook", "첫 장면", 0),
        ("board", f"연도판 {year}", at(t("board_settle"), 0.2)),
        ("dig", "삽질 한창", at(dig_mid)),
        ("jam", "실패 도장", at(t("stamp"), 0.3)),
        ("fixed", "보완 완료", at(t("check"), 0.3)),
        ("newyear", f"{new_year} 고리", at(t("year_gold"), 0.5)),
        ("fireworks", "삽 모양 불꽃", at(next((e["t"] for e in reel.events("fw_burst") if e.get("kind") == "shape"), None), 0.3)),
        ("final", "마지막", reel.last),
    ]
    return [p for p in picks if p[2] is not None]


def moments(reel: Reel) -> dict[str, int | None]:
    """검사에 쓰는 순간 → 프레임 번호(그 장면이 없는 대본이면 None)."""
    at, t, st = reel.at, reel.t, reel.state
    m = dict(first=0, first3=3, first6=6, last=reel.last, last1=reel.last - 1, last3=reel.last - 3, last6=reel.last - 6,
             mid=reel.frames // 2, mid1=reel.frames // 2 + 1)
    # 이음매: 마지막 프레임 바로 앞까지의 이웃 프레임 쌍 LOOP_PAIRS개
    for k in range(LOOP_PAIRS + 2):
        m[f"end{k}"] = reel.last - k
    # ✓는 줄이 끝난 뒤: 0.5초 넘게 도는 줄마다 실행과 끝 사이 한가운데 / 끝나고 0.3초 뒤
    for ln in reel.lines:
        done = reel.done_t(ln)
        if ln["ok"] and done is not None and done - ln["fireAt"] >= 0.5:
            m[f"run_mid{ln['idx']}"] = reel.at((ln["fireAt"] + done) / 2)
            if done + 0.3 <= reel.last / reel.fps:
                m[f"run_done{ln['idx']}"] = reel.at(done, 0.3)
    # 연도판: 넘어가기 0.1초 전 / 잠기고 0.8초 뒤 / 걸리기 전후(빨간 빛이 깜박이므로 0.3초 뒤 앞뒤 한 프레임까지 본다)
    m["ice"] = at(t("year_roll"), -0.1) if t("year_roll") is not None else reel.last
    m["gold"] = at(t("year_gold"), 0.8)
    jam, stamp, fix = t("jam"), t("stamp"), t("fix_stamp")
    m["jam_before"] = at(jam, -0.3)
    for name, shift in (("jam_after_a", 0.3 - 1 / reel.fps), ("jam_after_b", 0.3), ("jam_after_c", 0.3 + 1 / reel.fps)):
        m[name] = at(jam, shift)
    # 확인란: 무엇이든 그 앞을 가리거나 바꾸기 전(카운트다운 숫자·걸림·체크 중 가장 이른 것 0.3초 전) /
    #         도장과 '보완 완료' 사이 한가운데(고치지 않는 대본이면 도장 0.5초 뒤) / 체크 0.4초 뒤
    changes = [x for x in (t("count"), jam, t("check")) if x is not None]
    m["tag_plain"] = at(min(changes), -0.3) if changes else reel.last
    m["tag_red"] = at(stamp, 0.5 if fix is None else (fix - stamp) / 2) if stamp is not None else None
    m["tag_gold"] = at(t("check"), 0.4)
    # 색 빠짐: 걸리기 전 1초 / 도장 0.3초 뒤부터 고치는 줄의 '보완 완료'까지(고치지 않으면 1초 동안)
    if jam is not None and stamp is not None:
        for i, f in enumerate(reel.spread(jam - 1.0, jam - 1 / reel.fps)):
            m[f"warm{i}"] = f
        for i, f in enumerate(reel.spread(stamp + 0.3, fix if fix is not None else stamp + 1.3)):
            m[f"cold{i}"] = f
    # 흙더미: 삽질이 끝난 순간 / 금빛이 오르기 직전 / 마지막 띠가 바뀌고 0.6초 뒤
    m["dug"] = reel.after(t("dig_end"))
    m["soil"] = at(t("gild"), -0.1) if t("gild") is not None else reel.last
    m["gilded"] = at(t("gild", -1), 0.6)
    # 해상도 업: 2027이 잠기기 0.1초 전 / 2초 뒤(고리는 1.4초 동안 퍼진다)
    m["res_before"], m["res_after"] = at(t("year_gold"), -0.1), at(t("year_gold"), 2.0)
    # newyear.js 창: 삽질이 30% 지난 때부터 0.25초 동안 프레임마다
    if st["dig"]:
        t0 = t("dig_start") + 0.3 * st["dig"]["D"]
        for i, f in enumerate(range(at(t0), at(t0, 0.25) + 1)):
            m[f"paneB{i}"] = f
    # 제목: 맺는 말로 바뀌기 0.4초 전 / 0.8초 뒤, 첫 오류 0.3초 전 / 뒤
    swap = reel.d["swapT"]
    m["head_before"], m["head_after"] = at(swap, -0.4), at(swap, 0.8)
    m["hook_before"], m["hook_red"] = at(t("enter_error"), -0.3), at(t("enter_error"), 0.3)
    # 불꽃: 첫 발이 터지기 0.1초 전(불씨는 올라가는 중) / 터지고 0.1초 뒤
    m["fw_before"], m["fw_after"] = at(t("fw_burst"), -0.1), at(t("fw_burst"), 0.1)
    # 안전 구역: SAMPLE_STEP초마다 + 줄마다 실행 0.2초 뒤(창 머리 값·막대가 바뀌는 순간)
    samples = {at(k * SAMPLE_STEP) for k in range(int(reel.frames / reel.fps / SAMPLE_STEP) + 1)} | {reel.last}
    samples |= {at(ln["fireAt"], 0.2) for ln in reel.lines}
    for f in sorted(samples):
        m[f"s{f:03d}"] = f
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
    """연도판(글자): 넘어가기 전엔 얼음빛(파르스름한 흰 글자), 잠긴 뒤엔 금빛. 끝내 못 넘어가는 대본이면 ice에 마지막 화면을 받는다."""
    if not reel.state["yearSet"]:
        rep.skip(group, "연도판 색", "대본에 year = … 줄이 없음")
        return
    w_ice, n_ice = reel.board_tone(ice)
    if gold is None:
        rep.add(group, "연도판 색", n_ice > 0 and w_ice < LIM["board_ice"],
                f"새해로 넘어가지 않음 → 끝까지 얼음빛: 밝은 글자 {n_ice}화소의 R−B {w_ice:+.1f} (기준 < {LIM['board_ice']})", ice=w_ice)
        return
    w_gold, n_gold = reel.board_tone(gold)
    rep.add(group, "연도판 색", n_ice > 0 and n_gold > 0 and w_ice < LIM["board_ice"] and w_gold > LIM["board_gold"],
            f"상자 안 밝은 글자(휘도 > {LIM['lit']})의 R−B — 넘어가기 0.1초 전 {w_ice:+.1f} ({n_ice}화소, 얼음빛 < {LIM['board_ice']}) → "
            f"잠기고 0.8초 뒤 {w_gold:+.1f} ({n_gold}화소, 금빛 > {LIM['board_gold']})", ice=w_ice, gold=w_gold)


def check_jam(rep: Report, reel: Reel, pic):
    """새해로 넘기다 걸리면 연도판이 빨갛게 달아오른다(그 순간 무대 색이 빠지기 시작하는데도)."""
    if reel.t("jam") is None or not reel.state["yearSet"]:
        rep.skip("B", "연도판 걸림", "대본에 새해로 넘기다 걸리는 줄이 없음")
        return
    before = reel.board_redness(pic("jam_before"))
    after = max(reel.board_redness(pic(k)) for k in ("jam_after_a", "jam_after_b", "jam_after_c"))
    rep.add("B", "연도판 걸림", after - before >= LIM["jam_red"],
            f"연도판 상자 전체의 붉은 정도 R−(G+B)/2 — 걸리기 0.3초 전 {before:+.1f} → 0.3초 뒤(앞뒤 한 프레임 중 최대) {after:+.1f} "
            f"(늘어난 양 {after - before:+.1f}, 기준 ≥ {LIM['jam_red']})", before=before, after=after)


def check_tag(rep: Report, reel: Reel, pic):
    """연도판 밑 확인란: 처음엔 기본색, 실패 도장이 찍힌 동안 빨강, 체크된 뒤 금."""
    if not reel.state["yearSet"]:
        rep.skip("B", "확인란", "대본에 year = … 줄이 없음")
        return
    steps = [("기본", "tag_plain", "처음"), ("빨강", "tag_red", "도장과 '보완 완료' 사이"), ("금", "tag_gold", "체크 0.4초 뒤")]
    label = reel.tag_label(pic("tag_plain"))
    seen = [(want, when, *reel.tag_state(pic(key), label)) for want, key, when in steps if pic(key) is not None]
    rep.add("B", "확인란", label is not None and all(want == kind for want, _, kind, _, _ in seen),
            ("글자 상자를 찾지 못함(처음 프레임에 '수고했어'가 없음) · " if label is None else
             f"'수고했어' 글자 상자 x {label[2]}~{label[3]}, y {label[0]}~{label[1]}의 위쪽 65%(그 밑을 지나는 도장 테두리는 빼고) — ") +
            " → ".join(f"{when} {kind}({n}화소, B−R {rgb[2] - rgb[0]:+.0f} · R−max(G,B) {rgb[0] - max(rgb[1], rgb[2]):+.0f} · "
                       f"min(R,G)−B {min(rgb[0], rgb[1]) - rgb[2]:+.0f})" for _, when, kind, n, rgb in seen)
            + " (기대 " + " → ".join(want for want, *_ in seen) + ")",
            states=[dict(want=want, seen=kind, pixels=n, rgb=rgb.round(1).tolist()) for want, _, kind, n, rgb in seen])


def check_mound_top(rep: Report, group: str, reel: Reel, img: np.ndarray, frame: int):
    """삽질이 끝난 순간 흙더미 윗변이 GROUND − h 에 있는가(글자 한 줄 높이만큼의 오차는 둔다)."""
    want = reel.stage["GROUND"] - reel.state["dig"]["h"]
    top = reel.mound_top(img)
    rep.add(group, "흙더미 높이", top is not None and abs(top - want) <= LIM["mound_px"],
            f"프레임 {frame}(삽질 끝): 윗변 y={top} (기대 GROUND {reel.stage['GROUND']} − h {reel.state['dig']['h']:.1f} = {want:.1f}"
            f" ±{LIM['mound_px']}, 삽질 {reel.state['dig']['n']}번)", top=top, want=want)


def check_bands(rep: Report, group: str, reel: Reel, soil: np.ndarray, gilded: np.ndarray | None):
    """달 띠 색: 금빛으로 바뀌기 전엔 전부 흙, 바뀐 뒤엔 전부 금. 안 바뀌는 대본이면 soil에 마지막 화면을 받는다."""
    if not reel.state["dig"]:
        rep.skip(group, "흙더미 색", "대본에 삽질 줄이 없음")
        return
    before, t_before = reel.band_kinds(soil), reel.band_tints(soil)
    span = lambda v: f"{min(v):.2f}~{max(v):.2f}" if v else "-"
    if gilded is None:
        rep.add(group, "흙더미 색", bool(before) and set(before) == {"흙"},
                f"금빛으로 바뀌지 않음 → 끝까지 흙 {before.count('흙')}/{len(before)}띠 ((R−B)/R {span(t_before)}, 금 기준 > {LIM['gold_tint']})",
                before=before, tints=t_before)
        return
    after, t_after = reel.band_kinds(gilded), reel.band_tints(gilded)
    rep.add(group, "흙더미 색", bool(before) and set(before) == {"흙"} and set(after) == {"금"},
            f"첫 금빛 0.1초 전 흙 {before.count('흙')}/{len(before)}띠 ((R−B)/R {span(t_before)}) → 마지막 띠가 바뀌고 0.6초 뒤 "
            f"금 {after.count('금')}/{len(after)}띠 ({span(t_after)}) · 금 기준 > {LIM['gold_tint']}",
            before=before, after=after, tints_before=t_before, tints_after=t_after)


def check_chill(rep: Report, reel: Reel, pic, plan: dict):
    """실패한 동안에는 무대에서 색이 빠진다."""
    warm = [reel.scenery_chroma(pic(k)) for k in plan if k.startswith("warm")]
    cold = [reel.scenery_chroma(pic(k)) for k in plan if k.startswith("cold")]
    if not warm or not cold:
        rep.skip("B", "실패한 동안 색 빠짐", "대본에 새해로 넘기다 걸리는 줄이 없음")
        return
    before, during = float(np.mean(warm)), float(np.mean(cold))
    rep.add("B", "실패한 동안 색 빠짐", during <= before * LIM["chill_ratio"],
            f"무대 배경(흙더미 윗변 아래, 이름표 오른쪽) 평균 채도 — 걸리기 전 1초 {before:.1f} → 도장 0.3초 뒤부터 '보완 완료'까지 {during:.1f} "
            f"(비율 {during / before:.2f}, 기준 ≤ {LIM['chill_ratio']} · 프레임 {len(warm)}장 대 {len(cold)}장)",
            before=before, during=during)


def check_resolution(rep: Report, reel: Reel, pic):
    """해상도 업: 2027이 잠기면 연도판에서 고리가 퍼지며 글자 칸이 작아진다 → 같은 자리의 글자 줄이 촘촘해진다."""
    if not reel.state["yearUp"] or not reel.state["dig"] or pic("res_before") is None:
        rep.skip("B", "해상도 업", "새해로 넘어가지 않거나 흙더미가 없는 대본")
        return
    (p0, n0), (p1, n1) = reel.glyph_rows(pic("res_before")), reel.glyph_rows(pic("res_after"))
    rep.add("B", "해상도 업", n1 >= n0 * LIM["res_gain"],
            f"흙더미 오른 옆구리 띠의 글자 줄 — 잠기기 0.1초 전 간격 {p0:.1f}px(100px에 {n0:.1f}줄) → 2초 뒤 {p1:.1f}px({n1:.1f}줄) "
            f"(배율 {n1 / n0:.2f}, 기준 ≥ {LIM['res_gain']})", before=dict(period=p0, rows=n0), after=dict(period=p1, rows=n1))


def mark_wanted(reel: Reel, ln: dict, now: float) -> str | None:
    """시각 now에 그 줄 앞에 보여야 하는 표시: 'ok' · 'error' · None(없음) · '?'(그려지는 중이거나 끝나는 때를 몰라 따지지 않음).
    ✓는 줄이 끝난 때(done_t)부터 0.24초 동안 그려지고, ✕는 실행 0.06~0.26초 사이에 그려진다(editor.js drawCheck·drawCross)."""
    if ln["silent"] or ln["fireAt"] > now + 1e-6:
        return None
    if not ln["ok"]:
        return "error" if now >= ln["fireAt"] + 0.26 else (None if now < ln["fireAt"] + 0.06 else "?")
    done = reel.done_t(ln)
    if done is None:
        return "?"
    return "ok" if now >= done + 0.24 else (None if now < done else "?")


def check_running_marks(rep: Report, reel: Reel, pic, plan: dict):
    """✓는 줄이 '끝난' 뒤에 뜬다: 0.5초 넘게 도는 줄(삽질·카운트다운·불꽃…)마다 실행과 끝 사이 한가운데에는 그 줄에 표시가 없고,
    끝나고 0.3초 뒤에는 초록 ✓가 있다. 끝나는 때는 시각표의 사건으로 정한다(Reel.done_t)."""
    rows = []
    for ln in reel.lines:
        i, key = ln["idx"], f"run_mid{ln['idx']}"
        if key not in plan:
            continue
        done = reel.done_t(ln)
        mid = reel.mark_at(pic(key), i)
        after = reel.mark_at(pic(f"run_done{i}"), i) if f"run_done{i}" in plan else "-"
        rows.append(dict(line=i + 1, text=ln["text"], fire=ln["fireAt"], done=done, mid_frame=plan[key], mid=mid,
                         after_frame=plan.get(f"run_done{i}"), after=after, ok=mid is None and after in ("ok", "-")))
    if not rows:
        rep.skip("B", "✓는 줄이 끝난 뒤", "0.5초 넘게 도는 줄이 없음")
        return
    rep.add("B", "✓는 줄이 끝난 뒤", all(r["ok"] for r in rows),
            " · ".join(f"{r['line']}번째 '{r['text']}' (실행 {r['fire']:.2f}초 → 끝 {r['done']:.2f}초): 한가운데 프레임 {r['mid_frame']} 표시 "
                       f"{r['mid'] or '없음'} (기대 없음) → 끝 0.3초 뒤 프레임 {r['after_frame']} 표시 {r['after']} (기대 ok)" for r in rows),
            lines=rows)


def check_editor(rep: Report, group: str, reel: Reel, img: np.ndarray, frame: int):
    """마지막 프레임(모든 줄이 끝난 뒤)의 2026.py: 실행되어 성공한 줄은 초록 ✓, 실패한 줄은 빨강 ✕,
    주석·빈 줄·그냥 변수 저장(silent)은 표시 없음. 실행 막대는 마지막으로 실행된 줄 하나에만 — 실패한 줄이면 빨강,
    맨 끝 줄이 주석(silent)이면 금, 그 밖은 보라."""
    now = reel.sec(frame)
    marks = []
    for i, ln in enumerate(reel.lines):
        want, mid = mark_wanted(reel, ln, now), False
        if want == "?":                                    # 표시가 그려지는 중(0.24초)이거나 끝나는 때를 모름 — 따지지 않는다
            want, mid = None, True
        marks.append(dict(line=ln["idx"] + 1, text=ln["text"], want=want, seen=reel.mark_at(img, i), drawing=mid))
    wrong = [m for m in marks if m["seen"] != m["want"] and not m["drawing"]]
    count = {k: sum(m["seen"] == k for m in marks) for k in ("ok", "error", None)}
    text = f"프레임 {frame}: ✓ {count['ok']}줄 · ✕ {count['error']}줄 · 표시 없음 {count[None]}줄 (✓는 줄이 끝난 뒤에 기대)"
    if any(m["drawing"] for m in marks):
        text += " · 그려지는 중이라 안 따진 줄 " + ", ".join(str(m["line"]) for m in marks if m["drawing"])
    if wrong:
        text += " — 어긋남: " + ", ".join(f"{m['line']}번째 줄({m['text']}) 기대 {m['want']} 읽음 {m['seen']}" for m in wrong)
    rep.add(group, "편집기 실행 표시", not wrong, text, marks=marks)

    fired = reel.fired_lines(now)
    bars = reel.bar_lines(img)
    if not fired:
        want_bar = []
    else:
        cur = fired[-1]
        color = "빨강" if not cur["ok"] else ("금" if cur["silent"] and cur["idx"] == reel.lines[-1]["idx"] else "보라")
        want_bar = [(cur["idx"], color)]
    rep.add(group, "실행 막대", bars == want_bar,
            "막대가 보이는 줄 " + (", ".join(f"{i + 1}번째({c})" for i, c in bars) or "없음")
            + " (기대 " + (", ".join(f"{i + 1}번째 '{reel.lines[i]['text']}'({c})" for i, c in want_bar) or "없음") + ")",
            bars=bars, want=want_bar)


def check_terminal(rep: Report, reel: Reel, img: np.ndarray):
    """마지막 프레임의 터미널: 금색 상태 줄('= 오류 n건 · 헛삽질 n건')이 보이고, 그것이 결과 줄 가운데 맨 끝(맨 아래 frame 줄 바로 위)이어야
    한다 — 모든 줄이 끝난 뒤에 찍는 요약이므로."""
    status = reel.d.get("status")
    if not status:
        rep.skip("B", "터미널 상태 줄", "실행되는 줄이 없어 상태 줄이 없음")
        return
    lines = reel.terminal_lines(img)
    logs = lines[:-1]                                      # 맨 아래는 frame NNN/480 줄
    gold = [i for i, ln in enumerate(logs) if ln["gold"] >= LIM["gold_px"]]
    # 시각표로 만든 터미널 줄 차례(엔진과 같은 규칙) — 금색은 '⏸ 예외에서 멈춤'과 상태 줄뿐
    want = reel.term_rows(reel.sec(reel.last))
    names = dict(prompt="$ node render.js", ok="✓ {n}", error="✕ {n}", at="at …:{n}", pause="⏸ 멈춤", resume="▶ 계속",
                 rename="↻ 파일 이름", status="= 상태")
    label = lambda r: names[r["kind"]].format(n=(r["line"] or 0) + 1)
    want_gold = [i for i, r in enumerate(want) if r["kind"] in ("pause", "status")]
    at_status = next((i for i, r in enumerate(want) if r["kind"] == "status"), None)
    where = ", ".join(f"{i + 1}번째(y {logs[i]['y0']}~{logs[i]['y1']}, 금색 {logs[i]['gold']}화소)" for i in gold) or "없음"
    ok = len(logs) == len(want) and gold == want_gold and at_status is not None
    rep.add("B", "터미널 상태 줄", ok,
            f"마지막 프레임 터미널: 결과 줄 {len(logs)}개 + frame 줄 · 금색 줄 {where} — 시각표로 본 차례 "
            + " / ".join(f"{i + 1}.{label(r)}" for i, r in enumerate(want))
            + f" → 금색은 " + (", ".join(f"{i + 1}번째({label(want[i])})" for i in want_gold) or "없음")
            + f"이어야 함 (줄 수 {len(want)}) · 상태 '{status['text']}' {status['t']:.2f}초",
            lines=lines, gold_rows=gold, want_rows=want, want_gold=want_gold)
    if not ok:
        rep.skip("B", "상태 줄이 맨 끝", "화면의 터미널 줄이 시각표의 차례와 맞지 않아 따질 수 없음(위 검사 실패)")
        return
    after = want[at_status + 1:]
    why = "".join(f" — 상태 줄은 {status['t']:.2f}초(바쁜 구간 끝 − 0.4초)에 찍히는데, {label(r)} 줄은 그 줄이 끝나는 {r['t']:.2f}초에 찍혀 요약 뒤로 밀린다"
                  for r in after)
    rep.add("B", "상태 줄이 맨 끝", not after,
            f"금색 상태 줄({at_status + 1}번째) 아래에 결과 줄 {len(logs) - 1 - at_status}개" + why, rows_below=len(after))


def check_code_pane(rep: Report, reel: Reel, pic, plan: dict):
    """삽질하는 동안 newyear.js 창이 돈다: 0.25초 떨어진 두 프레임 사이 창이 달라지고, 그 사이 프레임마다 막대 자리가 옮겨 다닌다."""
    keys = sorted((k for k in plan if k.startswith("paneB")), key=lambda k: int(k[5:]))
    if len(keys) < 2:
        rep.skip("B", "newyear.js 창이 돈다", "대본에 삽질 줄이 없음")
        return
    a, b = pic(keys[0]), pic(keys[-1])
    share = changed_share(reel.pane_b(a), reel.pane_b(b))
    bars = [reel.pane_b_bar(pic(k)) for k in keys]
    distinct = sorted({y for y in bars if y is not None})
    rep.add("B", "newyear.js 창이 돈다", share >= LIM["pane_change"] and len(distinct) >= 2,
            f"프레임 {plan[keys[0]]} → {plan[keys[-1]]}(0.25초): 창에서 크게 달라진 화소 {share:.1%} (기준 ≥ {LIM['pane_change']:.1%}) · "
            f"그 사이 {len(keys)}프레임의 막대 y {bars} → 서로 다른 자리 {len(distinct)}곳 (기준 ≥ 2)", changed=share, bars=bars)


def check_headline(rep: Report, reel: Reel, pic):
    """위쪽 큰 글자: 예고한 줄에서 오류가 나는 순간 둘째 줄이 빨개지고, 새해로 넘어가면 맺는 말로 바뀌고, 끝에서 낚는 말로 돌아온다."""
    if pic("hook_red") is None:
        rep.skip("B", "낚는 말 빨강", "대본에 오류가 나는 줄이 없음")
    else:
        before, after = reel.hook2_redness(pic("hook_before")), reel.hook2_redness(pic("hook_red"))
        rep.add("B", "낚는 말 빨강", after - before >= LIM["hook_red"],
                f"둘째 줄 '{reel.d['copy']['hook'][1]}' 글자의 R−G — 첫 오류 0.3초 전 {before:+.1f} → 0.3초 뒤 {after:+.1f} "
                f"(늘어난 양 {after - before:+.1f}, 기준 ≥ {LIM['hook_red']})", before=before, after=after)
    if reel.d["swapT"] is None:
        rep.skip("B", "제목 교체", "맺는 말로 바뀌지 않는 대본(swapT 없음)")
        return
    changed = reel.head_change(pic("head_before"), pic("head_after"))
    back = reel.head_change(pic("first"), pic("last"))
    rep.add("B", "제목 교체", changed >= LIM["head_change"] and back <= LIM["head_change"],
            f"바뀌기 0.4초 전과 0.8초 뒤 사이 제목 띠에서 달라진 화소 {changed:.1%} (기준 ≥ {LIM['head_change']:.0%}) · "
            f"끝에서 낚는 말로 돌아옴: 마지막 프레임과 첫 프레임 사이 {back:.1%} (기준 < {LIM['head_change']:.0%}, 여유 {LIM['head_change'] - back:.1%})",
            changed=changed, back=back)


def check_fireworks(rep: Report, reel: Reel, pic):
    """불꽃: 대본에 적은 수만큼 터지고, 그중 한 발만 삽 모양이고, 쏘는 순서대로 달 띠(months)를 따라 솟고,
    첫 발이 터진 자리의 하늘이 밝아진다."""
    fw = reel.state["fw"]
    if not fw:
        rep.skip("B", "불꽃", "대본에 불꽃 줄이 없음")
        return
    line, bursts, launches = reel.line_for(fw["t"]), reel.events("fw_burst"), reel.events("fw_launch")
    want = line["args"][0] if line and line["args"] else fw["n"]
    shapes = sum(b.get("kind") == "shape" for b in bursts)
    rep.add("B", "불꽃 수", len(bursts) == want and shapes == 1,
            f"fw_burst {len(bursts)}건 (대본 '{line['text'] if line else '?'}' → {want}발) · 삽 모양(kind 'shape') {shapes}발 (기대 1발)",
            bursts=len(bursts), want=want, shapes=shapes)
    times = [e["t"] for e in launches]
    months = fw.get("months") or list(range(len(launches)))
    bands_up = reel.state["dig"]["bands"] if reel.state["dig"] else 0
    want_bands = [months[j] % bands_up if bands_up else -1 for j in range(len(launches))]
    seen_bands = [e.get("band") for e in launches]
    rep.add("B", "불꽃 순서", times == sorted(times) and seen_bands == want_bands,
            f"fw_launch {len(launches)}건 시각 {'오름차순' if times == sorted(times) else '뒤섞임'} ({times[0]:.2f}~{times[-1]:.2f}초) · "
            f"솟는 달 띠 {seen_bands} (기대: 쏘는 순서 j의 months[j] mod 쌓인 띠 {bands_up} = {want_bands})" if launches else
            "fw_launch 없음", times=times, bands=seen_bands, want_bands=want_bands)
    if not bursts or pic("fw_before") is None:
        rep.add("B", "불꽃 밝기", False, "영상 안에서 쏘거나 터지는 불꽃이 없음")
        return
    x, half = bursts[0]["x"] * reel.stage["W"], bursts[0]["size"] / 2
    glow, focus, n = reel.sky_glow(pic("fw_before"), pic("fw_after"), x, half)
    rep.add("B", "불꽃 밝기", glow >= LIM["fw_glow"] and focus >= LIM["fw_focus"],
            f"첫 불꽃({bursts[0].get('kind')}, {bursts[0]['t']:.2f}초)이 터진 기둥 x {x:.0f}±{half:.0f}의 하늘(흙더미 위) — 터지기 0.1초 전 → "
            f"0.1초 뒤 평균 밝기 {glow:+.1f} (기준 ≥ {LIM['fw_glow']}) · 크게 밝아진 화소 {n}개, 기둥당 나머지 하늘의 {focus:.1f}배 "
            f"(기준 ≥ {LIM['fw_focus']})", glow=glow, focus=focus, pixels=n)


def check_story(rep: Report, reel: Reel, pic, plan: dict):
    check_board(rep, "B", reel, pic("ice"), pic("gold") if reel.t("year_roll") is not None else None)
    check_jam(rep, reel, pic)
    check_tag(rep, reel, pic)
    if reel.t("dig_end") is None:
        rep.skip("B", "흙더미 높이", "대본에 삽질 줄이 없음")
    else:
        check_mound_top(rep, "B", reel, pic("dug"), plan["dug"])
    check_bands(rep, "B", reel, pic("soil"), pic("gilded"))
    check_chill(rep, reel, pic, plan)
    check_resolution(rep, reel, pic)
    check_editor(rep, "B", reel, pic("last"), reel.last)
    check_running_marks(rep, reel, pic, plan)
    check_terminal(rep, reel, pic("last"))
    check_code_pane(rep, reel, pic, plan)
    check_headline(rep, reel, pic)
    check_fireworks(rep, reel, pic)


# ======================================================================== C. 이음매
def check_loop(rep: Report, reel: Reel, pic):
    """마지막 프레임 → 첫 프레임이 여느 프레임 넘김만큼만 달라야 한다(제목은 끝에서 맺는 말 → 낚는 말로 바뀌는 중이라 뺀다).
    평균 차이는 영상 한가운데의 이웃 프레임과 견준다. 한 군데만 튀는지는 {BLOCK}px 칸마다, 이음매 양쪽의 이웃 프레임
    (마지막 프레임 바로 앞까지 LOOP_PAIRS쌍 — 같은 장면이고, 마지막 프레임이 틀려도 기준이 따라 흔들리지 않게 그 프레임은 뺀다)이 '같은 칸'에서 가장 크게 바뀐 양과 견준다 — newyear.js 창처럼 막대가 옮겨 갈 때마다
    크게 바뀌는 칸은 이음매에서도 그만큼 바뀌어도 되고, 늘 잔잔한 칸(무대)은 이음매에서도 잔잔해야 한다. 칸마다 견주므로
    한쪽 절반만 흐리게 다시 압축해도(그쪽 이웃 차이만 줄어든다) 다른 쪽 칸의 기준이 흔들리지 않는다."""
    seam, seam_cells = reel.scene_cells(pic("last"), pic("first"))
    pairs = [(f"end{k + 2}", f"end{k + 1}") for k in range(LOOP_PAIRS)]      # 마지막 프레임은 빼고(이음매 자체가 섞이지 않게)
    ref = np.maximum.reduce([reel.scene_cells(pic(a), pic(b))[1] for a, b in pairs])
    limit_cells = ref * LIM["loop_ratio"] + LIM["loop_block_floor"]
    mid, mid_block = reel.scene_diff(pic("mid"), pic("mid1"))
    limit = mid * LIM["loop_ratio"] + LIM["loop_floor"]
    over = seam_cells - limit_cells
    worst = np.unravel_index(int(over.argmax()), over.shape)
    top = np.unravel_index(int(seam_cells.argmax()), seam_cells.shape)
    place = lambda rc: "x {}, y {}".format(*reel.cell_place(*rc))
    y0, y1 = reel.head_rows()
    head = reel.head_change(pic("last"), pic("first"))
    rep.add("C", "마지막 → 첫 프레임", seam <= limit and over.max() <= 0,
            f"평균 차이 {seam:.2f} (기준 ≤ {limit:.2f} = 영상 가운데 이웃 프레임 {reel.frames // 2}→{reel.frames // 2 + 1}의 {mid:.2f} × {LIM['loop_ratio']} + 여유, "
            f"여유 {limit - seam:+.2f}) · {BLOCK}px 칸마다: 이음매에서 가장 크게 바뀐 칸 {seam_cells[top]:.1f} ({place(top)}) — 같은 칸의 이웃 프레임 최대 "
            f"{ref[top]:.1f} → 기준 ≤ {limit_cells[top]:.1f} · 기준에 가장 바짝 붙은 칸 {seam_cells[worst]:.1f} ({place(worst)}, 기준 ≤ {limit_cells[worst]:.1f}, "
            f"여유 {-over.max():+.1f}) · 이웃 프레임: {reel.last - LOOP_PAIRS - 1}→…→{reel.last - 1}, 칸 기준 = 같은 칸의 최대 × "
            f"{LIM['loop_ratio']} + {LIM['loop_block_floor']} — 참고: 가운데 이웃의 가장 큰 칸 {mid_block:.1f} · 제목 띠 y {y0}~{y1}은 빼고 쟀고, "
            f"그 띠에서 크게 달라진 화소는 {head:.1%}",
            seam=seam, limit=limit, middle=mid, seam_block=float(seam_cells.max()), cell_margin=float(-over.max()),
            worst_cell=reel.cell_place(*worst), head_changed=head)


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
    if from_mp4 is None:
        rep.skip("D", "영상이 지금 소스와 같음", "MP4 프레임을 풀지 못함(화면 크기나 프레임 수가 시각표와 다름)")
    elif a is None:
        rep.add("D", "영상이 지금 소스와 같음", False, f"node render.js --still {reel.last} 실패 — 견줄 화면이 없음")
    else:
        mad, block = diff_stats(a[0], from_mp4) if a[0].shape == from_mp4.shape else (float("inf"), float("inf"))
        rep.add("D", "영상이 지금 소스와 같음", block <= LIM["fresh_block"],
                f"프레임 {reel.last}: 지금 그린 화면과 MP4의 차이 — 평균 {mad:.2f}, 가장 큰 {BLOCK}px 칸 {block:.1f} "
                f"(기준 ≤ {LIM['fresh_block']}, 압축 손실만 있어야 한다)", mad=mad, block=block)


# ======================================================================== E. 대본 연동
def try_dig(rep: Report, reel: Reel):
    """① 삽질 수를 바꾸면 흙더미 높이·멈추는 날짜·이름표 수가 그만큼 바뀌고, 화면의 흙더미 윗변도 따라간다."""
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
            f"'{text}' → state.dig.h {d['h']:.2f}px (기대 {n}/{s['YEAR_DAYS']} × {s['FULL_H']} = {want_h:.2f}) · {n}번째 날 = {var.date_of(n)} "
            f"(기대 {date}) · 이름표가 붙는 달 {d['labeled']}개 · band 사건 {labels}건 (기대 {full}개: 끝까지 채운 달만)",
            h=d["h"], want_h=want_h, date=var.date_of(n), labeled=d["labeled"], band_events=labels)
    frame = var.after(var.t("dig_end"))
    stills = render_stills(TMP / "dig", [frame], path)
    if stills is None:
        rep.add("E", "흙더미 높이", False, "정지 화면을 그리지 못함")
    else:
        check_mound_top(rep, "E", var, stills[0], frame)


def try_without_say(rep: Report, reel: Reel):
    """② "수고했어" 줄을 지우면 새해로 못 넘어간다: 연도판은 얼음빛 그대로, 흙더미는 흙 그대로, 낚는 말도 그대로."""
    say, rolled = reel.line_for(reel.t("bubble")), reel.line_for(reel.t("year_roll"))
    if say is None or not reel.state["say"]["thanked"] or rolled is None:
        rep.skip("E", "수고했어 삭제", "대본에 \"수고했어\" 한마디나 새해로 넘어가는 줄이 없음")
        return
    path, var, err = try_script("nosay", [ln["text"] for ln in reel.lines if ln is not say])
    if var is None:
        rep.add("E", "수고했어 삭제 → 시각표", False, f"대본을 그리지 못함 {err}")
        return
    # 그 한마디가 없으면, 새해로 넘기던 줄(과 같은 효과를 부르는 줄)은 전부 실패한다
    want = len(reel.failed_lines()) + sum(ln["key"] == rolled["key"] for ln in reel.lines)
    failed = len(var.failed_lines())
    rep.add("E", "수고했어 삭제 → 시각표",
            var.d["success"] is False and failed == want and var.t("year_roll") is None and var.d["swapT"] is None,
            f"success={var.d['success']} · 실패한 줄 {failed}개 (기대 {want}개: "
            + ", ".join(f"{ln['idx'] + 1}번째 '{ln['text']}'" for ln in var.failed_lines())
            + f") · year_roll {len(var.events('year_roll'))}건 · 맺는 말로 바뀌는 시각 {var.d['swapT']}", failed=failed, want=want)
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
    """③ 없는 이름을 맨 앞줄에 넣으면 렌더가 죽지 않고 그 줄에서 NameError가 나며, 낚는 말의 줄 번호가 그 줄로 바뀐다.
    화면에서도: 그 줄 앞에 빨간 ✕, 빨간 실행 막대, 낚는 말 둘째 줄이 빨개진다."""
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
    mark, bars = var.mark_at(shot, 0), var.bar_lines(shot)
    nxt = next((ln["fireAt"] for ln in var.lines[1:]), math.inf)
    want_bars = [(0, "빨강")] if nxt > var.sec(frame) else bars       # 다음 줄이 이미 돌았으면 막대는 따지지 않는다
    redder = var.hook2_redness(shot) - var.hook2_redness(hook)
    rep.add("E", "없는 이름 → 화면", mark == "error" and bars == want_bars and redder >= LIM["hook_red"],
            f"실행 0.5초 뒤(프레임 {frame}): 첫 줄 표시 {mark} (기대 error) · 실행 막대 "
            + (", ".join(f"{i + 1}번째({c})" for i, c in bars) or "없음") + " (기대 1번째(빨강)) · "
            f"낚는 말 둘째 줄 R−G {redder:+.1f} 늘어남 (기준 ≥ {LIM['hook_red']})", mark=mark, bars=bars, hook_redder=redder)


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
    """⑤ 눈송이 수를 바꾸면 같은 프레임의 하늘에 보이는 눈(글자)이 그만큼 달라진다."""
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
            f"프레임 {frame}의 제목 위 하늘(y < {reel.head_rows()[0]})에서 밝은 글자 화소 — '{line['text']}' {counts[line['args'][0]]}개 · "
            f"'{text}' {counts[n]}개 (적은 쪽 ÷ 많은 쪽 {counts[few] / max(counts[many], 1):.2f}, 기준 ≤ {LIM['snow_ratio']})", counts=counts)


def check_script_drives(rep: Report, reel: Reel):
    try_dig(rep, reel)
    try_without_say(rep, reel)
    try_unknown_name(rep, reel)
    try_fireworks(rep, reel)
    try_snow(rep, reel)


# ======================================================================== F. 안전 구역
def check_safe_zones(rep: Report, reel: Reel, pic, plan: dict):
    ed, B = reel.ed, reel.ed["B"]
    keys = sorted(k for k in plan if re.fullmatch(r"s\d{3}", k))
    shots = [(plan[k], pic(k), reel.editor_text(pic(k))) for k in keys]
    card_right = ed["cardX"] + ed["cardW"]
    b_head = (B["y"], B["y"] + B["head"])                 # newyear.js 창 머리(오른쪽 끝에 지금 값이 붙는다)

    # 앱 단추 자리: x > SAFE_RIGHT_X, y SAFE_RIGHT_Y 안의 편집기 글자. newyear.js 창 머리의 값은 따로 본다(지금 배치에서는 구역 밖).
    rows = [y for y in range(*SAFE_RIGHT_Y) if not b_head[0] <= y < b_head[1]]
    worst, brightest, hits = (0, None, None), (0.0, None), []
    for frame, img, mask in shots:
        zone = mask[rows][:, SAFE_RIGHT_X + 1 - reel.split:]
        cols = np.flatnonzero(zone.sum(axis=0) >= 2)
        if not len(cols):
            continue
        right = SAFE_RIGHT_X + 1 + int(cols[-1])
        ys = np.flatnonzero(zone[:, cols[-1]])
        y_at = rows[int(ys[len(ys) // 2])]
        hits.append(frame)
        if right > worst[0]:
            worst = (right, frame, y_at)
        lum = np.where(zone, luma(img[rows][:, SAFE_RIGHT_X + 1:].astype(np.float64)), 0)
        py, px = np.unravel_index(int(lum.argmax()), lum.shape)
        if lum[py, px] > brightest[0]:
            brightest = (float(lum[py, px]), (SAFE_RIGHT_X + 1 + int(px), rows[int(py)], frame))
    head_value = [(reel.text_right(mask, *b_head, x_from=SAFE_RIGHT_X + 1), frame) for frame, _, mask in shots]
    head_value = max(((x, f) for x, f in head_value if x is not None), default=(None, None))
    text = (f"x > {SAFE_RIGHT_X}, y {SAFE_RIGHT_Y[0]}~{SAFE_RIGHT_Y[1]}에 편집기 글자가 있는 프레임 {len(hits)}/{len(shots)}장"
            + (f" — 가장 오른쪽 x={worst[0]} (프레임 {worst[1]} = {reel.sec(worst[1]):.2f}초, y {worst[2]}, {reel.pane_of(worst[2])} 창) · "
               f"가장 밝은 글자 화소 휘도 {brightest[0]:.0f} at ({brightest[1][0]},{brightest[1][1]}) 프레임 {brightest[1][2]} "
               f"({reel.pane_of(brightest[1][1])} 창)" if hits else "")
            + f" · 참고: 구역에서 뺀 newyear.js 창 머리(y {b_head[0]}~{b_head[1]})의 지금 값은 x {head_value[0]}까지"
            + (f"(프레임 {head_value[1]})" if head_value[1] is not None else "")
            + f" · 0.5초마다 + 줄마다 실행 0.2초 뒤 프레임 {len(shots)}장")
    rep.add("F", "앱 단추 자리", not hits, text, frames_hit=hits, rightmost=worst[0], brightest=brightest[0],
            head_value_right=head_value[0])

    # 창 글자가 창 안에: 칸마다 (창 위·아래 끝 4px 안쪽) 글자가 닿는 가장 오른쪽 x와 창 오른쪽 끝의 여백
    margins = {}
    for name in ("A", "B", "C"):
        p = ed[name]
        ends = [(reel.text_right(mask, p["y"] + 4, p["y"] + p["h"] - 4), frame) for frame, _, mask in shots]
        x, frame = max(((x, f) for x, f in ends if x is not None), default=(None, None))
        margins[name] = dict(right=x, frame=frame, margin=None if x is None else card_right - 1 - x)
    tight = min((m["margin"] for m in margins.values() if m["margin"] is not None), default=None)
    rep.add("F", "창 글자 오른쪽 끝", tight is not None and tight >= LIM["card_margin"],
            " · ".join(f"{n} 창 글자 끝 x={m['right']} (프레임 {m['frame']}, 여백 {m['margin']}px)" for n, m in margins.items())
            + f" — 창 오른쪽 끝 {card_right - 1}, 기준 여백 ≥ {LIM['card_margin']}px", margins=margins)

    # 맨 위: 배치로 본 가장 높은 요소와, 화면에서 잰 가장 밝은 것·가장 큰 밝은 덩어리
    tops = {"제목 윗변": reel.head["y1"] - reel.head["px"] / 2, "2026.py 창 윗변": ed["A"]["y"]}
    if reel.state["yearSet"]:
        tops["연도판 윗변"] = reel.stage["BOARD"]["cy"] - reel.stage["BOARD"]["ch"] / 2
    name, y = min(tops.items(), key=lambda kv: kv[1])
    rep.add("F", "맨 위 구역(배치)", y >= SAFE_TOP_Y, f"가장 높이 놓인 요소는 {name} y={y:.0f} (기준 ≥ {SAFE_TOP_Y})", tops=tops)
    # 화면에서: 눈·불꽃처럼 움직이는 것은 3프레임 간격 세 장의 최솟값으로 지우고, 가만히 있는 밝은 것만 남겨 가장 긴 가로 줄을 잰다
    found = []
    for shot, keys3 in (("첫 장면", ("first", "first3", "first6")), ("끝 장면", ("last6", "last3", "last"))):
        zones = [luma(pic(k)[:SAFE_TOP_Y]) for k in keys3]
        length, x, yy = longest_run(np.minimum.reduce(zones) > LIM["solid"])
        py, px = np.unravel_index(int(zones[-1].argmax()), zones[-1].shape)
        found.append(dict(shot=shot, still_run=length, still_x=x, still_y=yy,
                          peak=float(zones[-1].max()), peak_x=int(px), peak_y=int(py)))
    big, peak = max(found, key=lambda f: f["still_run"]), max(found, key=lambda f: f["peak"])
    rep.add("F", "맨 위 구역(화면)", big["still_run"] <= LIM["solid_run"],
            f"y<{SAFE_TOP_Y}에서 가장 밝은 것은 {peak['shot']} ({peak['peak_x']},{peak['peak_y']}) 밝기 {peak['peak']:.0f} · "
            f"가만히 있는 밝은 것의 가장 긴 가로 줄 {big['still_run']}px"
            + (f" ({big['still_x']},{big['still_y']}) {big['shot']}" if big["still_run"] else "")
            + f" (기준 ≤ {LIM['solid_run']}px — 별·눈·불꽃 글자는 통과, 글자판·제목이면 걸린다)", zones=found)

    # 피드·프로필 격자에서는 가운데 4:5만 보인다: 제목 글자(화면에서 잰 높이)와 연도판(배치)이 그 안에 있는가
    crop_h = reel.w * FEED_RATIO[1] / FEED_RATIO[0]
    feed = ((reel.h - crop_h) / 2, (reel.h + crop_h) / 2)
    spans = {"첫 프레임 제목": reel.head_extent(pic("first")), "마지막 프레임 제목": reel.head_extent(pic("last"))}
    if reel.d["swapT"] is not None and pic("head_after") is not None:
        spans["맺는 말"] = reel.head_extent(pic("head_after"))
    if reel.state["yearSet"]:
        b = reel.stage["BOARD"]
        spans["연도판"] = (b["cy"] - b["ch"] / 2, b["cy"] + b["ch"] / 2)
    inside = all(v is not None and feed[0] <= v[0] and v[1] <= feed[1] for v in spans.values())
    rep.add("F", "피드 4:5 화면", inside,
            " · ".join(f"{k} y " + (f"{v[0]:.0f}~{v[1]:.0f}" if v else "안 보임") for k, v in spans.items())
            + f" — 보이는 범위 y {feed[0]:.0f}~{feed[1]:.0f}", spans=spans, feed=feed)


def spans_of(frames: list[int]) -> str:
    """[273, 274, 275, 300] → '273~275, 300'."""
    out, run_ = [], []
    for f in sorted(frames):
        if run_ and f != run_[-1] + 1:
            out.append(run_)
            run_ = []
        run_.append(f)
    if run_:
        out.append(run_)
    return ", ".join(f"{r[0]}~{r[-1]}" if len(r) > 1 else str(r[0]) for r in out)


def check_header_overlap(rep: Report, reel: Reel, strip: np.ndarray | None):
    """newyear.js 창 머리: 왼쪽 위치 글자와 오른쪽 정렬된 지금 값이 겹치지 않는다 — 영상의 모든 프레임에서(header_gaps).
    시각표로 보아 값이 떠 있어야 하는 구간(value_windows)에서 값을 못 찾거나, 값은 있는데 맞는 위치 글자 기준이 없으면 실패다(생략이 아니라)."""
    if strip is None or len(strip) != reel.frames:
        rep.add("F", "newyear.js 머리 겹침", False, "MP4에서 창 머리 띠를 풀지 못했거나 프레임 수가 시각표와 다름")
        return
    found = header_gaps(reel, strip)
    rows, has = found["rows"], found["has_value"]
    must = sorted({f for t0, t1, _ in reel.value_windows() for f in range(reel.after(t0), reel.at(t1) + 1)})
    missing = [f for f in must if not has[f]]
    unmatched = [f for f, g in rows.items() if g is None]
    gaps = {f: g for f, g in rows.items() if g is not None}
    bad = sorted(f for f, g in gaps.items() if g[0] < LIM["crumb_gap"])
    if not gaps:
        rep.add("F", "newyear.js 머리 겹침", False,
                f"지금 값이 뜬 프레임을 하나도 못 찾음 (값이 떠 있어야 하는 프레임 {len(must)}장: " + spans_of(must) + ")")
        return
    f_min = min(gaps, key=lambda f: gaps[f][0])
    g_min = gaps[f_min]
    worst = {}
    for f in bad:                                           # 겹친 구간마다 가장 깊은 겹침
        worst.setdefault(gaps[f][1:], []).append(f)
    text = (f"영상 전체 {reel.frames}장 중 값이 뜬 프레임 {len(gaps) + len(unmatched)}장 · 가장 좁은 틈 {g_min[0]:+d}px "
            f"(프레임 {f_min} = {reel.sec(f_min):.2f}초: 위치 글자 끝 x={g_min[1]}, 값 시작 x={g_min[2]}) · 기준 ≥ {LIM['crumb_gap']}px · "
            f"모자란 프레임 {len(bad)}장" + (" — " + " · ".join(
                f"{spans_of(fs)}({reel.sec(fs[0]):.2f}~{reel.sec(fs[-1]):.2f}초) 틈 {gaps[fs[0]][0]:+d}px (위치 글자 끝 x={k[0]}, 값 시작 x={k[1]})"
                for k, fs in worst.items()) if bad else "")
            + f" · 위치 글자 기준(값 없는 프레임) {len(found['refs'])}가지"
            + (f" · 값이 떠 있어야 하는데 못 찾은 프레임 {len(missing)}장: {spans_of(missing)}" if missing else "")
            + (f" · 맞는 위치 글자 기준이 없는 프레임 {len(unmatched)}장: {spans_of(unmatched)}" if unmatched else ""))
    rep.add("F", "newyear.js 머리 겹침", not bad and not missing and not unmatched, text,
            narrowest=g_min[0], frame=f_min, bad_frames=bad, missing=missing, unmatched=unmatched,
            refs=found["refs"], must_frames=len(must))


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


def check_audio(rep: Report, mp4: Path, reel: Reel, video: dict, audio: dict | None):
    if audio is None:
        rep.skip("G", "음량·침묵 구간", "소리 줄기 없음(무음 영상)")
    else:
        lufs, peak = loudness(mp4)
        lo, hi = LIM["lufs"]
        rep.add("G", "통합 음량", lo <= lufs <= hi, f"{lufs:.1f} LUFS (기준 {lo}~{hi})", lufs=lufs)
        rep.add("G", "트루 피크", peak <= LIM["true_peak"], f"{peak:.1f} dBTP (기준 ≤ {LIM['true_peak']})", true_peak=peak)

        # 침묵 구간: 실패 도장이 찍히고 0.35초 뒤부터 그다음 줄이 실행될 때까지. 음악은 끊기고 디버거 '틱'만 남는 정적.
        jam, stamp = reel.t("jam"), reel.t("stamp")
        start = None if stamp is None else stamp + 0.35
        nxt = None if start is None else next((e["t"] for e in reel.d["events"]
                                               if e["type"] in ("enter", "enter_error") and e["t"] > start), None)
        if nxt is None:
            rep.skip("G", "도장 뒤 침묵", "걸리는 장면이나 그 뒤에 실행되는 줄이 없음")
        else:
            rate = int(SPEC["audio"][1])
            raw = run(["ffmpeg", "-v", "error", "-i", mp4, "-map", "0:a:0", "-ac", "2", "-ar", rate, "-f", "f32le", "-"], check=True).stdout
            pcm = np.frombuffer(raw, np.float32).reshape(-1, 2)
            quiet = rms_db(pcm, rate, start, nxt)
            loud = rms_db(pcm, rate, max(0.0, jam - 2.0), jam)
            line = next((ln for ln in reel.lines if abs(ln["fireAt"] - nxt) < 1e-3), None)
            rep.add("G", "도장 뒤 침묵", loud - quiet >= LIM["silence_db"],
                    f"도장 0.35초 뒤 {start:.2f}초 ~ 다음 줄 실행 {nxt:.2f}초" + (f"('{line['text']}')" if line else "")
                    + f" RMS {quiet:.1f} dB · 걸리기 전 2초 {loud:.1f} dB → 차이 {loud - quiet:.1f} dB (기준 ≥ {LIM['silence_db']})",
                    quiet_db=quiet, loud_db=loud, window=(start, nxt))

    # 효과음판: 같은 영상에 가락을 뺀 소리를 입힌 파일. 소리가 AAC이고 길이가 본판과 같아야 한다.
    if not FX_VIDEO.exists():
        rep.add("G", "효과음판", False, f"{FX_VIDEO.name} 이 없음 — python3 audio.py 로 다시 만드세요")
        return
    fx = probe(FX_VIDEO)
    if fx is None:
        rep.add("G", "효과음판", False, f"{FX_VIDEO.name} 을 읽을 수 없음")
        return
    fv, fa = fx
    dur, fdur = float(video["duration"]), float(fv["duration"])
    if fa is None:
        rep.add("G", "효과음판", False, f"{FX_VIDEO.name}: 소리 줄기 없음 (영상 {fdur:.3f}초)")
        return
    ref = float(audio["duration"]) if audio else dur
    adur = float(fa["duration"])
    ok = (fa["codec_name"], fa["sample_rate"], fa["channels"]) == SPEC["audio"] and abs(adur - ref) <= 0.05 and abs(fdur - dur) <= 0.02
    rep.add("G", "효과음판", ok,
            f"{FX_VIDEO.name}: 소리 {fa['codec_name']} {fa['sample_rate']}Hz {fa['channels']}ch {adur:.3f}초 "
            f"(본판 소리 {ref:.3f}±0.05) · 영상 {fv['codec_name']} {fdur:.3f}초 (본판 {dur:.3f}±0.02)",
            fx_audio=dict(codec=fa["codec_name"], duration=adur), fx_video_duration=fdur)


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
    font, _ = label_font(24)
    sheet = Image.new("RGB", (tile_w * len(shots), tile_h + band), (12, 16, 34))
    draw = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(shots):
        sheet.paste(Image.fromarray(img).resize((tile_w, tile_h), Image.LANCZOS), (i * tile_w, band))
        draw.text((i * tile_w + 10, 10), label, font=font, fill=(238, 243, 255))
    sheet.save(out, optimize=True)


def write_review_images(reel: Reel, frames: dict[int, np.ndarray]) -> list[str]:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    for old in FRAMES_DIR.glob("rep_*.png"):
        old.unlink()
    korean = label_font(24)[1]
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
        check_header_overlap(rep, reel, decode_strip(mp4, reel))
        images = write_review_images(reel, frames)
    check_audio(rep, mp4, reel, video, audio)
    shutil.rmtree(TMP, ignore_errors=True)

    failed = rep.failed()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / "verify_report.json").write_text(json.dumps(dict(
        file=mp4.name, events=str(EVENTS.relative_to(ROOT)), script=reel.d["script"], video=video, audio=audio,
        frames={k: v for k, v in plan.items() if v is not None}, limits=LIM, checks=rep.rows, images=images,
        all_ok=not failed), ensure_ascii=False, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
        encoding="utf-8")
    rep.table()
    done = sum(r["ok"] is not None for r in rep.rows)
    print(f"전체: {'통과' if not failed else '실패'} — 검사 {done}개 중 {done - len(failed)}개 통과, {len(failed)}개 실패"
          f" · 보고서 {FRAMES_DIR / 'verify_report.json'}")
    if failed:
        print("실패한 검사: " + " · ".join(f"{r['group']} {r['name']}" for r in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
