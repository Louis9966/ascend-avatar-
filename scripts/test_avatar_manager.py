"""Smoke test for AvatarManager upload/validation (CPU only)."""
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
    manager = AvatarManager(cfg, torch.device("cpu"))
    video_path = Path("/ascend-avatar/avatars/default_base.mp4")
    data = video_path.read_bytes()
    print(f"Uploading {video_path}, size={len(data)} bytes")
    result = await manager.upload_video(data, "default_base.mp4")
    print("Upload result:", result)

    upload_id = result["upload_id"]
    # Poll status
    for _ in range(120):
        status = manager.get_status(upload_id)
        print("Status:", status)
        if status["status"] in ("ready", "error"):
            break
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
