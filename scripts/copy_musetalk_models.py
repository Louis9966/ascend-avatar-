import shutil
import os

src = "/home/HwHiAiUser/.cache/modelscope/hub/models/geekane/musetalk"
dst = "/ascend-avatar/thg/models"

if not os.path.exists(src):
    print(f"Source not found: {src}")
    exit(1)

mappings = {
    "musetalk/musetalk.json": "musetalk/musetalk.json",
    "musetalk/pytorch_model.bin": "musetalk/pytorch_model.bin",
    "sd-vae-ft-mse/config.json": "sd-vae/config.json",
    "sd-vae-ft-mse/diffusion_pytorch_model.bin": "sd-vae/diffusion_pytorch_model.bin",
    "face-parse-bisent/79999_iter.pth": "face-parse-bisent/79999_iter.pth",
    "face-parse-bisent/resnet18-5c106cde.pth": "face-parse-bisent/resnet18-5c106cde.pth",
    "dwpose/dw-ll_ucoco_384.pth": "dwpose/dw-ll_ucoco_384.pth",
    "whisper/tiny.pt": "whisper/tiny.pt",
}

for s, d in mappings.items():
    s_path = os.path.join(src, s)
    d_path = os.path.join(dst, d)
    if os.path.exists(s_path):
        os.makedirs(os.path.dirname(d_path), exist_ok=True)
        shutil.copy(s_path, d_path)
        print(f"Copied {s} -> {d}")
    else:
        print(f"Missing: {s}")

print(f"\nFiles in {dst}:")
for root, dirs, files in os.walk(dst):
    for f in files:
        print(os.path.join(root, f))
