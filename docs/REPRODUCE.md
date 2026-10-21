# 复现说明

## 本机数值与页面

从仓库根目录按[首页快速运行](../README.md#快速运行)创建独立 Python 环境、安装 `nano_chameleon/requirements-verified.txt`，并启动 `nano_chameleon/demo_server.py`。该依赖清单固定了原验证环境版本；没有在本轮执行一次全新联网安装。

Windows 是原验证环境。macOS / Linux 的命令按标准 Python 虚拟环境路径提供，尚未在这些系统进行本轮实测。首次安装仍须联网，前端库已随项目提供。

手动仿真的新记录写入 `nano_chameleon/demo_runs/`，不会覆盖封存的 AGH 记录。上传目标时使用 `wavelength_nm,qsca` 两列，示例见 [`example_target.csv`](../nano_chameleon/example_target.csv)。

同一实验只允许单进程写入；揭盲后不能继续拟合。变更目标或搜索策略时新建实验，保留原记录。

## 历史结果与轨迹

| 任务 | 数值记录与 HTML 报告的文件名主干 |
| --- | --- |
| `clean_a` | `69f40ac21827433a98ad5a231b92706c` |
| `clean_b` | `6316c87602d84c2fab5e20a6ed5bcad9` |
| `noisy` | `4ca3625df4674a17a83544d289127441` |
| `mismatch` | `93dd00121a0c415681d5d3c0d66770fa` |

轨迹在 [`AGH_trace/`](../AGH_trace/)，数值记录在 [`nano_chameleon/runs/`](../nano_chameleon/runs/)，报告在 [`nano_chameleon/reports/`](../nano_chameleon/reports/)。HTML 文件下载后可在本地打开；GitHub 文件页主要用于查看文件，不会把 Python 服务自动部署为网站。

## 新的 Agnes / AGH 执行

1. 另行安装 [Agnes Harness](https://github.com/AgnesAI-Labs/agnes-harness)，按它的当前官方文档配置自己的 Agnes Provider。
2. 把本项目 `nano_chameleon/mcp_server.py` 配为 stdio MCP 服务。Python 应使用本项目虚拟环境里的可执行文件，脚本填写本机绝对路径。
3. 按 AGH 界面或官方指南完成 MCP 审核和启用，确认五个工具可用。
4. 新建目标与实验 ID，依 [`AGH_TASK.md`](../nano_chameleon/AGH_TASK.md)执行并导出新记录。历史脚本使用的是当时 AGH SDK 的内部源代码接口；需要匹配原接口或按当前官方接口适配。

原集成过程见 [`AGH_RUNBOOK.md`](../nano_chameleon/AGH_RUNBOOK.md)和 [`AGH_SCHEDULE.md`](../nano_chameleon/AGH_SCHEDULE.md)。这些文档中的磁盘路径、会话地址、Node/pnpm 版本是历史记录，不能直接当作当前安装要求。新执行应使用自己电脑的路径和工作目录。

本仓库不包含 AGH 安装包、模型账号或 Provider 密钥。数值测试与历史回放可以独立运行；需要重新调用 Agnes 时再配置自己的环境。
