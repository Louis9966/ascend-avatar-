# ascend-avatar Loop 状态

项目: ascend-avatar
当前 Phase: 10
上次心跳: 2026-06-24 19:10:00
上次更新者: claude
状态: COMPLETED

## 已完成 Phase
- [x] Phase 0: 环境基线验证
- [x] Phase 1: 技术选型与架构设计
- [x] Phase 2: LLM 流式接入层
- [x] Phase 3: TTS 引擎集成
- [x] Phase 4: THG 唇形同步引擎（基础跑通，torch.compile 后二次渲染 3.67s/3s 音频）
- [x] Phase 5: 实时流式管线串联
- [x] Phase 6: Gradio 前端与接口文档
- [x] Phase 7: 集成验收与测试
- [x] Phase 8: 视频上传 + PaddleSpeech TTS + 视频生成工作流
- [x] Phase 9: 视频生成嘴部清晰度优化
- [x] Phase 10: 进一步降低模糊 + 输入缩放 + GFPGAN 后处理（已切至 NPU）

## 当前状态
Phase 10 已完成：默认 `THG_BLUR_RATIO` 降至 0.03，`MUSE_TALK_BBOX_SHIFT` 设为 -7，新增 `THG_PREPARE_RESOLUTION=512x512` 对 avatar 输入做中心裁剪缩放，视频生成路径可选 GFPGAN v1.4 后处理（NPU，颜色通道已修复）。嘴部 bbox 检测已改用 MediaPipe Face Mesh 嘴唇关键点（Haar 兜底），嘴部区域更聚焦、唇线对齐更好。使用 MyVideo_1.mp4 全流程验证成功，颜色正常，输出 512×512@25fps，RAW 嘴部 Laplacian 210.27，GFPGAN NPU 后 331.68。

## Phase 9 目标
1. 降低嘴部 mask 羽化，提升唇线锐度。
2. 渲染 256×256 → 原 bbox 时使用更锐利插值。
3. 所有关键参数可通过 `.env` 调优。
4. 保持实时对话路径与视频生成路径行为一致。

## Phase 9 子任务
- [x] 9.1 `src/config.py` 新增 `THG_*` / `FFMPEG_*` 参数
- [x] 9.2 `thg/musetalk/utils/blending.py` `get_image_prepare_material` 支持 `blur_ratio` 等参数（向后兼容）
- [x] 9.3 `src/thg_engine.py` 使用新参数：mask、渲染插值、FFmpeg preset/CRF
- [x] 9.4 `src/avatar_manager.py` / `src/pipeline.py` 传递新参数
- [x] 9.5 更新 `config/.env.example`、`docs/deploy.md`、`docs/benchmark.md`
- [x] 9.6 端到端验证：清理缓存后生成视频，主观/客观评估嘴部清晰度

## Phase 9 实测指标
- 文本："你好，欢迎使用数字人。今天天气真不错。"（17 中文字符）
- TTS：PaddleSpeech `fastspeech2_aishell3` + `hifigan_aishell3`，约 27s
- THG + mux：约 2-3 分钟（含 MuseTalk 预处理）
- 输出：H.264 512×512 25fps，136 帧（约 5.4s）+ AAC 16kHz mono
- 嘴部 ROI Laplacian 方差均值：新配置 **1065.55** vs 旧配置基线 **1063.68**（提升约 0.18%）

## 全流程验证（sample/MyVideo_1.mp4）
- 上传视频：1280×720@25fps，26.3s，658 帧，`upload_id=49a6c93f7de1f8a0`
- MuseTalk 预处理：约 35 分钟（首次长视频 + 658 帧）
- 生成文本："你好，这是用 MyVideo_1 做的数字人测试。"
- 生成任务：`job_id=d657ab22e0314538`，PaddleSpeech TTS，THG 完成
- 输出：`/ascend-avatar/output/generated/MyVideo_1_verify.mp4`
- 输出格式：H.264 1280×720 25fps，92 帧（3.68s），文件 360K
- 嘴部 ROI Laplacian 方差均值：**123.38**

## Phase 8 子任务（保留）
- [x] 8.1 PaddleSpeech TTS 封装（`src/paddlespeech_tts_engine.py` 已完成，含 `spk_id`、懒加载、fallback）
- [x] 8.1.1 容器内 PaddleSpeech + 模型下载环境补齐（`onnxoptimizer`/`aistudio_sdk`/`scikit-learn` libgomp TLS 等问题已修复，模型已下载至 `~/.paddlespeech/models/`，TTS 不再 fallback）
- [x] 8.2 视频上传 API 与前端两步式 UI（`/api/upload`、状态轮询、上传校验、Tab 切换）
- [x] 8.3 动态 Avatar 管理（`src/avatar_manager.py`，按视频 hash 缓存，LRU 淘汰，磁盘缓存可恢复）
- [x] 8.4 视频生成管线（`src/video_gen_pipeline.py`，Text → TTS → THG → MP4，含 edge-tts fallback）
- [x] 8.5 下载/输出机制与状态轮询（`/api/generate`、`/api/download/{job_id}`、进度推送）
- [x] 8.6 端到端验证：默认 avatar 视频上传 → 使用 PaddleSpeech TTS 生成 MP4 成功，输出 H264+AAC，512x512，时长与文本匹配

## 实测关键指标（Phase 7 基线）
- LLM 首 token: ~80 ms
- TTS 延迟: ~1.5-3 s（edge-tts 网络）
- 首帧视频延迟: ~1.75-3.15 s
- THG 渲染: ~3.67s/3s 音频（NPU prewarm 后）
- 视频帧率: 25 fps
- NPU 内存: ~4.3 GB

## Phase 8 新增实测指标
- 10s 上传视频 MuseTalk 预处理（NPU）：约 2 分钟（复用已缓存 default avatar 时更快）
- PaddleSpeech CPU TTS（warm 后）：约 27s/16 中文字符
- 17 字文本 PaddleSpeech TTS + THG + mux 生成 MP4：约 45s，输出 4.4s 视频
- 输出格式：H.264 512x512 + AAC 16kHz mono
- 上传校验：时长、25fps 转码、人脸检测通过
- TTS 引擎：成功使用 `paddlespeech`，未触发 edge-tts fallback

## 遗留优化
- PaddleSpeech 环境补齐后关闭 edge-tts fallback，实测本地 CPU TTS 延迟。
- 可将 MuseTalk 渲染改为边生成边推送，进一步压缩首帧（实时对话场景）。

## 已知坑
- `torch_npu` 必须 `source /usr/local/Ascend/ascend-toolkit/set_env.sh` 并设置 `ASCEND_VISIBLE_DEVICES=7` 才能初始化。
- 外部 LLM 端点 `modelhub.lgdg.cc` 不可达；本地 MindIE 服务在 `192.168.1.117:1025` 可用，已改用。
- MuseTalk 预处理依赖 mmpose / face-detection，已用 OpenCV Haar 补丁替换。
- NumPy 必须 < 2.0。
- edge-tts 的 `pitch` 参数单位必须是 `Hz`。
- torch_npu `torch.compile(backend='npu')` 需要 `sympy==1.12`。
- torch_npu 图编译器暂不支持 `aten._assert_async.msg`，已用运行时补丁绕过 diffusers shape assert。
- ffmpeg/ffprobe 位于 `/ascend-avatar/bin/`，运行时需要加入 `PATH`。
- Gradio 4.44.1 在容器内阻塞式 `demo.launch()` 会挂起，已改用 FastAPI + uvicorn。
- `App.create_app(demo)` 会覆盖根路由，需用 Starlette `Mount` 将 Gradio 挂到 `/gradio`。
- **PaddleSpeech 基于 PaddlePaddle，昇腾 910B 上无原生 NPU 后端支持，TTS 计划在 CPU 运行。**
- **Starlette `Route` 挂载的纯函数端点不会自动做 FastAPI 参数绑定；需要显式接收 `Request` 并从 `request.path_params` / `await request.form()` 取参数。**
- **在线程池（`run_in_executor`）中执行 `torch_npu` 运算前，必须先调用 `torch_npu.npu.set_device(device)` 初始化 NPU 上下文，否则报 `context pointer null`。MuseTalk 预处理与渲染已增加 `_prepare_on_device` / `_render_on_device` 包装。**
- **PaddleSpeech 完整安装依赖 `onnxoptimizer`（需要 CMake >=3.22 <4）、`paddlenlp` 及其依赖，容器内已通过 `--no-build-isolation` + `cmake<4` 构建成功；`aistudio-sdk` 需固定 0.2.6。**
- **PaddleSpeech 首次使用需下载 `fastspeech2_aishell3` + `hifigan_aishell3` 模型；离线环境需预置到 `~/.paddlespeech/models/`。**
- **每个上传视频需独立 MuseTalkAvatar 预处理，多视频并发需 LRU 缓存避免 NPU 内存耗尽。**
- **上传视频需 ffmpeg 转 25fps、OpenCV Haar 人脸检测；无人脸或超时长需拒绝。**
- **修改 `THG_BLUR_RATIO`、`THG_EXPAND`、`THG_UPPER_BOUNDARY_RATIO` 等 mask 参数后，已缓存的 avatar 目录需要删除或使用 `force=True` 重新 prepare，否则仍使用旧 mask。**
