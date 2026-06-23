import time
import torch
from pathlib import Path
from src.thg_engine import MuseTalkAvatar
from src.config import Config

cfg = Config()
avatar = MuseTalkAvatar(
    avatar_id=cfg.avatar_id,
    video_path=cfg.avatar_video,
    model_dir=cfg.muse_model_dir,
    whisper_dir=cfg.muse_whisper_dir,
    device=torch.device(cfg.ascend_npu_device),
    batch_size=cfg.muse_batch_size,
    fps=cfg.muse_fps,
)
avatar.prepare()
t0 = time.time()
avatar.render_to_video(Path("/tmp/thg_test.wav"), Path("/tmp/thg_test2.mp4"))
print("second render time", time.time() - t0)
