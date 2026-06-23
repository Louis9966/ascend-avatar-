#!/bin/bash
set -e
LOG=/ascend-avatar/logs/whisper_download.log
exec > "$LOG" 2>&1
export PATH=/usr/local/python3.9.2/bin:$PATH
export HF_ENDPOINT=https://hf-mirror.com
python - <<'PY'
from huggingface_hub import snapshot_download
import os
dst = '/ascend-avatar/thg/models/whisper_hf'
os.makedirs(dst, exist_ok=True)
print('Downloading whisper-tiny from HF mirror...')
cache = snapshot_download('openai/whisper-tiny', local_dir=dst, resume_download=True)
print('saved to', dst)
PY
