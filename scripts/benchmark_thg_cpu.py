import time
import torch
from pathlib import Path
from src.thg_engine import MuseTalkAvatar
from src.config import Config

cfg = Config()
# Force CPU to compare speed with NPU fallback
avatar = MuseTalkAvatar(
    avatar_id=cfg.avatar_id + "_cpu",
    video_path=cfg.avatar_video,
    model_dir=cfg.muse_model_dir,
    whisper_dir=cfg.muse_whisper_dir,
    device=torch.device("cpu"),
    batch_size=cfg.muse_batch_size,
    fps=cfg.muse_fps,
)
avatar.prepare()
t0 = time.time()
avatar.render_to_video(Path("/tmp/thg_test.wav"), Path("/tmp/thg_test_cpu.mp4"))
print("CPU second render time", time.time() - t0)
