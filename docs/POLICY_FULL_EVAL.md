# Policy 完整 Baseline 评测操作单

本流程沿用 2026 年 10 月 28 日已经跑通的 Policy 检查点与兼容入口，在现有 `vjepa-dev` 容器中运行完整 LIBERO-Plus 评测。只需 Policy 推理环境和 Plus 仿真环境，AC 不参与此项评测。

当前已验证单任务 1/1 成功；完整 baseline 成绩需以下流程运行结束并通过验收后获得。

## 1 先确认本次评测范围

| Suite | Episode 数 | 最大控制步数 |
| --- | ---: | ---: |
| libero_spatial | 2402 | 220 |
| libero_object | 2518 | 280 |
| libero_goal | 2591 | 300 |
| libero_10 | 2519 | 520 |
| 合计 | 10030 | 按 Suite 执行 |

每任务运行 1 次。使用 GPU 0，四个 Suite 串行；动作块 32 步，每次执行前 16 步后重新推理；历史图像间隔 4 个环境步，随机种子 7。

## 2 在服务器安装本仓库的运行脚本

这一步把教程中新增的脚本放到服务器，首次执行一次即可。不要把“本地教程已经生成”当成“服务器已经安装脚本”。

宿主机进入原容器；容器已在运行时可跳过 `docker start`：

```bash
docker start vjepa-dev
docker exec -it vjepa-dev bash
```

以下在容器内执行。将教程仓库放在独立目录，保持已跑通的模型仓库和 Python 环境：

```bash
mkdir -p /workspace/vjepa/tutorials
git clone https://github.com/yxt02/WAM.git /workspace/vjepa/tutorials/WAM
export WAM_TUTORIAL_DIR=/workspace/vjepa/tutorials/WAM
```

如果已经克隆了本教程仓库，跳过上一块，用下面的更新指令：

```bash
export WAM_TUTORIAL_DIR=/workspace/vjepa/tutorials/WAM
git -C "$WAM_TUTORIAL_DIR" pull --ff-only
```

复制所需的 5 个文件；先备份服务器已有同名文件：

```bash
export WAM_BACKUP_DIR="/workspace/vjepa/cache/scripts_before_full_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$WAM_BACKUP_DIR" /workspace/vjepa/scripts

for name in common.env policy_plus.env serve_policy_libero_compat.py \
  run_policy_plus.sh verify_policy_plus_full.sh; do
  if [ -f "/workspace/vjepa/scripts/$name" ]; then
    cp "/workspace/vjepa/scripts/$name" "$WAM_BACKUP_DIR/$name"
  fi
  cp "$WAM_TUTORIAL_DIR/scripts/$name" "/workspace/vjepa/scripts/$name"
done

source /workspace/vjepa/scripts/policy_plus.env
```

检查路径是否与你的服务器一致：

```bash
printf '%s\n' \
  "POLICY_PYTHON=$POLICY_PYTHON" \
  "LIBERO_PLUS_PYTHON=$LIBERO_PLUS_PYTHON" \
  "CHECKPOINT=$CHECKPOINT" \
  "DATASET_STATS=$DATASET_STATS" \
  "ENCODER=$VJEPA2_ENCODER_CHECKPOINT" \
  "MANIFEST=$LIBERO_PLUS_MANIFEST" \
  "TEXT_CACHE=$TEXT_EMBEDDING_CACHE" \
  "SERVER=$POLICY_SERVER_SCRIPT"
```

本文环境文件使用已跑通的这些路径：

```text
Policy Python  /workspace/vjepa/envs/policy/bin/python
Plus Python    /workspace/vjepa/envs/libero-plus/bin/python
Policy run     /workspace/vjepa/checkpoints/policy/released/checkpoints/libero/pretrained_predictor
Checkpoint     上述目录中的 checkpoint_step021360.pt
Dataset stats  上述目录中的 dataset_stats.json
Encoder        /workspace/vjepa/checkpoints/policy/vjepa2_1_vitl_dist_vitG_384.pt
Plus manifest  /workspace/vjepa/cache/libero-plus-tasks.json
T5 cache       /workspace/vjepa/cache/libero_plus_t5
```

路径不同就修改 `/workspace/vjepa/scripts/policy_plus.env`，然后重新 source。启动脚本会再次加载它，因此 GPU、端口、渲染等参数也在这里修改，外层临时 export 可能被覆盖。

## 3 进入持久会话并启动全量评测

从刚才的容器终端执行 `exit` 返回宿主机，或另开宿主机 SSH 终端。先建立 tmux 会话：

```bash
# 宿主机；没有 tmux 时先安装 sudo apt-get install -y tmux
tmux new -s vjepa_full
docker exec -it vjepa-dev bash
```

如果 `vjepa_full` 会话已经存在，先用 `tmux attach -t vjepa_full` 查看原评测是否仍在运行。不要重复启动同一项评测。

在这个持久会话的容器终端中执行：

```bash
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

"$POLICY_PYTHON" -c \
  'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'

ss -ltnp '( sport = :14001 or sport = :14002 or sport = :14003 or sport = :14004 )'
```

Torch 检查的最后一项应为 `True`。端口检查应没有监听服务的条目；若有此前手动启动的 Policy 服务，回到其终端按 `Ctrl+C` 正常结束，再检查。统一 launcher 会管理服务端和客户端。

正式启动只运行这一条：

```bash
bash /workspace/vjepa/scripts/run_policy_plus.sh full
```

`full` 模式会自动完成：

- 设置四个 Suite、`EVAL_GPUS=0` 和 `EVAL_SERIAL=1`。
- 设置 `NUM_TRIALS_PER_TASK=1`，并清除旧的 `MAX_TASKS`。
- 设置 `ALLOW_INCOMPLETE=0`，要求所选完整任务集合完成。
- 设置 `RECORD_VIDEO=0`，避免全量产生 10030 个视频。
- 检查两个解释器、策略与视觉权重、统计文件、配置、manifest、兼容入口和全部文本缓存。
- 创建新的空结果目录，打印 `EVAL_DIR=...`，并把路径保存到 `/workspace/vjepa/cache/latest_plus_full.path`。
- 调用上游 `examples/libero_plus/evaluate_policy.sh`，自动启动与回收 Policy 服务和仿真客户端。

`Validated 1549 cached prompts` 只表示文本缓存验证通过，不是评测结果。请保存启动窗口打印的精确结果路径。

按 `Ctrl+B`，松开后按 `D` 可离开 tmux 而让评测继续。之后在宿主机执行 `tmux attach -t vjepa_full` 返回。

## 4 另开终端查看进度

```bash
# 宿主机
docker exec -it vjepa-dev bash

# 容器内
export EVAL_DIR="$(cat /workspace/vjepa/cache/latest_plus_full.path)"
echo "$EVAL_DIR"
tail -f "$EVAL_DIR/libero_spatial.log"
```

`Ctrl+C` 只退出这个终端中的 `tail`。串行进入下一 Suite 后，改看 `libero_object.log`、`libero_goal.log` 或 `libero_10.log`。

查看各套件完成数和 worker 状态：

```bash
for suite in libero_spatial libero_object libero_goal libero_10; do
  file="$EVAL_DIR/$suite/episodes.jsonl"
  count=0
  if [ -f "$file" ]; then count=$(wc -l < "$file"); fi
  status=not_started
  if [ -f "$EVAL_DIR/$suite.status" ]; then
    status=$(cat "$EVAL_DIR/$suite.status")
  fi
  echo "$suite: $count episodes, status=$status"
done
nvidia-smi
```

`running` 表示该 worker 正在执行，`0` 表示正常完成，非零表示该 worker 失败。上游串行调度在某个 Suite 失败后可能继续后续 Suite，最终才汇总 incomplete，因此要同时看完成数和状态。

另一个全量评测会更新 latest 路径文件；观察本次运行时，继续保留已打印的具体 `EVAL_DIR`。不要在监控终端重新生成时间戳。

## 5 完成后先验收 再读取成绩

在容器中执行，使用本次真实输出目录：

```bash
export EVAL_DIR="$(cat /workspace/vjepa/cache/latest_plus_full.path)"
bash /workspace/vjepa/scripts/verify_policy_plus_full.sh "$EVAL_DIR"
cat "$EVAL_DIR/summary.txt"
/workspace/vjepa/envs/policy/bin/python -m json.tool "$EVAL_DIR/results.json"
```

验收成功应打印：

```text
Full LIBERO-Plus coverage verified: 10030/10030
```

验收会调用上游 validator，并检查：四个 Suite 的任务身份、无缺失和重复、每任务 `episode_id=0`、指令及 manifest 哈希匹配、各 Suite 数量正确、四个 worker 状态为 0，以及 `complete=true` 和 `selected_complete=true`。

通过后，用下面的指令查看总成功率和七类扰动成绩：

```bash
/workspace/vjepa/envs/policy/bin/python - "$EVAL_DIR/results.revalidated.json" <<'PY'
import json
import sys
from pathlib import Path
r = json.loads(Path(sys.argv[1]).read_text())
print(f"Overall: {r['successes']}/{r['episodes']} = {100 * r['success_rate']:.2f}%")
for name, row in sorted(r['categories'].items()):
    print(f"{name}: {row['successes']}/{row['episodes']} = {100 * row['success_rate']:.2f}%")
PY
```

总成功率按全部 10030 个 Episode 计算，不能直接平均四个 Suite 的百分比。任务正常结束且 `success=false` 是任务失败，会计入成绩；推理崩溃或渲染错误导致的未完成 Episode 不能当作完整成绩。

## 6 想先看到机器人表现

在完整评测启动前，可先运行前 10 个任务并录制视频：

```bash
bash /workspace/vjepa/scripts/run_policy_plus.sh ten
export EVAL_DIR="$(cat /workspace/vjepa/cache/latest_plus_ten.path)"
find "$EVAL_DIR" -type f -name '*.mp4' -printf '%p\n'
```

视频保存在本次 `EVAL_DIR/libero_spatial/` 下。`ten` 只检查部分任务，不替代完整 baseline。单张 GPU 上等待它完成并退出后，再启动 `full`。

## 7 报错时按当前日志定位

```bash
rg -n 'Traceback|KeyError|RuntimeError|OSError|Error|Failed|address already in use' \
  "$EVAL_DIR"/*_runner.log \
  "$EVAL_DIR"/*_server.log \
  "$EVAL_DIR"/libero_*.log
```

| 现象 | 处理 |
| --- | --- |
| 缺少 `LIBERO_PLUS_PYTHON` 或其他路径 | 重新 source 统一配置；先确认是当前终端的变量问题 |
| `observation.images.image` 缺失 | 检查实际使用的是 `serve_policy_libero_compat.py`，保留四张图像的格式转换 |
| 14001 到 14004 端口占用 | 结束对应旧服务后再运行 launcher |
| KeyError 后出现 EGL 清理异常 | 优先修最早的推理异常，再确认渲染是否独立失败 |
| 文本缓存缺失或 provenance 不匹配 | 按完整教程校验或准备匹配的 Plus 缓存 |
| 某 Suite 状态非零或最终 incomplete | 检查对应 server、client 和 runner 日志，不能只看其他 Suite 仍在运行 |

此版本不支持自动断点续跑。中断或失败后保留原日志，修复原因，再用新目录重新运行。不要直接把几个部分结果目录拼成已完成的完整评测。

## 8 保留本次 Baseline 的版本

等 launcher 完全退出后再保存附加文件到结果目录：

```bash
source /workspace/vjepa/scripts/policy_plus.env
git -C "$POLICY_REPO" rev-parse HEAD > "$EVAL_DIR/policy.commit.txt"
git -C /workspace/vjepa/tutorials/WAM rev-parse HEAD > "$EVAL_DIR/tutorial.commit.txt"
cp /workspace/vjepa/scripts/policy_plus.env "$EVAL_DIR/"
cp "$POLICY_SERVER_SCRIPT" "$EVAL_DIR/"
sha256sum "$CHECKPOINT" "$DATASET_STATS" "$VJEPA2_ENCODER_CHECKPOINT" \
  "$LIBERO_PLUS_MANIFEST" "$POLICY_SERVER_SCRIPT" > "$EVAL_DIR/artifacts.sha256"
```

本操作单提供启动和验收方法；仓库本身未在本地发起远端 GPU 评测。实际完整成绩以运行产物为准。
