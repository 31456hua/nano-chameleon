# 竞赛演示台与录屏顺序

## 定位

**纳米变色龙：给 AI 一条目标光谱，让它提出颗粒候选，再用物理仿真和留出波长检验。**

当前交付是均匀球体、恒定 n/k 的仿真逆设计，不是“说任意颜色就得到真实材料制备配方”。不展示未实现的材料分类、壳层、神经网络训练或波段外预测。

## 启动与复现

在本目录执行，Python 3.11+：

```powershell
python -m pip install -r requirements-demo.txt
python prepare_demo_assets.py
python demo_server.py --port 4190
```

打开 http://127.0.0.1:4190/ 。只监听本机；端口已占用时用 `--port 4191`，页面地址同步改为 4191。前端库已随本目录提供，无 CDN 依赖。AGH 工作台独立运行在 4177；页面不读取 Provider 凭据。

`手动仿真` 实际调用 MiePython 和 SciPy，不调用 Agnes。其记录位于 `demo_runs/`，不会写入 AGH 的 `runs/`。每次新建或上传都产生新的实验 ID，不覆盖旧试验。CSV 使用 `wavelength_nm,qsca` 两列，15-400 个不同的正波长，Qsca 非负且有限；它不是未经标定的照片或任意归一化强度。

`Agnes 真实记录` 只读展示四个已完成任务及官方 SDK 保存的原生工具链，不表示正在实时调用模型。原会话链接指向 4177，工作台离线时归档记录仍可展示。现场实时 AGH 执行按 `AGH_RUNBOOK.md`、`AGH_SCHEDULE.md` 复现，不在网页内伪造模型运行。

## 3-5 分钟演示顺序

| 时间 | 实际画面 | 讲述重点 |
| --- | --- | --- |
| 0:00-0:25 | 目标 A、训练目标点和候选曲线 | 目标驱动的颗粒逆设计，减少模型内的盲目试算；当前是仿真验证 |
| 0:25-1:05 | 手动仿真，滑动粒径/n/k，记录两个候选 | 正向物理计算会改变散射曲线；每次记录都保留。手动模式不冒充 AI |
| 1:05-1:35 | 数值搜索、训练误差演进、候选回放 | 搜索工具是 SciPy；五代不等于五次试算。候选排序不是置信概率 |
| 1:35-2:05 | 锁定最佳并验证、揭盲、导出报告 | 先按训练误差选定参数，再一次性公开留出波长。当前是波段内留出，不是外推 |
| 2:05-3:05 | 切换 Agnes 真实记录，展开工具链 | Agnes 通过 AGH 检查目标、提出候选、利用反馈搜索、再试算、验证、导出。显示模型名与原会话；录屏时称为历史真实运行 |
| 3:05-3:35 | 带噪声和色散失配目标 | 噪声案例达标；失配案例留出 NRMSE 10.88%，超过预设 5%。执行完成不等于科学模型适用 |
| 3:35-4:00 | 透射色预览和报告 | 色块是固定观察条件下的辅助仿真，不代表实物色或制备配方。总结可核验闭环及下一阶段真实数据需求 |

录屏应由团队操作并解释关键实现。需要展示“实时 Agnes”时，另录真实 AGH 调度过程；不要将曲线播放动画说成当前模型在思考。这里未生成或提交视频、成员声明、公开项目帖或报名资料。

## 透射色的定义

- 在 360-830 nm、1 nm 步长下计算 Qext，使用 `T(λ)=exp[-τ_ref (d/200nm)^2 Qext(λ)]`。
- `τ_ref` 是颗粒柱数密度乘以 200 nm 球的几何截面积，不是某个实际溶液浓度或制备建议。所有尺寸比较在相同柱数密度假设下进行。
- 用 D65 光源、CIE 1931 2° 观察者积分得到 XYZ，转换为 sRGB；超出显示色域时裁剪并标注。
- 模型为稀分散、独立均匀球体的直射透射，不包含多重散射、浓度相关相互作用、壳层和实际色散。n/k 在整个色度积分范围内也被假设恒定。
- 算法使用 [Colour 的光谱积分接口](https://colour.readthedocs.io/en/latest/generated/colour.sd_to_XYZ.html)和 [XYZ 转 sRGB 接口](https://colour.readthedocs.io/en/latest/generated/colour.XYZ_to_sRGB.html)。不能直接把 Qsca 当作反射率映射颜色。

## 资产和测试

- `angular-scattering.png` 是 `prepare_demo_assets.py` 用 MiePython + Matplotlib 计算的角分布图，不是实物照片，也不使用其他 AI 模型生成。
- Plotly.js 由已安装的 Python Plotly 6.9.0 导出，MIT 许可信息保留在脚本头部；Lucide 为 ISC 授权，部分图标衍生自 MIT 授权的 Feather，完整说明见 `demo_web/LUCIDE_LICENSE`。图标来源 https://lucide.dev/ 。Colour 0.4.7 为 BSD-3-Clause 组件。
- 页面仅接受配置端口的本机 Host；修改操作需要同源 Origin 与短期请求令牌。它不是多用户服务，不应直接暴露到互联网。
- `python -m unittest test_engine.py test_mcp.py test_validation.py test_benchmark.py test_dispatch.py test_demo.py` 检查核心、MCP、调度、演示台与留出隔离。
- `work/verify_demo.cjs` 为本机浏览器回归检查，截图和机器可读结果位于项目根目录的 `work/`。这些是验收记录，不是新增 Agnes 执行证据。
