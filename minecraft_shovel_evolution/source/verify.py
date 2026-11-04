#!/usr/bin/env python3
"""완성 영상 검증 — ffprobe 규격 확인 + 대표 프레임 추출 + 텍셀 색 대조.

    python3 verify.py [영상.mp4]

1) ffprobe: 코덱 H.264, 1920x1080, 30fps, 240프레임, 8.0초, yuv420p
2) 대표 프레임 4장(1.0초 나무 / 3.0초 돌 / 5.0초 철 / 마지막 다이아)을 frames/에 PNG로 추출
3) 추출 프레임에서 삽의 모든 텍셀 중심 색을 원본 텍스처 색과 대조
   → 네 재질 중 가장 가까운 것이 기대 재질인지, 색 오차가 작은지(뭉개짐·번짐 없음) 확인
4) 전환 구간 12프레임 모음(frames/transitions_sheet.png), 대표 4장 모음(frames/representative_sheet.png)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from render import FPS, H, NFRAMES, ORDER, W, Textures, frame_state  # noqa: E402
from scene import tex_to_screen  # noqa: E402

REP = ((30, "wooden"), (90, "stone"), (150, "iron"), (NFRAMES - 1, "diamond"))
TRANSITION_FRAMES = (57, 60, 63, 70, 117, 120, 126, 135, 177, 180, 186, 200)


def probe(mp4: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,profile,width,height,pix_fmt,r_frame_rate,"
         "avg_frame_rate,nb_read_frames,duration,display_aspect_ratio,color_space"
         ":format=duration,size,bit_rate,format_name", "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True).stdout
    j = json.loads(out)
    return {**j["streams"][0], **{f"format_{k}": v for k, v in j["format"].items()}}


def extract(mp4: Path, frames, out_paths):
    expr = "+".join(f"eq(n\\,{n})" for n in frames)
    tmp = out_paths[0].parent / "_tmp_%03d.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4), "-vf", f"select={expr}",
                    "-fps_mode", "passthrough", "-pix_fmt", "rgb24", str(tmp)], check=True)
    for i, p in enumerate(out_paths):
        (p.parent / f"_tmp_{i + 1:03d}.png").replace(p)


def texel_check(img: np.ndarray, n: int, texs: Textures) -> dict:
    st = frame_state(n, texs.anchor)
    cells = np.argwhere(texs.rgba[ORDER[0]][..., 3] > 0)
    got = []
    for r, c in cells:
        x, y = tex_to_screen(c + 0.5, r + 0.5, st["cx"], st["cy"], st["texel"], st["angle"],
                             texs.anchor)
        xi, yi = int(round(x)), int(round(y))
        got.append(img[yi - 2:yi + 3, xi - 2:xi + 3].reshape(-1, 3).mean(0))
    got = np.array(got)
    err = {}
    for name in ORDER:
        exp = texs.rgba[name][cells[:, 0], cells[:, 1], :3] * 255
        err[name] = np.abs(got - exp).max(1)        # 텍셀별 최대 채널 오차
    best = min(ORDER, key=lambda k: err[k].mean())
    return dict(frame=n, time_s=round(n / FPS, 3), center=(st["cx"], st["cy"]),
                texel_px=round(st["texel"], 3), angle_deg=round(st["angle"], 3),
                texels=len(cells), best_match=best,
                mean_err=round(float(err[best].mean()), 2), max_err=round(float(err[best].max()), 2),
                err_vs_others={k: round(float(v.mean()), 1) for k, v in err.items() if k != best})


def sheet(paths, cols, w, h, out):
    rows = (len(paths) + cols - 1) // cols
    s = Image.new("RGB", (cols * w, rows * h))
    for i, p in enumerate(paths):
        s.paste(Image.open(p).resize((w, h), Image.BILINEAR), ((i % cols) * w, (i // cols) * h))
    s.save(out, optimize=True)


def main():
    root = HERE.parent
    mp4 = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "minecraft_shovel_evolution.mp4"
    fdir = root / "frames"
    fdir.mkdir(exist_ok=True)
    info = probe(mp4)
    dur = float(info["format_duration"])
    checks = {
        "codec h264": info["codec_name"] == "h264",
        "1920x1080": (info["width"], info["height"]) == (W, H),
        "16:9": info.get("display_aspect_ratio") in ("16:9", None),
        "30fps": info["r_frame_rate"] == "30/1" and info["avg_frame_rate"] == "30/1",
        "240 frames": int(info["nb_read_frames"]) == NFRAMES,
        "8.0 s": abs(dur - 8.0) < 0.05,
        "yuv420p": info["pix_fmt"] == "yuv420p",
    }

    texs = Textures()
    rep_paths = [fdir / f"rep_{i + 1}_{name}_f{n:03d}.png" for i, (n, name) in enumerate(REP)]
    extract(mp4, [n for n, _ in REP], rep_paths)
    texel = []
    for (n, name), p in zip(REP, rep_paths):
        r = texel_check(np.asarray(Image.open(p).convert("RGB"), np.float32), n, texs)
        r["expected"] = name
        r["ok"] = r["best_match"] == name and r["max_err"] < 16
        texel.append(r)
        checks[f"frame {n} = {name} shovel"] = r["ok"]
    same_geom = len({(r["texel_px"], r["angle_deg"]) for r in texel}) == 1
    checks["same size & axis in all 4 frames"] = same_geom
    checks["4 textures share one silhouette"] = texs.same_silhouette

    tr_paths = [fdir / f"_tr_{n:03d}.png" for n in TRANSITION_FRAMES]
    extract(mp4, TRANSITION_FRAMES, tr_paths)
    sheet(tr_paths, 4, 480, 270, fdir / "transitions_sheet.png")
    for p in tr_paths:
        p.unlink()
    sheet(rep_paths, 2, 960, 540, fdir / "representative_sheet.png")

    report = dict(file=str(mp4.name), probe=info, checks=checks, texel_check=texel,
                  all_ok=all(checks.values()))
    (fdir / "verify_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"파일: {mp4}  ({int(info['format_size']) / 1e6:.2f} MB)")
    print(f"길이 {dur:.3f}s · {info['width']}x{info['height']} · {info['r_frame_rate']} fps · "
          f"{info['nb_read_frames']} 프레임 · {info['codec_name']} {info['profile']} · {info['pix_fmt']}")
    for r in texel:
        print(f"  f{r['frame']:03d} ({r['time_s']}s) 기대 {r['expected']:<7} → 판정 {r['best_match']:<7}"
              f" 텍셀 {r['texels']}개 평균오차 {r['mean_err']} 최대 {r['max_err']}"
              f"  중심{r['center']} 텍셀 {r['texel_px']}px 각도 {r['angle_deg']}°")
    for k, v in checks.items():
        print(f"  [{'OK' if v else 'NG'}] {k}")
    print("전체:", "통과" if report["all_ok"] else "실패")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
