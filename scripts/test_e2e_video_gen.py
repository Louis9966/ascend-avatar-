"""End-to-end upload + generate test with fallback TTS and NPU render."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/ascend-avatar")

import torch
from src.avatar_manager import AvatarManager
from src.config import Config
from src.video_gen_pipeline import VideoGenPipeline


async def main():
    cfg = Config()
    cfg.ensure_dirs()
    manager = AvatarManager(cfg, torch.device("npu:0"))
    pipeline = VideoGenPipeline(cfg, manager)

    video_path = Path("/ascend-avatar/avatars/default_base.mp4")
    data = video_path.read_bytes()
    print("Uploading video...")
    up = await manager.upload_video(data, "default_base.mp4")
    upload_id = up["upload_id"]
    print(f"upload_id={upload_id}")

    # Wait for avatar ready
    for i in range(200):
        await asyncio.sleep(2)
        st = manager.get_status(upload_id)
        print(f"[{i}] upload status={st['status']} progress={st.get('progress')} msg={st.get('message')}")
        if st["status"] in ("ready", "error"):
            break

    if manager.get_status(upload_id)["status"] != "ready":
        print("Avatar not ready")
        return

    text = "你好，欢迎使用昇腾数字人。"
    print("Submitting generation job...")
    job_id = await pipeline.submit(upload_id, text, spk_id=0)
    print(f"job_id={job_id}")

    for i in range(300):
        await asyncio.sleep(2)
        st = pipeline.get_status(job_id)
        print(f"[{i}] job status={st['status']} progress={st.get('progress')} msg={st.get('message')} tts={st.get('tts_engine_used')}")
        if st["status"] in ("done", "error"):
            break

    output = pipeline.get_output_path(job_id)
    print("Output:", output, "exists:", output.exists() if output else False)


if __name__ == "__main__":
    asyncio.run(main())
