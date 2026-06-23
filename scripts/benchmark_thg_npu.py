import asyncio
import time
import torch
from pathlib import Path
from src.thg_engine import MuseTalkAvatar
from src.tts_engine import EdgeTTSEngine
from src.config import Config

async def main():
    cfg = Config()
    device = torch.device("npu:0")
    avatar = MuseTalkAvatar(
        avatar_id=cfg.avatar_id,
        video_path=cfg.avatar_video,
        model_dir=cfg.muse_model_dir,
        whisper_dir=cfg.muse_whisper_dir,
        device=device,
        batch_size=cfg.muse_batch_size,
        fps=cfg.muse_fps,
    )
    avatar.prepare()
    tts = EdgeTTSEngine(voice="zh-CN-XiaoxiaoNeural")
    wav = await tts.synthesize("你好，这是数字人测试。", "/tmp/thg_test.wav")

    for i in range(2):
        out = Path(f"/tmp/thg_test_render_{i}.mp4")
        t0 = time.time()
        avatar.render_to_video(Path(wav), out)
        print(f"render {i} time", time.time() - t0)

if __name__ == "__main__":
    asyncio.run(main())
