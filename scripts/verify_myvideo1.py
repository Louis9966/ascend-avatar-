"""End-to-end verification on MyVideo_1 with the latest quality settings."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, "/ascend-avatar")
os.chdir("/ascend-avatar")

from src.avatar_manager import AvatarManager
from src.config import Config
from src.video_gen_pipeline import VideoGenPipeline


VIDEO_PATH = Path("/ascend-avatar/sample/MyVideo_1.mp4")
TEXT = "波坡摸佛吃葡萄不吐葡萄皮"


async def main():
    cfg = Config()
    device = torch.device(cfg.ascend_npu_device)
    manager = AvatarManager(cfg, device)
    pipeline = VideoGenPipeline(cfg, manager)

    # Upload MyVideo_1 (or reuse a previously uploaded one).
    print(f"[TEST] Uploading {VIDEO_PATH}")
    file_bytes = VIDEO_PATH.read_bytes()
    info = await manager.upload_video(file_bytes, VIDEO_PATH.name)
    upload_id = info["upload_id"]
    print(f"[TEST] upload_id={upload_id}")

    # Wait for MuseTalk prepare to finish.
    for _ in range(1800):
        status = manager.get_status(upload_id)
        if status and status.get("status") == "ready":
            break
        if status and status.get("status") == "error":
            raise RuntimeError(f"Prepare failed: {status.get('message')}")
        await asyncio.sleep(2.0)
    else:
        raise RuntimeError("Timeout waiting for avatar prepare")

    print(f"[TEST] Avatar ready, submitting generation job: {TEXT!r}")
    job_id = await pipeline.submit(upload_id, TEXT)
    print(f"[TEST] job_id={job_id}")

    # Poll until completion.
    for _ in range(1800):
        st = pipeline.get_status(job_id)
        if st is None:
            raise RuntimeError("Job disappeared")
        print(
            f"[TEST] {time.strftime('%H:%M:%S')} status={st['status']} "
            f"progress={st.get('progress', 0):.2f} msg={st.get('message')}"
        )
        if st["status"] == "done":
            break
        if st["status"] == "error":
            raise RuntimeError(f"Job failed: {st.get('error')}")
        await asyncio.sleep(2.0)
    else:
        raise RuntimeError("Timeout waiting for job")

    output_path = Path(pipeline.get_output_path(job_id))
    print(f"[TEST] Output saved to {output_path}")

    # Report durations.
    probe = subprocess.run(
        [
            "/ascend-avatar/bin/ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-show_entries", "stream=codec_type,duration",
            "-of", "default=noprint_wrappers=1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    print("[TEST] ffprobe output:\n" + probe.stdout)

    # Report mouth sharpness.
    sys.path.insert(0, "/ascend-avatar/scripts")
    from ab_mouth_sharpness import _video_sharpness
    sharp, frames, _ = _video_sharpness(output_path)
    print(f"[TEST] sharpness={sharp:.2f} frames={frames}")
    return output_path


if __name__ == "__main__":
    out = asyncio.run(main())
    print("[TEST] final output:", out)
