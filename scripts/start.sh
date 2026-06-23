#!/bin/bash
# Start the ascend-avatar service inside the container.
# Usage: docker exec -it ascend-avatar bash /ascend-avatar/scripts/start.sh
#
# This script starts both MediaMTX (RTMP/WebRTC/HLS) and the WebUI.
# The WebUI prewarms the NPU compile cache (~7-8 min) before accepting requests.

set -e

export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH

# Source CANN environment so torch_npu can initialize.
if [ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]; then
    source /usr/local/Ascend/ascend-toolkit/set_env.sh
fi

# Restrict to the single NPU assigned to this container.
export ASCEND_VISIBLE_DEVICES=7
export ASCEND_RT_VISIBLE_DEVICES=7

# Default to the local MindIE endpoint if not configured.
export LLM_BASE_URL="${LLM_BASE_URL:-http://192.168.1.117:1025/v1}"
export LLM_MODEL="${LLM_MODEL:-qwen3_32b}"

# Unbuffered Python output for logging.
export PYTHONUNBUFFERED=1

cd /ascend-avatar

# Start MediaMTX (RTMP/WebRTC/HLS media server).
echo "[START] Starting MediaMTX..."
if ! pgrep -x mediamtx > /dev/null 2>&1; then
    nohup /ascend-avatar/bin/mediamtx /ascend-avatar/config/mediamtx.yml \
        > /tmp/mediamtx.log 2>&1 &
    sleep 2
    echo "[START] MediaMTX started (PID $(pgrep -x mediamtx))"
else
    echo "[START] MediaMTX already running"
fi

# Start WebUI with NPU prewarm.
echo "[START] Starting WebUI (NPU prewarm ~7-8 min)..."
python -u -m src.webui
