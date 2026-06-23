"""Phase 9 end-to-end quality verification script."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from src.avatar_manager import AvatarManager
from src.config import Config
from src.video_gen_pipeline import VideoGenPipeline


async def main():
    cfg = Config()
    device = torch.device(cfg.ascend_npu_device)
    manager = AvatarManager(cfg, device)
    pipeline = VideoGenPipeline(cfg, manager)

    base_video = cfg.avatar_video
    print(f"[verify] Using base video: {base_video}")
    file_bytes = base_video.read_bytes()

    upload_info = await manager.upload_video(file_bytes, base_video.name)
    upload_id = upload_info["upload_id"]
    print(f"[verify] upload_id={upload_id}")

    for _ in range(300):
        st = manager.get_status(upload_id)
        print(f"[verify] upload status: {st['status']} - {st.get('message','')}")
        if st["status"] == "ready":
            break
        if st["status"] == "error":
            raise RuntimeError(f"upload failed: {st.get('message')}")
        await asyncio.sleep(1)
    else:
        raise RuntimeError("upload timeout")

    text = "你好，欢迎使用数字人。今天天气真不错。"
    print(f"[verify] submitting text={text!r}")
    job_id = await pipeline.submit(upload_id, text, spk_id=0)
    print(f"[verify] job_id={job_id}")

    for _ in range(300):
        st = pipeline.get_status(job_id)
        print(f"[verify] job status: {st['status']} - {st.get('message','')} progress={st.get('progress')}")
        if st["status"] == "done":
            break
        if st["status"] == "error":
            raise RuntimeError(f"generation failed: {st.get('error')}")
        await asyncio.sleep(1)
    else:
        raise RuntimeError("generation timeout")

    out_path = pipeline.get_output_path(job_id)
    print(f"[verify] output: {out_path}")

    # Compute mouth sharpness on a few frames
    cap = cv2.VideoCapture(str(out_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[verify] total frames: {total}")
    sharpness = []
    indices = [int(total * i / 4) for i in range(1, 4)]
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        # mouth ROI estimate (center-lower face)
        h, w = frame.shape[:2]
        y1, y2 = int(h * 0.55), int(h * 0.78)
        x1, x2 = int(w * 0.38), int(w * 0.62)
        roi = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        sharpness.append(cv2.Laplacian(gray, cv2.CV_64F).var())
    cap.release()
    print(f"[verify] mouth Laplacian variance samples: {sharpness}")
    if sharpness:
        print(f"[verify] mean sharpness: {sum(sharpness)/len(sharpness):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
