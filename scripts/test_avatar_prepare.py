"""Poll avatar preparation status."""
import asyncio
import sys

sys.path.insert(0, "/ascend-avatar")

from src.avatar_manager import AvatarManager
from src.config import Config
import torch


async def main():
    cfg = Config()
    cfg.ensure_dirs()
    manager = AvatarManager(cfg, torch.device("cpu"))
    video_path = "/ascend-avatar/avatars/default_base.mp4"
    data = open(video_path, "rb").read()
    result = await manager.upload_video(data, "default_base.mp4")
    upload_id = result["upload_id"]
    print(f"upload_id={upload_id}")
    for i in range(30):
        await asyncio.sleep(2)
        st = manager.get_status(upload_id)
        print(f"[{i}] status={st['status']} progress={st.get('progress')} msg={st.get('message')}")
        if st["status"] in ("ready", "error"):
            break


if __name__ == "__main__":
    asyncio.run(main())
