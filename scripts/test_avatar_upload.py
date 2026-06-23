"""Minimal smoke test for AvatarManager.upload_video."""
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
    print("Config loaded")
    manager = AvatarManager(cfg, torch.device("cpu"))
    print("Manager created")
    video_path = Path("/ascend-avatar/avatars/default_base.mp4")
    data = video_path.read_bytes()
    print(f"Read {len(data)} bytes")
    result = await manager.upload_video(data, "default_base.mp4")
    print("Upload returned:", result)


if __name__ == "__main__":
    asyncio.run(main())
