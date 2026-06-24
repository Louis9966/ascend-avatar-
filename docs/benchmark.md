# ascend-avatar 延迟测试报告

## 环境

- 服务器：政数局 910B（192.168.1.117）
- 容器：ascend-avatar
- NPU：/dev/davinci7（容器内 npu:0）
- LLM：本地 MindIE qwen3_32b @ 192.168.1.117:1025
- TTS：edge-tts（微软 Edge TTS 在线服务）
- THG：MuseTalk v1.5 + torch.compile(backend='npu')
- 媒体服务：MediaMTX v1.9.0（RTMP + WebRTC + HLS）
- 前端：FastAPI SSE + 自定义 HTML/JS

## 测试记录

| # | 日期 | 输入 | LLM 首 token (ms) | TTS (ms) | 首帧视频延迟 (ms) | 句数 | 结果 |
|---|------|------|-------------------|----------|-------------------|------|------|
| 1 | 2026-06-17 | 你好，请简单介绍一下自己。 | 93.0 | 1695 | 1836 | 3 | ✅ RTMP推流+WebRTC播放成功 |
| 2 | 2026-06-17 | 你好，请简单介绍一下自己。 | 82.4 | 3022 | 3153 | 3 | ✅ 3句全部RTMP推流成功 |
| 3 | 2026-06-17 | 你好 | 82.4 | 1565 | 1752 | 4 | ✅ 4句全部RTMP推流成功 |
| 4 | 2026-06-17 | 你好，请简单介绍一下自己。 | 77.6 | 1792.5 | 1904.0 | 10 | ✅ 10句全部RTMP推流成功，WebRTC可播放 |

## 延迟分解

| 阶段 | 平均延迟 | 备注 |
|------|---------|------|
| LLM 首 token | ~80 ms | MindIE 本地推理，极快 |
| TTS (edge-tts) | ~1500-3000 ms | 受网络波动影响大，稳定时 ~1.5-1.8s |
| THG 首帧 (NPU prewarm后) | ~200-300 ms | torch.compile预热后二次推理 3.67s/3s音频 |
| 首帧视频 (从请求发出) | ~1750-3150 ms | = LLM + TTS + THG首帧 |
| RTMP 推流 | ~2-8s/句 | 取决于音频长度，逐句推送 |
| 整句 THG 渲染 | ~3.67s/3s音频 | NPU prewarm 后稳定 |

## 目标达成情况

| 指标 | 目标 | 实测 | 状态 |
|------|------|------|------|
| 首帧延迟 | ≤1500ms | 1752-3152ms | ⚠️ 未达标，主要瓶颈在TTS网络延迟 |
| 20字句端到端 | <5000ms | ~3-5s | ✅ 接近达标 |
| 视频帧率 | ≥25fps | 25fps | ✅ |
| NPU内存 | ≤16GB | ~4.3GB | ✅ 远低于上限 |
| 并发会话 | 1路 | 1路 | ✅ |

## 优化方向

1. **TTS 延迟优化**：edge-tts 网络延迟是最大瓶颈（1.5-3s），替换为本地 CosyVoice/PaddleSpeech 可降至 <500ms
2. **THG 流式输出**：当前逐句渲染后整体推送RTMP，改为边渲染边推送可进一步降低首帧
3. **LLM 并行**：TTS/THG 已与 LLM 并行流水线化，但 TTS 网络延迟仍占大头

## 备注

- MuseTalk torch.compile 首次预热需 7-8 分钟，之后推理稳定在 3.67s/3s 音频
- MediaMTX v1.9.0 使用正则路径 `~^(.+)$` 允许动态 RTMP 推流路径
- 所有测试在 NPU prewarm 完成后执行

## Phase 9：视频生成嘴部清晰度优化

### 优化项

| 参数 | 旧值 | 新值 | 说明 |
|------|------|------|------|
| Mask 高斯模糊系数 | 0.1（硬编码） | 0.05（可配置） | 降低嘴部边缘羽化 |
| 渲染上采样插值 | INTER_LINEAR（默认） | INTER_LANCZOS4 | 256×256 贴回原 bbox 时更清晰 |
| FFmpeg preset | 无 | medium（可配置） | 编码速度/质量可控 |

### 关键环境变量

```bash
THG_BLUR_RATIO=0.05
THG_RENDER_INTERPOLATION=lanczos4
FFMPEG_CRF=18
FFMPEG_PRESET=medium
```

### 验证方法

1. 清理旧缓存后重新上传/预处理 avatar：
   ```bash
   rm -rf /ascend-avatar/output/v15/avatars/<upload_id>
   ```
2. 调用 `/api/generate` 生成短视频，文本建议包含明显嘴型变化（如 "波坡摸佛"）。
3. 抽取若干帧，计算嘴部 ROI 的 Laplacian 方差，或主观对比唇线清晰度。

### 测试记录

| # | 日期 | 配置 | 文本 | 素材 | 输出 | 嘴部 Laplacian 方差均值 | 备注 |
|---|------|------|------|------|------|------------------------|------|
| 1 | 2026-06-23 | blur=0.05, lanczos4, preset=medium | 你好，欢迎使用数字人。今天天气真不错。 | 默认 avatar 512×512 | 512×512@25fps, 136 帧 | **1065.55** | 新默认配置，PaddleSpeech TTS |
| 2 | 2026-06-23 | blur=0.1, linear, preset=medium | 同上 | 默认 avatar 512×512 | 512×512@25fps, 136 帧 | **1063.68** | 旧配置基线 |
| 3 | 2026-06-23 | blur=0.05, lanczos4, preset=medium | 你好，这是用 MyVideo_1 做的数字人测试。 | MyVideo_1.mp4 1280×720@25fps | 1280×720@25fps, 92 帧 | **123.38** | 用户上传样片全流程验证 |

### 调参建议

- 嘴部边缘仍偏软：适当降低 `THG_BLUR_RATIO`（0.03–0.05）。
- 出现 mask 接缝/抖动：适当提高 `THG_BLUR_RATIO`（0.06–0.08）或增大 `THG_EXPAND`。
- 需要更小文件/更快编码：将 `FFMPEG_PRESET` 改为 `fast` 或 `veryfast`，`FFMPEG_CRF` 改为 23。

## Phase 10：进一步降低模糊 + 输入缩放 + GFPGAN 后处理

### 优化项

| 参数 | 旧值 | 新值 | 说明 |
|------|------|------|------|
| 默认 `THG_BLUR_RATIO` | 0.05 | 0.03 | 更小的 mask 高斯核，嘴部边缘更锐 |
| `MUSE_TALK_BBOX_SHIFT` | 0 | -7 | 嘴部 bbox 更紧凑（A/B 中表现最好） |
| 输入预处理 | 原分辨率 | 512×512 | 上传/默认 avatar 先中心裁剪为正方形再缩放，降低 256→原图的上采样失真 |
| 后处理 | 无 | GFPGAN v1.4 (NPU) | 视频生成模式下可选人脸增强；已切至 NPU |

### 关键环境变量

```bash
THG_BLUR_RATIO=0.03
MUSE_TALK_BBOX_SHIFT=-7
THG_PREPARE_RESOLUTION=512x512
VIDEO_GEN_POSTPROCESS_GFPGAN=true
GFPGAN_MODEL_PATH=/ascend-avatar/thg/models/gfpgan/GFPGANv1.4.pth
GFPGAN_DEVICE=npu
```

### 测试记录（MyVideo_1.mp4）

| 配置 | 输出 | 嘴部 Laplacian 方差均值 | GFPGAN 耗时 | 备注 |
|------|------|------------------------|------------|------|
| blur=0.03, bbox=-7, 512×512 输入 | 512×512@25fps, 86 帧, RAW | **166.23** | - | 未做 GFPGAN |
| 同上 + GFPGAN v1.4 NPU | 512×512@25fps, 86 帧 | **298.32** | **~42 s** | 颜色正常，肤色/背景保持；Laplacian 提升约 79% |

> 注：早期的 GFPGAN 后处理实现错误地做了 `COLOR_RGB2BGR`，导致红蓝通道互换（蓝色背景变红、皮肤红色变蓝）。已在 `src/gfpgan_postprocess.py` 中移除该转换，因为 GFPGAN 的 `paste_back=True` 实际返回的是 BGR 格式。

### 注意事项

- `THG_PREPARE_RESOLUTION=512x512` 会对输入做中心裁剪，人物必须在画面中心。
- GFPGAN 在 CPU 上处理约 92 帧需要 1–2 分钟；切换到 `GFPGAN_DEVICE=npu` 后降至约 40–45 秒。
- 首次使用 GFPGAN 会自动下载 `detection_Resnet50_Final.pth` 和 `parsing_parsenet.pth` 到 `gfpgan/weights/`；离线环境请提前放置。
- NPU 路径会自动初始化 `torch_npu.npu.set_device`，并在失败时回退到 CPU，避免任务失败。
