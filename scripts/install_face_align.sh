#!/bin/bash
set -e
LOG=/ascend-avatar/logs/face_align_install.log
exec > "$LOG" 2>&1
export PATH=/usr/local/python3.9.2/bin:$PATH
pip install --no-cache-dir face-alignment==1.4.1
echo "DONE"
