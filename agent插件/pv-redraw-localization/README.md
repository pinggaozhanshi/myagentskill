# PV重绘、本地化与歌曲合成工作流

入口：[SKILL.md](SKILL.md)。无技能系统的Agent也可以直接读取该文件，并按链接读取相关细节。

## 怎么调用

给Agent的任务提示可写：

> 请先读取本包的SKILL.md，使用本工作流完成这段动画PV的人物替换/歌词本地化/音轨替换。先检查我提供的源片与当前工程，沿用已有授权，交付新的可播放成片、验证记录和接续状态。

支持Agent Skills格式的宿主：将整个`pv-redraw-localization`文件夹放进其技能目录。Codex可显式调用`$pv-redraw-localization`；本机安装位置见交付说明。自动发现与调用取决于宿主，读取能力与工具能力是两件事，不保证任何Agent无需配置就能自动调用。

## 包含什么

| 文件 | 用途 |
|---|---|
| SKILL.md / AGENTS.md | 技能入口、任务识别与路由 |
| references/production.md | 素材接续、原画生成、曝光、站位和动态验收 |
| references/lyrics.md | 字幕清除、人物保护、排版与动画 |
| references/audio-and-delivery.md | ACE时间坐标、歌曲对齐、封装和验收 |
| references/lessons.md | 故障根因索引、实测案例、历史错误的纠正 |
| references/tools.md | 工具命令与缺少工具时的替代路径 |
| templates/project-manifest.json | 需要按当前源片重填的镜头/曝光/歌词结构示例，不能直接制作 |
| scripts/pv_tools.py | 帧区间、tick换算、音轨lag与视频码流核查 |
| evidence/validation.md | 本包的验证范围与行为测试结果 |
| MANIFEST.json | 打包文件长度及SHA256（自身不纳入自身哈希） |

文档可独立使用。可选媒体工具需要Python、NumPy和PyAV；`self-test`的结构检查仅需标准库，DSP检查需NumPy。包中不携带原视频、人物原画、字体文件、模型权重、账户、API密钥或运行时；它打包的是可复用经验和机械核查工具，不是原项目复刻安装包。

## 来源和适用边界

从《魔法女仆》PV的v1–v11素材生成、已知问题修正、增绘稳定、中文歌词和中文演唱合成中提炼，日期2026-10-08。通用方法见技能与参考；数量、帧号、鞋底误差和偏移等实测记录放在案例章节。本文不把近似原画、编码数值检查或未进行的主观试听包装成逐像素复刻或完整发行验收。
