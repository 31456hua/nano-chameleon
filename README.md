# 纳米变色龙 · Nano Chameleon

输入目标光谱，使用 Agnes / AGH 调用 MiePython、SciPy 和 MCP 工具，搜索球形纳米颗粒参数，保存试算过程，并在锁定参数后用留出波长验证结果。

团队：范式 U226；成员：花豫苏、胡彬。

源码仓库：[31456hua/nano-chameleon](https://github.com/31456hua/nano-chameleon)。

本项目提供物理计算源码、本机演示台、合成数据、四条历史 Agnes 执行记录和 HTML 报告。当前结果来自均匀球体与恒定折射率模型，用于仿真筛选与科学计算演示；尚无真实材料实验。

[演示视频（B 站）](https://www.bilibili.com/video/BV1EXpQ6MEMP/) · [项目说明](docs/PROJECT.md) · [复现说明](docs/REPRODUCE.md) · [来源与 AI 辅助说明](docs/SOURCES.md)

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

## 运行测试

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

| 合成目标 | 候选数量 | 留出 NRMSE | 预设门槛 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 无噪声 A | 647 | 0.0000293% | 1% | 达标 |
| 无噪声 B | 643 | 0.00000118% | 1% | 达标 |
| 带噪声 | 351 | 2.174% | 6% | 达标 |
| 色散失配 | 279 | 10.884% | 5% | 未达标 |

这四条历史任务共记录 1,920 个候选。另有 18 次 SciPy 基线，不能计为 Agnes 调用。以上为原波段内的合成数据留出验证，良好拟合不证明参数唯一；色散失配的失败结果一并保留。

## 目录

| 路径 | 内容 |
| --- | --- |
| `nano_chameleon/` | 数值引擎、MCP 服务、演示台、测试、归档结果和报告 |
| `AGH_trace/` | 四条主要历史执行轨迹的便捷入口 |
| `offline_validation/` | 已封存的合成验证设定 |
| `docs/` | 项目、复现、来源和归档说明 |
| `evidence/` | 历史验证记录及公开副本的本轮测试日志 |
| `LICENSES/` | 已收集的第三方组件许可原文 |

## 使用范围与来源

模型假设为均匀、单分散球体，折射率 n/k 在波段内恒定；当前没有材料识别、任意形状、壳层结构或真实制备配方。透射色预览由固定观察条件下的科学计算生成。

代码、测试、界面、文档和实验调度含 AI 辅助。核心历史任务使用记录标识为 `agnes-3.0-flash` 的模型，经 AGH 调用数值工具；本项目没有训练新的 Agnes / CNN 权重。详细组件与素材来源见[来源说明](docs/SOURCES.md)。

## 许可证

本仓库的团队原创软件及其配套文档采用 [MIT 许可证](LICENSE)。第三方代码保留各自许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [LICENSES](LICENSES/)。外链视频及其音频素材不在本仓库分发范围内，不随本项目的 MIT 许可再授权。
