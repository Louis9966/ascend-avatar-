from modelscope import snapshot_download
import shutil
import os

models_dir = "/ascend-avatar/thg/models"
os.makedirs(models_dir, exist_ok=True)

# Download MuseTalk weights from ModelScope
cache = snapshot_download("TMElyralab/MuseTalk")
print("MuseTalk downloaded to:", cache)

# Copy needed files to models directory
needed = [
    "musetalkV15/musetalk.json",
    "musetalkV15/unet.pth",
    "musetalk/musetalk.json",
    "musetalk/pytorch_model.bin",
]
for f in needed:
    src = os.path.join(cache, f)
    dst = os.path.join(models_dir, f)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        print(f"Copied {f}")

# SD VAE
print("Downloading SD VAE...")
cache = snapshot_download("AI-ModelScope/sd-vae-ft-mse")
for f in ["config.json", "diffusion_pytorch_model.bin"]:
    src = os.path.join(cache, f)
    dst = os.path.join(models_dir, "sd-vae", f)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        print(f"Copied sd-vae/{f}")

# Whisper
print("Downloading Whisper...")
cache = snapshot_download("OpenAI/Whisper-Tiny")
for f in ["config.json", "pytorch_model.bin", "preprocessor_config.json"]:
    src = os.path.join(cache, f)
    dst = os.path.join(models_dir, "whisper", f)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        print(f"Copied whisper/{f}")

print("Done")
