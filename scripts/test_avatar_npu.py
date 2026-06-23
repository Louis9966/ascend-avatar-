"""Smoke test for AvatarManager upload + NPU prepare."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/ascend-avatar")

import torch
from src.avatar_manager import AvatarManager
from src.config import Config


async def main():
    cfg = Config()
    cfg.ensure_dirs()
    manager = AvatarManager(cfg, torch.device("npu:0"))
    video_path = Path("/ascend-avatar/avatars/default_base.mp4")
    data = video_path.read_bytes()
    print(f"Uploading {len(data)} bytes")
    result = await manager.upload_video(data, "default_base.mp4")
    upload_id = result["upload_id"]
    print(f"upload_id={upload_id}, status={result['status']}")

    for i in range(180):
        await asyncio.sleep(2)
        st = manager.get_status(upload_id)
        print(f"[{i}] status={st['status']} progress={st.get('progress')} msg={st.get('message')}")
        if st["status"] in ("ready", "error"):
            break


if __name__ == "__main__":
    asyncio.run(main())
