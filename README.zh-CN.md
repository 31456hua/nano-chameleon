# 纳米变色龙 · Nano Chameleon

[English](README.md) | 简体中文

<p align="center">
  <b>给一条目标光谱，反推纳米颗粒参数：一条可复现、可审计、敢报告失败的逆设计流水线。</b>
</p>

团队：范式 U226 · 成员：花豫苏、胡彬 · 2026 黑客松本科生组

## 目录

- [项目介绍](#项目介绍)
- [视频介绍](#视频介绍)
- [架构介绍](#架构介绍)
- [集成标准](#集成标准)
- [快速运行](#快速运行)
- [历史结果](#历史结果)
- [仓库目录](#仓库目录)
- [模型假设、范围与来源](#模型假设范围与来源)
- [许可证](#许可证)

## 项目介绍

纳米变色龙把**纳米颗粒颜色的逆设计**组织成一条可运行、可检查的流水线：给定一条目标散射光谱，反推颗粒的光学参数（粒径、折射率 *n*、消光系数 *k*），并用从未参与拟合的留出波长证明结果可外推。

### 项目背景

纳米颗粒的颜色是**结构色**：白光照到小球体上发生米氏散射，散射效率 Q_sca(λ) 随波长变化，透射光因此带上颜色。正演容易（参数 → 光谱），反演很难，因为

- **参数耦合**——粒径与 *n* 在同一共振位置互相补偿；
- **多解性**——不同的 (d, n, k) 可能给出几乎相同的光谱，有噪声时更明显；
- **模型失配**——恒定 *n*/*k* 根本无法表达色散材料。

因此逆设计是在物理边界内做搜索并做验证，而不是解一个唯一方程。结果只有通过**封存的留出验收**才算数：参数只按训练误差选定、锁定，再对隐藏波长一次性评分。

### 核心功能

- **物理引擎**——基于 [MiePython](https://github.com/scottprahl/MiePython) 的确定性米氏散射计算，SciPy 差分进化加局部精修的数值优化。
- **模型驱动的实验闭环**——Agnes 在 [Agnes Harness](https://github.com/AgnesAI-Labs/agnes-harness)（AGH）内担任实验调度员：检查封存目标、提出候选、经 MCP 调用物理工具、依据反馈调整、导出报告。每次候选都落盘，模型本身不做物理计算。
- **封存盲验证**——内部留出波长集在锁定参数后一次性公开，之后拒绝继续拟合。
- **本机演示台**——本地网页界面：手动仿真、四条历史 Agnes 任务回放、报告一键生成。
- **可复现基准套件**——确定性合成场景（无噪声、带噪声、边界、模型失配）+ 预设门槛 + 封存证据。

### 创新亮点

- **分工而不是"AI 猜物理"**：Agnes 负责规划、反馈、记录（调度员角色）；MiePython/SciPy 负责确定性计算。物理正确性不依赖大模型的记忆。
- **留出验收即考试**：候选只按训练误差选择，揭盲一次性且不可逆（引擎在封存后拒绝试算写入）。
- **负结果是一等证据**：模型失配场景故意未达 5% 适配门槛（留出 NRMSE 10.884%），团队把它如实报告为"恒定 (n, k) 模型不适用"的边界证据，而不是藏起来。
- **全程可审计**：1,920 条封存候选曲线、AGH 原生轨迹、SHA-256 校验和与依赖版本钉死，仓库内每个数字都可复核。

范围声明：结果来自均匀球体、恒定折射率模型与合成数据，用于仿真筛选与科学计算演示；没有真实材料实验，不保证参数唯一。

## 视频介绍

**[B 站观看 4 分钟 AGH 演示视频](https://www.bilibili.com/video/BV1EXpQ6MEMP/)**——目标设置、Agnes 闭环、封存揭盲与报告导出的完整过程。

该录像源文件（U226_范式_纳米变色龙_演示_AGH版.mp4，2026-10-12 上传）不随仓库分发，B 站链接为规范引用。

## 架构介绍

四层分工，各管一块、各有自己的审计面：

```
 Agnes 模型（agnes-3.0-flash，经 AGH Provider 配置）
   规划 · 提议候选 · 依据反馈调整 · 记录决策
                │  MCP（stdio 上的 JSON-RPC）
 Agnes Harness（AGH）——执行底座
   会话 · 工具审批 · 原生轨迹 · 恢复
                │  5 个 nano-chameleon 工具
 nano-chameleon 服务（Python，stdio MCP 服务）
   封存实验存储 · 留出封存 · 逐次试验落盘
                │  调用
 确定性物理与数值计算（MiePython + SciPy + NumPy）
   正向 Mie Qsca(λ) · 差分进化 + 精修 · RMSE
```

### 核心模块

| 模块 | 职责 |
| --- | --- |
| `nano_chameleon/engine.py` | 目标 CSV 校验、实验存储（按 `run_id` 存 JSON）、留出封存、试算落盘、优化器、一次性 finalize |
| `nano_chameleon/mcp_server.py` | 以 stdio 提供下方 5 个工具的 MCP 服务（FastMCP） |
| `nano_chameleon/demo_server.py` | 本机演示台：手动仿真、历史回放、交互式报告 |
| `nano_chameleon/benchmark.py` | 确定性合成场景、SciPy 基线运行、HTML/JSON 汇总报告 |
| `nano_chameleon/report.py` | 自包含交互式 HTML 报告（全部试算 + 留出） |
| `nano_chameleon/cli.py` | 命令行工作流（`prepare / demo / fit / trial / status / validate / report`） |
| `AGH_trace/`、`evidence/`、`offline_validation/` | 封存原生轨迹、测试日志与验证设定（`SHA256SUMS.txt` 提供校验和） |

### 执行流程

1. `prepare` 读入目标 CSV，封存内部留出集，写入 `runs/`——智能体只能通过工具看到训练点。
2. Agnes 任务循环：`inspect_experiment` → 手动 `simulate_candidate` 试算 → `search_candidates`（物理约束、可复现）→ 反馈驱动的试算。
3. `validate_unseen_wavelengths` 按训练误差锁定最佳候选，公开留出评分，封存实验。
4. `export_experiment_report` 导出本地交互式报告。

基准层生成六个确定性合成场景（两条无噪声目标、一条带噪声目标、一条违反恒定 (n, k) 模型的色散目标，外加两个参数边界探测），运行封存、可复现的基线；结果汇总为离线 HTML。

## 集成标准

### MCP 工具接口

传输方式：**stdio 上的 JSON-RPC 2.0**；服务名 `nano-chameleon`（FastMCP）。工具目录、参数类型与后置条件：

| 工具 | 参数 | 后置条件 |
| --- | --- | --- |
| `inspect_experiment(run_id)` | `run_id: str`（32 位十六进制） | 只读；返回模型、*n_env*、参数边界、训练数据对、留出数量、最佳试算；封存目标保持隐藏 |
| `simulate_candidate(run_id, diameter_nm, n_real, k)` | 浮点数，范围 [50, 500] nm、[1.05, 2.8]、[0, 0.35] | 记录一次米氏试算；返回训练曲线 + RMSE；封存后拒绝 |
| `search_candidates(run_id, generations=20, seed=7)` | `generations ∈ [1, 30]`（整数）、`seed: int` | 可复现的差分进化 + 局部精修；返回训练最优解 |
| `validate_unseen_wavelengths(run_id)` | — | 不可逆：锁定最佳试算、公开留出 RMSE/NRMSE、封存实验 |
| `export_experiment_report(run_id)` | — | 要求已完成验证；返回 HTML 报告路径 |

协议不变量：

- **封存留出**——留出目标只在 finalize 时公开一次，此后拒绝一切试算写入。
- **全程落盘**——每个候选（参数、完整曲线、RMSE）都持久化；不重算、不虚构。
- **显式报错**——非法输入、越界参数、非有限值、重复波长、封存后写入均抛出 `ValueError`/协议错误，不做静默失败。
- **隔离**——一个服务进程只写一个实验；批量任务串行执行。

### AGH 接入

MCP 服务使用项目自带的虚拟环境启动；在 AGH 的 MCP 配置中指向解释器与脚本路径：

```sh
# 在 Agnes Harness 源码根目录执行（当前官方语法见其文档）
node packages/cli/dist/local/agnes.mjs mcp add nano-chameleon \
  --name nano-chameleon \
  --stdio "<python解释器路径>" \
  --arg "<绝对路径>/nano_chameleon/mcp_server.py"
```

随后在 AGH 中完成 MCP 审核、信任、启用与工具目录检查，并按 `nano_chameleon/AGH_TASK.md` 发起任务（替换 `run_id`）。审批模式、Provider 密钥与模型选择留在 AGH 侧；本仓库不保存任何密钥。`agh_dispatch.py` 是有界的串行调度扩展：每条任务一次搜索（≤15 代）、≤12 次手动试算、一次验证、最多两次报告导出。

### 演示台 HTTP API

仅本机回环服务（只绑定 `127.0.0.1`/`localhost`；POST 需要 `/api/config` 发放的本次启动专用令牌）。操作一览：

| 路由 | 方法 | 用途 |
| --- | --- | --- |
| `/` | GET | 演示界面 |
| `/api/config` | GET | 获取本次启动的令牌与预置场景列表 |
| `/api/evidence/{case}` | GET | 回放一条已核验轨迹的历史 Agnes 归档运行 |
| `/api/create` | POST | 由目标 CSV 或预置场景创建封存实验 |
| `/api/preview` | POST | 计算候选参数对应的训练曲线与透射色预览 |
| `/api/trial` | POST | 执行一次被记录的物理试算 |
| `/api/search` | POST | 运行有界可复现优化器（5 代，种子 7） |
| `/api/validate` | POST | 终结：锁定参数并公开留出 |
| `/api/report` | POST | 导出交互式 HTML 报告 |
| `/api/colour` | POST | 计算给定参数下的透射色 |
| `/report/{run_id}`、`/evidence-report/{case}` | GET | 获取已生成的报告 HTML |

### 数据格式

- **目标 CSV**——`wavelength_nm,qsca` 两列（UTF-8，容忍 BOM）；15–400 行；波长为正、互异、升序；Qsca 有限、非负。
- **实验 JSON**——按 `run_id` 存于 `runs/`；封存存储在设计上不对智能体开放；可用 `NANO_CHAMELEON_STORE` 迁移位置。
- **报告 HTML**——自包含（内联 JS/CSS），可离线查看；交互式曲线展示全部试算与留出。

## 快速运行

需要 Python 3.11+。以下命令在仓库根目录执行，首次安装依赖需要联网。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r nano_chameleon\requirements-verified.txt
.\.venv\Scripts\python.exe nano_chameleon\demo_server.py --port 4190
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r nano_chameleon/requirements-verified.txt
.venv/bin/python nano_chameleon/demo_server.py --port 4190
```

浏览器打开 <http://127.0.0.1:4190/>。端口已占用时，把命令和地址中的端口都改为 `4191`。

- **手动仿真**：实际执行物理计算与数值搜索。
- **Agnes 真实记录**：回放已归档的四个历史任务。
- **重新运行 Agnes**：需要另行安装 AGH，并配置自己的模型账号和 MCP 服务；见[复现说明](docs/REPRODUCE.md)。

页面服务只用于本机演示。`127.0.0.1` 是访问者自己的电脑地址；公开源码后，其他人需要下载并在自己的电脑上启动。

### 运行测试

Windows：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s nano_chameleon -p "test_*.py" -v
```

macOS / Linux：

```bash
.venv/bin/python -m unittest discover -s nano_chameleon -p 'test_*.py' -v
```

原补交材料记录了 2026-10-11 / 12 的 42 项测试；公开副本的本轮复核结果见 [evidence](evidence/)。封存记录、原始测试与本轮检查的关系见[归档说明](docs/ARCHIVE.md)。

## 历史结果

四条封存 Agnes 任务共 1,920 条候选曲线，模型 `agnes-3.0-flash`，已对照 AGH 原生轨迹核验：

| 合成目标 | 候选数量 | 留出 NRMSE | 预设门槛 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 无噪声 A | 647 | 0.0000293% | 1% | 达标 |
| 无噪声 B | 643 | 0.00000118% | 1% | 达标 |
| 带噪声 | 351 | 2.174% | 6% | 达标 |
| 色散失配 | 279 | 10.884% | 5% | **未达标**——作为模型适用边界如实报告 |

另有 18 次带种子的 SciPy 数值基线（7,576 次评估）作为独立证据类别封存，**不能计为 Agnes 调用**。所有目标均为合成数据；留出验证只衡量原波段内插值。良好拟合不证明参数唯一；失配的失败结果被有意保留。详见 [BENCHMARK.md](nano_chameleon/BENCHMARK.md)、[AGH_SCHEDULE.md](nano_chameleon/AGH_SCHEDULE.md)、[VERIFICATION.md](nano_chameleon/VERIFICATION.md)。

## 仓库目录

| 路径 | 内容 |
| --- | --- |
| `nano_chameleon/` | 数值引擎、MCP 服务、演示台、CLI、测试、封存运行与报告 |
| `AGH_trace/` | 四条主要历史执行轨迹 |
| `offline_validation/` | 已封存的合成验证设定 |
| `docs/` | 项目、复现、来源和归档说明 |
| `evidence/` | 历史验证日志及公开副本的本轮测试日志 |
| `LICENSES/` | 已收集的第三方组件许可原文 |
| `SHA256SUMS.txt` | 封存文件的校验和 |

## 模型假设、范围与来源

- 模型：均匀、单分散球体，折射率 *n*/*k* 在波段内恒定（吸收约定 n − i·k），介质折射率 1.0。不含材料识别、任意形状、壳层、尺寸分布或真实制备配方。
- 数据：程序生成的合成光谱，不含第三方实测光谱。
- AI 辅助：代码、测试、界面、文档与实验调度含 AI 辅助；封存的历史任务使用标识为 `agnes-3.0-flash` 的模型经 AGH 调用数值工具。没有训练新的 Agnes/CNN 权重；18 次 SciPy 基线不是 Agnes 调用。
- 完整组件与素材来源：[docs/SOURCES.md](docs/SOURCES.md)。

## 许可证

团队原创软件及其配套文档采用 [MIT 许可证](LICENSE)。第三方代码保留各自许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [LICENSES](LICENSES/)。外链演示视频及其音频素材不在本仓库分发范围内，不随本项目的 MIT 许可再授权。
