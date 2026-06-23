# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ascend-avatar** is a real-time conversational 2D digital human system running on a single Ascend 910B NPU. The current implementation is functionally complete (Phase 7 done): a user submits text through a browser, the backend streams an LLM reply, splits it into sentences, synthesizes each sentence with TTS, renders lip-sync video frames with MuseTalk v1.5, and pushes the result to the browser via RTMP → WebRTC (MediaMTX).

Core flow: user text → streaming LLM → sentence segmentation → streaming TTS → MuseTalk THG → per-sentence RTMP stream → WebRTC playback in the browser.

Authoritative requirements live in [`README.md`](README.md); the backend architecture reference is in [`昇腾910B_2D实时对话数字人_后端推理与渲染方案.md`](昇腾910B_2D实时对话数字人_后端推理与渲染方案.md).

## Hard Constraints (do not violate)

- **Target hardware**: single Ascend 910B, exposed inside the container as `/dev/davinci7`.
- **Target container**: `swr.cn-south-1.myhuaweicloud.com/ascendhub/ascend-pytorch:24.0.0-A2-2.1.0-ubuntu20.04`.
- **No host installs**: install nothing on the host server. Do all development and verification inside the running `ascend-avatar` container.
- **Container launch flags** (reference — recreate only if the container is rebuilt):
  ```bash
  docker run -itd --privileged --net=host --ipc=host --name=ascend-avatar \
    --device=/dev/davinci7 \
    --device=/dev/davinci_manager \
    --device=/dev/devmm_svm \
    --device=/dev/hisi_hdc \
    -v /usr/local/dcmi:/usr/local/dcmi:ro \
    -v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi:ro \
    -v /usr/local/Ascend/driver/:/usr/local/Ascend/driver:ro \
    -v /usr/local/sbin/:/usr/local/sbin:ro \
    -v /data/ascend-avatar:/ascend-avatar \
    -p 8188:8188 \
    swr.cn-south-1.myhuaweicloud.com/ascendhub/ascend-pytorch:24.0.0-A2-2.1.0-ubuntu20.04 \
    /bin/bash
  ```
- **Software versions**:
  - CANN must match the host driver/firmware (host is CANN 8.0 class).
  - PyTorch 2.1.0 + torch_npu 2.1.0.
  - **NumPy < 2.0** (strict).
  - `sympy==1.12` (torch_npu dynamo crashes with the container's default sympy 1.4).
  - Python 3.9.2 in the container (despite the PRD saying 3.10.x).
- **LLM endpoint**: local MindIE service at `http://192.168.1.117:1025/v1`, model `qwen3_32b`. The external endpoint `modelhub.lgdg.cc` is unreachable from this environment; do not use it. No API key is required for the local endpoint.

## Development Environment

- The working directory inside the container is `/ascend-avatar` (mounted from `/data/ascend-avatar` on the host).
- Re-enter the container with: `docker exec -it ascend-avatar /bin/bash`.
- Verify NPU visibility before any serious work:
  ```bash
  npu-smi info
  python -c "import torch, torch_npu; print(torch_npu.npu.is_available())"
  python -c "import numpy; assert numpy.__version__ < '2', 'NumPy must be < 2.0'"
  ```
- Source the CANN toolkit environment and restrict NPU visibility in every shell that touches torch_npu:
  ```bash
  source /usr/local/Ascend/ascend-toolkit/set_env.sh
  export ASCEND_VISIBLE_DEVICES=7
  export ASCEND_RT_VISIBLE_DEVICES=7
  ```
- The project has no formal test suite (no pytest, no `tests/` directory). Validation is done through ad-hoc scripts in `scripts/` and module-level `if __name__ == "__main__"` blocks.

## Common Commands

All commands are meant to be run **inside the `ascend-avatar` container** from `/ascend-avatar`.

### Start the full service

```bash
bash /ascend-avatar/scripts/start.sh
```

This starts MediaMTX (RTMP/WebRTC/HLS) and then launches the WebUI. The WebUI prewarms the NPU compile cache, which takes **~7–8 minutes** on first start.

### Install / refresh Python dependencies

```bash
export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
pip install --no-cache-dir -r /ascend-avatar/config/requirements.txt
```

### Run the WebUI directly (for debugging)

```bash
export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
export ASCEND_VISIBLE_DEVICES=7
export ASCEND_RT_VISIBLE_DEVICES=7
cd /ascend-avatar
python -m src.webui
```

### Run module smoke tests

Each module has a self-contained `__main__` block. These are useful for quick verification but do not replace a test suite:

```bash
# LLM streaming smoke test
python -m src.llm_client

# TTS smoke test
python -m src.tts_engine

# THG end-to-end render (requires NPU prewarm)
python -m src.thg_engine

# Full pipeline (LLM → TTS → THG → RTMP)
python -m src.pipeline
```

### Run ad-hoc benchmarks

```bash
# THG render benchmark (two passes, NPU)
python /ascend-avatar/scripts/benchmark_thg_npu.py

# RTMP streaming smoke test
python /ascend-avatar/scripts/test_stream.py
```

### Verify services are up

```bash
# MediaMTX
pgrep -x mediamtx

# WebUI
pgrep -f "src.webui"

# Basic HTTP checks
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8188/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8188/api/chat
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8188/gradio/
```

## High-Level Architecture

The runtime is a single Python process built around a long-lived `ConversationPipeline`:

1. **HTTP entry**: `src/webui.py` builds a FastAPI app.
   - `/` serves a custom chat HTML/JS page.
   - `/api/chat` is an SSE endpoint that accepts `text`, `voice`, `lang`, and `max_tokens` query parameters and returns a stream of pipeline events.
   - `/gradio/` mounts a minimal Gradio admin panel via Starlette `Mount`.
2. **Pipeline** (`src/pipeline.py`): one `ConversationPipeline` instance is created at startup and reused across requests. It prewarms the NPU graphs once and maintains conversation history.
3. **Streaming flow** per request:
   - LLM streams deltas via `src/llm_client.py`.
   - `src/utils.py::segment_text` flushes sentence-ending chunks.
   - Each sentence is sent to `src/tts_engine.py` (edge-tts) to produce a WAV file.
   - `src/thg_engine.py` renders lip-sync BGR frames from the WAV via MuseTalk v1.5.
   - `src/streaming.py::RTMPStreamer` pipes frames through `ffmpeg` to a per-sentence RTMP path on the local MediaMTX server.
   - The frontend receives a `stream_ready` SSE event containing the WebRTC URL and switches the player from the idle loop video to the WebRTC iframe.
4. **Avatar assets**: `MuseTalkAvatar.prepare()` precomputes face boxes, masks, and VAE latents from `avatars/default_base.mp4` and caches them under `output/v15/avatars/default/`. This is a one-time cost per avatar.
5. **Media server**: MediaMTX (binary at `bin/mediamtx`, config at `config/mediamtx.yml`) listens on RTMP `:1935`, WebRTC `:8889`, and HLS `:8888`.

## Module Boundaries

- `src/config.py` — frozen dataclass + `load_config()` that reads `.env` files and environment variables. All paths and model parameters flow from here.
- `src/llm_client.py` — async OpenAI-compatible streaming client. Emits `(delta_text, metadata)` tuples; metadata includes `first_token_latency_ms`.
- `src/tts_engine.py` — `EdgeTTSEngine` wrapping `edge-tts`. Includes simple Chinese/English language detection and voice selection.
- `src/thg_engine.py` — `MuseTalkAvatar` wrapping MuseTalk v1.5. Handles model loading, avatar preparation, and frame-by-frame inference. Uses OpenCV Haar detection (`src/_preprocessing_patch.py`) instead of mmpose/mmcv.
- `src/streaming.py` — `RTMPStreamer` that pipes raw BGR frames into `ffmpeg` and pushes to RTMP.
- `src/pipeline.py` — `ConversationPipeline` orchestrating LLM → TTS → THG → RTMP with per-sentence event emissions.
- `src/webui.py` — FastAPI + SSE + Gradio mount. The `ConversationPipeline` is prewarmed once at startup and shared.
- `src/utils.py` — text segmentation utility.
- `src/_preprocessing_patch.py` — drop-in replacement for `musetalk.utils.preprocessing` that uses Haar cascades instead of mmpose.

## Loop Methodology

The project is meant to be built in phases defined in [`README.md`](README.md) §8. Each phase must produce a checkpoint file under `loop/checkpoints/` and update `loop/STATE.md`. Long-running tasks (model downloads, compiles) must heartbeat in `STATE.md` every 5 minutes.

Phases 0–7 are currently marked complete in `loop/STATE.md`. When adding new capabilities (e.g., replacing edge-tts with a local TTS), update `loop/STATE.md` and `loop/context_state.md` to reflect the new work stream.

## Required Deliverables

The following exist and should be kept current (from [`README.md`](README.md) §6):

- `docs/api.md` — front-end/back-end message format, event stream, error codes.
- `docs/deploy.md` — container startup steps.
- `docs/benchmark.md` — latency measurements.
- `config/.env.example` — required configuration template.
- `avatars/default.jpg` and `avatars/default_base.mp4` — default 2D avatar image and idle-loop video.
- `voices/` — built-in voice references (currently populated via edge-tts voices; no local reference files required).
- `loop/STATE.md` and `loop/checkpoints/phase_0.ok` … `phase_7.ok`.

## Key Performance Targets & Current Status

| Target | Goal | Current status |
|--------|------|----------------|
| First-frame latency | ≤1.5s from user submit to first video frame | ~1.75–3.15s; bottleneck is edge-tts network latency |
| ~20-character sentence end-to-end | <5s | ~3–5s |
| Video output | ≥25 fps, stutter-free | 25 fps achieved |
| NPU memory | ≤16 GB for one concurrent session | ~4.3 GB |

MuseTalk NPU inference uses `torch.compile(backend='npu')`. The **first compile takes ~7–8 minutes**; after prewarm, rendering is ~3.67s for 3s of audio.

## Known Pitfalls

- `torch_npu` must have `source /usr/local/Ascend/ascend-toolkit/set_env.sh` and `ASCEND_VISIBLE_DEVICES=7`/`ASCEND_RT_VISIBLE_DEVICES=7` set, or initialization fails.
- `torch.compile(backend='npu')` requires `sympy==1.12`; the container default `sympy==1.4` causes dynamo failures.
- `diffusers` contains `assert hidden_states.shape[1] == self.channels` that torch_npu cannot compile. The codebase patches this at runtime; do not remove `_preprocessing_patch.py` imports.
- `edge-tts` `pitch` parameter unit must be `Hz` (e.g., `+0Hz`), not `%`.
- MuseTalk internally uses relative paths from its repository root, so `thg_engine.py` `chdir`s to `/ascend-avatar/thg` during preparation and inference and restores the cwd afterward.
- `App.create_app(demo)` from Gradio replaces the FastAPI root route. Mount Gradio at `/gradio` with Starlette `Mount`, then explicitly register `/` and `/api/chat` on the parent FastAPI app.
- Gradio 4.44.1 `demo.launch()` blocks and hangs in this container. The app uses uvicorn directly via `uvicorn.run(app, ...)`.
- `pkill -f` may match the current command itself; prefer exact PID `kill` when stopping services.
- The local MindIE LLM endpoint at `192.168.1.117:1025/v1` is the only working LLM backend from this container.

## Server Access (for reference)

- Host: `192.168.1.117`
- User: `ascend`
- Container name: `ascend-avatar`
- Re-enter the container with: `docker exec -it ascend-avatar /bin/bash`

Work only inside the container; do not install software on the host.
