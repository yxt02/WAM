# VJEPA AC 与 Policy 环境配置和运行教程

整理日期 2026 年 10 月 28 日

本文覆盖四条流程：AC 从零配置、AC 已有环境运行、Policy 从零配置、Policy 已有环境运行。Policy 部分保留本次 LIBERO Plus 调试中实际使用的路径、兼容修复与单任务成功记录，并给出完整评测指令。

**验证范围**：2026 年 10 月 28 日已确认 Policy 在 LIBERO Plus 的 `libero_spatial` 中完成 task 0 的 1 次 episode，结果为 `success=true`。完整 10030 次评测是后续运行方案。AC 章节采用固定版本官方代码的部署与最小推理流程，首次执行后按章节中的验收标准确认结果。

## 1 使用方式和环境关系

### 1 1 按当前状态选择入口

| 当前状态 | 执行路径 |
| --- | --- |
| 空项目目录，需要重新部署 | 第 2 章公共准备，然后执行 AC 或 Policy 的从零配置章节 |
| AC 已经安装好 | 跳到 AC 已有环境启动，只恢复路径并运行，不重新安装依赖 |
| 今天的 Policy 环境保持完整 | 跳到 Policy 已有环境启动，加载环境文件后选择单任务或全量评测 |
| 当前运行报错 | 先定位当前输出目录，查看客户端和服务端日志，再查故障处理章节 |

所有 `/workspace/vjepa/...` 路径均在容器内使用。标注“宿主机”的命令在服务器外层终端执行。已有可用容器时，直接进入容器，跳过新建步骤。

### 1 2 三个环境分别做什么

| 环境 | 作用 | 是否用于 Policy 的 Plus 评测 |
| --- | --- | --- |
| AC | V JEPA 2 AC 编码与动作条件预测，可运行官方能量图及规划演示 | 不需要同时启动 |
| policy | 加载 Policy 检查点、视觉编码器和语言缓存，返回动作块 | 需要，作为推理服务 |
| libero-plus | 运行 MuJoCo 仿真，发送观测并执行动作 | 需要，作为仿真客户端 |

Policy 评测的进程关系：

```text
LIBERO Plus 仿真客户端
  双相机当前帧和历史帧 + 状态 + 指令
              ↓ 本地 WebSocket
兼容入口 → Policy 推理服务 → 32 步动作块
              ↓
仿真执行前 16 步 → 重新观测 → 再次推理
```

统一评测脚本会管理服务端和客户端。终端中不需要同时激活两个环境，脚本会分别调用 `POLICY_PYTHON` 和 `LIBERO_PLUS_PYTHON` 的绝对路径。不要为这条评测额外手动启动一个占用相同端口的服务。

### 1 3 固定版本

| 项目 | 仓库 | 本文核对的提交 |
| --- | --- | --- |
| AC | facebookresearch/vjepa2 | 204698b45b3712590f06245fbfba32d3be539812 |
| Policy | breez3young/VJEPA-Policy 的 release 分支 | d0e75c44463f85942f3580813fbcfe904cc0cf15 |
| LIBERO Plus | sylvestf/LIBERO-plus | 4976dc30028e805ff8094b55501d532c48fec182 |

新机器按固定提交安装；已经跑通的机器先保存当前版本和补丁，按“已有环境”流程继续，不在运行前直接更新仓库。依赖安装组合与当天实际环境版本应分别留档。

## 2 公共准备

### 2 1 检查宿主机

“从零配置”从项目目录和 Python 环境尚未建立开始，宿主机应为 Ubuntu x86_64，并已准备 NVIDIA 驱动、Docker 和 NVIDIA Container Toolkit。先在宿主机执行：

```bash
nvidia-smi
docker version
docker ps -a --filter name=vjepa-dev
```

`nvidia-smi` 应显示显卡和驱动；`docker version` 应显示客户端和服务端版本。尚未安装 Docker 或 GPU 容器支持时，按 [Docker Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/) 和 [NVIDIA Container Toolkit 安装说明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) 先完成宿主机配置。驱动在宿主机管理，不在容器内另装一套驱动。

检查 Docker 是否能访问 GPU：

```bash
docker run --rm --runtime=nvidia --gpus all ubuntu:22.04 nvidia-smi
```

此步骤只检查 GPU 容器链路，不代表 Python 中的 CUDA 已经可用。后面还需要分别检查 AC 和 Policy 环境的 `torch.cuda.is_available()`。该检查方式见 [NVIDIA 官方示例](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html)。

### 2 2 已有容器直接进入

```bash
# 宿主机执行；容器已在运行时不需要 docker start
docker start vjepa-dev
docker exec -it vjepa-dev bash
```

`docker start` 启动原容器，保留已经安装的系统依赖；`docker exec` 打开其中一个新终端。新终端不会继承上次终端的 `export`，必须重新加载对应环境文件。

已有容器还要核对创建时是否提供了 `graphics` 能力：

```bash
# 宿主机执行
docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' vjepa-dev \
  | grep NVIDIA_DRIVER_CAPABILITIES
```

应包含 `graphics` 或 `all`。`nvidia-smi` 成功仅证明诊断链路；缺少图形能力时，在容器内重新 export 或安装 `libegl1` 不能补上创建时没有挂载的 NVIDIA 图形库。需要按下一节保留数据挂载目录，另建具有图形能力的容器。参见 [NVIDIA 驱动能力说明](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html)。

### 2 3 没有容器时新建

下面是一套用于新部署的容器方案。数据挂载到宿主机目录，AC、Policy 和缓存都放在同一持久化目录中。

```bash
# 宿主机执行；目录可改为有足够空间的数据盘
export VJEPA_HOST_DIR="$HOME/vjepa"
mkdir -p "$VJEPA_HOST_DIR"

docker run -d \
  --name vjepa-dev \
  --runtime=nvidia \
  --gpus '"device=0"' \
  --shm-size=16g \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
  -v "$VJEPA_HOST_DIR:/workspace/vjepa" \
  -w /workspace/vjepa \
  ubuntu:22.04 sleep infinity

docker exec -it vjepa-dev bash
```

| 参数 | 含义 |
| --- | --- |
| `--name vjepa-dev` | 固定容器名称，后续用该名称进入 |
| `--gpus '"device=0"'` | 将宿主机 GPU 0 提供给容器；本教程按单卡串行运行 |
| `--shm-size=16g` | 为视频与多进程操作预留共享内存 |
| `NVIDIA_DRIVER_CAPABILITIES` | 提供计算、诊断和 EGL 所需的图形能力 |
| `-v` | 将宿主机数据目录挂载到容器，保存环境、权重和输出 |
| `-w` | 设置进入容器后的工作目录 |
| `sleep infinity` | 使容器持续运行，后续通过 exec 开新终端 |

已有同名容器时不要重复运行 `docker run`。先执行上一节的进入命令。

### 2 4 安装容器系统依赖并建立目录

以下在新容器内以 root 执行；如果已有容器使用普通用户，在系统安装命令前加 `sudo`。

```bash
apt-get update
apt-get install -y \
  ca-certificates curl wget git unzip bzip2 build-essential pkg-config iproute2 ripgrep \
  ffmpeg libexpat1 libfontconfig1-dev libmagickwand-dev \
  libgl1 libegl1 libosmesa6 libglib2.0-0

mkdir -p /workspace/vjepa/{repos,envs,checkpoints,cache,outputs,scripts,installers,config}
```

`libegl1`、`libgl1` 用于图像渲染；`libosmesa6` 留作 CPU 渲染排查；`ffmpeg` 用于视频；编译工具用于 Python 包安装。这里只做一次，后续启动不用重复安装。

### 2 5 安装 Conda 并设置持久化缓存

已有 Conda 时直接加载现有的 `conda.sh`。新环境可用 [Miniforge 官方安装器](https://github.com/conda-forge/miniforge)：

```bash
cd /workspace/vjepa/installers
curl -fL --retry 3 \
  https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh \
  -o Miniforge3-Linux-x86_64.sh

bash Miniforge3-Linux-x86_64.sh -b -p /workspace/vjepa/miniforge3
source /workspace/vjepa/miniforge3/etc/profile.d/conda.sh
conda --version

cat > /workspace/vjepa/scripts/common.env <<'ENV'
export HF_HOME=/workspace/vjepa/cache/huggingface
export TORCH_HOME=/workspace/vjepa/cache/torch
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,::1"
export no_proxy="$NO_PROXY"
ENV

source /workspace/vjepa/scripts/common.env
```

`-b` 表示无交互安装；`-p` 指定 Conda 根目录。`HF_HOME` 和 `TORCH_HOME` 保存下载缓存。`NO_PROXY` 和 `no_proxy` 让本地 WebSocket 绕过代理，保留已有的其他排除项。使用网络代理下载模型时，代理的端口和地址按服务器实际配置设置；容器里的 `127.0.0.1` 指向容器自身。

后续新终端需要使用 Conda 命令时先加载 `conda.sh`。单纯调用 `/workspace/vjepa/envs/.../bin/python` 则不必激活环境。

本文的 `date -u` 为结果目录生成 UTC 时间戳；结尾 `Z` 表示 UTC，北京时间加 8 小时。例如 `20261028T114417Z` 对应北京时间 10 月 28 日 19 时 44 分 17 秒。

### 2 6 放置随文脚本

教程附带的 `scripts` 目录包含 AC 最小推理、Policy 兼容入口、环境文件、检查和启动脚本。将目录内容放入容器的 `/workspace/vjepa/scripts/`，再按后文核对实际路径。

```bash
# 宿主机执行；将路径替换为本次解压后的 scripts 目录
docker cp /实际解压路径/scripts/. vjepa-dev:/workspace/vjepa/scripts/
```

已有同名兼容脚本时先保存副本，再对照教程更新。脚本中的环境路径与本文一致；权重和缓存仍需要在从零配置步骤中准备，复制脚本不会自动下载这些大文件。

## 3 AC 从零配置

本章给出 Meta 官方 V-JEPA 2-AC 固定版本的独立配置流程。命令采用 `/workspace/vjepa` 目录布局，配套 `smoke_ac.py` 完成真实示例轨迹的前向预测，并可运行 CEM 动作规划。这里的安装方案与脚本来自官方源码重建；执行是否成功，以目标机器输出为准。

| 项目 | 本章固定设置 |
| --- | --- |
| 官方仓库 | `https://github.com/facebookresearch/vjepa2.git` |
| 代码版本 | `204698b45b3712590f06245fbfba32d3be539812` |
| 仓库目录 | `/workspace/vjepa/repos/vjepa2` |
| 独立环境 | `/workspace/vjepa/envs/ac` |
| Python | 3.12；该版本源码的 `setup.py` 要求至少 3.11 |
| 本教程选用的 PyTorch | `torch==2.5.1` 和 `torchvision==0.20.1`，CUDA 12.4 wheel |
| AC 权重 | `/workspace/vjepa/checkpoints/ac/vjepa2-ac-vitg.pt` |
| 示例轨迹 | 仓库自带 `notebooks/franka_example_traj.npz` |
| 本地检查脚本 | `/workspace/vjepa/scripts/smoke_ac.py` |

PyTorch 版本是本教程为明确安装指令而选定的组合；官方 AC requirements 只规定 `torch>=2`，不构成已验证的完整依赖锁定文件。CUDA 12.4 wheel 命令来自 [PyTorch 官方历史版本页面](https://pytorch.org/get-started/previous-versions/)。

### 配置步骤

### 第一步 确认公共准备已完成

先完成第 2 章，在容器内加载 Conda 和公共缓存配置。已有 Conda 根目录不同的机器，把第一条路径换成现有的 conda.sh。

```bash
source /workspace/vjepa/miniforge3/etc/profile.d/conda.sh
source /workspace/vjepa/scripts/common.env
nvidia-smi
conda --version
mkdir -p /workspace/vjepa/checkpoints/ac /workspace/vjepa/config
```

### 第二步 下载并固定源码

```bash
git clone https://github.com/facebookresearch/vjepa2.git \
  /workspace/vjepa/repos/vjepa2

git -C /workspace/vjepa/repos/vjepa2 checkout --detach \
  204698b45b3712590f06245fbfba32d3be539812

git -C /workspace/vjepa/repos/vjepa2 rev-parse HEAD
```

`--detach` 让代码固定在这个提交，避免以后分支更新改变接口。最后一行应输出相同的完整提交号。如果该目录已经存在，先核对版本和已有改动，直接进入后续的“已有环境日常启动”。

### 第三步 创建独立 Python 环境

```bash
conda create --prefix /workspace/vjepa/envs/ac python=3.12 pip -y
conda activate /workspace/vjepa/envs/ac

export AC_PYTHON=/workspace/vjepa/envs/ac/bin/python
"$AC_PYTHON" -m pip install --upgrade pip

"$AC_PYTHON" -m pip install \
  torch==2.5.1 torchvision==0.20.1 \
  --index-url https://download.pytorch.org/whl/cu124

cat > /workspace/vjepa/config/ac-constraints.txt <<'TXT'
torch==2.5.1
torchvision==0.20.1
numpy<2
TXT

cd /workspace/vjepa/repos/vjepa2
"$AC_PYTHON" -m pip install \
  --constraint /workspace/vjepa/config/ac-constraints.txt -e .
"$AC_PYTHON" -m pip install \
  --constraint /workspace/vjepa/config/ac-constraints.txt scipy matplotlib

"$AC_PYTHON" -m pip check
"$AC_PYTHON" -c \
  'import sys, torch; print(sys.executable); print(torch.__version__, torch.version.cuda); print("CUDA:", torch.cuda.is_available())'
```

| 参数或设置 | 作用 |
| --- | --- |
| `--prefix /workspace/vjepa/envs/ac` | 把环境安装到固定路径，避免依赖 Conda 环境名查找 |
| `python=3.12` | 满足固定源码的 Python 要求；不能照搬 Policy 的 Python 3.10 环境 |
| `"$AC_PYTHON" -m pip` | 确保包安装进 AC 解释器所属环境 |
| `--index-url .../cu124` | 选择带 CUDA 12.4 runtime 的 PyTorch wheel |
| `--constraint` | 后续安装时保留这组 Torch 和 torchvision，限制 NumPy 小于 2 |
| `-e .` | 安装当前仓库的依赖，并使用可编辑安装方式 |
| `scipy` | 官方位姿转换和 CEM 工具使用 SciPy 的旋转变换 |
| `matplotlib` | 官方 Notebook 和检查脚本依赖的绘图包 |
| `pip check` | 检查安装包声明的依赖冲突 |

GPU 路线要求最后输出 `CUDA: True`。如果为 `False`，先检查是否使用了 `/workspace/vjepa/envs/ac/bin/python`、是否装成 CPU 版 Torch、当前驱动是否支持所选 wheel，再继续。若驱动不适合 CUDA 12.4，从 PyTorch 官方页面选择驱动支持的 wheel 组合，保持 torch 和 torchvision 的配套版本一致，并相应修改约束文件。

### 第四步 下载 AC 权重并保存校验值

```bash
export AC_CHECKPOINT=/workspace/vjepa/checkpoints/ac/vjepa2-ac-vitg.pt

curl --fail --location --retry 5 --continue-at - \
  --output "${AC_CHECKPOINT}.part" \
  https://dl.fbaipublicfiles.com/vjepa2/vjepa2-ac-vitg.pt \
  && mv "${AC_CHECKPOINT}.part" "$AC_CHECKPOINT"

test -s "$AC_CHECKPOINT"
sha256sum "$AC_CHECKPOINT" > "${AC_CHECKPOINT}.sha256"
sha256sum -c "${AC_CHECKPOINT}.sha256"
```

`--fail` 遇到 HTTP 错误时退出，避免把错误页面当成模型；`--location` 跟随重定向；`--retry 5` 重试下载；`--continue-at -` 从现有 `.part` 文件继续。只有下载命令成功后，才把临时文件改为正式权重名。这里生成的 SHA-256 用于今后确认文件没有变化；它不是与官方发布的校验值进行比对。

权重地址与 [官方固定版本 README](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/README.md) 的 AC 下载链接一致。必须使用 `vjepa2-ac-vitg.pt`；普通视觉权重、V-JEPA 2.1 权重和 Policy checkpoint 的结构与用途不同。

### 第五步 保存日常环境变量

```bash
cat > /workspace/vjepa/scripts/ac.env <<'SH'
source /workspace/vjepa/scripts/common.env
export AC_REPO=/workspace/vjepa/repos/vjepa2
export AC_PYTHON=/workspace/vjepa/envs/ac/bin/python
export AC_CHECKPOINT=/workspace/vjepa/checkpoints/ac/vjepa2-ac-vitg.pt
export AC_TRAJECTORY="$AC_REPO/notebooks/franka_example_traj.npz"
SH

source /workspace/vjepa/scripts/ac.env
```

`source` 把文件里的变量载入当前终端。新建终端、重连 SSH 或重新启动 tmux 后，需要再次执行；它不会重新安装环境，也不会自动启动模型。

### 第六步 安装配套检查脚本

第 2 章已将配套脚本复制到容器。这里检查脚本位置并校验语法：

```bash
test -f /workspace/vjepa/scripts/smoke_ac.py
"/workspace/vjepa/envs/ac/bin/python" -m py_compile \
  /workspace/vjepa/scripts/smoke_ac.py
```

运行时显式使用 Python，因此脚本不需要执行权限。`py_compile` 只检查语法，不加载模型。

### 首次运行前先避免这些问题

| 问题 | 提前处理方式 |
| --- | --- |
| 默认下载访问 `localhost:8300` | 固定源码的 `src/hub/backbones.py` 当前把下载基址设为本地测试地址。配套脚本使用 `pretrained=False`，再从 `--checkpoint` 显式加载本地权重，完全跳过这个下载分支 |
| Python 版本不匹配 | 本章使用 AC 的 Python 3.12；Policy 和 Plus 的 Python 3.10 不用于安装此固定版本 AC |
| 找不到 `src`、`app` 或 Notebook 的 `utils` | 脚本根据 `--repo` 显式设置源码路径和 Notebook 工具路径；不要把 `--repo` 指向 VJEPA-Policy |
| 找不到 `franka_example_traj.npz` | 默认轨迹是 AC 仓库自带文件；脚本使用绝对路径，不依赖当前工作目录 |
| checkpoint 缺少 `encoder` 或 `predictor` | 检查权重文件是否为 `vjepa2-ac-vitg.pt`，以及下载是否完整 |
| 错误被 `strict=False` 隐藏 | 脚本检查 encoder 缺失键及异常多余键；predictor 使用严格加载。不通过时先核对版本与权重 |
| 显存不足 | 先运行 `--mode predict`；规划时保持少量 `--samples`，不要一开始照搬 Notebook 的大动作网格。`bf16` 可减少部分推理计算内存，但脚本权重仍为 FP32；必要时选择 `--device cpu --precision fp32`，会显著变慢 |
| CPU 与 GPU 张量混用 | 通过 `--device` 统一模型、图像、状态和动作所在设备 |
| 模型能加载但并未实际推理 | 以 `result.json` 的表征形状、有限数值检查和 `smoke_passed` 为准；只打印模型名不足以验收 |

上述 localhost 下载地址问题可在 [官方固定版本源码](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/src/hub/backbones.py) 直接核对。

### 第七步 运行一次真实轨迹预测

```bash
source /workspace/vjepa/scripts/ac.env

test -x "$AC_PYTHON"
test -s "$AC_CHECKPOINT"
test -f "$AC_TRAJECTORY"
test -f /workspace/vjepa/scripts/smoke_ac.py

export AC_OUT="/workspace/vjepa/outputs/ac_predict_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$AC_OUT"

set -o pipefail
CUDA_VISIBLE_DEVICES=0 "$AC_PYTHON" /workspace/vjepa/scripts/smoke_ac.py \
  --repo "$AC_REPO" \
  --checkpoint "$AC_CHECKPOINT" \
  --trajectory "$AC_TRAJECTORY" \
  --device cuda:0 --precision fp32 \
  --mode predict --seed 7 \
  --output-dir "$AC_OUT" \
  2>&1 | tee "$AC_OUT.log"

cat "$AC_OUT/result.json"
```

日志写到与结果目录同级的 `.log` 文件，因此脚本启动时结果目录仍为空。`set -o pipefail` 保证模型失败时，不会被末尾 `tee` 的成功状态掩盖。

脚本读取示例轨迹第 0 和第 1 帧，根据这两个时刻的状态差计算动作，将当前图像表征和动作送入 AC predictor，再与下一帧真实图像表征计算 L1 误差。它不会连接仿真或控制真机。

验收时应看到：

- 末尾输出 `AC smoke passed`，并生成 `result.json`。
- `smoke_passed` 为 `true`。
- 当前和预测表征形状应为 `[1, 256, 1408]`，预测结果均为有限数值。
- `one_step_jepa_l1` 是这次预测的表征误差。这里只用于检查计算链路；没有把任意误差阈值当作任务成功标准。

### 第八步 在同一环境运行 CEM 规划

```bash
source /workspace/vjepa/scripts/ac.env
export AC_OUT="/workspace/vjepa/outputs/ac_plan_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$AC_OUT"

set -o pipefail
CUDA_VISIBLE_DEVICES=0 "$AC_PYTHON" /workspace/vjepa/scripts/smoke_ac.py \
  --repo "$AC_REPO" --checkpoint "$AC_CHECKPOINT" \
  --trajectory "$AC_TRAJECTORY" \
  --device cuda:0 --precision fp32 \
  --mode plan --samples 25 --topk 10 --cem-steps 2 \
  --rollout 2 --maxnorm 0.075 --seed 7 \
  --output-dir "$AC_OUT" \
  2>&1 | tee "$AC_OUT.log"
```

`plan` 会先做相同的预测检查，再把第二帧作为目标运行 CEM。`result.json` 的 `planned_actions` 应为 2 行、每行 7 个数。该结果是模型规划输出，没有在真实环境中执行；它不能作为机器人任务成功率。

| 参数 | 默认值或示例 | 解释 |
| --- | --- | --- |
| `--repo` | AC 仓库绝对路径 | 指定本地源码；脚本核对固定提交号 |
| `--checkpoint` | AC 权重绝对路径 | 本地读取 `encoder` 和 `predictor`，不触发 Hub 下载 |
| `--trajectory` | 仓库自带 `.npz` | 使用 `observations` 和 `states` 字段，取第一段轨迹前两帧 |
| `--output-dir` | 每次新建目录 | 保存 `result.json`，拒绝使用已有内容的目录 |
| `--device` | `cuda:0` | 使用进程内编号为 0 的 CUDA 设备；`cpu` 为 CPU 运行 |
| `CUDA_VISIBLE_DEVICES=0` | 物理 GPU 0 | 限制本进程可见设备；例如改成 `2` 后，脚本内仍写 `cuda:0` |
| `--precision` | `fp32` | 使用 FP32；支持 BF16 的 NVIDIA GPU 可改成 `bf16` 开启计算自动混合精度 |
| `--mode` | `predict` 或 `plan` | 分别执行一次预测，或预测检查加 CEM 搜索 |
| `--samples` | 25 | 每次 CEM 更新采样多少条候选动作轨迹；越大越耗显存和计算 |
| `--topk` | 10 | 保留误差最小的候选轨迹，用来更新采样分布；要求 `2 <= topk <= samples` |
| `--cem-steps` | 2 | 更新候选动作分布的轮数；增加后耗时增加 |
| `--rollout` | 2 | 每条候选轨迹向前预测的动作步数；本脚本限制最多 32 |
| `--maxnorm` | 0.075 | 按官方 CEM 实现限制每个平移轴的动作分量在正负此值内；不是三维向量范数约束 |
| `--seed` | 7 | 设置 NumPy 与 Torch 随机种子；不同设备或精度仍可能有数值差异 |

`samples`、`topk`、`cem-steps`、`rollout` 和 `maxnorm` 只影响 `plan` 模式的 CEM；`predict` 模式仍会检查它们的取值是否合法。前三维动作为平移增量，中间三维为旋转增量，最后一维为夹爪增量；官方这个 CEM 示例把旋转增量固定为零。不要直接把它当作 LIBERO 控制接口。

## 4 AC 已有环境启动

已经安装好环境、保存权重和配套脚本后，每次只需载入变量并运行。无需重新创建环境、下载权重，也无需启动 Policy 服务。

### 日常做一次 AC 预测

```bash
source /workspace/vjepa/scripts/ac.env
export AC_OUT="/workspace/vjepa/outputs/ac_predict_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$AC_OUT"

set -o pipefail
CUDA_VISIBLE_DEVICES=0 "$AC_PYTHON" /workspace/vjepa/scripts/smoke_ac.py \
  --repo "$AC_REPO" --checkpoint "$AC_CHECKPOINT" \
  --device cuda:0 --precision fp32 --mode predict \
  --output-dir "$AC_OUT" \
  2>&1 | tee "$AC_OUT.log"
```

这里省略 `--trajectory` 和 `--seed` 时，分别使用 AC 仓库自带轨迹和默认种子 7。显式使用 `AC_PYTHON` 已确定解释器，不要求先执行 `conda activate`；需要在终端交互使用 `python` 时，再执行 `conda activate /workspace/vjepa/envs/ac`。

### 日常运行规划

将上一条命令的 `--mode predict` 改为以下参数，并为结果使用新目录：

```bash
source /workspace/vjepa/scripts/ac.env
export AC_OUT="/workspace/vjepa/outputs/ac_plan_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$AC_OUT"

set -o pipefail
CUDA_VISIBLE_DEVICES=0 "$AC_PYTHON" /workspace/vjepa/scripts/smoke_ac.py \
  --repo "$AC_REPO" --checkpoint "$AC_CHECKPOINT" \
  --device cuda:0 --precision fp32 --mode plan \
  --samples 25 --topk 10 --cem-steps 2 --rollout 2 --maxnorm 0.075 \
  --output-dir "$AC_OUT" \
  2>&1 | tee "$AC_OUT.log"
```

停止运行按 `Ctrl+C`。每次完成后保留 `result.json` 与同名日志；重跑时使用新输出目录。

### 只在环境发生变化时重新检查

```bash
source /workspace/vjepa/miniforge3/etc/profile.d/conda.sh
source /workspace/vjepa/scripts/ac.env
"$AC_PYTHON" -m pip check
sha256sum -c "${AC_CHECKPOINT}.sha256"
git -C "$AC_REPO" rev-parse HEAD
"$AC_PYTHON" -m pip freeze > /workspace/vjepa/config/ac-pip-freeze.txt
conda list --prefix /workspace/vjepa/envs/ac --explicit \
  > /workspace/vjepa/config/ac-conda-explicit.txt
```

包版本快照应在本机首次跑通后保存，用于今后复原该机器的实际环境。如果已有 AC 环境来自别的源码版本，先记录其版本和本地改动，再与本章方案比较；不要直接在现有工作目录执行回退覆盖。

### AC 来源与验证范围

配置依据为固定提交的 [README](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/README.md)、[setup.py](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/setup.py)、[backbones.py](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/src/hub/backbones.py)、[官方能量与规划示例](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/notebooks/energy_landscape_example.ipynb)、[WorldModel 包装器](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/notebooks/utils/world_model_wrapper.py) 和 [CEM 实现](https://github.com/facebookresearch/vjepa2/blob/204698b45b3712590f06245fbfba32d3be539812/notebooks/utils/mpc_utils.py)。配套脚本完成语法检查；模型权重下载、依赖安装与 GPU 执行需在目标服务器完成。

## 5 Policy 从零配置

本节从 `/workspace/vjepa` 已创建、conda 可用、容器能够访问 GPU 开始。新机器依次完成本节；已有可运行环境直接跳到“Policy 已有环境后的日常启动”。

当天已经验证的是：`pretrained_predictor/checkpoint_step021360.pt` 配合兼容服务，在 LIBERO-Plus 的 `libero_spatial` 第0个任务完成1个成功 Episode。新建依赖组合、其他任务和全量成绩需要在目标服务器验收。

### 固定仓库与目录

```bash
source /workspace/vjepa/miniforge3/etc/profile.d/conda.sh
source /workspace/vjepa/scripts/common.env
mkdir -p /workspace/vjepa/{repos,envs,checkpoints/policy,cache,scripts,outputs,downloads}

git clone --branch release https://github.com/breez3young/VJEPA-Policy.git \
  /workspace/vjepa/repos/VJEPA-Policy
git -C /workspace/vjepa/repos/VJEPA-Policy checkout --detach \
  d0e75c44463f85942f3580813fbcfe904cc0cf15

git clone https://github.com/sylvestf/LIBERO-plus.git \
  /workspace/vjepa/repos/LIBERO-plus
git -C /workspace/vjepa/repos/LIBERO-plus checkout --detach \
  4976dc30028e805ff8094b55501d532c48fec182
```

这组固定版本对应本文的脚本、任务清单和兼容修复。已有仓库应先核对 `git rev-parse HEAD`，保留本地修改，不直接覆盖。

### 创建 policy 推理环境

Policy 与 Plus 仿真使用两个 Python 环境。Policy 包要求 Python 3.10 及以上；本教程用3.10统一重建。下面的 CUDA12.4、Torch2.6.0、TorchVision0.21.0 是明确的重建参考组合，不是当天环境的完整版本导出。CUDA PyTorch 必须与宿主机 NVIDIA 驱动兼容。若按本教程选用该组合，先保存约束，避免后续安装项目时被替换。

```bash
conda create -p /workspace/vjepa/envs/policy python=3.10 pip -y
export POLICY_PYTHON=/workspace/vjepa/envs/policy/bin/python
"$POLICY_PYTHON" -m pip install --upgrade pip

cat > /workspace/vjepa/cache/policy_constraints.txt <<'EOF'
torch==2.6.0
torchvision==0.21.0
torchcodec==0.2.1
lerobot==0.3.3
transformers==4.51.3
timm>=1.0,<2
numpy==1.26.4
EOF

"$POLICY_PYTHON" -m pip install torch==2.6.0 torchvision==0.21.0 \
  --index-url https://download.pytorch.org/whl/cu124

cd /workspace/vjepa/repos/VJEPA-Policy
"$POLICY_PYTHON" -m pip install \
  -c /workspace/vjepa/cache/policy_constraints.txt -e '.[serving]'

"$POLICY_PYTHON" -m pip check
"$POLICY_PYTHON" -c \
  'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'
"$POLICY_PYTHON" scripts/check_environment.py --profile policy --require-cuda
```

`-e` 使环境直接使用当前仓库源码；`.[serving]` 加装 WebSocket 服务需要的 `openpi-client`、`tyro` 和 `websockets`。不在 policy 环境中安装 Plus 仿真包。

Torch与TorchVision必须配对。LeRobot0.3.3要求TorchVision至少0.21，因此不要把下一节 Plus 环境的 `torch==2.5.1/torchvision==0.20.1` 直接照搬给 policy。TorchCodec0.2对应Torch2.6；如改Torch版本，应同步核对TorchVision和TorchCodec。参考依据为 [PyTorch版本安装表](https://pytorch.org/get-started/previous-versions/)、[LeRobot0.3.3依赖](https://github.com/huggingface/lerobot/blob/v0.3.3/pyproject.toml) 和 [TorchCodec兼容表](https://github.com/meta-pytorch/torchcodec#compatibility-with-torch-versions)。

### 创建独立的 Plus 仿真环境

```bash
conda create -p /workspace/vjepa/envs/libero-plus python=3.10 pip -y
export LIBERO_PLUS_PYTHON=/workspace/vjepa/envs/libero-plus/bin/python
"$LIBERO_PLUS_PYTHON" -m pip install --upgrade pip

"$LIBERO_PLUS_PYTHON" -m pip install torch==2.5.1 torchvision==0.20.1 \
  --index-url https://download.pytorch.org/whl/cpu

cd /workspace/vjepa/repos/VJEPA-Policy
"$LIBERO_PLUS_PYTHON" -m pip install -r examples/libero_plus/requirements.txt
"$LIBERO_PLUS_PYTHON" -m pip install -e /workspace/vjepa/repos/LIBERO-plus
"$LIBERO_PLUS_PYTHON" -m pip check
```

Plus这里使用CPU版Torch读取仿真初始状态文件；策略在另一个环境中用GPU推理。官方Plus依赖固定了robosuite1.4.1、MuJoCo3.2.3、BDDL1.0.1、gym0.25.2和robomimic0.3.0，并约束NumPy小于2。普通LIBERO和Plus注册同名Python包，必须放在独立环境，配置目录也分开。[Plus环境说明](https://github.com/breez3young/VJEPA-Policy/blob/d0e75c44463f85942f3580813fbcfe904cc0cf15/examples/libero_plus/README.md)

此处所需MagickWand、EGL、OSMesa、FFmpeg和unzip应已在公共准备中安装。

### 准备已训练策略和视觉权重

需要存在以下三个文件：

```text
/workspace/vjepa/checkpoints/policy/
├── released/checkpoints/libero/pretrained_predictor/
│   ├── checkpoint_step021360.pt
│   └── dataset_stats.json
└── vjepa2_1_vitl_dist_vitG_384.pt
```

把当天已经使用的 `released` 权重目录原样备份、恢复到上述位置。策略checkpoint与 `dataset_stats.json` 应来自同一个run。现有记录确认了文件路径与成功运行，未保留该策略权重包的下载地址；固定上游README也没有给出可核实的完整策略下载链接，因此不要用另一个模型的权重替代这一目录。

若缺少视觉编码器，可以从Meta提供的对应地址取得。已有正确文件则跳过：

```bash
curl -fL --retry 3 \
  https://dl.fbaipublicfiles.com/vjepa2/vjepa2_1_vitl_dist_vitG_384.pt \
  -o /workspace/vjepa/checkpoints/policy/vjepa2_1_vitl_dist_vitG_384.pt
```

视觉权重是V-JEPA2.1 ViT-L。AC的 `vjepa2-ac-vitg.pt` 用于另一条流程，不能替代policy所需的encoder或完整策略checkpoint。

### 保存统一环境配置

将下面内容保存为 `/workspace/vjepa/scripts/policy_plus.env`。教程脚本包提供同名文件，可直接复制。所有路径与当天成功记录保持一致；新机器若采用不同挂载位置，只修改这里。

```bash
# Load with: source /workspace/vjepa/scripts/policy_plus.env
source /workspace/vjepa/scripts/common.env
export POLICY_REPO=/workspace/vjepa/repos/VJEPA-Policy
export POLICY_PYTHON=/workspace/vjepa/envs/policy/bin/python
export LIBERO_PLUS_PYTHON=/workspace/vjepa/envs/libero-plus/bin/python

export RUN_DIR=/workspace/vjepa/checkpoints/policy/released/checkpoints/libero/pretrained_predictor
export CHECKPOINT="$RUN_DIR/checkpoint_step021360.pt"
export DATASET_STATS="$RUN_DIR/dataset_stats.json"
export VJEPA2_ENCODER_CHECKPOINT=/workspace/vjepa/checkpoints/policy/vjepa2_1_vitl_dist_vitG_384.pt

export LIBERO_PLUS_ROOT=/workspace/vjepa/repos/LIBERO-plus
export LIBERO_CONFIG_PATH=/workspace/vjepa/cache/libero-plus-conf
export LIBERO_PLUS_MANIFEST=/workspace/vjepa/cache/libero-plus-tasks.json
export TEXT_EMBEDDING_CACHE=/workspace/vjepa/cache/libero_plus_t5
export POLICY_SERVER_SCRIPT=/workspace/vjepa/scripts/serve_policy_libero_compat.py
export PYTHONPATH="$POLICY_REPO:$POLICY_REPO/src:$LIBERO_PLUS_ROOT"

export EVAL_GPUS=0
export EVAL_SERIAL=1
export NUM_TRIALS_PER_TASK=1
export EVAL_SEED=7
export REPLAN_STEPS=16
export FRAME_STRIDE=4
export LIBERO_MUJOCO_GL=egl
export BASE_PORT=14001

# Recover the checkpoint's geometry; do not inherit a training recipe's overrides.
unset POLICY_PRECISION POLICY_T5_LEN POLICY_MAX_STATE_DIM
unset POLICY_CROP_SIZE POLICY_VIEW_LAYOUT POLICY_VIEWS
unset POLICY_ENCODER_INTERPOLATE_ROPE POLICY_CORRECTED_PREDICTOR_ROPE
unset ENCODER ENCODER_FAMILY ENCODER_MODEL_NAME ENCODER_CHECKPOINT_KEY
unset PRED_DEPTH PRED_EMBED_DIM PRED_NUM_HEADS
unset ACTION_HIDDEN_SIZE ACTION_NUM_LAYERS
```

新开终端后必须重新 `source`，否则会重现 `LIBERO_PLUS_PYTHON: Set LIBERO_PLUS_PYTHON ...`。变量不会从另一个终端自动共享。脚本使用两个解释器的绝对路径，不依赖当前提示符显示 `(policy)` 还是 `(libero-plus)`。

`unset` 是为了让服务从本次checkpoint恢复实际几何参数，避免继承另一套训练环境的强制覆盖值。对于不同或旧checkpoint，应按其训练配置单独恢复这些值。

### 下载并安装 Plus 场景资源

来源为 [Sylvest LIBERO-plus官方资源](https://huggingface.co/datasets/Sylvest/LIBERO-plus/tree/main) 中的 `assets.zip`。已有解压后的完整资源可跳过下载。

```bash
source /workspace/vjepa/scripts/policy_plus.env
mkdir -p /workspace/vjepa/downloads/libero-plus

"$POLICY_PYTHON" - <<'PY'
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id="Sylvest/LIBERO-plus",
    repo_type="dataset",
    filename="assets.zip",
    local_dir="/workspace/vjepa/downloads/libero-plus",
)
print(path)
PY

sha256sum /workspace/vjepa/downloads/libero-plus/assets.zip \
  > /workspace/vjepa/cache/libero-plus-assets.sha256

unzip /workspace/vjepa/downloads/libero-plus/assets.zip \
  -d "$LIBERO_PLUS_ROOT/libero/libero"

test -d "$LIBERO_PLUS_ROOT/libero/libero/assets/textures"
test -d "$LIBERO_PLUS_ROOT/libero/libero/assets/new_objects"
```

BDDL任务与init states由固定Git版本提供；`assets.zip`补齐纹理、物体模型等资源。不要多套一层目录，最终必须是 `.../libero/libero/assets/textures`。

### 生成隔离配置和完整任务清单

先生成配置，再import LIBERO，避免第一次导入时写入错误的默认路径。

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

"$LIBERO_PLUS_PYTHON" examples/libero_plus/prepare.py \
  --libero-plus-root "$LIBERO_PLUS_ROOT" \
  --config-dir "$LIBERO_CONFIG_PATH" \
  --output "$LIBERO_PLUS_MANIFEST"

"$LIBERO_PLUS_PYTHON" -c \
  'from libero.libero import benchmark; print(benchmark.__file__)'
```

`--libero-plus-root` 指向Plus仓库；`--config-dir` 写出隔离的 `config.yaml`；`--output` 写出10,030个任务的manifest。最后打印的模块路径应属于 `/workspace/vjepa/repos/LIBERO-plus/`。`prepare.py`还检查固定提交、分类文件、资源、任务数量与实际import来源。

已有配置内容与目标路径不一致时，先核对是否迁移过仓库；不要反复覆盖旧配置。确定路径变化后，改用一个新的 `LIBERO_CONFIG_PATH` 并重新准备清单。

### 一次性生成 Plus 的 T5 指令缓存

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

"$POLICY_PYTHON" examples/libero_plus/cache_text.py \
  --manifest "$LIBERO_PLUS_MANIFEST" \
  --cache-dir "$TEXT_EMBEDDING_CACHE" \
  --model-name google/t5-v1_1-xxl \
  --context-length 128 \
  --device cuda

"$POLICY_PYTHON" scripts/validate_eval_results.py cache-plus \
  "$TEXT_EMBEDDING_CACHE" \
  --manifest "$LIBERO_PLUS_MANIFEST" \
  --context-length 128
```

`--manifest` 提供全部实际任务指令，包括语言扰动；`--cache-dir` 保存指令特征；`--model-name` 应与策略使用的T5来源一致；`--context-length 128` 明确缓存长度；`--device cuda` 用GPU完成一次性编码。若已有缓存包含 `libero_plus_cache.json`，应优先校验后复用；不要每天重算。

当天校验输出 `Validated 1549 cached prompts`：这是本次完整清单的去重指令数，不是任务数或Episode数。完整benchmark仍有10,030个任务。缓存记录manifest哈希、模型来源和长度；换清单、换T5或换长度时需使用匹配缓存。

### 提前安装当天验证成功的兼容入口

固定版本客户端发送斜杠格式字段，policy内部读取点号格式字段并需要Torch图像张量。原版直连会在首次动作请求报 `KeyError: 'observation.images.image'`。保存下面的原始兼容代码为 `/workspace/vjepa/scripts/serve_policy_libero_compat.py`，在首次评测前就启用：

```python
import logging
import numpy as np
import torch
import tyro

from examples.libero import serve_policy as stock

OriginalPolicy = stock.VJEPAPolicyServing

CAMERAS = {
    "observation/image": "observation.images.image",
    "observation/wrist_image": "observation.images.wrist_image",
    "observation/image_past": "observation.images.image_past",
    "observation/wrist_image_past": "observation.images.wrist_image_past",
}

class LiberoCompatiblePolicy(OriginalPolicy):
    def infer(self, obs):
        # Preserve native serving inputs unchanged.
        if "observation/image" not in obs:
            return super().infer(obs)

        converted = {}

        for source, target in CAMERAS.items():
            image = np.asarray(obs[source])

            if image.ndim != 3 or image.shape[-1] != 3:
                raise ValueError(
                    f"Invalid image shape for {source}: {image.shape}"
                )
            if image.dtype != np.uint8:
                raise ValueError(
                    f"Expected uint8 image for {source}, got {image.dtype}"
                )

            # HWC uint8 -> CHW float32 [0, 1]
            converted[target] = (
                torch.from_numpy(np.ascontiguousarray(image))
                .permute(2, 0, 1)
                .float()
                .div_(255.0)
            )

        converted["observation.state"] = torch.as_tensor(
            obs["observation/state"], dtype=torch.float32
        )
        converted["task"] = [str(obs["prompt"])]

        return super().infer(converted)

stock.VJEPAPolicyServing = LiberoCompatiblePolicy

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, force=True)
    stock.main(tyro.cli(stock.Args))
```

兼容层保持双摄像头和past帧；图像由HWC uint8转换成CHW float32的0到1范围，随后由原服务还原并按官方流程预处理。客户端原有的180度图像旋转保持不变。只重命名NumPy图像键不够。状态映射为 `observation.state`，语言映射为 `task=[prompt]`；状态和动作的归一化仍由原policy处理。

这里要纠正原对话的一处表述：LIBERO客户端拼接的原始状态通常为8维，即位置3、轴角3、夹爪关节2；环境动作是7维。不要为满足“7维状态”而裁掉状态字段。实际state处理由checkpoint与 `dataset_stats.json` 约定。

### 首次启动前检查

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

"$POLICY_PYTHON" -m py_compile "$POLICY_SERVER_SCRIPT"
"$POLICY_PYTHON" scripts/check_environment.py --profile policy --require-cuda
"$LIBERO_PLUS_PYTHON" scripts/check_environment.py --profile libero-plus

for file in "$CHECKPOINT" "$DATASET_STATS" "$VJEPA2_ENCODER_CHECKPOINT" \
  "$LIBERO_CONFIG_PATH/config.yaml" "$LIBERO_PLUS_MANIFEST"; do
  test -s "$file" || { echo "Missing or empty: $file"; exit 1; }
done

ss -ltnp 'sport = :14001'
```

14001若已有手动policy服务监听，回到启动它的终端按Ctrl+C结束；不要在旧服务旁再启动评测launcher。launcher自己启动服务、等待 `/healthz`、启动仿真客户端并回收进程。单卡串行四suite会依次使用14001到14004端口，也应保持空闲。

路径检查只能证明文件存在；环境检查证明依赖可导入；一次成功Episode才证明观测、推理和动作执行链路已打通。

## 6 Policy 已有环境启动和评测

不必重新装依赖、下载权重或计算T5。每次进入原容器后加载统一配置，选择本次任务范围并使用新结果目录。

```bash
# 宿主机
docker start vjepa-dev
docker exec -it vjepa-dev bash

# 容器内
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"
```

若容器已经运行，直接 `docker exec` 即可。AC环境无需随此评测一起启动；此处实际运行的两个进程是policy服务与Plus仿真客户端。

把教程提供的 `run_policy_plus.sh` 和 `verify_policy_plus_full.sh` 与前述两个文件一同放入 `/workspace/vjepa/scripts/`。启动脚本自动source配置、检查关键文件与完整文本缓存、选择模式、创建新输出目录，并打印 `EVAL_DIR=...`。

```bash
# 单任务单Episode，录制视频
bash /workspace/vjepa/scripts/run_policy_plus.sh smoke

# 前10个任务，每任务1个Episode，录制视频
bash /workspace/vjepa/scripts/run_policy_plus.sh ten

# 四suite的10030个任务，每任务1个Episode，不录视频
bash /workspace/vjepa/scripts/run_policy_plus.sh full
```

每次只选一条。`smoke`、`ten`、`full`是随教程启动脚本的模式，不是上游launcher参数。上游真实入口始终为：

```bash
bash examples/libero_plus/evaluate_policy.sh "$RUN_DIR" "$CHECKPOINT"
```

### 常用参数对照

| 参数 | 本教程值 | 含义 |
| --- | --- | --- |
| `POLICY_PYTHON` | policy环境的绝对Python路径 | 推理服务解释器 |
| `LIBERO_PLUS_PYTHON` | Plus环境的绝对Python路径 | 仿真客户端解释器 |
| `RUN_DIR` | pretrained_predictor目录 | 此次策略run及匹配统计的位置 |
| `CHECKPOINT` | checkpoint_step021360.pt | 要评测的完整策略权重 |
| `DATASET_STATS` | 同run的dataset_stats.json | 状态与动作归一化统计 |
| `VJEPA2_ENCODER_CHECKPOINT` | V-JEPA2.1 ViT-L权重 | 冻结视觉encoder |
| `POLICY_SERVER_SCRIPT` | serve_policy_libero_compat.py | 启用观测协议适配 |
| `LIBERO_CONFIG_PATH` | cache/libero-plus-conf | Plus独立配置目录，不是config文件本身 |
| `LIBERO_PLUS_MANIFEST` | 完整tasks.json | task身份、指令、类别及哈希来源 |
| `TEXT_EMBEDDING_CACHE` | cache/libero_plus_t5 | 与清单、T5和长度一致的缓存 |
| `EVAL_SUITES` | 逗号分隔suite名 | 选择任务套件 |
| `EVAL_GPUS` | 0 | 使用对当前容器可见的GPU |
| `EVAL_SERIAL` | 1 | 多suite在一张卡上依次运行 |
| `NUM_TRIALS_PER_TASK` | 1 | 每个任务的Episode数；Plus强制1 |
| `MAX_TASKS` | 1、10或unset | 每个所选suite只跑前N个任务 |
| `ALLOW_INCOMPLETE` | 诊断1，完整评测0 | 是否容许任务覆盖不完整 |
| `EVAL_SEED` | 7 | 随机种子 |
| `REPLAN_STEPS` | 16 | 每次执行预测动作块的前16步后重新规划 |
| `FRAME_STRIDE` | 4 | 历史图像与当前图像相差4个原始环境步 |
| `RECORD_VIDEO` | 诊断1，全量0 | 是否生成Episode视频 |
| `LIBERO_MUJOCO_GL` | egl | 渲染后端；必要时可改osmesa排查 |
| `BASE_PORT` | 14001 | 各suite按索引使用14001到14004 |
| `EVAL_DIR` | 每次新目录 | 日志、逐Episode结果与汇总的保存位置 |

任务数和Episode数不能混用。真实变量名是 `NUM_TRIALS_PER_TASK`；`NUM_TRIALS_TASK`不会被该脚本读取。`MAX_TASKS=1`只限制任务数，普通LIBERO若保留默认50次试验，仍会跑50个Episode。本文每次明确设置 `NUM_TRIALS_PER_TASK=1`；Plus wrapper也会强制每任务一次。

### 单任务闭环验收

不使用教程启动脚本时，直接执行以下完整指令。它保留了当天成功的配置，并明确设置一次Episode：

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

export EVAL_SUITES=libero_spatial
export EVAL_GPUS=0 EVAL_SERIAL=1
export NUM_TRIALS_PER_TASK=1
export MAX_TASKS=1 ALLOW_INCOMPLETE=1 RECORD_VIDEO=1
export EVAL_DIR="/workspace/vjepa/outputs/plus_smoke_$(date -u +%Y%m%dT%H%M%SZ)"

bash examples/libero_plus/evaluate_policy.sh "$RUN_DIR" "$CHECKPOINT"

cat "$EVAL_DIR/summary.txt"
cat "$EVAL_DIR/libero_spatial/libero_spatial_eval_results.txt"
cat "$EVAL_DIR/libero_spatial/episodes.jsonl"
find "$EVAL_DIR" -type f -name '*.mp4' -printf '%p %k KB\n'
```

正常结束意味着程序与结果校验通过；任务是否成功看 `episodes.jsonl` 中的 `success`。`success:false`且Episode完整结束属于任务失败；服务异常、渲染崩溃不应算作一次已完成任务失败。

当天成功记录为：

```text
EVAL_DIR=/workspace/vjepa/outputs/plus_compat_20261028T114417Z
suite=libero_spatial
task_id=0
episode_id=0
success=true
category=Background Textures
视频=libero_spatial/task0000_episode000_success.mp4
```

任务指令为“pick up the black bowl between the plate and the ramekin and place it on the plate”。manifest哈希为 `0a097d4113f32fa6762807eba684a825d01b6c44267a31d5e732e1630683b177`。这是1个成功样本；部分评测的 `complete:false` 符合预期。

如需检查10个任务，将 `MAX_TASKS=10`，换新 `EVAL_DIR` 后启动，其余保持不变。前10个任务不保证覆盖七类扰动。

### 完整 Baseline 评测

#### 在持久会话中启动

宿主机使用tmux，进入原容器后选全量模式：

```bash
# 宿主机；首次缺少 tmux 时先执行 sudo apt-get install -y tmux
tmux new -s vjepa_full
docker exec -it vjepa-dev bash

# 容器内，使用教程启动脚本
bash /workspace/vjepa/scripts/run_policy_plus.sh full
```

或者直接用官方入口：

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

export EVAL_SUITES=libero_spatial,libero_object,libero_goal,libero_10
export EVAL_GPUS=0 EVAL_SERIAL=1
export NUM_TRIALS_PER_TASK=1
unset MAX_TASKS
export ALLOW_INCOMPLETE=0 RECORD_VIDEO=0
export EVAL_DIR="/workspace/vjepa/outputs/libero_plus_full_$(date -u +%Y%m%dT%H%M%SZ)"

bash examples/libero_plus/evaluate_policy.sh "$RUN_DIR" "$CHECKPOINT"
```

必须 `unset MAX_TASKS`：只把 `ALLOW_INCOMPLETE` 改成0而留着任务限制，会被launcher拒绝。不要额外手动开14001服务。单卡下保持串行；默认并行四suite需要为每个suite提供GPU条目，不应将4套模型同时塞进同一张4090。

| Suite | 必须完成的Episode数 | 最大控制步数 |
| --- | ---: | ---: |
| libero_spatial | 2402 | 220 |
| libero_object | 2518 | 280 |
| libero_goal | 2591 | 300 |
| libero_10 | 2519 | 520 |
| 合计 | 10030 | 按suite执行 |

每任务还先执行10个静置步让物体稳定。控制步上限不代表每次都要跑满。当前输入为双摄像头、当前帧加past帧；模型预测32步动作，每次先执行16步，再取新观测重规划。

#### 另开终端查看进度

新终端不会继承评测窗口的 `EVAL_DIR`。若使用教程 `full` 模式，可读取它保存的路径；若用官方直接命令，则把启动窗口的绝对输出目录填给 `EVAL_DIR`。

```bash
# 新终端进入同一容器后
export EVAL_DIR="$(cat /workspace/vjepa/cache/latest_plus_full.path)"

tail -f "$EVAL_DIR/libero_spatial.log"
```

`Ctrl+C`只退出当前查看日志的 `tail`。切换suite后，改看对应log。查看完成数量：

```bash
for suite in libero_spatial libero_object libero_goal libero_10; do
  file="$EVAL_DIR/$suite/episodes.jsonl"
  if [ -f "$file" ]; then
    count=$(wc -l < "$file")
  else
    count=0
  fi
  echo "$suite: $count episodes completed"
done
nvidia-smi
```

tmux中按 `Ctrl+B` 后按 `D` 脱离会话；宿主机重新进入用 `tmux attach -t vjepa_full`。日志写入文件时，主终端长时间无输出不等于卡住。

#### 完成后严格验收

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"
# 将此处改为实际完整评测目录；教程full模式可使用下面这一行
export EVAL_DIR="$(cat /workspace/vjepa/cache/latest_plus_full.path)"

cat "$EVAL_DIR/summary.txt"
"$POLICY_PYTHON" -m json.tool "$EVAL_DIR/results.json"

"$POLICY_PYTHON" scripts/validate_eval_results.py libero-plus \
  "$EVAL_DIR" --manifest "$EVAL_DIR/task_manifest.json"

bash /workspace/vjepa/scripts/verify_policy_plus_full.sh "$EVAL_DIR"
```

官方validator逐项检查：四suite全部任务身份完整、无重复、每任务只有 `episode_id=0`、`success`为布尔值、指令及类别与manifest一致、manifest哈希相符。教程验收脚本在此基础上要求四个worker的 `.status` 全为0，并核对 `episodes=10030`、各suite数量及 `complete=true`、`selected_complete=true`，保存 `results.revalidated.json`。

完整成功率按全部10,030个Episode加权计算，不把四个suite百分比直接平均。七类扰动的分母与成功率在 `results.json` 的 `categories` 字段中。

`[done]`表示请求范围内的程序与结果校验通过；若此前允许部分任务，即使打印 `[done]` 也不是完整benchmark。当天记录提供的是单Episode成功以及随后全量启动的指令，没有全量评测完成分数。

#### 保存版本与结果

等官方launcher结束后再把附加文件写进结果目录；启动前往目录塞文件会触发“目录必须为空”的检查。

```bash
git -C "$POLICY_REPO" rev-parse HEAD > "$EVAL_DIR/policy.commit.txt"
git -C "$POLICY_REPO" diff > "$EVAL_DIR/policy.local.diff"
git -C "$LIBERO_PLUS_ROOT" rev-parse HEAD > "$EVAL_DIR/libero-plus.commit.txt"
cp /workspace/vjepa/scripts/policy_plus.env "$EVAL_DIR/"
cp "$POLICY_SERVER_SCRIPT" "$EVAL_DIR/"
"$POLICY_PYTHON" -m pip freeze > "$EVAL_DIR/policy.freeze.txt"
"$LIBERO_PLUS_PYTHON" -m pip freeze > "$EVAL_DIR/libero-plus.freeze.txt"
sha256sum "$CHECKPOINT" "$DATASET_STATS" "$VJEPA2_ENCODER_CHECKPOINT" \
  "$LIBERO_PLUS_MANIFEST" "$POLICY_SERVER_SCRIPT" \
  > "$EVAL_DIR/artifacts.sha256"
```

官方脚本没有自动续跑。中断后保留已有Episode和日志用于分析；修复原因后换新输出目录重新启动，不在原目录补跑后直接宣称完整成绩。

## 7 故障定位和本次调试记录

| 现象 | 含义 | 处理 |
| --- | --- | --- |
| `LIBERO_PLUS_PYTHON` 未设置 | 新终端丢失export | 重新source统一env，无需重装 |
| `address already in use` | 手动server或旧进程占用端口 | 查监听者，在原终端正常结束；确认14001到14004空闲 |
| `Validated 1549 cached prompts`后仍incomplete | 缓存校验过，某worker失败 | 看suite的runner、server与client日志 |
| `KeyError: observation.images.image` | wire字段与内部字段不一致 | 确认POLICY_SERVER_SCRIPT为compat入口，并重启新评测 |
| 改键后出现图像类型或布局错误 | HWC NumPy未转换 | 使用本文原兼容层的CHW Torch float转换 |
| 旧smoke日志报错但新compat已done | 查到了旧结果目录 | 始终用本次明确EVAL_DIR查日志 |
| KeyError之后出现EGL析构异常 | 可能是异常退出时清理失败 | 先修最早的推理错误，再判断渲染是否独立失败 |
| 独立EGL初始化失败 | 驱动、GPU可见性或渲染后端有问题 | 检查GPU暴露与EGL依赖；必要时新目录用osmesa重试并记录后端 |
| 缺prompt或cache provenance错误 | 缓存与清单/T5/长度不匹配 | 重新校验；用正确配置在独立缓存目录准备 |
| 输出目录必须为空 | 复用了上次目录 | 每次换新EVAL_DIR；上游不支持自动续跑 |

定位本次错误只需查相关日志：

```bash
rg -n 'Traceback|KeyError|RuntimeError|OSError|Error|Failed|address already in use' \
  "$EVAL_DIR/libero_spatial_runner.log" \
  "$EVAL_DIR/libero_spatial_server.log" \
  "$EVAL_DIR/libero_spatial.log"
```

如果确定要排查渲染，先source统一env，再设置 `export LIBERO_MUJOCO_GL=osmesa`，换一个新 `EVAL_DIR`，使用官方直接入口运行单任务。教程启动脚本每次会重新source默认env，因此用它时应先修改env中的该项，不能只在外层export后期待保留。

### 本次调试留下的最短排查链路

1. 入口立即提示缺少 `LIBERO_PLUS_PYTHON`：加载统一环境文件，恢复当前终端的变量。
2. 五项路径检查通过、1549 条缓存通过，但仍提示 incomplete：继续读当前 suite 的日志，不据此重装环境。
3. 服务端明确报缺少相机键：启用兼容入口，同时适配四张相机图像、状态和指令的数据格式。
4. 在新目录重跑并核对 Episode：`plus_compat_20261028T114417Z` 的 task 0、episode 0 为 `success=true`，生成成功视频。

失败的旧目录为 `/workspace/vjepa/outputs/plus_smoke_20261028T114132Z`。新兼容运行成功后，旧目录仍保留原有 KeyError 和 EGL 日志，这是历史记录，不代表新运行仍有相同故障。优先使用启动时打印的精确 `EVAL_DIR`，不只通过“最新 summary 文件”猜测当前运行。

### EGL 仍然独立失败时的检查

在容器内查看可见 GPU 和系统库：

```bash
nvidia-smi
printenv NVIDIA_DRIVER_CAPABILITIES
ldconfig -p | grep -E 'libEGL|libGLX|libOSMesa'
```

如果是渲染初始化本身报错，而不是前面的推理异常引出的清理错误，再核对第 2 章的容器图形能力和系统库。后端切换只是排查选项；改变为 `osmesa` 时要记录到该次实验配置，使用单任务、新结果目录复测。

### 停止与再次运行

在启动评测的原终端按 `Ctrl+C`，等待 launcher 回收其子进程。先确认 suite 日志及端口状态，再启动下一次运行。不要通过重复启动 launcher 解决卡住，也不要同时在另一终端手动启动同端口 server。

重连 SSH 时，先在宿主机执行 `tmux attach -t vjepa_full`，查看原进程是否还在运行。已有评测仍在运行就继续观察；确需重跑时保留旧日志并使用新输出目录。

## 8 配套脚本和命令速查

### 配套文件

| 文件 | 用途 |
| --- | --- |
| `common.env` | 固定下载缓存和本地连接的代理排除项 |
| `ac.env` | AC 仓库、解释器、权重和轨迹路径 |
| `smoke_ac.py` | 本地 AC 真实轨迹预测和可选 CEM 规划 |
| `policy_plus.env` | Policy 和 Plus 的全部日常配置 |
| `serve_policy_libero_compat.py` | 本次成功运行所用的观测协议兼容入口 |
| `run_policy_plus.sh` | 统一选择 smoke、ten、full 模式 |
| `verify_policy_plus_full.sh` | 复核完整 10030 次评测及 worker 状态 |

脚本安装位置统一为 `/workspace/vjepa/scripts/`。全部脚本随教程提供；AC 与 Policy 的环境文件只负责恢复变量，只有调用运行脚本时才会启动模型。

### 命令中常见符号的含义

| 写法 | 含义 |
| --- | --- |
| `source 文件` | 在当前终端读取变量，供后续命令使用 |
| `export NAME=value` | 设置变量并传给脚本及其子进程 |
| `unset NAME` | 删除残留覆盖值，恢复脚本或 checkpoint 默认设置 |
| `"$NAME"` | 展开变量并保留其中可能存在的空格 |
| `cat > 文件 <<'EOF'` | 把后面的文字原样写入文件；单引号使变量在写入时不展开 |
| `"$PYTHON" -m pip` | 使用指定环境自己的 pip，避免装到另一个环境 |
| `-e .` 和 `-c 文件` | 分别表示使用当前源码安装，以及按版本约束解析依赖 |
| `2>&1` | 将报错和普通输出合并到同一个日志流 |
| `\| tee 日志` | 一边在终端显示，一边保存日志；配合 pipefail 保留失败状态 |
| `date -u` | 生成 UTC 时间；目录末尾 Z 与北京时间相差 8 小时 |

### 验证范围和来源

本教程的运行记录来自 2026 年 10 月 28 日《介绍 VJEPA模型》聊天中保存的终端输出；Policy 兼容入口保留该次使用的代码。部署步骤还核对了固定版本 AC 与 Policy 源码。随文新脚本和命令已做语法检查；新建环境组合、AC 预测脚本与完整评测均需在目标 GPU 服务器执行验收。

- [Meta VJEPA 2 固定版本代码](https://github.com/facebookresearch/vjepa2/tree/204698b45b3712590f06245fbfba32d3be539812)
- [Policy 固定版本部署说明](https://github.com/breez3young/VJEPA-Policy/blob/d0e75c44463f85942f3580813fbcfe904cc0cf15/docs/setup.md)
- [Policy 的 LIBERO Plus 环境和评测说明](https://github.com/breez3young/VJEPA-Policy/blob/d0e75c44463f85942f3580813fbcfe904cc0cf15/examples/libero_plus/README.md)
- [统一评测 launcher 源码](https://github.com/breez3young/VJEPA-Policy/blob/d0e75c44463f85942f3580813fbcfe904cc0cf15/examples/libero/evaluate_policy.sh)
- [完整性校验源码](https://github.com/breez3young/VJEPA-Policy/blob/d0e75c44463f85942f3580813fbcfe904cc0cf15/scripts/validate_eval_results.py)
