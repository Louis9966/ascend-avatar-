#!/bin/bash
# Foreground entrypoint for the ascend-avatar backend service in Docker Compose.
# Usage: referenced by docker-compose.yml; do not run directly unless debugging.
#
# This script sources the CANN environment, restricts NPU visibility, and execs
# the WebUI process so that Python becomes PID 1 and logs go to stdout/stderr.

set -e

export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH

# Source CANN environment so torch_npu can initialize.
if [ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]; then
    source /usr/local/Ascend/ascend-toolkit/set_env.sh
fi

# Restrict to the single NPU assigned to this container.
export ASCEND_VISIBLE_DEVICES=7
export ASCEND_RT_VISIBLE_DEVICES=7

# Work around scikit-learn/libgomp "cannot allocate memory in static TLS block"
# on ARM/ubuntu20.04 by preloading the libgomp bundled with scikit-learn.
SKLEARN_GOMP=$(python -c "import sklearn, pathlib, glob; print(glob.glob(str(pathlib.Path(sklearn.__file__).parent.parent / 'scikit_learn.libs' / 'libgomp*.so*'))[0])" 2>/dev/null)
if [ -n "$SKLEARN_GOMP" ]; then
    export LD_PRELOAD="$SKLEARN_GOMP:${LD_PRELOAD}"
fi
# Force eager symbol resolution so preloaded libgomp TLS is allocated early.
export LD_BIND_NOW=1

# Unbuffered Python output for logging.
export PYTHONUNBUFFERED=1

# Default to the local MindIE endpoint if not configured.
export LLM_BASE_URL="${LLM_BASE_URL:-http://192.168.1.117:1025/v1}"
export LLM_MODEL="${LLM_MODEL:-qwen3_32b}"

cd /ascend-avatar

# Ensure system libraries required by Python packages are present.
# These are installed into the container filesystem, so they must be
# reinstalled on every container recreation.
echo "[ENTRYPOINT] Installing system dependencies..."
apt-get update
apt-get install -y libsndfile1

# Ensure Python dependencies are installed. The base image is reused across
# container recreations, so site-packages live inside the container; use a
# marker file on the mounted project directory to avoid reinstalling on every
# restart.
DEPS_MARKER="/ascend-avatar/.compose_deps_installed"
if [ ! -f "$DEPS_MARKER" ] || ! python -c "import gradio" 2>/dev/null; then
    echo "[ENTRYPOINT] Installing Python dependencies..."
    pip install --no-cache-dir -r /ascend-avatar/config/requirements.txt
    touch "$DEPS_MARKER"
fi

# Install PaddleSpeech from the local checkout so our wrapper can import it.
# This is done after requirements.txt because paddlespeech is intentionally
# omitted from the pip requirements (we want the local source tree).
# If this step fails, the backend still starts and the video-generation
# pipeline will fall back to edge-tts for TTS.
PADDLESPEECH_MARKER="/ascend-avatar/.compose_paddlespeech_installed"
if [ ! -f "$PADDLESPEECH_MARKER" ] || ! python -c "import paddlespeech" 2>/dev/null; then
    echo "[ENTRYPOINT] Installing PaddleSpeech from local source (optional)..."
    if (
        cd /ascend-avatar/PaddleSpeech
        pip install --no-cache-dir -e .
    ); then
        touch "$PADDLESPEECH_MARKER"
        echo "[ENTRYPOINT] PaddleSpeech installed."
    else
        echo "[ENTRYPOINT] WARNING: PaddleSpeech local install failed; TTS will fall back to edge-tts."
    fi
    cd /ascend-avatar
fi

# Pre-download PaddleSpeech TTS checkpoints so the first request does not
# block on network I/O. If the container is offline or the install failed,
# the pipeline falls back to edge-tts.
PADDLESPEECH_MODEL_MARKER="/ascend-avatar/.compose_paddlespeech_models_downloaded"
if [ ! -f "$PADDLESPEECH_MODEL_MARKER" ]; then
    echo "[ENTRYPOINT] Pre-downloading PaddleSpeech TTS models (optional)..."
    if python - <<'PYEOF'
import paddle
from paddlespeech.cli.tts.infer import TTSExecutor

# Use CPU; NPU backend for PaddlePaddle is not available in this container.
paddle.set_device("cpu")

tts = TTSExecutor()
tts._init_from_path(
    am="fastspeech2_aishell3",
    voc="hifigan_aishell3",
    lang="zh",
)
print("[ENTRYPOINT] PaddleSpeech models ready")
PYEOF
    then
        touch "$PADDLESPEECH_MODEL_MARKER"
    else
        echo "[ENTRYPOINT] WARNING: PaddleSpeech model download failed; TTS will fall back to edge-tts."
    fi
fi

# MediaMTX is managed as a separate Compose service; wait until its RTMP port
# is reachable before starting the NPU prewarm.
MEDIAMTX_HOST="${MEDIAMTX_HOST:-127.0.0.1}"
MEDIAMTX_RTMP_PORT="${MEDIAMTX_RTMP_PORT:-1935}"
echo "[ENTRYPOINT] Waiting for MediaMTX at ${MEDIAMTX_HOST}:${MEDIAMTX_RTMP_PORT}..."
for i in $(seq 1 60); do
    if timeout 2 bash -c "> /dev/tcp/${MEDIAMTX_HOST}/${MEDIAMTX_RTMP_PORT}" 2>/dev/null; then
        echo "[ENTRYPOINT] MediaMTX is reachable."
        break
    fi
    sleep 2
done

# MediaMTX is managed as a separate Compose service; do not start it here.
exec python -u -m src.webui
