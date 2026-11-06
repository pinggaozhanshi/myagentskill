# myagentskill

我自己的 Agent 技能包仓库。收的是做自媒体内容时反复用得上、并且已经跑通过几轮真实项目的**工作流**：
不是提示词合集，是「入口文档 + 分轮参考 + 可执行脚本 + 验证记录」的完整包。

每个包都能独立落地：Agent 读得懂，脚本跑得起来，出过的错记在里面。

## 里面有什么

| 包 | 做什么 | 入口 |
|---|---|---|
| [pv-redraw-localization](agent插件/pv-redraw-localization/) | 动画 PV 的人物替换/重绘、缺姿势增绘、稳定合成、烧录歌词本地化、音轨替换与编码验收 | [SKILL.md](agent插件/pv-redraw-localization/SKILL.md) |
| [ace-vocal-tuning](agent插件/ace-vocal-tuning/) | 以原唱为参考的 ACE Studio 合成人声调教：谱面核对、时值、音高曲线、音节结尾、盲听、混音交付 | [SKILL.md](agent插件/ace-vocal-tuning/SKILL.md) |

两个包的压缩包也在 `agent插件/` 下（`*_20261106.zip`），适合整包下载后丢进技能目录。

## 怎么用

**方式一：让 Agent 直接读。** 把 `SKILL.md` 的路径给它，一句话说清任务：

> 请先读 `agent插件/ace-vocal-tuning/SKILL.md`，用这套流程调教《曲名》的副歌段：洛天依，日语原词。
> 素材在 `<位置>`。先跟我确认要确认的事，再建工程、做基线和各轮，最后给音量对齐的盲听包。

`SKILL.md` 里有一张路由表，按要做的事指向对应的 `references/` 文档，不用一次读完全部。

**方式二：装成技能。** 把整个包目录放进宿主的技能目录。支持 Agent Skills 格式的宿主可自动发现；
Codex 可以显式调用 `$pv-redraw-localization`、`$ace-vocal-tuning`。自动发现取决于宿主实现，读取能力和工具能力是两件事——
包能被读，不代表宿主就能操作 ACE Studio 或视频编码。

## 约定

- **只放做法，不放素材。** 仓库里没有原视频、音频、人物原画、字体、模型权重、工程文件或账号凭据。
- **案例数字不是默认值。** 文档里出现的 BPM、帧号、音符序号、电平差、具体路径，都是当时那首歌、那个源片的实测记录。
  照用的是规则和阈值，换新素材要重新量。
- **规则先定死。** 所有包都是这个路子：阈值和改法在运行前写好，不看结果回改规则；退步就照实记。
- **验证记录留着。** `evidence/` 里是这个包在真实项目上跑出来的结果，包括失败和没被采纳的尝试。

## 目录

```
agent插件/
├─ README.md                 两个包的索引
├─ pv-redraw-localization/   PV 重绘与本地化
│  ├─ SKILL.md / AGENTS.md   入口与路由
│  ├─ references/            分主题的方法与实测
│  ├─ scripts/pv_tools.py    帧区间、tick 换算、音轨 lag、码流核查
│  ├─ templates/             项目清单模板
│  └─ evidence/              验证范围与行为测试
└─ ace-vocal-tuning/         ACE 人声调教
   ├─ SKILL.md / AGENTS.md   入口与路由
   ├─ references/            各轮的方法、量法、限度
   ├─ scripts/               通用工具（复制进项目、配 project.json 使用）
   ├─ templates/             新项目骨架
   └─ evidence/              验证记录与回归用例
```

新增包沿用同样的结构：入口 `SKILL.md`、参考 `references/`、脚本 `scripts/`、模板 `templates/`、记录 `evidence/`、打包校验 `MANIFEST.json`。
