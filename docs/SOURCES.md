# 来源与模型使用说明

项目：纳米变色龙；范式 U226。以下为原材料中的技术与素材来源记录，公开副本整理日期为 2026-10-21。

## 核心运行模型

| 名称/版本记录                   | 环节                          | 调用方式                                                | 证据                                            |
| ------------------------- | --------------------------- | --------------------------------------------------- | --------------------------------------------- |
| agnes-3.0-flash，独立构建版本未留存 | 目标检查、任务规划、候选设计、反馈调整、验证解释与导出 | 已配置 Agnes Provider 的 AGH，经官方 SDK 调度和 stdio MCP 专业工具 | 四条原生轨迹中的 request/header、tool/call、tool/result |

四条核验轨迹的请求头均为 Agnes。MiePython 与 SciPy 是专业数值计算工具，不是额外语言模型，也没有训练新的 Agnes/CNN 权重。

## 开发与后期辅助（不混同核心运行）

- 视频采用团队提供的九段曼波合成配音，来源工具 https://tools.dayun.cool/manbo 。语音模型名称、版本和声线授权未获得凭据，不编造；比赛展示与公开传播是否允许须确认。
- 后期字幕时间辅助使用本机 faster-whisper 1.2.1 的 Whisper base/small；权重修订未记录。模型仅作后期识别，不用于物理反演，不随源码分发。字幕经项目脚本文字修正，最终仍须人工听审。
- 剪辑软件采用剪映专业版；录屏来自团队提供视频，摘要图依据封存结果制作。无需把每个后期操作写成作品技术创新；但不能隐瞒按规则需说明的模型辅助或素材来源。

通知的“仅 Agnes”与当前官网允许其他合法模型的文字存在差异，辅助开发、语音生成及识别是否落入限制需取得主办方最终口径。此说明是事实记录，不是已获许可的结论。

## 专业组件

下列版本是本轮提交副本复验环境；历史基准版本另见 benchmark_summary.json。

| 组件                  | 本轮版本           | 用途                  | 来源 / 许可                                                             |
| ------------------- | -------------- | ------------------- | ------------------------------------------------------------------- |
| MiePython           | 3.3.0          | 均匀球体 Qsca/Qext 正向计算 | https://github.com/scottprahl/miepython / MIT                       |
| NumPy               | 2.4.6          | 数组计算                | https://numpy.org/ / BSD 主许可及发行包附带许可                                |
| SciPy               | 1.17.1         | 差分进化和局部精修           | https://scipy.org/ / BSD 主许可及发行包附带许可                                |
| MCP Python SDK      | 1.30.0         | stdio MCP 接口        | https://github.com/modelcontextprotocol/python-sdk / MIT            |
| Matplotlib          | 3.11.2         | 科学曲线和角分布图           | https://matplotlib.org/ / 发行包许可原文                                   |
| Colour              | 0.4.7          | CIE/XYZ/sRGB 色度积分   | https://www.colour-science.org/ / BSD-3-Clause                      |
| Plotly Python       | 6.9.0          | HTML 报告             | https://github.com/plotly/plotly.py / MIT                           |
| Plotly.js           | 3.7.0          | 本地前端绘图              | https://github.com/plotly/plotly.js / MIT                           |
| Lucide              | 1.8.0          | 前端图标                | https://lucide.dev/ / ISC，部分图标含 Feather MIT 来源                      |
| Starlette / Uvicorn | 1.7.0 / 0.54.0 | 本机演示台服务             | https://www.starlette.io/ 、 https://www.uvicorn.org/ / BSD-3-Clause |
| httpx               | 0.28.1         | 自动测试客户端             | https://www.python-httpx.org/ / BSD-3-Clause                        |
| Agnes Harness       | 精确构建版本未保存在本包   | 智能体运行、MCP 连接与轨迹     | https://github.com/AgnesAI-Labs/agnes-harness ，另行安装，不再分发其源码/凭据      |

../LICENSES/ 保存直接依赖发行包的许可原文及实际打包的前端库许可。
本包不分发 Python/Node/AGH 安装文件或依赖二进制；安装者仍须遵守各自完整依赖的许可。
公开版的团队原创软件与配套文档采用根目录 MIT 许可证；第三方内容保留原许可。

## 数据、图像与证据

- 目标数据为 benchmark.py 程序合成；参数、噪声、失配设定见 offline_validation 的已封存 suite_private.json。
- Qsca/Qext 是球体仿真结果，不是真实材料测量，未引入第三方实测光谱。
- angular-scattering.png 由 prepare_demo_assets.py 调用 MiePython/Matplotlib 计算。
- 录屏由团队提供；结果摘要由已封存数据排版，不是生成的现场操作画面。
- 原生 AGH 轨迹、失败快照及报告从既有运行归档原样复制。历史路径只用于溯源，不能作为移机命令。
- 原始音频、声音授权材料尚未提供公开许可凭据。未经确认不把“有音频文件”当成“可公开使用”。

## 公开副本范围

本仓库不分发原视频、原始音频、报名表和联系方式。外链视频的声音及素材许可不由本仓库 MIT 许可证代为授予。上文中赛事规则与许可待确认的记载属于历史材料，不代表本轮取得了额外授权。
