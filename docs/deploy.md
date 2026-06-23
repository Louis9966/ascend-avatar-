# ascend-avatar 部署说明

## 环境要求

- 服务器：政数局 910B（IP `192.168.1.117`）
- 可用 NPU：`/dev/davinci7`（容器内映射为 `npu:0`）
- 容器镜像：`swr.cn-south-1.myhuaweicloud.com/ascendhub/ascend-pytorch:24.0.0-A2-2.1.0-ubuntu20.04`
- 所有操作在容器内完成，不在宿主机安装服务

## 启动容器（模板）

首次创建容器时使用：

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

> 容器已存在时无需重复创建，后续用 Docker Compose 启动服务即可。

## 进入容器

Docker Compose 部署下实际容器名为 `ascend-avatar-backend`：

```bash
docker exec -it ascend-avatar-backend /bin/bash
```

> 原单一 `ascend-avatar` 容器名仅用于传统 `docker run` 启动方式。

## 安装依赖

```bash
export PATH=/ascend-avatar/bin:/home/HwHiAiUser/.local/bin:/usr/local/python3.9.2/bin:$PATH
source /usr/local/Ascend/ascend-toolkit/set_env.sh
pip install --no-cache-dir -r /ascend-avatar/config/requirements.txt
```

### PaddleSpeech 本地环境（视频生成 TTS 使用）

PaddleSpeech 基于 PaddlePaddle，昇腾 910B 无原生 NPU 后端，因此 TTS 在 CPU 运行。本地源码位于 `/ascend-avatar/PaddleSpeech`，安装要点：

```bash
# 1. 固定 aistudio-sdk 版本，避免 paddlenlp 导入失败
pip install 'aistudio-sdk==0.2.6'

# 2. 安装 CMake 3.x 与构建依赖，使用 --no-build-isolation 构建 onnxoptimizer
pip install 'cmake<4' wheel pybind11 protobuf
pip install --no-cache-dir --no-build-isolation onnxoptimizer

# 3. 安装 PaddleSpeech 源码
cd /ascend-avatar/PaddleSpeech
pip install --no-cache-dir -e .

# 4. 首次调用会自动下载 fastspeech2_aishell3 + hifigan_aishell3 模型到 ~/.paddlespeech/models/
#    离线环境请提前预置该目录。
```

`scripts/entrypoint-backend.sh` 中已包含非阻塞安装与预下载逻辑，失败时会自动回退到 edge-tts，不会阻塞后端启动。

## 启动服务（推荐：Docker Compose）

在宿主机 `/data/ascend-avatar` 目录执行：

```bash
cd /data/ascend-avatar
docker-compose up -d
```

这会启动两个 service：
- `mediamtx`：RTMP/WebRTC/HLS 媒体服务器。
- `backend`：FastAPI 后端 + 前端静态资源，NPU 预热完成后监听 `0.0.0.0:8188`。

### 查看日志

```bash
# MediaMTX
docker-compose logs -f mediamtx

# 后端（含 NPU 预热进度、uvicorn 访问日志）
docker-compose logs -f backend
```

### 停止服务

```bash
docker-compose down
```

### 重启单个 service

```bash
docker-compose restart mediamtx
docker-compose restart backend
```

## 传统启动方式（兼容性）

如果暂时不想使用 Docker Compose，仍可进入容器后执行：

```bash
bash /ascend-avatar/scripts/start.sh
```

> 注意：`start.sh` 使用 `nohup` 在后台启动 MediaMTX，日志写入 `/tmp/mediamtx.log`，不会进入 `docker logs`。

## 访问服务

- 主对话页面：`http://192.168.1.117:8188/`
- Gradio 管理面板：`http://192.168.1.117:8188/gradio/`
- SSE 端点：`http://192.168.1.117:8188/api/chat`
- 视频上传：`POST http://192.168.1.117:8188/api/upload`
- 生成任务：`POST http://192.168.1.117:8188/api/generate`
- 下载结果：`GET http://192.168.1.117:8188/api/download/{job_id}`

详见 [`docs/api.md`](api.md)。

## 配置项

可创建 `/ascend-avatar/config/.env` 覆盖默认值：

```bash
LLM_BASE_URL=http://192.168.1.117:1025/v1
LLM_MODEL=qwen3_32b
ASCEND_NPU_DEVICE=npu:0
MUSE_TALK_BATCH_SIZE=8
MUSE_TALK_FPS=25
WEBUI_PORT=8188

# MediaMTX 地址（Compose 模式下保持 127.0.0.1 即可）
MEDIAMTX_HOST=127.0.0.1
MEDIAMTX_RTMP_PORT=1935
MEDIAMTX_WEBRTC_PORT=8889

# 视频生成
VIDEO_GEN_TTS_ENGINE=paddlespeech
VIDEO_GEN_FALLBACK_TTS=True
MAX_UPLOAD_DURATION_S=30
MAX_UPLOAD_SIZE_MB=200
AVATAR_CACHE_SIZE=3

# 视频生成画质调优（Phase 9）
# THG_BLUR_RATIO 越小嘴部边缘越锐利，但过低可能出现 mask 接缝；默认 0.05
THG_EXTRA_MARGIN=10
THG_PARSING_MODE=jaw
THG_LEFT_CHEEK_WIDTH=90
THG_RIGHT_CHEEK_WIDTH=90
THG_UPPER_BOUNDARY_RATIO=0.5
THG_EXPAND=1.5
THG_BLUR_RATIO=0.05
THG_RENDER_INTERPOLATION=lanczos4
FFMPEG_CRF=18
FFMPEG_PRESET=medium

PADDLESPEECH_AM=fastspeech2_aishell3
PADDLESPEECH_VOC=hifigan_aishell3
PADDLESPEECH_LANG=zh
PADDLESPEECH_SPK_ID=0
PADDLESPEECH_DEVICE=cpu
```

## 默认形象与音色

- 默认形象：`/ascend-avatar/avatars/default.jpg`
- 默认 base 视频：`/ascend-avatar/avatars/default_base.mp4`
- 实时对话音色：由 edge-tts 提供，可在前端下拉选择。
- 视频合成音色：由 PaddleSpeech `fastspeech2_aishell3` 提供，支持 `spk_id` 0–173，可通过 `/api/voices` 查看。

## 故障排查

1. **NPU 不可用**：检查 `npu-smi info`，确认容器挂载了 `/dev/davinci7`。
2. **torch_npu 初始化失败**：确认已 `source /usr/local/Ascend/ascend-toolkit/set_env.sh` 且 `ASCEND_VISIBLE_DEVICES=7`。
3. **LLM 无响应**：确认 MindIE 服务在 `192.168.1.117:1025` 可用。
4. **edge-tts TTS 失败**：检查外网连通性，edge-tts 需访问微软服务器。
5. **PaddleSpeech TTS 失败**：检查 `aistudio-sdk==0.2.6`、`onnxoptimizer` 是否已构建、模型是否已下载到 `~/.paddlespeech/models/`。
6. **MuseTalk 预处理/渲染报 `context pointer null`**：确认 `src/avatar_manager.py` 中 `_prepare_on_device` / `_render_on_device` 已调用 `torch_npu.npu.set_device(device)`。
7. **MuseTalk 预处理失败**：确认 `install_mmlab.sh` 已成功安装依赖，且上传视频通过人脸检测。
8. **MediaMTX 启动失败**：查看 `docker-compose logs -f mediamtx`，常见问题包括端口占用或配置格式错误。
9. **Broken pipe / RTMP 推流失败**：确认 MediaMTX 已 healthy（后端会等待 healthcheck 通过后再启动）。
10. **上传/生成状态 404**：Starlette `Route` 端点需要显式接收 `Request` 并从 `request.path_params` 读取路径参数。
11. **修改 THG 清晰度参数后效果没变化**：mask 参数只在 `MuseTalkAvatar.prepare()` 时生效，已缓存的 avatar 需要删除 `output/v15/avatars/<upload_id>` 目录后重新上传/预处理，或临时设置 `force=True` 重新 prepare。
