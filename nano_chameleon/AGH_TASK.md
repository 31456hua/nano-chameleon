# AGH 演示任务

当前本机已准备一条尚未揭盲的示例光谱，实验 ID：`39cfa00bc622478a8ba4eb1dd4cec5fa`。在 AGH 配好允许的 Agnes 模型后，新建任务并发送以下文本。任务工作目录建议使用不含 `runs/` 和原始 CSV 的空目录。

> 你是纳米颗粒反向设计实验员。实验 ID 为 39cfa00bc622478a8ba4eb1dd4cec5fa。先调用 nano-chameleon 的 inspect_experiment，说明目标、参数边界和逆问题可能不唯一的原因。规划并执行至少两次 simulate_candidate，每次根据训练 RMSE 和散射曲线调整下一候选。调用 search_candidates 完成物理约束搜索，解释最优参数，再根据搜索反馈设计至少一次 simulate_candidate。整个搜索阶段只使用工具公开的训练数据，不读取 runs/、原始 CSV 或留出目标。最后调用 validate_unseen_wavelengths 锁定参数并解释训练与留出误差，然后调用 export_experiment_report。请把每步决策、工具返回和异常处理写入本次 AGH 轨迹，不要虚构结果。

这条示例目标由程序合成。正式参赛时，先用自己的测量或公开数据 CSV 创建新的实验 ID，并在任务文本中替换；如实注明数据和第三方代码来源。
