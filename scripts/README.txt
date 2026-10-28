VJEPA AC 与 Policy 配套脚本

配合《VJEPA_AC与Policy_配置运行教程_2026-10-28》使用。
将 scripts 目录的内容复制到容器 /workspace/vjepa/scripts/。

本包包括
common.env                 公共缓存和本地代理排除项
ac.env                     AC路径变量
smoke_ac.py                AC前向检查与可选CEM
policy_plus.env            Policy与Plus路径和控制参数
serve_policy_libero_compat.py  本次已跑通的兼容入口
run_policy_plus.sh         smoke、ten、full三种模式
verify_policy_plus_full.sh 完整10030次评测验收

先按教程完成环境、权重、资源、manifest和文本缓存准备。
已有完整Policy配置后
bash /workspace/vjepa/scripts/run_policy_plus.sh smoke
或
bash /workspace/vjepa/scripts/run_policy_plus.sh full

AC最小运行的全部参数和示例命令见教程第3和第4章。
AC脚本与新建依赖组合未在本机进行GPU运行；以目标服务器验收为准。
脚本包不包含权重、T5模型或仿真资源。
