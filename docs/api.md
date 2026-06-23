# ascend-avatar 接口文档

## 运行方式

前端通过两种方式与后端交互：

1. **实时对话**：通过 `/api/chat` 的 SSE（Server-Sent Events）流式接收事件。
2. **视频生成**：通过 `/api/upload`、`/api/generate`、`/api/download/{job_id}` 等 REST 端点完成“上传视频 → 输入文本 → 生成 MP4”的两步式工作流。

Gradio 管理面板挂载在 `/gradio/`，主对话页面在 `/`。

---

## 实时对话事件（后端 → 前端）

| event | payload 字段 | 说明 |
|-------|-------------|------|
| `start` | `session_id` | 一次对话开始 |
| `llm_text` | `delta`, `text`, `first_token_latency_ms` | LLM 流式文本增量与累计文本 |
| `stream_ready` | `webrtc_url` | 当前句子的 WebRTC 播放地址已可用 |
| `combined_video` | `video_path`, `combined_video_path`, `sentence`, `first_video_latency_ms`, `end_to_end_ms` | 新的句子视频已生成，合并后的完整视频路径 |
| `done` | `text` | 整轮对话完成 |
| `error` | `message` | 发生错误 |

## 实时对话前端 → 后端

访问 SSE 端点 `/api/chat` 时通过 URL 查询参数传入：

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 用户输入（必填） |
| `voice` | string | edge-tts Voice ID，如 `zh-CN-XiaoxiaoNeural` |
| `lang` | string | `auto` / `zh` / `en` |
| `max_tokens` | int | 最大生成 token 数，默认 128 |

示例：

```bash
curl -N 'http://192.168.1.117:8188/api/chat?text=你好&lang=zh&voice=zh-CN-XiaoxiaoNeural'
```

---

## 视频生成 REST 端点

### 1. 上传源视频

`POST /api/upload`

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | multipart/file | 上传的人脸视频（建议 H.264，正面清晰人脸） |

返回：

```json
{
  "upload_id": "e9e5c2dab2c65311",
  "status": "preprocessing",
  "message": "初始化 MuseTalk Avatar...",
  "progress": 0.5
}
```

上传后会异步进行：

1. 转码为 25fps、H.264、无音轨。
2. 人脸检测（至少 80% 采样帧检测到正面人脸）。
3. MuseTalk Avatar 预处理（首次较慢，约 2 分钟）。

### 2. 查询上传状态

`GET /api/upload/status/{upload_id}`

返回：

```json
{
  "upload_id": "e9e5c2dab2c65311",
  "status": "ready",
  "message": "准备完成",
  "progress": 1.0
}
```

当 `status` 为 `ready` 时才可调用 `/api/generate`。

### 3. 提交生成任务

`POST /api/generate`

| 字段 | 类型 | 说明 |
|------|------|------|
| `upload_id` | string | 已准备好的视频 ID |
| `text` | string | 需要合成的文本（中文） |
| `spk_id` | int | PaddleSpeech 说话人 ID，默认 0（`fastspeech2_aishell3` 支持 0–173） |
| `voice_id` | string | 可选；若启用 edge-tts fallback 时使用 |

返回：

```json
{
  "job_id": "b8e2107c58bc44a3",
  "status": "queued"
}
```

生成流程：

1. 使用 PaddleSpeech `fastspeech2_aishell3` + `hifigan_aishell3` 在 CPU 上合成音频。
2. 使用 MuseTalk（NPU）渲染唇形同步视频。
3. 合成 H.264 + AAC MP4。

### 4. 查询生成任务状态

`GET /api/generate/status/{job_id}`

返回：

```json
{
  "job_id": "b8e2107c58bc44a3",
  "upload_id": "e9e5c2dab2c65311",
  "status": "done",
  "message": "生成完成",
  "progress": 1.0,
  "tts_engine_used": "paddlespeech",
  "error": null
}
```

### 5. 下载生成结果

`GET /api/download/{job_id}`

仅在 `status == "done"` 时返回 `video/mp4` 文件，否则返回 400/404 JSON 错误。

### 6. 获取可用音色

`GET /api/voices`

返回 edge-tts 与 PaddleSpeech 的可用音色列表：

```json
{
  "edge_tts": [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "中文-女声（晓晓）"},
    ...
  ],
  "paddlespeech": [
    {"id": 0, "name": "speaker_0"},
    ...
  ]
}
```

---

## 错误说明

系统内部错误通过 JSON 或 SSE `error` 事件文本返回，未单独编码。常见情况：

- LLM 服务不可达：检查 `LLM_BASE_URL` 与 MindIE 服务状态。
- TTS 失败：PaddleSpeech 模型缺失、NLTK 数据下载被拦截、或 edge-tts 网络异常。
- THG 失败：avatar 素材缺失、模型路径错误、NPU 上下文未初始化。
- 上传校验失败：视频过大（默认 200MB）、过长（默认 30s）、无人脸、转码失败。

## 静态资源

- 生成视频保存在 `/ascend-avatar/output/generated/{job_id}/output.mp4`。
- 默认 avatar 资源：`/ascend-avatar/avatars/default.jpg`、`/ascend-avatar/avatars/default_base.mp4`。
