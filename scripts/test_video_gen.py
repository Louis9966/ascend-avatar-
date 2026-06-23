"""End-to-end video generation test using an already-prepared avatar."""
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

    upload_id = "e9e5c2dab2c65311"  # from previous upload test
    text = "你好，欢迎使用昇腾数字人。"
    job_id = await pipeline.submit(upload_id, text, spk_id=0)
    print(f"Submitted job {job_id}")

    for i in range(300):
        await asyncio.sleep(2)
        st = pipeline.get_status(job_id)
        print(f"[{i}] status={st['status']} progress={st.get('progress')} msg={st.get('message')} tts={st.get('tts_engine_used')}")
        if st["status"] in ("done", "error"):
            break

    output = pipeline.get_output_path(job_id)
    print("Output:", output, "exists:", output.exists() if output else False)


if __name__ == "__main__":
    asyncio.run(main())
