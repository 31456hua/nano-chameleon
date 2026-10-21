# AGH 接入与参赛核验

## 本机联调状态

已在用户现有的 AGH 工作台 `http://127.0.0.1:4177/` 接入 `nano-chameleon` MCP 服务，状态为 `connection=ready`，工具目录显示 5 个工具。使用该工作台已配置的 `agnes-3.0-flash` 模型完成一条真实 AGH 任务轨迹：两次初始试算、一次约束搜索、一次基于反馈的试算、七个未见波长的验证和报告导出。会话地址：`http://127.0.0.1:4177/?session=f65a8a7e-e07a-4ada-94f1-a8a628ec1a43`。本项目没有保存 Provider 密钥。

另曾在隔离的 `work/agh-home` 配置下启动 `http://127.0.0.1:4180/` 用于 MCP 连通性检查；该实例没有配置模型，不是上述真实任务的执行环境。

2026-10-11 已恢复原 4177 工作台，并通过官方 SDK 完成四条扩展评测及一次封存后收尾恢复。调度器不切换审批模式、不读取模型密钥，限制搜索为一次 15 代、手动试算最多 12 次。结果、会话链接及安全启动注意事项见 [调度与恢复记录](AGH_SCHEDULE.md)。这是实验与评测调度，不是 Agnes 模型权重训练。

## 1. 准备一次实验

用 `python cli.py prepare target.csv` 创建实验，并记下 `run_id`。目标光谱的完整值保存在本机 `runs/`，不要让智能体直接读取该文件；工具只提供训练波长和目标值。真实盲测应由另一位成员保管留出集，防止模型从原始 CSV 绕过流程查看答案。

## 2. 将 MCP 工具交给 AGH

按照 [AGH 官方安装指南](https://github.com/AgnesAI-Labs/agnes-harness/blob/main/README.zh-CN.md)启动 AGH。官方主线当前是开发者预览，要求 Node.js 24.10+ 与 pnpm 10.34.5。在 AGH Web 的 Provider 设置里配置赛事账号提供的 Agnes 模型并测试连接；不要把密钥写入本项目。AGH 源码根目录下运行以下命令；移动本项目后应调整脚本绝对路径：

```text
node packages/cli/dist/local/agnes.mjs mcp add nano-chameleon --name nano-chameleon --stdio "D:\python\python.exe" --arg "D:\chat Gpt\2026-10-10\miepython-https-github-com-scottprahl-miepython-3\outputs\nano_chameleon\mcp_server.py"
node packages/cli/dist/local/agnes.mjs mcp get nano-chameleon
```

根据 `get` 返回的当前 revision，依照 [官方 MCP 指南](https://github.com/AgnesAI-Labs/agnes-harness/blob/main/docs/guide/mcp.zh-CN.md)完成审核、启用和工具目录检查。每次写操作后重新 `get` 获取 revision：

```text
node packages/cli/dist/local/agnes.mjs mcp trust nano-chameleon --expected-revision REVISION
node packages/cli/dist/local/agnes.mjs mcp get nano-chameleon
node packages/cli/dist/local/agnes.mjs mcp enable nano-chameleon --expected-revision NEW_REVISION
node packages/cli/dist/local/agnes.mjs mcp status nano-chameleon
node packages/cli/dist/local/agnes.mjs mcp tools nano-chameleon
```

也可在 AGH 会话中请求连接这个本地 stdio MCP，再在设置的 MCP 页面审核并启用。确认会话里能够真实调用 `inspect_experiment` 和 `simulate_candidate`。配置 AGH 时只选择赛事允许的 Agnes 模型，不要在本项目保存密钥。

## 3. AGH 会话任务文本

将下面的任务文本发给 AGH，替换实验 ID：

> 你是纳米颗粒反向设计实验员。实验 ID 为 RUN_ID。先调用 inspect_experiment，说明目标、参数边界和可能的非唯一性。规划并执行至少两次 simulate_candidate，分析返回的训练 RMSE 和曲线如何改变下一步。然后调用 search_candidates 进行物理约束搜索，解释最优参数，并根据反馈再设计至少一次 simulate_candidate。只能依据工具公开的训练数据选择参数，不要读取 runs/、原始 CSV 或任何留出目标。最后调用 validate_unseen_wavelengths 锁定最佳参数并解释训练与留出误差，再调用 export_experiment_report。不得虚构试验结果或把数值基线称作 Agnes 模型调用。

## 4. 证据检查

- AGH 原生轨迹应显示规划、MCP 工具调用、反馈调整、最终验证至少三个连续步骤。
- 模型名称、版本、使用环节及调用方式由实际 AGH 会话记录填写；不要根据本项目代码推断。
- 保存 AGH 工具调用记录、HTML 报告、目标数据来源、正常/边界/失败样例，以及队伍成员的独立完成说明。
- `runs/*.json` 含完整目标数据；提交公开证据时先检查数据授权和隐私，不要包含密钥。

完整的本机实测结果见 [验证记录](VERIFICATION.md)。示例目标是无噪声合成数据，零误差不能代表真实材料测量精度。原参赛材料另有资格、声明和提交检查，未收入此公开副本；公开副本范围见[归档说明](../docs/ARCHIVE.md)。

批量任务应逐个执行，同一实验文件只由一个服务进程写入。搜索代数限制不包含局部精修的额外评估，也不是多次工具调用的总预算；调用方应明确每个实验允许的搜索次数和试算次数。

赛事技术要求和提交细则以活动官方页面为准：https://agnes-ai.cn/hackathon 。
