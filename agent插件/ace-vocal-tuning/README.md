# ACE 人声调教工作流（以原唱为参考）

入口：[SKILL.md](SKILL.md)。没有技能系统的 Agent 直接读这个文件，按里面的表格读相关参考。

## 怎么调用

给 Agent 的任务提示可以这样写：

> 请先读取 `D:\自媒体\可复用工作流\ace-vocal-tuning\SKILL.md`，用这套工作流调教《<曲名>》的 <段落>：洛天依，<语言>原词。
> 素材在 <位置>。先和我确认需要确认的事，再建项目、做基线和各轮，给我音量对齐的盲听包。

支持 Agent Skills 格式的宿主：把整个 `ace-vocal-tuning` 文件夹放进它的技能目录（Codex 可显式调用 `$ace-vocal-tuning`）。
自动发现取决于宿主；能读文件和能操作 ACE 是两回事，ACE 要开着，命令行才连得上。

## 包含什么

| 文件 | 用途 |
|---|---|
| `SKILL.md` / `AGENTS.md` | 入口：步骤、验证过的判断、交付状态、路由 |
| `references/setup.md` | 先问用户什么、软件环境、项目目录、`project.json`、安全规则 |
| `references/score-and-reference.md` | 谱面来源（UST / USTX / Pocket Singer / Vocal to MIDI）、网格、参考人声、F0、读音 |
| `references/ace-cli.md` | 用到的 ACE 命令、渲染、离线改工程、九条实测行为 |
| `references/round1-timing.md`、`round2-pitch.md`、`round-endings.md`、`round3-expression.md` | 各轮的量法、规则、结果和限度 |
| `references/evaluation-and-blind-test.md` | 信号检查、A/B 与盲听、门槛、四次试验的结果 |
| `references/harmony.md`、`mix-and-delivery.md`、`revisions.md`、`originals.md` | 和声、混音交付、交付后修改、原创曲 |
| `references/lessons.md`、`tools.md` | 症状索引、脚本清单 |
| `scripts/` | 通用脚本（复制进项目，配 `project.json` 用）；`scripts/examples/` 是和具体歌绑定的示例 |
| `templates/` | 新项目的 `project.json`、README、来源台账、谱面决定、调教记录、试验报告、`.gitignore` |
| `evidence/` | 验证记录与回归测试（`regression/` 里有假 ACE 命令行和两套用例） |
| `requirements.txt`、`MANIFEST.json` | 依赖；打包文件的长度与 SHA-256（自身不计入） |

包里没有任何音频、ACE 工程、谱面、歌词、模型权重或账号；它打包的是做法、规则、工具和验证记录。
脚本里写死的本机路径（Python、LibreSVIP、RMVPE 研究目录）在 `project.json` 里都能改。

## 来源和适用边界

从四次洛天依翻唱试验提炼（2026-10-18 至 10-24）：

- 《超级超级超级讨厌》：日语，USTX 谱面，官方清唱；
- 《反乌托邦》：中文，Pocket Singer 工程；
- 《妄想感傷代償連盟》：日语，UST 谱面，Stem Splitter 分离；含完整副歌、和声、三次交付修改；
- 《绯红》：日语，Vocal to MIDI 出谱，ACE 2.1.9。

另有《刷到》原创曲的读音覆盖做法。前三首的盲听都是调教版胜，表情参数和 EQ 提亮都没被选中；
《绯红》的音节结尾轮在信号上有效，用户还没回复。

适用：单一速度、以原唱为参考的洛天依 V1 人声。变速的歌、其他声库或 V2 模型、没有原唱的原创曲，只有部分适用（见各篇的“限度”）。
本包不把信号指标说成听感，也不把案例的数字当默认值。
