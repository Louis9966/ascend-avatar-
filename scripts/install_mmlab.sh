#!/bin/bash
set -e
LOG=/ascend-avatar/logs/mmlab_install.log
mkdir -p /ascend-avatar/logs
exec > "$LOG" 2>&1
export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH
pip install --no-cache-dir -U setuptools wheel
pip install --no-cache-dir -U openmim face-detection==0.2.2
pip install --no-cache-dir --retries 10 --timeout 300 mmengine mmcv==2.0.1 mmdet==3.1.0 mmpose==1.1.0
echo "INSTALL_DONE"
