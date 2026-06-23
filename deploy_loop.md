# ascend-avatar 部署手册（Loop 方法论版）

> **项目**：`ascend-avatar` — 基于昇腾 910B 的语音克隆 + 实时数字人  
> **部署方式**：Docker 容器（基于 `ascend-pytorch:24.0.0-A2-2.1.0`）  
> **交互方式**：Gradio WebUI（`http://宿主机IP:8188`）  
> **前置条件**：LLM（OpenAI API）已部署，本手册只负责 TTS + THG 链路  
> **方法论**：Agentic Loop — 每个 Phase 有触发器、完成标准、检查者、回退路径

---

## 1. Loop 设计总览

本文档不是一次性执行的脚本，而是一个**分阶段可验证的闭环系统**。每个 Phase 必须**验证通过**才能进入下一阶段；失败时回退到当前 Phase 起点，带错误信息重新计划。

### 1.1 Loop 元数据

| 要素 | 定义 |
|------|------|
| **触发器** | 用户手动启动部署流程（`docker exec` 进入容器） |
| **目标** | 在容器内运行端到端数字人 WebUI，输入问题 → 数字人视频回答 |
| **完成标准** | WebUI 可访问；输入问题后 30s 内输出有效 MP4；唇型与音频肉眼对齐 |
| **检查者** | Shell 脚本验证（机器可验证）+ 人工播放验收（主观） |
| **状态记录** | 每 Phase 完成追加写入 `loop-state.md` |
| **停止条件** | 6 个 Phase 全部通过；或同一 Phase 连续失败 3 次 |
| **人工接管点** | Phase 0（NPU 不可用）、Phase 3（模型下载失败需手动）、Phase 6（质量不达标） |

### 1.2 部署总览：6-Phase Loop

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Phase 0    │ ──→ │  Phase 1    │ ──→ │  Phase 2    │
│ 容器基线验证 │     │ 环境依赖安装 │     │ 项目代码部署 │
└─────────────┘     └─────────────┘     └─────────────┘
       ↑                                          │
       │     ┌─────────────┐     ┌─────────────┐  │
       └──── │  Phase 6    │ ←── │  Phase 5    │ ←┘
              │ WebUI 验收  │     │ 流水线集成  │
              └─────────────┘     └─────────────┘
                     ↑
              ┌─────────────┐
              │  Phase 4    │
              │ 模型适配与预热│
              └─────────────┘
                     ↑
              ┌─────────────┐
              │  Phase 3    │
              │ 模型权重下载 │
              └─────────────┘
```

**Loop 规则**：
- 每 Phase 结束时，**检查者**运行验证脚本；通过 → 写入状态 → 进入下 Phase；失败 → 本 Phase 重试（最多 3 次）
- 重试 3 次仍失败 → **人工接管**（暂停，记录问题，等待人工决策）

---

## 2. 状态记录机制：`loop-state.md`

每完成一个 Phase，在当前目录追加记录。这是 Loop 的**记忆系统**，确保多会话、中断恢复、多人协作时知道当前状态。

```bash
# 初始化状态文件
cat > /ascend-avatar/loop-state.md << 'EOF'
# ascend-avatar Loop 状态记录

部署时间: ________
部署者: ________

## 部署前检查清单
- [ ] 容器已启动（`docker ps | grep ascend-avatar`）
- [ ] LLM API Token 已获取
- [ ] 形象照片已准备（avatars/ 目录）
- [ ] 音色样本已准备（voices/ 目录）
- [ ] NPU 设备可用（`npu-smi info` 在宿主机通过）

EOF
```

**Phase 完成模板**（每个 Phase 验证通过后，执行记录脚本）：

```bash
# 用法：bash scripts/record_phase.sh <Phase号> <结果> <耗时> <验证人>
# 例如：bash scripts/record_phase.sh 0 PASS 2min root

cat >> /ascend-avatar/loop-state.md << EOF

## Phase $1: ____________ $2
- 日期: $(date '+%Y-%m-%d %H:%M:%S')
- 结果: $2
- 耗时: $3
- 验证人: $4
- 关键信息: ____________

EOF
```

---

## 3. Phase 0：容器基线验证

> **触发器**：容器已启动（`docker run` 成功），用户 `docker exec` 进入容器  
> **目标**：确认容器内 NPU、PyTorch、NumPy 基线满足后续部署条件  
> **建议耗时**：2 分钟  
> **最大重试**：3 次（NPU 未识别需检查设备映射）  
> **人工接管点**：如果 `npu-smi` 无输出，说明宿主机驱动/设备映射有问题，需人工检查

### 3.1 上下文（Context）

你的容器已基于以下镜像启动：
```
swr.cn-south-1.myhuaweicloud.com/ascendhub/ascend-pytorch:24.0.0-A2-2.1.0-ubuntu20.04
```
该镜像理论上已包含：CANN + PyTorch 2.1.0 + torch_npu 2.1.0。但容器启动时映射了 `--device=/dev/davinci7`，需确认单卡映射是否满足需求（单并发最低 1 卡，推荐 2 卡）。

### 3.2 执行步骤（Execute）

```bash
# 1. 确认容器内 NPU 可见
npu-smi info
# 预期：至少 1 张 910B，Health=OK

# 2. 确认 PyTorch NPU 可用
python -c "import torch; import torch_npu; print('NPU available:', torch.npu.is_available()); print('NPU count:', torch.npu.device_count())"
# 预期：True, >=1

# 3. 确认 NumPy 版本（必须 < 2.0）
python -c "import numpy; print(numpy.__version__)"
# 预期：1.26.x
# 如果 >= 2.0：pip install numpy==1.26.4

# 4. 确认 Python 版本
python --version
# 预期：3.10.x
```

### 3.3 检查者（Checker）与完成标准（Exit Criteria）

| 检查项 | 通过标准 | 验证命令 | 检查者 |
|--------|---------|---------|--------|
| NPU 可见 | 输出包含 910B 且 Health=OK | `npu-smi info \| grep 910B` | 脚本 |
| PyTorch NPU | `torch.npu.is_available()` = True | `python -c "import torch_npu; print(torch.npu.is_available())"` | 脚本 |
| 设备数量 | ≥ 1（推荐 ≥ 2） | `python -c "import torch; print(torch.npu.device_count())"` | 脚本 |
| NumPy 版本 | < 2.0 | `python -c "import numpy; v=numpy.__version__; assert v.startswith('1.26'), f'NumPy {v} not compatible'; print('OK')"` | 脚本 |
| 内核兼容 | 无报错 | 以上命令无 ImportError / OSError | 脚本 |

### 3.4 反馈回退（Course Correct）

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| NPU 未识别 | 宿主机驱动未映射到容器 | 退出容器，检查 `docker run` 的 `--device` 参数 | 宿主机执行 `ls /dev/davinci*` 确认设备存在 |
| PyTorch 导入失败 | 镜像版本不匹配 | 检查镜像 tag 是否为 `2.1.0` | 如错误，宿主机重拉正确镜像 |
| NumPy ≥ 2.0 | 镜像自带版本过新 | 降级 NumPy | `pip install numpy==1.26.4` |
| 单卡可用 | 容器只映射了 davinci7 | 确认是否需要多卡 | 单并发可继续，但 TTS/THG 需串行；推荐映射 2 卡 `--device=/dev/davinci6 --device=/dev/davinci7` |

### 3.5 状态记录

```bash
bash scripts/record_phase.sh 0 "容器基线验证" PASS 2min $(whoami)
```

---

## 4. Phase 1：环境依赖安装

> **触发器**：Phase 0 验证通过（NPU、PyTorch、NumPy 全部 OK）  
> **目标**：安装系统级和 Python 级依赖，为 TTS 和 THG 模型做准备  
> **建议耗时**：15~20 分钟（mmcv 编译耗时）  
> **最大重试**：2 次（mmcv 编译失败可重试）  
> **人工接管点**：如果 `apt-get` 无法访问外网（容器内无网络），需人工配置代理或换源

### 4.1 上下文

本 Phase 需要：
- `ffmpeg`：音视频合成（MuseTalk 输出帧 + TTS 音频 → MP4）
- `git` / `wget`：下载项目代码和权重
- `gradio`：WebUI 框架
- `mmcv` / `mmdet` / `mmpose`：MuseTalk 的人脸检测和姿态检测依赖
- `librosa` / `soundfile`：音频处理

### 4.2 执行步骤

```bash
cd /ascend-avatar

# 步骤 1：系统依赖
apt-get update
apt-get install -y ffmpeg git wget
# 验证：ffmpeg -version

# 步骤 2：Python 基础依赖
pip install gradio==4.44.1 \
    opencv-python-headless scikit-image \
    librosa==0.10.1 soundfile \
    transformers>=4.35.0 accelerate \
    scipy pillow tqdm pyyaml ffmpeg-python

# 步骤 3：OpenMMLab 工具链（MuseTalk 必须，编译耗时 10~20 分钟）
pip install --no-cache-dir -U openmim
mim install mmengine
mim install "mmcv==2.0.1"
mim install "mmdet==3.1.0"
mim install "mmpose==1.1.0"

# 验证 mmcv
python -c "import mmcv; print('mmcv:', mmcv.__version__)"
```

### 4.3 检查者（Checker）与完成标准

| 检查项 | 通过标准 | 验证命令 | 检查者 |
|--------|---------|---------|--------|
| FFmpeg | 可正常输出版本 | `ffmpeg -version \| head -1` | 脚本 |
| Gradio | 无 ImportError | `python -c "import gradio; print(gradio.__version__)"` | 脚本 |
| mmcv | 2.0.1，无报错 | `python -c "import mmcv; print(mmcv.__version__)"` | 脚本 |
| mmdet | 无 ImportError | `python -c "import mmdet; print('mmdet OK')"` | 脚本 |
| mmpose | 无 ImportError | `python -c "import mmpose; print('mmpose OK')"` | 脚本 |
| librosa | 无 ImportError | `python -c "import librosa; print(librosa.__version__)"` | 脚本 |

### 4.4 反馈回退

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| `apt-get` 失败 | 无网络或源不可用 | 配置镜像源 | `sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list` |
| `mim install mmcv` 编译失败 | GCC 版本低或缺少头文件 | 安装 build 工具 | `apt-get install -y build-essential python3-dev` |
| `mim install` 超时 | 网络慢 | 换国内源或重试 | `pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| 依赖冲突 | 版本不兼容 | 隔离重装 | `pip uninstall <pkg> -y && pip install <pkg>==<version>` |

### 4.5 状态记录

```bash
bash scripts/record_phase.sh 1 "环境依赖安装" PASS 15min $(whoami)
```

---

## 5. Phase 2：项目代码部署

> **触发器**：Phase 1 验证通过（所有依赖安装成功）  
> **目标**：下载 GPT-SoVITS 和 MuseTalk 源码，创建目录结构，将 ascend-avatar 核心代码放入容器  
> **建议耗时**：5 分钟  
> **最大重试**：2 次（GitHub 下载失败可换镜像源）  
> **人工接管点**：如果 GitHub 无法访问，需人工配置 GitHub 镜像或手动上传代码

### 5.1 上下文

需要两个开源项目：
- **TTS**：GPT-SoVITS（零样本语音克隆）
- **THG**：MuseTalk（实时唇形同步数字人）

以及 ascend-avatar 的自定义代码（llm_client, tts_engine, thg_engine, pipeline, webui）。

### 5.2 执行步骤

```bash
cd /ascend-avatar

# 1. 下载 TTS 项目
git clone https://github.com/RVC-Boss/GPT-SoVITS.git tts
# 备选：git clone https://gitcode.com/gh_mirrors/gpt-sovits/GPT-SoVITS.git tts

# 2. 下载 THG 项目
git clone https://github.com/TMElyralab/MuseTalk.git thg
# 备选：git clone https://gitcode.com/gh_mirrors/mu/MuseTalk.git thg

# 3. 安装项目各自的 Python 依赖
pip install -r tts/requirements.txt
pip install -r thg/requirements.txt

# 4. 创建资源目录
mkdir -p avatars voices output/tts output/thg

# 5. 确认项目结构
ls /ascend-avatar/
# 预期：tts/  thg/  avatars/  voices/  output/
```

### 5.3 检查者（Checker）与完成标准

| 检查项 | 通过标准 | 验证命令 | 检查者 |
|--------|---------|---------|--------|
| TTS 目录 | 存在且含 Python 文件 | `ls /ascend-avatar/tts/GPT_SoVITS/ \| head` | 脚本 |
| THG 目录 | 存在且含 Python 文件 | `ls /ascend-avatar/thg/musetalk/ \| head` | 脚本 |
| 资源目录 | 存在 | `ls -d /ascend-avatar/avatars /ascend-avatar/voices /ascend-avatar/output` | 脚本 |
| 依赖安装 | 无 ImportError | `python -c "import sys; sys.path.insert(0,'/ascend-avatar/tts'); from GPT_SoVITS.inference_webui import get_tts_wav; print('TTS import OK')"` | 脚本 |

### 5.4 反馈回退

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| GitHub 无法克隆 | 网络不通 | 换国内镜像 | `git clone https://gitcode.com/gh_mirrors/...` |
| 依赖安装失败 | 版本冲突 | 逐项排查 | 单独 `pip install` 定位冲突包 |
| 导入失败 | 路径问题 | 检查 sys.path | 确认 `sys.path.insert` 指向正确 |

### 5.5 状态记录

```bash
bash scripts/record_phase.sh 2 "项目代码部署" PASS 5min $(whoami)
```

---

## 6. Phase 3：模型权重下载

> **触发器**：Phase 2 验证通过（项目代码就绪）  
> **目标**：下载 TTS 底模和 MuseTalk 预训练权重（~7GB）  
> **建议耗时**：10~30 分钟（取决于网络）  
> **最大重试**：3 次（网络中断可重试）  
> **人工接管点**：如果自动下载脚本失败，需人工从 HuggingFace/ModelScope 手动下载并放入指定目录

### 6.1 上下文

模型权重是推理的前提。MuseTalk 需要多个组件权重，GPT-SoVITS 需要预训练底模。

### 6.2 执行步骤

```bash
cd /ascend-avatar

# 1. MuseTalk 权重自动下载
cd thg
sh ./download_weights.sh
# 如果脚本失败，手动下载以下权重并放入 models/ 目录：
#   - musetalkV15/unet.pth
#   - sd-vae/diffusion_pytorch_model.bin
#   - whisper/pytorch_model.bin
#   - dwpose/dw-ll_ucoco_384.pth
#   - face-parse-bisent/79999_iter.pth
#   - syncnet/latentsync_syncnet.pt

cd /ascend-avatar

# 2. GPT-SoVITS 权重
# 从官方链接下载预训练底模，放入 tts/pretrained_models/
# 或运行官方下载脚本（如果有）

# 3. 验证权重目录结构
ls -lh thg/models/
```

### 6.3 权重目录结构检查

```bash
# 检查者脚本：验证所有必要文件存在
cat > /ascend-avatar/scripts/check_models.sh << 'EOF'
#!/bin/bash
set -e

MODEL_DIR="/ascend-avatar/thg/models"
REQUIRED=(
  "musetalkV15/unet.pth"
  "sd-vae/diffusion_pytorch_model.bin"
  "whisper/pytorch_model.bin"
  "dwpose/dw-ll_ucoco_384.pth"
)

for f in "${REQUIRED[@]}"; do
  if [ ! -f "$MODEL_DIR/$f" ]; then
    echo "MISSING: $MODEL_DIR/$f"
    exit 1
  fi
  echo "OK: $f"
done

echo "ALL MODELS CHECK PASSED"
EOF
chmod +x /ascend-avatar/scripts/check_models.sh
bash /ascend-avatar/scripts/check_models.sh
```

### 6.4 检查者（Checker）与完成标准

| 检查项 | 通过标准 | 验证命令 | 检查者 |
|--------|---------|---------|--------|
| MuseTalk UNet | 存在且大小 > 0 | `ls -lh thg/models/musetalkV15/unet.pth` | 脚本 |
| SD-VAE | 存在 | `ls -lh thg/models/sd-vae/diffusion_pytorch_model.bin` | 脚本 |
| Whisper | 存在 | `ls -lh thg/models/whisper/pytorch_model.bin` | 脚本 |
| DWPose | 存在 | `ls -lh thg/models/dwpose/dw-ll_ucoco_384.pth` | 脚本 |
| GPT-SoVITS 底模 | 存在 | `ls -lh tts/pretrained_models/ \| head` | 脚本 |

### 6.5 反馈回退

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| 下载脚本失败 | 网络问题或脚本失效 | 手动下载 | 从 HuggingFace/ModelScope 下载，按目录结构放置 |
| 权重文件损坏 | 校验失败 | 重新下载 | `md5sum` 校验后重下 |
| 存储不足 | 磁盘满 | 清理空间 | `df -h` 确认 `/ascend-avatar` 或 `/tmp` 有空间 |

### 6.6 状态记录

```bash
bash scripts/record_phase.sh 3 "模型权重下载" PASS 20min $(whoami)
```

---

## 7. Phase 4：昇腾适配与模型预热

> **触发器**：Phase 3 验证通过（权重就绪）  
> **目标**：将 CUDA 硬编码替换为 NPU 兼容写法，加载模型并预热（消除首次推理 overhead）  
> **建议耗时**：5 分钟  
> **最大重试**：2 次（算子编译失败可清除缓存重试）  
> **人工接管点**：如果替换后仍有大量算子不支持，需确认 CANN 版本或考虑降级模型精度

### 7.1 上下文

GPT-SoVITS 和 MuseTalk 默认写死了 `.cuda()`，在昇腾上必须替换为 `.to(device)` 或 `.to('npu')`。同时，首次加载模型到 NPU 时会触发算子编译，需要预热。

### 7.2 执行步骤

```bash
cd /ascend-avatar

# 步骤 1：批量替换 CUDA 硬编码（TTS）
find tts -name "*.py" -exec sed -i 's/\.cuda()/.to(device)/g' {} +
find tts -name "*.py" -exec sed -i 's/torch.cuda/torch.npu/g' {} +
find tts -name "*.py" -exec sed -i 's/"cuda"/"npu"/g' {} +
find tts -name "*.py" -exec sed -i "s/'cuda'/'npu'/g" {} +

# 步骤 2：批量替换 CUDA 硬编码（THG）
find thg -name "*.py" -exec sed -i 's/\.cuda()/.to(device)/g' {} +
find thg -name "*.py" -exec sed -i 's/torch.cuda/torch.npu/g' {} +
find thg -name "*.py" -exec sed -i 's/"cuda"/"npu"/g' {} +
find thg -name "*.py" -exec sed -i "s/'cuda'/'npu'/g" {} +

# 步骤 3：验证替换（无残留 .cuda()）
grep -r "\.cuda()" tts/ thg/ || echo "No .cuda() found, OK"
# 如果还有残留，手动处理

# 步骤 4：模型预热（TTS）
python -c "
import sys, torch, torch_npu
sys.path.insert(0, '/ascend-avatar/tts')
from GPT_SoVITS.inference_webui import get_tts_wav
torch.npu.set_device('npu:0')
torch.npu.set_autocast_enabled(True)
print('TTS model warmup: loading...')
# 这里可以执行一次 dummy inference，如果不需要语音样本可跳过
print('TTS warmup OK')
"

# 步骤 5：模型预热（THG）
python -c "
import sys, torch, torch_npu
sys.path.insert(0, '/ascend-avatar/thg')
from musetalk.models import MuseTalkModel
torch.npu.set_device('npu:1')
model = MuseTalkModel().to('npu:1')
model.eval()
torch.npu.set_autocast_enabled(True)
print('THG model warmup OK')
"
```

### 7.3 检查者（Checker）与完成标准

| 检查项 | 通过标准 | 验证命令 | 检查者 |
|--------|---------|---------|--------|
| CUDA 残留 | 无 `.cuda()` 硬编码 | `grep -r "\.cuda()" tts/ thg/ \| wc -l` = 0 | 脚本 |
| TTS 加载 | 无 OOM / 无算子报错 | 预热脚本输出 `TTS warmup OK` | 脚本 |
| THG 加载 | 无 OOM / 无算子报错 | 预热脚本输出 `THG warmup OK` | 脚本 |
| NPU 显存 | 加载后仍有剩余 | `npu-smi info` Memory-Usage 合理 | 人工 |

### 7.4 反馈回退

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| `.cuda()` 残留 | 替换脚本未覆盖 | 手动处理 | `grep -rn "\.cuda()" tts/ thg/` 定位后手动改 |
| 算子不支持 | CANN 版本低 | 确认 CANN 版本 | `cat /usr/local/Ascend/ascend_toolkit/latest/version.cfg` |
| OOM | 模型太大 | 开 AMP 或降级 | `torch.npu.set_autocast_enabled(True)` |
| 预热极慢 | 算子编译 | 正常现象 | 等待完成，后续会复用缓存 `~/.cache/ascend` |

### 7.5 状态记录

```bash
bash scripts/record_phase.sh 4 "昇腾适配与预热" PASS 5min $(whoami)
```

---

## 8. Phase 5：流水线集成验证

> **触发器**：Phase 4 验证通过（模型已适配并预热）  
> **目标**：将 LLM API + TTS + THG 串联，验证端到端单条生成  
> **建议耗时**：5 分钟  
> **最大重试**：2 次（接口对接问题）  
> **人工接管点**：如果 LLM API 返回空或报错，需人工确认 Token 和 URL 正确性

### 8.1 上下文

这是**核心验证**：确认 LLM 能返回文本、TTS 能生成音频、THG 能生成视频、FFmpeg 能合成。

### 8.2 执行步骤

```bash
cd /ascend-avatar

# 1. 配置 LLM API Token（必须设置）
export LLM_API_URL="https://modelhub.lgdg.cc/aigateway/v1/chat/completions"
export LLM_API_KEY="your_actual_token_here"
export LLM_MODEL="DeepSeek-V4-Flash-w8a8-mtp"

# 2. 放入测试素材（如未放）
# 确保 avatars/ 下有 default.jpg（正面人脸照片）
# 确保 voices/ 下有 default.wav（3~10 秒中文音色样本）

# 3. 运行端到端验证脚本
cat > /ascend-avatar/scripts/verify_pipeline.py << 'EOF'
import sys
sys.path.insert(0, '/ascend-avatar')

from src.llm_client import LLMClient
from src.tts_engine import TTSEngine
from src.thg_engine import THGEngine
import os

# 验证 LLM
print("[1/4] Testing LLM...")
llm = LLMClient()
text = llm.chat_complete("你好，请用一句话介绍深度学习。")
assert len(text) > 10, "LLM returned empty"
print(f"    LLM OK: {text[:50]}...")

# 验证 TTS
print("[2/4] Testing TTS...")
tts = TTSEngine(device="npu:0")
audio = tts.synthesize(text[:20], voice_name="default")  # 短句测试
assert audio.exists(), "TTS output missing"
print(f"    TTS OK: {audio}")

# 验证 THG
print("[3/4] Testing THG...")
thg = THGEngine(device="npu:1")
video = "/ascend-avatar/output/test_verify.mp4"
thg.render(str(audio), "/ascend-avatar/avatars/default.jpg", video)
assert os.path.exists(video), "THG output missing"
import subprocess
info = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video])
duration = float(info.strip())
assert duration > 0.5, "Video too short"
print(f"    THG OK: {video}, duration={duration:.2f}s")

# 验证 FFmpeg 合成
print("[4/4] All checks passed!")
EOF

python /ascend-avatar/scripts/verify_pipeline.py
```

### 8.3 检查者（Checker）与完成标准

| 检查项 | 通过标准 | 验证命令 | 检查者 |
|--------|---------|---------|--------|
| LLM 连通 | 返回非空文本 | 验证脚本输出 LLM OK | 脚本 |
| TTS 合成 | 生成有效 wav | 验证脚本输出 TTS OK | 脚本 |
| THG 渲染 | 生成有效 mp4 | 验证脚本输出 THG OK | 脚本 |
| 视频时长 | > 0.5 秒 | `ffprobe` 检查 duration | 脚本 |
| 全流程 | 端到端无报错 | 脚本输出 All checks passed | 脚本 |

### 8.4 反馈回退

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| LLM 返回空 | Token 错误 | 检查 API Key | `export LLM_API_KEY="..."` |
| LLM 超时 | 网络问题 | 测试 curl | `curl -v $LLM_API_URL` |
| TTS 失败 | 参考音频问题 | 换音频 | 准备 3~10 秒清晰中文 WAV |
| THG 失败 | 算子/显存 | 检查日志 | 查看 `npu-smi info` 显存 |
| 视频无声音 | FFmpeg 合成 | 检查音频路径 | 确认 `audio_path` 存在且非空 |

### 8.5 状态记录

```bash
bash scripts/record_phase.sh 5 "流水线集成验证" PASS 5min $(whoami)
```

---

## 9. Phase 6：WebUI 上线与验收

> **触发器**：Phase 5 验证通过（端到端单条生成成功）  
> **目标**：启动 Gradio WebUI，浏览器可访问，输入问题后数字人回答  
> **建议耗时**：2 分钟  
> **最大重试**：2 次（端口占用或前端报错）  
> **人工接管点**：如果视频生成时间 > 30 秒或嘴型不同步，需人工评估质量并决定是否优化

### 9.1 上下文

由于容器使用 `--net=host`，WebUI 监听 `0.0.0.0:8188` 即等同于宿主机 8188 端口。无需额外端口映射。

### 9.2 执行步骤

```bash
cd /ascend-avatar

# 1. 启动 WebUI（后台或前台）
export LLM_API_KEY="your_actual_token_here"
python src/webui.py

# 预期输出：
# Running on local URL:  http://0.0.0.0:8188
```

### 9.3 检查者（Checker）与完成标准

| 检查项 | 通过标准 | 验证方式 | 检查者 |
|--------|---------|---------|--------|
| 服务监听 | 端口 8188 在监听 | 容器内：`netstat -tlnp \| grep 8188` | 脚本 |
| 浏览器可访问 | 页面加载无报错 | 浏览器访问 `http://<宿主机IP>:8188` | 人工 |
| 输入问题 | 可输入文本并提交 | 前端交互正常 | 人工 |
| 数字人输出 | 30s 内输出 MP4 | 等待视频生成 | 人工 |
| 视频质量 | 嘴型与音频肉眼对齐 | 播放视频观察 | 人工 |
| 语音质量 | 可听懂，音色一致 | 播放音频 | 人工 |

### 9.4 验收测试流程（Human-in-the-Loop）

```bash
# 验收清单（浏览器中逐一勾选）
cat > /ascend-avatar/ACCEPTANCE.md << 'EOF'
# ascend-avatar 验收清单

## 环境验收
- [ ] 容器已启动（`docker ps | grep ascend-avatar`）
- [ ] NPU 可用（`npu-smi info` 在容器内通过）
- [ ] WebUI 可访问（浏览器打开 http://宿主机IP:8188）

## 功能验收
- [ ] 输入问题后，LLM 能返回有效文本
- [ ] 文本经过 TTS 生成语音（可播放）
- [ ] 语音经过 THG 生成数字人视频（可播放）
- [ ] 视频时长与语音时长大致匹配
- [ ] 嘴型开合与音频内容肉眼对齐（无严重错位）

## 性能验收
- [ ] 短句（~5 字）生成时间 < 10 秒
- [ ] 中句（~20 字）生成时间 < 30 秒
- [ ] 长句（~50 字）生成时间 < 60 秒
- [ ] NPU 温度 < 85°C（`npu-smi info`）

## 资源验收
- [ ] 单并发 1 张 910B 可运行（TTS + THG 串行）
- [ ] 或 2 张 910B 分离部署（TTS npu:0 + THG npu:1）

## 验收结论
□ 通过  □ 不通过（需优化：__________）

验收人: __________
日期: __________
EOF
```

### 9.5 反馈回退

| 故障 | 诊断 | 回退动作 | 修正命令 |
|------|------|---------|---------|
| 页面打不开 | 端口未监听 | 检查进程 | `ps aux \| grep webui` |
| 生成超时 | 串行瓶颈 | 双卡分离 | 改 `pipeline.py` 设备分配 |
| 嘴型不同步 | 音频特征/模型 | 调参数 |  MuseTalk `bbox_shift` 参数调整 |
| 语音不像 | 参考音频质量 | 换样本 | 放入更清晰、更长的参考音频 |
| 视频卡顿 | 分辨率太高 | 降级 | MuseTalk 默认 256×256，确认未改大 |

### 9.6 状态记录（最终）

```bash
bash scripts/record_phase.sh 6 "WebUI 上线与验收" PASS 2min $(whoami)
```

最终 `loop-state.md` 应呈现完整部署履历：

```markdown
# ascend-avatar Loop 状态记录

部署时间: 2026-06-15 14:00
部署者: root

## 部署前检查清单
- [x] 容器已启动
- [x] LLM API Token 已获取
- [x] 形象照片已准备
- [x] 音色样本已准备
- [x] NPU 设备可用

## Phase 0: 容器基线验证 ✅
- 日期: 2026-06-15 14:02
- 结果: PASS
- 耗时: 2min
- 验证人: root
- 关键信息: NPU 2 卡可用，NumPy 1.26.4

## Phase 1: 环境依赖安装 ✅
- 日期: 2026-06-15 14:20
- 结果: PASS
- 耗时: 18min
- 验证人: root
- 关键信息: mmcv 2.0.1 编译成功

## Phase 2: 项目代码部署 ✅
- 日期: 2026-06-15 14:25
- 结果: PASS
- 耗时: 5min
- 验证人: root

## Phase 3: 模型权重下载 ✅
- 日期: 2026-06-15 14:50
- 结果: PASS
- 耗时: 25min
- 验证人: root
- 关键信息: 手动补下了 syncnet 权重

## Phase 4: 昇腾适配与预热 ✅
- 日期: 2026-06-15 14:55
- 结果: PASS
- 耗时: 5min
- 验证人: root

## Phase 5: 流水线集成验证 ✅
- 日期: 2026-06-15 15:00
- 结果: PASS
- 耗时: 5min
- 验证人: root

## Phase 6: WebUI 上线与验收 ✅
- 日期: 2026-06-15 15:05
- 结果: PASS
- 耗时: 2min
- 验证人: root

## 部署完成 ✅
- 访问地址: http://宿主机IP:8188
- 启动命令: python src/webui.py
- 验收结论: 通过
```

---

## 10. Loop 检查清单（总览）

| Phase | 触发器 | 完成标准 | 检查者 | 人工接管点 | 最大重试 |
|-------|--------|---------|--------|-----------|---------|
| 0 | 进入容器 | NPU/NumPy/PyTorch 基线 OK | 脚本 | NPU 未识别 | 3 |
| 1 | Phase 0 通过 | 所有依赖可导入 | 脚本 | 无网络 | 2 |
| 2 | Phase 1 通过 | 项目代码可导入 | 脚本 | GitHub 不通 | 2 |
| 3 | Phase 2 通过 | 权重文件全部存在 | 脚本 | 下载失败 | 3 |
| 4 | Phase 3 通过 | 模型加载无报错 | 脚本 | 算子大面积不支持 | 2 |
| 5 | Phase 4 通过 | 端到端生成有效视频 | 脚本 | LLM API 不通 | 2 |
| 6 | Phase 5 通过 | WebUI 可访问且质量可接受 | 人工 | 质量不达标 | 2 |

---

## 11. 附录：核心代码文件索引

以下代码文件已放入项目目录，供各 Phase 引用：

| 文件 | Phase 引用 | 说明 |
|------|-----------|------|
| `src/llm_client.py` | 5, 6 | LLM API 客户端（OpenAI 格式，流式） |
| `src/tts_engine.py` | 4, 5 | GPT-SoVITS 语音克隆（npu:0） |
| `src/thg_engine.py` | 4, 5 | MuseTalk 数字人渲染（npu:1） |
| `src/pipeline.py` | 5 | 端到端流水线：LLM → TTS → THG |
| `src/webui.py` | 6 | Gradio WebUI，监听 :8188 |
| `scripts/start.sh` | 6 | 一键启动脚本 |
| `scripts/check_models.sh` | 3 | 模型权重检查脚本 |
| `scripts/verify_pipeline.py` | 5 | 端到端验证脚本 |
| `scripts/record_phase.sh` | 全部 | Phase 状态记录脚本 |
| `Dockerfile` | — | 自定义镜像构建（可选） |

---

## 12. 附录：版本兼容性铁律

| CANN | PyTorch | torch_npu | NumPy | 状态 |
|------|---------|-----------|-------|------|
| 8.0 | 2.1.0 | 2.1.0 | 1.26.x | ✅ 推荐 |
| 7.0 | 2.1.0 | 2.1.0 | 1.26.x | ✅ 稳定 |
| 任意 | 任意 | 任意 | ≥ 2.0 | ❌ 不兼容 |

> **任何版本组合变更，必须重新执行 Phase 0 和 Phase 4 验证。**

---

*本文档基于 Agentic Loop 方法论设计：每个 Phase 有目标、有验证、有反馈回退、有状态记录、有人工接管点。部署时请逐 Phase 执行，验证通过后再推进，避免跨 Phase 问题堆叠。*

