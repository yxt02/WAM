# WAM 实验配置与运行记录

保存 V-JEPA AC 与 V-JEPA Policy 的环境教程、观测协议兼容入口和 LIBERO-Plus 评测脚本。

## 先运行 Policy Baseline

已有今天跑通的 `vjepa-dev` 容器、策略权重、Plus 仿真环境和 T5 缓存时，按 [Policy 完整评测操作单](docs/POLICY_FULL_EVAL.md) 执行。操作单包括把本仓库脚本安装到服务器、启动完整评测、查看进度、核验覆盖率和读取成绩。

脚本安装好后的启动入口：

```bash
bash /workspace/vjepa/scripts/run_policy_plus.sh full
```

`full` 运行四个套件，共 10030 个 Episode，使用 GPU 0 串行执行，每任务一次，启用严格完整性校验。脚本会自动启动 Policy 服务和 Plus 仿真客户端。

想先看机器人视频，可独立运行前 10 个任务：

```bash
bash /workspace/vjepa/scripts/run_policy_plus.sh ten
```

`ten` 录制视频，属于部分任务检查；`full` 默认关闭视频。两种模式分别保存结果。

## 文件入口

| 文件 | 内容 |
| --- | --- |
| [Policy 完整评测操作单](docs/POLICY_FULL_EVAL.md) | 已有环境的部署、启动、监控、验收和成绩读取 |
| [完整教程 Markdown](docs/AC_POLICY_SETUP_2026-10-28.md) | AC 与 Policy 从零配置、日常运行、参数和 Bug 处理 |
| [完整教程 Word](docs/AC_POLICY_SETUP_2026-10-28.docx) | 与 Markdown 同内容的排版阅读版 |
| [运行脚本](scripts/) | 环境文件、AC 检查、Policy 兼容入口和完整评测验收 |

## 当前验证状态

2026 年 10 月 28 日的记录已确认：Policy 在 LIBERO-Plus 的 `libero_spatial` task 0、episode 0 成功，生成成功视频。本仓库给出完整评测流程，尚不包含完整 10030 次评测的成绩。

AC 部署步骤基于固定版本官方源码重建，配套脚本已做语法检查；目标服务器的 GPU 运行结果按教程中的验收标准确认。策略权重、视觉权重、T5 模型、仿真资源和原始聊天 HTML 均不包含在本仓库中。

## 对照的上游版本

- AC：[`facebookresearch/vjepa2`，`204698b45b3712590f06245fbfba32d3be539812`](https://github.com/facebookresearch/vjepa2/tree/204698b45b3712590f06245fbfba32d3be539812)
- Policy：[`breez3young/VJEPA-Policy`，`d0e75c44463f85942f3580813fbcfe904cc0cf15`](https://github.com/breez3young/VJEPA-Policy/tree/d0e75c44463f85942f3580813fbcfe904cc0cf15)
- Plus：[`sylvestf/LIBERO-plus`，`4976dc30028e805ff8094b55501d532c48fec182`](https://github.com/sylvestf/LIBERO-plus/tree/4976dc30028e805ff8094b55501d532c48fec182)
