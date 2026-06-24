#!/usr/bin/env python3
"""A/B sweep for MuseTalk mouth sharpness.

Vary THG_BLUR_RATIO and MUSE_TALK_BBOX_SHIFT, keep the same TTS audio, and
compare mouth ROI sharpness (Laplacian variance) across generated videos.

Run inside the ascend-avatar container with CANN env and NPU device 7:

    export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH
    source /usr/local/Ascend/ascend-toolkit/set_env.sh
    export ASCEND_VISIBLE_DEVICES=7
    export ASCEND_RT_VISIBLE_DEVICES=7
    export LD_PRELOAD=$(python -c \
        "import sklearn.utils,glob,os; p=os.path.dirname(sklearn.utils.__file__); \\
         print(glob.glob(p+'/../../scikit_learn.libs/libgomp*')[0])")
    export LD_BIND_NOW=1
    cd /ascend-avatar
    python scripts/ab_mouth_sharpness.py
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

# Project root is two levels up from scripts/ab_mouth_sharpness.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import torch_npu  # noqa: E402
from src.config import Config, load_config  # noqa: E402
from src.paddlespeech_tts_engine import PaddleSpeechTTSEngine  # noqa: E402
from src.thg_engine import MuseTalkAvatar  # noqa: E402


TEXT = "波坡摸佛吃葡萄不吐葡萄皮"
BLUR_RATIOS = [0.05, 0.03]
BBOX_SHIFTS = [0, -5, -7]
OUT_DIR = Path("/ascend-avatar/output/ab_sharpness")
FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def _mouth_roi(frame: np.ndarray) -> np.ndarray | None:
    """Return a mouth ROI from the frame using Haar face detection."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(64, 64)
    )
    if len(faces) == 0:
        return None
    # Use the largest face
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    # Mouth is roughly the lower 35% of the face, centered 80% width
    mx = int(x + w * 0.1)
    my = int(y + h * 0.55)
    mw = int(w * 0.8)
    mh = int(h * 0.35)
    mh = min(mh, frame.shape[0] - my)
    mw = min(mw, frame.shape[1] - mx)
    if mw <= 0 or mh <= 0:
        return None
    return gray[my : my + mh, mx : mx + mw]


def _video_sharpness(video_path: Path) -> tuple[float, int, int]:
    """Return (mean_laplacian_variance, frames_with_face, total_frames)."""
    cap = cv2.VideoCapture(str(video_path))
    values = []
    total = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        total += 1
        roi = _mouth_roi(frame)
        if roi is None or roi.size == 0:
            continue
        values.append(cv2.Laplacian(roi, cv2.CV_64F).var())
    cap.release()
    if not values:
        return 0.0, 0, total
    return float(np.mean(values)), len(values), total


def _video_info(video_path: Path) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    info = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    info["duration"] = info["frames"] / info["fps"] if info["fps"] else 0.0
    info["size_kb"] = int(video_path.stat().st_size / 1024)
    return info


async def main() -> None:
    cfg = load_config()
    device = torch.device(cfg.ascend_npu_device)
    torch_npu.npu.set_device(device)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- synthesize TTS once for all combos ---------------------------------
    wav_path = OUT_DIR / "tts.wav"
    tts = PaddleSpeechTTSEngine(
        am=cfg.paddlespeech_am,
        voc=cfg.paddlespeech_voc,
        lang=cfg.paddlespeech_lang,
        spk_id=cfg.paddlespeech_spk_id,
        device=cfg.paddlespeech_device,
    )
    print(f"[A/B] Synthesizing TTS once for: {TEXT!r}")
    await tts.synthesize(TEXT, wav_path)
    print(f"[A/B] TTS saved to {wav_path}")

    # --- create a reusable avatar instance ----------------------------------
    avatar = MuseTalkAvatar(
        avatar_id="default",
        video_path=cfg.avatar_video,
        model_dir=cfg.muse_model_dir,
        whisper_dir=cfg.muse_whisper_dir,
        device=device,
        batch_size=cfg.muse_batch_size,
        fps=cfg.muse_fps,
        bbox_shift=0,
        version=cfg.muse_version,
        result_dir=cfg.output_dir,
        extra_margin=cfg.thg_extra_margin,
        parsing_mode=cfg.thg_parsing_mode,
        left_cheek_width=cfg.thg_left_cheek_width,
        right_cheek_width=cfg.thg_right_cheek_width,
        upper_boundary_ratio=cfg.thg_upper_boundary_ratio,
        expand=cfg.thg_expand,
        blur_ratio=0.05,
        render_interpolation=cfg.thg_render_interpolation,
        ffmpeg_crf=cfg.ffmpeg_crf,
        ffmpeg_preset=cfg.ffmpeg_preset,
    )

    results = []
    total_combos = len(BLUR_RATIOS) * len(BBOX_SHIFTS)
    combo_idx = 0

    for blur in BLUR_RATIOS:
        for shift in BBOX_SHIFTS:
            combo_idx += 1
            label = f"blur{blur}_shift{shift}"
            output_path = OUT_DIR / f"{label}.mp4"
            print(
                f"\n[A/B] [{combo_idx}/{total_combos}] blur_ratio={blur}, bbox_shift={shift} -> {output_path}"
            )

            avatar.blur_ratio = blur
            avatar.bbox_shift = shift

            # Force re-prepare so new mask/blur and bbox shift take effect
            avatar.prepare(force=True)
            avatar.render_to_video(wav_path, output_path)

            sharpness, face_frames, total_frames = _video_sharpness(output_path)
            info = _video_info(output_path)

            # Save a sample frame for visual inspection
            cap = cv2.VideoCapture(str(output_path))
            ret, sample_frame = cap.read()
            cap.release()
            if ret:
                cv2.imwrite(str(OUT_DIR / f"{label}_frame00.png"), sample_frame)

            results.append(
                {
                    "blur_ratio": blur,
                    "bbox_shift": shift,
                    "label": label,
                    "output_path": str(output_path),
                    "sharpness_mean": round(sharpness, 2),
                    "face_frames": face_frames,
                    "total_frames": total_frames,
                    "width": info["width"],
                    "height": info["height"],
                    "fps": round(info["fps"], 2),
                    "duration": round(info["duration"], 2),
                    "size_kb": info["size_kb"],
                }
            )
            print(
                f"[A/B]   sharpness={sharpness:.2f}  frames_with_face={face_frames}/{total_frames}  "
                f"duration={info['duration']:.2f}s  size={info['size_kb']}KB"
            )

    # --- write summary CSV --------------------------------------------------
    csv_path = OUT_DIR / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    # --- print final ranking ------------------------------------------------
    print("\n[A/B] ====== Summary ======")
    print(f"{'label':<20} {'sharpness':>12} {'duration':>10} {'size_kb':>10}")
    for r in sorted(results, key=lambda x: x["sharpness_mean"], reverse=True):
        print(
            f"{r['label']:<20} {r['sharpness_mean']:>12.2f} {r['duration']:>10.2f} {r['size_kb']:>10}"
        )
    print(f"\n[A/B] CSV saved to {csv_path}")
    print(f"[A/B] Output videos saved to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
