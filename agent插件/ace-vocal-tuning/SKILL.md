---
name: ace-vocal-tuning
description: Use when tuning a vocal-synth cover in ACE Studio (Luo Tianyi / 洛天依 V1 by default) against a reference performance through acestudio-cli — building the project from a UST, USTX, Pocket Singer or Vocal-to-MIDI score, measuring and fixing consonant timing, writing the reference pitch curve, checking and fixing syllable endings, optional expression parameters, level-matched blind tests, mixing, delivery and post-delivery revisions. 适用于以原唱为参考、用 ACE 命令行和信号检查调教洛天依翻唱：谱面与读音核对、时值、音高曲线、音节结尾、可选的表情参数、音量对齐盲听、混音交付和交付后修改。
---

# ACE 人声调教（以原唱为参考）

把原唱当尺子：每一轮只改一类东西，改法在运行前写成规则，用信号检查抓错、量和原唱的距离；
哪个版本更好，只由用户的音量对齐盲听决定。ACE Studio 全部经 `acestudio-cli` 操作（ACE 必须开着）。
方法来自四次翻唱试验（2026-10-18 至 10-24，洛天依 Verse23 / V1，中文一首、日语三首），工具在 `scripts/`，回归验证见 `evidence/validation.md`。

## 按任务读取

| 要做的事 | 读 |
|---|---|
| 第一次用、装环境、建新项目、先问用户什么 | [setup.md](references/setup.md) |
| 谱面从哪来、定网格、选参考人声、读音和歌词 | [score-and-reference.md](references/score-and-reference.md) |
| ACE 命令行用法、渲染、离线改工程、实测的坑 | [ace-cli.md](references/ace-cli.md) |
| 第 1 轮：辅音长度和句尾释放 | [round1-timing.md](references/round1-timing.md) |
| 第 2 轮：写原唱的音高曲线 | [round2-pitch.md](references/round2-pitch.md) |
| 第 2 轮之后：结尾检查和音节结尾轮 | [round-endings.md](references/round-endings.md) |
| 第 3 轮（可选）：力度、张力、气声、假声 | [round3-expression.md](references/round3-expression.md) |
| 评估指标、A/B、盲听、门槛 | [evaluation-and-blind-test.md](references/evaluation-and-blind-test.md) |
| 和声、齐唱、重叠句 | [harmony.md](references/harmony.md) |
| 混音、交付清单 | [mix-and-delivery.md](references/mix-and-delivery.md) |
| 用户听完要改 | [revisions.md](references/revisions.md) |
| 原创曲（没有原唱） | [originals.md](references/originals.md) |
| 看到某个症状，查原因 | [lessons.md](references/lessons.md) |
| 脚本清单、解释器、文件命名 | [tools.md](references/tools.md) |

各篇里的数字是那几首歌的实测，不是新歌的默认值；规则（阈值、上限）才是要照用的。

## 执行步骤

0. **开工前**：和用户确认曲目与试验段、歌词语言、每样下载、云端上传（Stem Splitter）、谁开 ACE；`acestudio-cli --version` 看版本，
   版本变了先读 `help`。建项目目录、`git init`、复制 `scripts/` 和 `templates/`、填 `project.json`（`setup.md`）。
1. **素材**：官方音轨和谱面存一份，SHA-256 和条款记进来源台账。
2. **参考人声**：官方清唱 > 官方音轨 − 伴奏 > Stem Splitter 分离（量音高、时值只用去混响那组；原样那组只定混音电平）。
3. **谱面**：读成 `score.json`；用两类证据定 BPM 和偏移并冻结；`note_check.py` 查八度、错音、整体偏移。
   没有谱面时用 Vocal to MIDI 出初稿，音节必须对官方读音逐拍对齐。
4. **基线 r0**：`ace_build.py` → `g2p_check.py` → `ace_readback.py`（读音逐字核对，多音字用 `phoneme set` 覆盖）→ `ace_render.py`
   → `ace_export.py --disable-fx` → Praat、RMVPE 两种 F0 → 量时值和音高。
5. **第 1 轮 时值**：`timing_voicing.py` 量 → `round1_timing.py` 出计划 → 人工看句尾释放（促音、短休止前不延长，用 `--skip` 排除）→ `--apply`
   → `state_with_project.py` 用打印的 savedPath 写 `ace_state_r1.json` → 渲染导出 → `compare_timing.py`（停顿有没有被唱过去也要看）。
6. **第 2 轮 音高**：`repeat_phrases.py` 列重复句、挑模板 → `build_target_f0.py` → `round2_pitch_online.py`（CLI 0.18 起，写前自动过 `target_check.py`）或 `round2_pitch.py`（离线）
   → 读回 → 渲染导出 → `pitch_eval.py`、`glitch_check.py`。被和声盖着的重复句抄模板的曲线（`round2-pitch.md` 的“重复句”）。
7. **结尾检查**：`vowel_coverage.py`、`voicing_check.py`、`ending_check.py`；超过触发线就做音节结尾轮（`endings_plan.py` → `endings_apply.py`），
   没超线也要 `voicing_clear.py` 清掉在线写音高留下的固定。
8. **盲听**：`make_ab.py` 出干声对（−20 LUFS）和带伴奏试听（人声按原曲人声的总电平）；基线和调教版随机甲乙，答案在用户回答前不读；
   原话记进报告。干声盲听调教版胜才算试验段通过，再推广到整段、整首。
9. **第 3 轮**只在用户提出具体听感时做：先锁四个参数，标定后小步改，单独盲听，选中才进成品。
10. **成品**：保存 → 重开 → 渲染导出；`mix_vocals.py`（不提亮；翻唱显式传 `--inst-db -4`，另出 `-7` 的备选；ACE 2.1.9 加 `--end-fade-ms 35`）
    → `mix_check.py` → 交付 WAV、MP3、干声、人声总线、校验值和说明（写明哪些没有人耳确认）。
11. **修改**：照抄用户原话、写清理解；从交付工程另存新一轮；只拼接改动的乐句（`splice_main.py`）；新版本另起文件名。
12. **每个阶段**提交 Git（计划、脚本、决定、校验值；音频、ACE 工程、导出、含歌词的谱面不进 Git）。交接时写明 ACE 里开着哪个工程、是否已保存。

## 验证过的判断

- **规则先定死**：阈值、上限、改哪些音在运行前写好，不看结果改规则；退步的音照实记，不偷偷回改。
- **一轮只改一类东西**，每轮一个独立工程（`ace/r0_baseline`、`r1_timing`、`r2_pitch`…），基线永不覆盖。
- **音高曲线收益最大**：误差中位 63 → 5、33 → 3.3、18–20 → 2.7–3.2、25 → 2.9 音分；三次盲听调教版都胜。
- **重复句用一条曲线**：VOCALOID 原唱的重复句常是同一条曲线复制的，挑没被和声盖着的那次当模板抄过去。《呐呐呐》用户听出 7 处里只有独唱的开头像原唱，其他 6 处的 3 半音上滑被“离谱面太远就不用”的保护规则切了。大滑音是辨识度，不是噪声。
- **“离目标几音分”不能证明目标对**：v2 是 3 音分，目标却是错的。同谱面的句子要互相比。
- **时值的方向因语言而异**：《反乌托邦》中文清声母偏短要拉长，三首日语清辅音偏长要缩短。不要预设。
- **ACE 改任何东西都重算整个片段**的 AI 音高和参数；AI 参数不存进工程。所以第 1 轮的 A/B 不是纯时值对比，参数轮必须先锁定。
- **去混响分离当尺子**：原样分离的人声带混响、叠着低八度，67% 的帧落到低八度。
- **“更接近原唱”不等于“更好听”**：调教版照搬了原唱的滑音习惯，换到洛天依身上自然不自然只能靠用户听。
- **表情参数轮两次都没赢 r2**：《反乌托邦》被听出“沙哑”，《妄想感傷代償連盟》“差别很小”。默认不做；做就先锁四个参数，气声不超过 ×1.2。
- **不提亮**：三次盲听都选不加工的版本。
- **翻唱人声要比原曲比例更靠前**：《绯红》按原曲比例混，用户说“音乐有点响”；v2 伴奏再降 4 dB，另给 −7 dB（用户还没选）。
- **重开工程再渲染会变**（p90 1.5 dB、最大 8.7 dB），锁参数也回不去：成品导出前先保存、重开、再渲染；交付后只拼接改动的乐句。
- **快歌里 ACE 的辅音会吃掉前一个元音**（默认 80–157 ms，原唱 0–51 ms），第 1 轮测不到：第 2 轮之后一定跑结尾检查。
- **在线写音高会把当时的无声判断固定住**：音节结尾轮的最后一步清成 auto。
- **读音只能靠读回确认**：G2P 不看上下文（多音字逐个核）；Vocal to MIDI 的音节只对约 75%。
- **两人合唱按两人的总电平放人声**；同一歌手的齐唱只唱一遍。
- **用户的未保存改动永远不丢**：从开着的工程另存为新工程带过去；不替用户保存，也不丢弃。

## 交付状态

每份报告写明到了哪一步：谱面核对通过 → 基线导出 → 各轮信号检查通过 → 结尾检查通过 → **用户盲听通过** → 成品混音 → 交付 → 修改中。
我们听不见：信号检查通过不等于好听，没做盲听就不说“通过”；没听过的地方写“没有人耳确认”，不声称试听过。
工具或权限不够时，照样完成能做的部分，如实写出剩下什么。

## 和其他技能的关系

- `中文术曲创作技能库/skills/tuning-chinese-synth-vocals`：通用的中文合成人声调教顺序（读音 → 时值 → 音高 → 表情）和门槛，没在 ACE 命令行上验证过。
  本包是以原唱为参考、带工具和实测的做法；两者不同时以本包为准（例如本包第 2 轮写整条原唱曲线、表情轮默认不做）。
  原创曲没有原唱时，那份技能的“有具体缺陷才改”更适用（见 `originals.md`）。
- `调教Agent研究/skills/ace-syllable-timing`：资料整理阶段的研究草稿，没有经过试验。
- ACE 官方插件 `acestudio` 的 skills（功能、工作流、音频插件）：操作 ACE 前读；本包只写调教本身。
