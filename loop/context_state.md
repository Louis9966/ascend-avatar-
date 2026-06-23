# ascend-avatar 上下文状态快照

> 本文件在上下文压缩前/关键节点更新，记录关键事实与未完成任务，避免压缩后丢失。

---

## 2026-06-23 17:49 最新快照

### 刚完成
- 用户要求将整个代码仓库（包括 `loop`）推送到 `https://github.com/Louis9966/ascend-avatar-.git`，并提供了 GitHub token。
- 评估仓库体积后发现无法直接推送全部内容（`thg/` 7.8GB、`venv/` ~1GB、`output/` 602MB、`bin/` 133MB、`PaddleSpeech/` 134MB 等），因此创建了 `.gitignore`，仅包含代码、配置、文档、`loop`、前端和小体积默认素材。
- 创建了 `scripts/push_github.sh`，通过 `GH_TOKEN` 环境变量读取 token，并使用临时 credential 文件安全推送。
- 尝试执行 `git init` 时被 Claude Code auto mode classifier 拦截（理由：批量推送到外部 GitHub 目标存在数据外泄风险），即使已获用户授权仍无法在当前会话执行任何 git 命令。
- 向用户提供了手动推送命令：
  ```bash
  cd /data/ascend-avatar
  GH_TOKEN=<token> bash scripts/push_github.sh
  ```
  或直接在对话中使用 `! GH_TOKEN=<token> bash /data/ascend-avatar/scripts/push_github.sh`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-23 17:49:21。

### 当前未完成任务
- [ ] 由用户执行推送脚本，将 ascend-avatar 仓库推送到 GitHub。
- [x] 其他 Phase 8 任务已完成。

### 已知坑（新增/确认）
- 当前 Claude Code 环境禁止执行 `git` 命令，推送需在用户本地终端或通过 `!` 前缀在对话中执行。
- GitHub token 不应写入仓库；推送脚本使用环境变量 + 临时凭证文件，完成后自动清理。
- 由于 GitHub 单文件/推送大小限制，模型权重、生成视频、虚拟环境、外部源码树（PaddleSpeech/MuseTalk）等未纳入推送；`.gitignore` 已做排除。

*更新时间：2026-06-23 17:49*

---

## 2026-06-23 17:12 最新快照

### 刚完成
- 用户调用 ascend-avatar context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-23 17:12:34。
- 自 2026-06-23 17:12 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-23 17:12 快照中的已完成状态。
  - [x] 更新 `docs/api.md` 以反映新增的视频生成 REST 端点。
  - [x] 更新 `docs/deploy.md` 以补充 Docker Compose 容器名、PaddleSpeech 环境、视频生成工作流说明。
  - [x] 将 `loop/STATE.md` 中 Phase 8 标记为完成。

### 已知坑
- 无新增；保持 2026-06-23 17:12 快照中的已知坑清单。

*更新时间：2026-06-23 17:12*

---

## 2026-06-23 17:12 最新快照

### 刚完成
- 修复 `src/config.py` 中 `avatar_cache_size` 默认值为字符串导致 `_trim_cache` 类型错误的问题。
- 修复 `src/webui.py` 中 Starlette `Route` 挂载的状态/下载端点未显式接收 `Request` 的问题（`upload_status`、`generate_status`、`download_video`）。
- 修复 `src/avatar_manager.py` 中 MuseTalk 预处理与渲染在线程池执行时缺少 NPU 上下文的问题，新增 `_prepare_on_device` / `_render_on_device`。
- 重启 `ascend-avatar-backend` 服务并等待 NPU 预热完成。
- 使用 `/api/upload` 成功上传 `default_base.mp4`，`upload_id=e9e5c2dab2c65311`，MuseTalk 预处理完成（status=ready）。
- 使用 `/api/generate` 提交 `text=你好，欢迎使用 PaddleSpeech 本地语音合成。`、`spk_id=0`，`tts_engine_used=paddlespeech`，生成成功，`job_id=b8e2107c58bc44a3`。
- 通过 `/api/download/b8e2107c58bc44a3` 下载并验证 MP4：H.264 512×512、25fps、时长 4.4s、AAC 16kHz mono。
- 直接测试 PaddleSpeech CPU TTS（warm 后）约 27s/16 中文字符。
- 更新 `loop/STATE.md` 心跳与 Phase 8 状态/指标。

### 当前未完成任务
- [x] 更新 `docs/api.md` 以反映新增的视频生成 REST 端点。
- [x] 更新 `docs/deploy.md` 以补充 Docker Compose 容器名、PaddleSpeech 环境、视频生成工作流说明。
- [x] 将 `loop/STATE.md` 中 Phase 8 标记为完成。

### 已知坑（新增/确认）
- Docker Compose 部署下实际容器名为 `ascend-avatar-backend`，不是 CLAUDE.md 中描述的单一 `ascend-avatar` 容器。
- Starlette `Route` 挂载的纯函数端点需要显式接收 `Request`，不能依赖 FastAPI 参数绑定。
- 在线程池中执行 `torch_npu` 运算前必须调用 `torch_npu.npu.set_device(device)` 建立 NPU 上下文。
- PaddleSpeech 安装需 `aistudio-sdk==0.2.6`、`cmake<4` + `--no-build-isolation` 构建 `onnxoptimizer`。
- scikit-learn 静态 TLS 问题通过预加载 sklearn-bundled `libgomp` 与 `LD_BIND_NOW=1` 解决。

*更新时间：2026-06-23 17:12*

---

## 2026-06-23 15:48 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-23 15:48:30。
- 自 2026-06-23 15:18 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-23 15:18 快照中的未完成任务清单。
  - [ ] 终止/跳过挂起的预下载进程，进入容器修复 PaddleSpeech 依赖。
  - [ ] 降级 `aistudio-sdk` 到 0.2.6（或兼容版本），修复 `paddlenlp` 导入。
  - [ ] 重新安装/构建 `onnxoptimizer`，完成 PaddleSpeech 本地安装。
  - [ ] 重新预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 验证 PaddleSpeech CPU TTS 推理成功。
  - [ ] 使用 PaddleSpeech TTS 重新跑通视频生成端到端链路。
  - [ ] 之后重启后端并验证前端页面与所有新 API。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑
- 无新增；保持 2026-06-23 15:18 快照中的已知坑清单。

*更新时间：2026-06-23 15:48*

---

## 2026-06-23 15:18 最新快照

### 刚完成
- 用户询问上次验证状态；回复并复核当前运行情况。
- 确认最新一次 Phase 8 端到端验证仍为 2026-06-22 12:59 的结果：
  - 输出文件 `/ascend-avatar/output/generated/51234c64a4604051/output.mp4`（60 KB）与 `tts.wav`（97 KB）均仍在。
  - 生成格式为 H.264 512×512 + AAC mono，时长约 3.1 s，与输入文本匹配。
- 服务健康检查（在 `ascend-avatar-backend` 容器内）：
  - WebUI（`src.webui`）、`entrypoint-backend`、MediaMTX 进程均在线。
  - `/`、`/api/chat`、`/api/voices` 均返回 HTTP 200。
- 复核发现：容器内 `ffprobe` 不在默认 PATH 中（命令未找到），如需媒体探针应使用 `/ascend-avatar/bin/ffprobe`。

### 当前未完成任务
- 无新增；保持 2026-06-23 14:56 快照中的未完成任务清单。
  - [ ] 终止/跳过挂起的预下载进程，进入容器修复 PaddleSpeech 依赖。
  - [ ] 降级 `aistudio-sdk` 到 0.2.6（或兼容版本），修复 `paddlenlp` 导入。
  - [ ] 重新安装/构建 `onnxoptimizer`，完成 PaddleSpeech 本地安装。
  - [ ] 重新预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 验证 PaddleSpeech CPU TTS 推理成功。
  - [ ] 使用 PaddleSpeech TTS 重新跑通视频生成端到端链路。
  - [ ] 之后重启后端并验证前端页面与所有新 API。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑（新增/确认）
- Docker Compose 部署下实际容器名为 `ascend-avatar-backend`，不是 CLAUDE.md 中描述的单一 `ascend-avatar` 容器。
- 容器内 `ffprobe` 需显式使用 `/ascend-avatar/bin/ffprobe`，默认 PATH 找不到。
- 其他已知坑保持 2026-06-23 14:56 快照不变。

*更新时间：2026-06-23 15:18*

---

## 2026-06-23 14:56 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-23 14:56:35。
- 自 2026-06-23 10:18 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-23 10:18 快照中的未完成任务清单。
  - [ ] 终止/跳过挂起的预下载进程，进入容器修复 PaddleSpeech 依赖。
  - [ ] 降级 `aistudio-sdk` 到 0.2.6（或兼容版本），修复 `paddlenlp` 导入。
  - [ ] 重新安装/构建 `onnxoptimizer`，完成 PaddleSpeech 本地安装。
  - [ ] 重新预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 验证 PaddleSpeech CPU TTS 推理成功。
  - [ ] 使用 PaddleSpeech TTS 重新跑通视频生成端到端链路。
  - [ ] 之后重启后端并验证前端页面与所有新 API。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑
- 无新增；保持 2026-06-23 10:18 快照中的已知坑清单。

*更新时间：2026-06-23 14:56*

---

## 2026-06-23 10:18 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-23 10:18:26。
- 自 2026-06-23 09:48 快照以来，无新增对话内容、事实、任务或修复。
- 上下文因连续调试轮次较长，触发压缩建议。

### 当前未完成任务
- 无新增；保持 2026-06-23 09:28 快照中的未完成任务清单。
  - [ ] 终止/跳过挂起的预下载进程，进入容器修复 PaddleSpeech 依赖。
  - [ ] 降级 `aistudio-sdk` 到 0.2.6（或兼容版本），修复 `paddlenlp` 导入。
  - [ ] 重新安装/构建 `onnxoptimizer`，完成 PaddleSpeech 本地安装。
  - [ ] 重新预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 验证 PaddleSpeech CPU TTS 推理成功。
  - [ ] 使用 PaddleSpeech TTS 重新跑通视频生成端到端链路。
  - [ ] 之后重启后端并验证前端页面与所有新 API。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑
- 无新增；保持 2026-06-23 09:28 快照中的已知坑清单。

*更新时间：2026-06-23 10:18*

---

## 2026-06-23 09:48 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-23 09:48:30。
- 自 2026-06-23 09:28 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-23 09:28 快照中的未完成任务清单。
  - [ ] 终止/跳过挂起的预下载进程，进入容器修复 PaddleSpeech 依赖。
  - [ ] 降级 `aistudio-sdk` 到 0.2.6（或兼容版本），修复 `paddlenlp` 导入。
  - [ ] 重新安装/构建 `onnxoptimizer`，完成 PaddleSpeech 本地安装。
  - [ ] 重新预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 验证 PaddleSpeech CPU TTS 推理成功。
  - [ ] 使用 PaddleSpeech TTS 重新跑通视频生成端到端链路。
  - [ ] 之后重启后端并验证前端页面与所有新 API。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑
- 无新增；保持 2026-06-23 09:28 快照中的已知坑清单。

*更新时间：2026-06-23 09:48*

---

## 2026-06-23 09:28 最新快照

### 刚完成
- 按用户要求重启 `ascend-avatar-backend` 容器以加载新 WebUI/API 代码。
- 监控入口脚本执行：
  - PaddleSpeech 本地安装已失败（`onnxoptimizer` 构建失败），符合预期。
  - 入口脚本进入可选的 PaddleSpeech 模型预下载，PID 392 持续运行约 22 分钟但无网络连接、无模型文件写入，判定为挂起/极慢重试。
- 在并行排查中确认 PaddleSpeech 环境的两个核心阻塞点：
  1. `onnxoptimizer` 仍未安装成功。
  2. `paddlenlp` 导入失败：`aistudio-sdk==0.3.8` 的 `aistudio_sdk.hub` 已移除 `download`；`aistudio-sdk==0.2.6` / `0.1.7` 仍保留该函数，可降级修复。
- 之前担心的 `g2p_en` NLTK 数据问题已自动解决（`averaged_perceptron_tagger` + `cmudict` 下载成功）。
- 容器内 `cmake` 实际版本为 4.3.4（pip 安装），早前 CMake 版本不足的报错可能已不适用，但 `onnxoptimizer` 仍因其他原因未构建成功。

### 当前未完成任务
- [ ] 终止/跳过挂起的预下载进程，进入容器修复 PaddleSpeech 依赖。
- [ ] 降级 `aistudio-sdk` 到 0.2.6（或兼容版本），修复 `paddlenlp` 导入。
- [ ] 重新安装/构建 `onnxoptimizer`，完成 PaddleSpeech 本地安装。
- [ ] 重新预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
- [ ] 验证 PaddleSpeech CPU TTS 推理成功。
- [ ] 使用 PaddleSpeech TTS 重新跑通视频生成端到端链路。
- [ ] 之后重启后端并验证前端页面与所有新 API。
- [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑（新增/确认）
- PaddleSpeech 模型预下载脚本在容器内可能长时间挂起（无网络活动、无文件写入），需人工介入或增加超时机制。
- `aistudio-sdk>=0.3.x` 与当前 `paddlenlp` 不兼容，必须降级到 0.2.x/0.1.x 才能导入 `paddlespeech` 的 NLP 相关模块。
- 即使 `paddlespeech` 包本身可部分导入，缺少 `onnxoptimizer` 仍会导致完整安装失败，可能在推理阶段暴露问题。

*更新时间：2026-06-23 09:28*

---

## 2026-06-22 21:19 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-22 21:19:41。
- 自 2026-06-22 21:04 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-22 21:05 快照中的未完成任务清单。
  - [ ] 补齐容器内 PaddleSpeech 完整运行环境。
  - [ ] 使用 PaddleSpeech 本地 TTS 重新跑通端到端视频生成。
  - [ ] 预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 重启后端容器并验证前端页面所有新接口。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑
- 无新增；保持 2026-06-22 21:05 快照中的已知坑清单。

*更新时间：2026-06-22 21:19*

---

## 2026-06-22 21:04 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-22 21:04:41。
- 自 2026-06-22 21:05 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-22 21:05 快照中的未完成任务清单。
  - [ ] 补齐容器内 PaddleSpeech 完整运行环境。
  - [ ] 使用 PaddleSpeech 本地 TTS 重新跑通端到端视频生成。
  - [ ] 预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型。
  - [ ] 重启后端容器并验证前端页面所有新接口。
  - [ ] 更新 `docs/api.md` / `docs/deploy.md`。

### 已知坑
- 无新增；保持 2026-06-22 21:05 快照中的已知坑清单。

*更新时间：2026-06-22 21:04*

---

## 2026-06-22 21:05 最新快照

### 刚完成
- Phase 8 代码实现完成：
  - `src/config.py` / `config/.env.example`：新增上传目录、生成目录、PaddleSpeech、Avatar 缓存、视频限制等配置。
  - `src/paddlespeech_tts_engine.py`：新建 PaddleSpeech TTS 封装，支持 `spk_id`、异步 CPU 推理、失败回退。
  - `src/avatar_manager.py`：新建动态 Avatar 管理器，支持视频上传保存、hash 生成 avatar_id、25fps 转码、时长/人脸校验、LRU 内存缓存 + 磁盘缓存恢复。
  - `src/video_gen_pipeline.py`：新建视频生成管线，含任务状态机、PaddleSpeech → edge-tts fallback、THG 渲染。
  - `src/webui.py`：新增 `/api/upload`、上传状态、`/api/generate`、生成状态、`/api/download/{job_id}`、`/api/voices`，保留 `/api/chat`。
  - `frontend/index.html` / `chat.js` / `chat.css`：新增实时对话/视频生成 Tab 切换、两步式上传生成 UI、进度条、结果播放/下载。
  - `config/requirements.txt`：新增 `paddlepaddle` 与相关依赖；`paddlespeech` 通过本地源码/entrypoint 安装。
  - `scripts/entrypoint-backend.sh`：PaddleSpeech 本地安装与模型预下载改为非阻塞，失败时允许回退 edge-tts 启动。
- 系统测试通过：在 `ascend-avatar-backend` 容器内，使用默认 `default_base.mp4` 完成上传 → 预处理 → 文本生成 → MP4 输出的端到端流程。
  - 输出文件：`/ascend-avatar/output/generated/51234c64a4604051/output.mp4`
  - 格式：H.264 512x512 + AAC mono，时长约 3.1s，与输入文本匹配。
  - 当前 TTS 因 PaddleSpeech 环境未完全就绪而回退到 edge-tts；视频生成管线本身已跑通。

### 当前未完成任务
- [ ] 补齐容器内 PaddleSpeech 完整运行环境（`onnxoptimizer` 构建 / `paddlenlp` 依赖 / `averaged_perceptron_tagger` NLTK 数据）。
- [ ] 使用 PaddleSpeech 本地 TTS 重新跑通端到端视频生成，不再 fallback。
- [ ] 预下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型到容器或挂载点。
- [ ] 重启后端容器并验证前端页面所有新接口。
- [ ] 更新 `docs/api.md` / `docs/deploy.md` 以覆盖视频生成工作流。

### 已知坑（新增/确认）
- PaddleSpeech 完整安装链路过重，涉及 `onnxoptimizer` 源码编译（需 CMake >=3.22）、`paddlenlp` 版本/依赖、`aistudio_sdk.hub.download` 兼容性、`g2p_en` 所需的 NLTK tagger 数据下载；在受限网络/容器环境下容易失败。
- 当前已采用“entrypoint 非阻塞安装 + 运行时 fallback edge-tts”的兜底策略，确保服务可启动、视频生成可用。
- MuseTalk 预处理在 NPU 上约 6 分钟/10s 视频（含模型加载），预处理完成后同一视频复用极快。
- 多视频并发需继续观察 NPU 内存；当前 `avatar_cache_size` 默认 3。

*更新时间：2026-06-22 21:05*

---

## 2026-06-22 18:15 最新快照

### 刚完成
- 用户调整项目目标：进入 Phase 8，新增“上传视频 + PaddleSpeech TTS + MuseTalk v1.5 唇形同步 → MP4”工作流。
- 通过苏格拉底式提问排除关键灰色地带，用户确认以下决策：
  - 保留现有实时对话模式，与新视频生成模式两者并存。
  - 前端采用两步式：先上传视频并等待预处理完成，再输入文本生成。
  - PaddleSpeech 默认使用多说话人模型 `fastspeech2_aishell3` + `hifigan_aishell3`，CPU 推理，前端提供 `spk_id` 选择。
  - 实时对话模式仍使用默认 `default_base.mp4`，不使用上传视频。
  - 上传视频严格校验（时长、25fps、人脸检测），PaddleSpeech 失败回退 edge-tts。
- 完成 Phase 8 实施规划，涵盖架构设计、文件变更清单、集成步骤、验证计划、风险与已知坑。
- 更新 `loop/STATE.md`：Phase 8 状态 IN_PROGRESS，子任务拆分，新增目标与已知坑。
- 更新 `loop/context_state.md`：记录目标调整与关键决策。

### 当前未完成任务（Phase 8）
- [ ] 8.1 PaddleSpeech TTS 集成（默认 `fastspeech2_aishell3` + `hifigan_aishell3`，CPU 推理，支持 spk_id）
- [ ] 8.2 视频上传 API 与前端两步式 UI
- [ ] 8.3 动态 Avatar 管理（按视频 hash 缓存 MuseTalkAvatar）
- [ ] 8.4 视频生成管线（Text → TTS → THG → MP4，含 edge-tts fallback）
- [ ] 8.5 下载/输出机制与状态轮询
- [ ] 8.6 端到端验证与文档更新

### 已知坑（新增/确认）
- PaddleSpeech 基于 PaddlePaddle，昇腾 910B 无原生 NPU 后端支持，TTS 必须在 CPU 运行。
- `fastspeech2_aishell3` + `hifigan_aishell3` 模型体积较大，首次使用需联网下载或预置到 `models/paddlespeech/`。
- 上传视频需 ffmpeg 转 25fps、OpenCV Haar 人脸检测；无人脸或超时长必须拒绝。
- 每个上传视频对应一个 `MuseTalkAvatar` 实例，prepare 耗时且占用 NPU/CPU 内存，需 LRU 缓存与并发限制。
- PaddlePaddle 与 PyTorch 共存时需保持 NumPy < 2.0，注意依赖冲突。
- `thg_engine.py` 运行时需 `chdir` 到 `THG_DIR`，AvatarManager 异步调用时需注意工作目录同步。

*更新时间：2026-06-22 18:15*

---

## 2026-06-22 10:00 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-22 10:00:00。
- 自 2026-06-18 14:44 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-18 14:44 快照中的未完成任务清单。
  - [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
  - [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧
  - [ ] 后续可考虑构建自定义后端镜像，将 `libsndfile1` 和 Python 依赖预装到镜像中

### 已知坑
- 无新增；保持 2026-06-18 14:44 快照中的已知坑清单。

*更新时间：2026-06-22 10:00*

---

## 2026-06-18 14:44 最新快照

### 刚完成
- 用户反馈网页仍显示 "Error: stream not found"，但 LLM 文本和 TTS 音频正常。
- 重新诊断：
  - 实际部署为 Docker Compose 双容器：`ascend-avatar-backend`（WebUI/NPU）+ `ascend-avatar-mediamtx`（官方镜像）。
  - MediaMTX 默认 internal auth 仅允许 127.0.0.1 访问 API，而 `src/pipeline.py` 用 `192.168.1.117:9997` 轮询路径状态，导致永远返回 `authentication error`。
  - 路径未上线就提前发出 `stream_ready`，浏览器连接到一个不存在的 WebRTC 路径。
- 修复：
  - `src/pipeline.py`：`_wait_for_path_online()` 改用 `http://127.0.0.1:9997`；只有 MediaMTX 报告 `ready` 后才发 `stream_ready`；超时延长至 15s。
  - `src/streaming.py`：ffmpeg 日志改为按 RTMP 路径命名（`/tmp/rtmp_ffmpeg_<path>.log`），避免覆盖。
  - `config/mediamtx-compose.yml`：显式配置 `authInternalUsers`，将 `192.168.1.117/32` 加入 API 白名单。
- 验证：
  - `docker compose restart mediamtx backend` 后，backend 完成 NPU 预热。
  - curl 触发对话：`stream_ready` 携带 `webrtc_url: http://192.168.1.117:8889/live/b9c214a5_0001/`。
  - MediaMTX 日志确认 `live/b9c214a5_0001` 上线（H264 + MPEG-4 Audio）。
  - WebRTC 播放页返回 HTTP 200。
- 告知用户刷新浏览器页面后重新发送消息测试。
- 回答用户访问地址：`http://192.168.1.117:8188/`。

### 当前未完成任务
- [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
- [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧
- [ ] 后续可考虑构建自定义后端镜像，将 `libsndfile1` 和 Python 依赖预装到镜像中

### 已知坑（新增/确认）
- MediaMTX API（`:9997`）默认仅允许 127.0.0.1/::1 访问；容器内查询必须显式使用 `127.0.0.1:9997`，不能依赖 `MEDIAMTX_HOST`。
- `stream_ready` 必须在 MediaMTX 路径实际 `ready` 之后再通知前端，否则浏览器会连接到一个不存在/已断开的路径。
- 实际部署为 Docker Compose 双容器（backend + mediamtx），与 `CLAUDE.md` 中描述的单一 `ascend-avatar` 容器不同；`docker compose up -d` 是推荐启动方式。
- 短句音频仍需补静默到至少 3–5 秒，确保 RTMP 流生命周期足够浏览器/WebRTC 建立连接。

*更新时间：2026-06-18 14:44*

---

## 2026-06-18 14:11 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-18 14:11:41。
- 自 2026-06-18 11:15 快照以来，无新增对话内容、事实、任务或修复。

### 当前未完成任务
- 无新增；保持 2026-06-18 11:15 快照中的未完成任务清单。

### 已知坑
- 无新增；保持 2026-06-18 11:15 快照中的已知坑清单。

*更新时间：2026-06-18 14:11*

---

## 2026-06-18 11:15 最新快照

### 刚完成
- 用户反馈：浏览器中只能看到字幕文字，听不到声音、看不到数字人。
- 诊断：
  - 第一句通常是短句（如“你好！”），TTS 音频只有 0.3–0.5 秒。
  - RTMP 推流瞬间结束，MediaMTX 来不及将路径注册为 online，浏览器 WebRTC 播放器连接时流已断开。
  - MediaMTX 日志显示浏览器反复尝试连接旧 session 的 `_0001` 路径，提示 `no stream is available`。
- 修复：
  - `src/pipeline.py`：短于 3 秒的 WAV 用 `pydub` 补静默到 3 秒，确保 RTMP 流至少持续数秒。
  - `src/pipeline.py`：将 `stream_ready` 事件推迟到 ffmpeg 吃下第一帧后再发送，避免浏览器过早连接。
  - `src/streaming.py`：保留 `ready_event` 机制，便于调用方等待首帧。
  - `frontend/static/js/chat.js`：`done` 事件现在切回 idle 视频，避免对话结束后仍停留在已断流的 iframe。
- 验证：
  - 通过 MediaMTX API 轮询确认第一句路径现在可稳定 online 4–5 秒。
  - `/`、`/api/chat`、`/gradio/` 均返回 200。
- 已告知用户刷新浏览器页面以加载新前端 JS。

### 当前未完成任务
- [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
- [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧
- [ ] 后续可考虑构建自定义后端镜像，将 `libsndfile1` 和 Python 依赖预装到镜像中

### 已知坑（新增/确认）
- 短句（≤1 秒音频）会导致 RTMP 流生命周期过短，浏览器 WebRTC 来不及连接；需用音频补静默或持续流架构解决。
- `stream_ready` 必须在 RTMP 路径实际 online 之后再通知前端，否则浏览器会连接到一个还不存在/已断开的路径。
- MediaMTX API（`:9997/v3/paths/list`）是判断路径是否 online 的可靠方式。
- `App.create_app(demo)` 会替换 FastAPI 实例并覆盖根路由；需用 Starlette `Mount` 将 Gradio 挂载到子路径，再显式注册 `/` 路由。
- `StaticFiles(html=True)` 作为 `/` 的 catch-all 挂载时，必须放在所有其他 mount 之后。
- 昇腾基础镜像未预装 `libsndfile1`，容器重建后系统包会丢失；当前方案是 entrypoint 每次启动时 apt 安装。
- `MEDIAMTX_HOST` 需要设置为浏览器可访问的 IP（如 `192.168.1.117`），不能只用 `127.0.0.1`。

*更新时间：2026-06-18 11:15*

---

## 2026-06-18 09:48 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-18 09:48:35。
- 自 2026-06-18 09:36 快照以来，无新增对话内容、事实或任务。

### 当前未完成任务
- 无新增；保持 2026-06-18 09:36 快照中的未完成任务清单。

### 已知坑
- 无新增；保持 2026-06-18 09:36 快照中的已知坑清单。

*更新时间：2026-06-18 09:48*

---

## 2026-06-18 09:36 最新快照

### 刚完成
- 进入 Plan Mode，通过苏格拉底式提问明确 Docker Compose 与前后端分离的范围：
  - Docker Compose 采用多 service 拆分：backend + 前端静态资源一个 service，MediaMTX 一个 service。
  - 前后端分离采用逻辑分离：前端文件独立到 `frontend/`，由后端同容器通过 FastAPI `StaticFiles` 提供。
  - 日志统一为 stdout/stderr；Gradio 保留 `/gradio`。
- 实现并验证 Docker Compose + 前后端逻辑分离：
  - `src/config.py`：新增 `mediamtx_host`、`mediamtx_rtmp_port`、`mediamtx_webrtc_port`；`rtmp_url` / `webrtc_play_url` 改为计算属性；更新 `.env.example`。
  - `src/pipeline.py`：用 `self.cfg.rtmp_url` 替换硬编码 RTMP URL。
  - `src/webui.py`：移除内嵌 `_CHAT_HTML`，改用 `StaticFiles` 挂载 `frontend/`、`/avatars`，保留 `/api/chat` 与 `/gradio`；修复 Gradio 被 catch-all 覆盖的问题（`/gradio` mount 必须在前端 `/` mount 之前）。
  - 新增 `frontend/index.html`、`frontend/static/css/chat.css`、`frontend/static/js/chat.js`。
  - 新增 `scripts/entrypoint-backend.sh`：前台启动、安装系统依赖（`libsndfile1`）、按需安装 Python 依赖、等待 MediaMTX RTMP 端口可达。
  - 新增 `config/mediamtx-compose.yml`：显式 `0.0.0.0` 绑定、开启 API、动态 `live/{id}` 路径、`rtsp: no`。
  - 新增 `docker-compose.yml`：backend 与 mediamtx 两个 service，`network_mode: host`，NPU 设备、驱动挂载、`depends_on`。
  - 更新 `docs/deploy.md`：以 `docker compose up -d` 为主启动方式，补充 `docker compose logs` 用法。
- 验证过程中发现并修复的问题：
  - 官方 `bluenviron/mediamtx:latest` 为 v1.19.1，`command` 只需传 config 路径，不能重复传 `/mediamtx`。
  - 官方 MediaMTX 镜像无 `wget`/`curl`，无法用 Docker healthcheck；改为后端 entrypoint 内轮询 RTMP 端口。
  - 新容器缺少 Python 依赖，entrypoint 内按需 `pip install -r config/requirements.txt`。
  - 新容器缺少 `libsndfile1`，entrypoint 内每次启动执行 `apt-get install -y libsndfile1`（容器文件系统不持久化）。
  - `StaticFiles(directory="frontend", html=True)` 会 catch-all，导致 `/gradio` 返回 404；调整 route mount 顺序解决。
- 最终验证：
  - `docker compose up -d` 成功启动两个 service。
  - `/`、`/static/css/chat.css`、`/static/js/chat.js`、`/avatars/default_base.mp4`、`/api/chat`、`/gradio/` 均返回 HTTP 200。
  - SSE 端到端测试通过，返回 `stream_ready` 且无 `[Errno 32] Broken pipe`。

### 当前未完成任务
- [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
- [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧
- [ ] 后续可考虑构建自定义后端镜像，将 `libsndfile1` 和 Python 依赖预装到镜像中，避免每次容器重建时重复安装

### 已知坑（新增/确认）
- `App.create_app(demo)` 会替换 FastAPI 实例并覆盖根路由；需用 Starlette `Mount` 将 Gradio 挂载到子路径，再显式注册 `/` 路由。
- `StaticFiles(html=True)` 作为 `/` 的 catch-all 挂载时，必须放在所有其他 mount（包括 `/gradio`、`/avatars`）之后，否则其他路径会被前端 index.html 吞掉。
- 容器内 `python -m src.webui` 进程在调试期间多次残留，阻塞 8188 端口；需要精确 PID `kill -9` 清理。
- `nohup python -m src.webui > /tmp/webui.log` 的日志中 torch.compile 阶段不输出进度，但 CPU 高占用说明仍在编译；需通过 curl 端口检查确认服务可用。
- MediaMTX v1.9.0/v1.19.1 配置文件中：
  - `rtmpEncryption` 等字段必须写成带引号的字符串 `"no"`，不能写裸 `no`（YAML 会解析为 bool）。
  - `webrtcExternalEncryptionKey` 在 v1.9.0 不存在，不能保留。
  - UDP 8000 默认被 RTSP 占用，若宿主机有冲突需显式 `rtsp: no`。
  - 动态 RTMP 路径需用正则路径，如 `~^live/(.+)$`。
- 官方 `bluenviron/mediamtx` 镜像不包含 shell 工具，不适合用 `wget`/`curl` 做 Docker healthcheck；可直接让后端服务轮询 RTMP 端口。
- 昇腾基础镜像未预装 `libsndfile1`，且容器重建后系统包会丢失；当前方案是 entrypoint 每次启动时 apt 安装。
- `MEDIAMTX_HOST` 需要设置为浏览器可访问的 IP（如 `192.168.1.117`），不能只用 `127.0.0.1`，否则 WebRTC 播放 URL 在浏览器端无法连接。

*更新时间：2026-06-18 09:36*

---

## 2026-06-17 17:04 最新快照

### 刚完成
- 响应用户要求，重写 `CLAUDE.md`，从早期 PRD 阶段描述更新为 Phase 7 完成后的实际运行状态。
- 回答用户关于项目运行状态的问题：确认 Phase 7 COMPLETED，端到端可运行，并给出关键指标。
- 诊断并修复主对话页面 `[Errno 32] Broken pipe` 错误：
  - 根因是容器内 MediaMTX 未运行。
  - `config/mediamtx.yml` 中 `rtmpEncryption: no` 被 YAML 解析为 bool，而 MediaMTX v1.9.0 期望 string，导致启动失败。
  - 原配置还包含 `webrtcExternalEncryptionKey` 等 v1.9.0 不支持的字段。
  - 宿主机 UDP 8000 被占用，保留 `rtsp: no` 避免冲突。
  - 重写 `config/mediamtx.yml` 为最小可用配置：RTMP `:1935`、WebRTC `:8889`、动态 `live/{id}` 正则路径、`rtsp: no`。
  - 在容器内启动 MediaMTX；SSE 端点 `/api/chat` 测试通过，可正常返回 `start`、`llm_text`、`stream_ready`、`sentence_stream_done`、`done`。

### 当前未完成任务
- [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
- [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧
- [ ] 评估/实现 Docker Compose 化部署（用户新提议）
- [ ] 评估/实现前后端分离架构（用户新提议）

### 已知坑（新增/确认）
- `App.create_app(demo)` 会替换 FastAPI 实例并覆盖根路由；需用 Starlette `Mount` 将 Gradio 挂载到子路径，再显式注册 `/` 路由。
- 容器内 `python -m src.webui` 进程在调试期间多次残留，阻塞 8188 端口；需要精确 PID `kill -9` 清理。
- `nohup python -m src.webui > /tmp/webui.log` 的日志中 torch.compile 阶段不输出进度，但 CPU 高占用说明仍在编译；需通过 curl 端口检查确认服务可用。
- MediaMTX v1.9.0 配置文件中：
  - `rtmpEncryption` 等字段必须写成带引号的字符串 `"no"`，不能写裸 `no`（YAML 会解析为 bool）。
  - `webrtcExternalEncryptionKey` 在该版本不存在，不能保留。
  - UDP 8000 默认被 RTSP 占用，若宿主机有冲突需显式 `rtsp: no`。
  - 动态 RTMP 路径需用正则路径，如 `~^live/(.+)$`。

*更新时间：2026-06-17 17:04*

---

## 2026-06-17 16:21 最新快照

### 刚完成
- 运行自动 context-compaction hook。
- 读取 `loop/context_state.md` 与 `loop/STATE.md`。
- 更新 `loop/STATE.md` 心跳时间为 2026-06-17 16:21:08。

### 当前未完成任务
- 无新增；保持 2026-06-17 16:19 快照中的未完成任务清单（本地 TTS 替换、可选的边生成边推送优化）。

### 已知坑
- 无新增；保持 2026-06-17 16:19 快照中的已知坑清单。

*更新时间：2026-06-17 16:21*

## 2026-06-16 10:30 最新快照

### 刚完成
- 已压缩上下文。
- 已添加自动 context-compaction hook（job ID: `c01708d1`）。
- MuseTalk NPU 推理通过 `torch.compile(backend='npu')` 大幅加速：二次渲染从 ~41s 降至 **3.67s**（3s 音频）。
- 修复：容器内 sympy 1.4 与 torch_npu dynamo 不兼容，升级至 `sympy==1.12`。
- 修复：diffusers 中 `assert hidden_states.shape[1] == self.channels` 无法被 torch_npu GE 转换器处理，运行时补丁绕过。
- 修复：`src/thg_engine.py` 在 CPU 设备上误用 half 精度；现在仅 NPU 使用 half。
- 跑通 `src/pipeline.py` 端到端（LLM+TTS+THG），生成 `/ascend-avatar/output/94d3c56a_combined.mp4`。

---

## 2026-06-17 15:37 最新快照

### 刚完成
- 通过 SSH 继续集成工作；清理了容器内残留的旧 WebUI/测试 Python 僵尸进程（PID 1100201/1109737 等）。
- 创建 `/ascend-avatar/config/mediamtx.yml` 并启动 MediaMTX v1.9.0：RTMP:1935、WebRTC:8889、HLS:8888。
- 重写 `src/webui.py`：改为 FastAPI + SSE 架构；根路径 `/` 返回自定义聊天 HTML；`/api/chat` 为 SSE 端点；Gradio 管理面板挂载到 `/gradio`。
- 修复 `build_app()` 中 Gradio 覆盖 `/` 根路由的问题，使用 Starlette `Mount` 将 Gradio 挂到 `/gradio`。
- 修复 pipeline 重复创建问题：启动时预热一个 `ConversationPipeline` 实例，SSE 请求复用该实例，避免每次请求都重新预热 7-8 分钟。
- 将本地 `src/webui.py` 同步到服务器 `/data/ascend-avatar/`。
- 重新启动 WebUI（PID 1130624），NPU 图编译预热进行中；已确认 `/`、`/api/chat`、`/gradio/` 均返回 HTTP 200。
- 验证 SSE 端点可返回 `start`、`llm_text` 事件，LLM 首 token 延迟约 93.4 ms。

### 当前未完成任务
- [ ] 通过浏览器/SSE Client 测试完整交互对话（LLM → TTS → THG → RTMP/WebRTC）并确认视频流播放
- [ ] 验证 WebRTC 视频流在 iframe 中可播放
- [ ] 补充 `docs/benchmark.md` 实测延迟数据
- [ ] 完成 Phase 5/6/7 验收与 `loop/STATE.md` 更新

### 已知坑（新增/确认）
- `App.create_app(demo)` 会替换 FastAPI 实例并覆盖根路由；需用 Starlette `Mount` 将 Gradio 挂载到子路径，再显式注册 `/` 路由。
- 容器内 `python -m src.webui` 进程在调试期间多次残留，阻塞 8188 端口；需要精确 PID `kill -9` 清理。
- `nohup python -m src.webui > /tmp/webui.log` 的日志中 torch.compile 阶段不输出进度，但 CPU 高占用说明仍在编译；需通过 curl 端口检查确认服务可用。
- MediaMTX 启动后需要确认 RTMP ingest 和 WebRTC play 都能工作。

*更新时间：2026-06-17 15:37*

---

## 2026-06-17 16:19 最新快照

### 刚完成
- 通过 SSE Client 完成完整端到端测试：输入 `你好，请简单介绍一下自己。`，得到 10 句完整 LLM 回复，每句均成功 RTMP 推流（H264 + MPEG-4 Audio）。
- MediaMTX 日志确认 `live/dccf1133_0001` 至 `live/dccf1133_0010` 全部 publishing 成功。
- WebRTC 播放页 `http://192.168.1.117:8889/live/{stream}/` 可访问。
- 更新 `docs/benchmark.md`，新增第 4 条实测记录：
  - LLM 首 token: 77.6 ms
  - TTS: 1792.5 ms
  - 首帧视频延迟: 1904.0 ms
  - 句数: 10
- 创建 Phase 5/6/7 checkpoint 文件：
  - `loop/checkpoints/phase_5.ok`
  - `loop/checkpoints/phase_6.ok`
  - `loop/checkpoints/phase_7.ok`
- 更新 `loop/STATE.md` 为 Phase 7、状态 COMPLETED，并同步到服务器 `/data/ascend-avatar/`。
- 所有 task list 任务标记为 completed。

### 当前未完成任务
- [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
- [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧

### 已知坑（新增/确认）
- `App.create_app(demo)` 会替换 FastAPI 实例并覆盖根路由；需用 Starlette `Mount` 将 Gradio 挂载到子路径，再显式注册 `/` 路由。
- 容器内 `python -m src.webui` 进程在调试期间多次残留，阻塞 8188 端口；需要精确 PID `kill -9` 清理。
- `nohup python -m src.webui > /tmp/webui.log` 的日志中 torch.compile 阶段不输出进度，但 CPU 高占用说明仍在编译；需通过 curl 端口检查确认服务可用。
- MediaMTX 启动后需要确认 RTMP ingest 和 WebRTC play 都能工作。
- 首帧延迟未达 ≤1500ms 目标，主要瓶颈是 edge-tts 网络延迟（~1.5-3s）。

*更新时间：2026-06-17 16:19*

### 已确认的关键事实
1. **目标服务器与容器**
   - 服务器：192.168.1.117，用户 ascend
   - 容器 `ascend-avatar` 正在运行，仅可使用 `/dev/davinci7`（容器内为 `npu:0`）
   - 容器镜像：`swr.cn-south-1.myhuaweicloud.com/ascendhub/ascend-pytorch:24.0.0-A2-2.1.0-ubuntu20.04`
   - 工作目录挂载：`/data/ascend-avatar` → `/ascend-avatar`

2. **环境基线**
   - Python 3.9.2、torch 2.1.0、torch_npu 2.1.0.post10、NumPy 1.26.4、sympy 1.12
   - 必须执行 `source /usr/local/Ascend/ascend-toolkit/set_env.sh`
   - 必须设置 `ASCEND_VISIBLE_DEVICES=7` 和 `ASCEND_RT_VISIBLE_DEVICES=7`
   - 已安装 `libsndfile1`（apt）以支持 soundfile/librosa
   - ffmpeg/ffprobe 位于 `/ascend-avatar/bin/`，启动脚本需要加入 `PATH`

3. **LLM**
   - 外部端点 `modelhub.lgdg.cc` 无法访问
   - 本地 MindIE 服务可用：`http://192.168.1.117:1025/v1`
   - 模型：`qwen3_32b`
   - 支持 OpenAI 兼容流式接口，无需 API Key

4. **TTS**
   - 使用 `edge-tts`（微软 Edge TTS 在线服务）
   - 音色参数：`rate=+0%`，`pitch=+0Hz`（Hz 是 edge-tts 要求）
   - 支持中文/英文/多音色
   - **当前最大瓶颈**：网络延迟 ~1.5-3s，导致首帧未达 ≤1500ms 目标

5. **THG / MuseTalk**
   - 使用 MuseTalk v1.5，模型已下载到 `/ascend-avatar/thg/models/`
   - Whisper 使用 HF 格式，位于 `/ascend-avatar/thg/models/whisper_hf`
   - 已用 OpenCV Haar 检测替代 mmpose/mmcv 做人脸框提取（避免 ARM 源码编译）
   - 默认 avatar 已预处理并缓存：`/ascend-avatar/output/v15/avatars/default/`
   - `torch.compile(backend='npu')` 已启用；首次编译慢（约 7-8 分钟），二次渲染 **3.67s**（3s 音频）

6. **实时管线**
   - LLM 流式输出 → 句子分段 → TTS → THG → RTMP 推流 全链路已跑通
   - 每句独立 RTMP 路径：`rtmp://127.0.0.1:1935/live/{session}_{index:04d}`
   - MediaMTX v1.9.0 提供 RTMP/WebRTC/HLS

7. **前端**
   - 根路径 `/` 为自定义 HTML/JS 聊天界面
   - `/api/chat` 为 SSE 端点
   - `/gradio/` 为管理面板

8. **代码结构**
   - `src/config.py`、`src/llm_client.py`、`src/tts_engine.py`、`src/thg_engine.py`、`src/pipeline.py`、`src/webui.py`
   - `src/streaming.py`：RTMP 推流器
   - `src/utils.py`：文本分段
   - `src/_preprocessing_patch.py`：Haar 预处理补丁
   - `scripts/start.sh`：启动服务
   - `docs/architecture.md`、`docs/api.md`、`docs/deploy.md`、`docs/benchmark.md` 已创建

### 当前未完成任务
- [ ] 替换 edge-tts 为本地 TTS（CosyVoice/PaddleSpeech）以将首帧延迟降至 ≤1500ms
- [ ] 可选：将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧

### 自动压缩 Hook
- 已创建 durable 定时任务（job ID: `c01708d1`），每 30 分钟（:07、:37）触发一次。
- 触发时会先读取当前会话上下文，把新的事实/决策/未完成任务追加写入 `loop/context_state.md`，并更新 `loop/STATE.md` 心跳。
- 当判断上下文接近满载时，会输出 `/compact` 提示以触发压缩；关键状态已先保存到 `loop/`。
- 该任务已持久化到 `.claude/scheduled_tasks.json`，会话重启后仍会生效。

### 已知坑
- `torch_npu` 必须 source CANN set_env.sh 并限制可见 NPU
- `edge-tts` 的 `pitch` 参数单位必须是 `Hz`
- `soundfile` 依赖系统 `libsndfile1`
- MuseTalk 内部很多路径相对于仓库根目录，运行时必须 `chdir` 到 `/ascend-avatar/thg`
- face_alignment 需要下载大模型且 SFD 下载极慢，已用 Haar 替代
- torch_npu `torch.compile(backend='npu')` 需要 `sympy>=1.11.1,<1.13`
- torch_npu 图编译器暂不支持 `aten._assert_async.msg`，已用运行时补丁绕过 diffusers 中的 shape assert
- Gradio 4.44.1 在容器内阻塞式 `demo.launch()` 会挂起，已改用 FastAPI + uvicorn
- `App.create_app(demo)` 会覆盖根路由，需用 Starlette `Mount` 将 Gradio 挂到 `/gradio`

---

## 2026-06-16 09:20 压缩前快照

### 已确认的关键事实

1. **目标服务器与容器**
   - 服务器：192.168.1.117，用户 ascend
   - 容器 `ascend-avatar` 正在运行，仅可使用 `/dev/davinci7`（容器内为 `npu:0`）
   - 容器镜像：`swr.cn-south-1.myhuaweicloud.com/ascendhub/ascend-pytorch:24.0.0-A2-2.1.0-ubuntu20.04`
   - 工作目录挂载：`/data/ascend-avatar` → `/ascend-avatar`

2. **环境基线**
   - Python 3.9.2、torch 2.1.0、torch_npu 2.1.0.post10、NumPy 1.26.4
   - 必须执行 `source /usr/local/Ascend/ascend-toolkit/set_env.sh`
   - 必须设置 `ASCEND_VISIBLE_DEVICES=7` 和 `ASCEND_RT_VISIBLE_DEVICES=7`
   - 已安装 `libsndfile1`（apt）以支持 soundfile/librosa

3. **LLM**
   - 外部端点 `modelhub.lgdg.cc` 无法访问
   - 本地 MindIE 服务可用：`http://192.168.1.117:1025/v1`
   - 模型：`qwen3_32b`
   - 支持 OpenAI 兼容流式接口，无需 API Key

4. **TTS**
   - 使用 `edge-tts`（微软 Edge TTS 在线服务）
   - 音色参数：`rate=+0%`，`pitch=+0Hz`（Hz 是 edge-tts 要求）
   - 支持中文/英文/多音色

5. **THG / MuseTalk**
   - 使用 MuseTalk v1.5，模型已下载到 `/ascend-avatar/thg/models/`
   - Whisper 使用 HF 格式，位于 `/ascend-avatar/thg/models/whisper_hf`
   - 已用 OpenCV Haar 检测替代 mmpose/mmcv 做人脸框提取（避免 ARM 源码编译）
   - 默认 avatar 已预处理并缓存：`/ascend-avatar/output/v15/avatars/default/`
   - 首帧/首次推理因 NPU 图编译/AICPU 回退非常慢；二次推理仍有优化空间

6. **代码结构**
   - `src/config.py`、`src/llm_client.py`、`src/tts_engine.py`、`src/thg_engine.py`、`src/pipeline.py`、`src/webui.py`
   - `src/_preprocessing_patch.py`：Haar 预处理补丁
   - `scripts/start.sh`：启动 Gradio 服务
   - `docs/architecture.md`、`docs/api.md`、`docs/deploy.md`、`docs/benchmark.md` 已创建

### 当前未完成任务

- [ ] 优化 MuseTalk 推理延迟（当前二次渲染约 1 分钟，不满足 ≤1.5s 首帧目标）
- [ ] 跑通 `src/pipeline.py` 端到端（LLM + TTS + THG）
- [ ] 启动并验证 Gradio UI
- [ ] 补充 `docs/benchmark.md` 实测延迟数据
- [ ] 完成 Phase 验收与 `loop/STATE.md` 更新

### 可能的优化方向

1. 减小 avatar base 视频长度（当前 10s/250 帧 → 可减少到 2s/50 帧）
2. 增大 `batch_size` 提高 NPU 利用率
3. 将 UNet/VAE 转 OM 模型以规避 AICPU 回退
4. 用 `ffmpeg` pipe 替代逐帧写 PNG，减少 I/O
5. 评估是否替换为 Wav2Lip 等更轻量的唇形模型

### 已知坑

- `torch_npu` 必须 source CANN set_env.sh 并限制可见 NPU
- `edge-tts` 的 `pitch` 参数单位必须是 `Hz`
- `soundfile` 依赖系统 `libsndfile1`
- MuseTalk 内部很多路径相对于仓库根目录，运行时必须 `chdir` 到 `/ascend-avatar/thg`
- face_alignment 需要下载大代码模型且 SFD 下载极慢，已用 Haar 替代

*更新时间：2026-06-16 09:20*
