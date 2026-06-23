# ascend-avatar Loop 状态记录

部署时间: 2026-06-15 14:00
部署者: root

## 部署前检查清单
- [x] 容器已启动（docker ps | grep ascend-avatar）
- [x] LLM API Token 已获取
- [x] 形象照片已准备（avatars/ 目录）
- [x] 音色样本已准备（voices/ 目录）
- [x] NPU 设备可用（npu-smi info 在宿主机通过）


## Phase 0: 容器基线验证 PASS
- 日期: 2026-06-15 06:50:13
- 结果: PASS
- 耗时: 2min
- 验证人: HwHiAiUser
- 关键信息: NPU 8卡可用，NumPy 1.26.4，torch 2.1.0，torch_npu 2.1.0.post10


## Phase 1: 环境依赖安装 PASS
- 日期: 2026-06-15 07:56:05
- 结果: PASS
- 耗时: 60min
- 验证人: HwHiAiUser
- 关键信息: mmcv-lite 2.0.1, mmdet, mmpose, gradio 4.44.1, ffmpeg static


## Phase 2: 项目代码部署 PASS
- 日期: 2026-06-15 09:44:21
- 结果: PASS
- 耗时: 20min
- 验证人: HwHiAiUser
- 关键信息: GPT-SoVITS 和 MuseTalk 代码已部署，TTS 缺少预训练模型权重

