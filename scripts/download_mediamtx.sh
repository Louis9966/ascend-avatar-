#!/bin/bash
set -e
LOG=/ascend-avatar/logs/mediamtx_download.log
exec > "$LOG" 2>&1
URL="https://github.com/bluenviron/mediamtx/releases/download/v1.11.3/mediamtx_v1.11.3_linux_arm64.tar.gz"
DST=/ascend-avatar/bin
mkdir -p "$DST"
cd /tmp
curl -L -o mediamtx.tar.gz "$URL"
tar -xzf mediamtx.tar.gz -C "$DST"
chmod +x "$DST/mediamtx"
echo "mediamtx downloaded"
ls -la "$DST"/mediamtx
