"""Synchronous MuseTalkAvatar.prepare test on CPU with prints."""
import sys
import time
from pathlib import Path

sys.path.insert(0, "/ascend-avatar")
sys.path.insert(0, "/ascend-avatar/thg")

import torch
from src.thg_engine import MuseTalkAvatar

print("torch device:", torch.device("cpu"))
t0 = time.time()
avatar = MuseTalkAvatar(
    avatar_id="test_cpu",
    video_path=Path("/ascend-avatar/avatars/default_base.mp4"),
    model_dir=Path("/ascend-avatar/thg/models"),
    whisper_dir=Path("/ascend-avatar/thg/models/whisper_hf"),
    device=torch.device("cpu"),
    batch_size=1,
)
print("Avatar created", time.time()-t0)
t0 = time.time()
avatar.prepare()
print("Prepare done", time.time()-t0)
