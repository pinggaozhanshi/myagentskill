# 示例脚本（和具体歌绑定，不能直接用）

这些脚本从各次试验里原样拷来，用来照着写新歌自己的版本。它们 `import common` 时用的是**原项目**的常量
（速度、tick 换算、写死的音符序号和路径），放进新项目前要改。通用工具在上一级 `scripts/`，那些可以直接用。

## `ust_呐呐呐/`（日语，UST 谱面，双人齐唱 + 和声，145 BPM，ACE 2.1.9 / CLI 0.18.7）

| 脚本 | 做什么 | 新歌要改什么 |
|---|---|---|
| `final_phrase_copy.py` | 把模板句的音高曲线抄到其余重复处：移调、和声按音高折线映射、结尾淡回，整段片段写回，逐点读回，最后清固定（方法见 `references/round2-pitch.md` 的“重复句”） | 状态文件是多轨格式（`tracks[].clips[]`）；spec 里的模板和各处 tick |
| `final_phrase_match.py` | 量每一次重复和模板的音高、电平、包络、频谱距离 | spec 里的模板和各处 tick；移调的句子频谱距离不可比 |
| `final_splice.py` | 多轨拼接：只把含改动音的整串音换进上一版干声，接口落在休止里两版都最安静的位置，读回校验 | 输出文件名里写死的 `r5_`；用于 2.1.9（休止是数字静音） |

## `v2m_绯红/`（日语，没有公开谱面，Vocal to MIDI 出初稿，102 BPM，ACE 2.1.9 / CLI 0.18.7）

| 脚本 | 做什么 | 新歌要改什么 |
|---|---|---|
| `build_score.py` | Vocal to MIDI 音符（`ace_v2m.py` 的输出）→ 量化到十六分网格 → 逐音对参考音高（Praat / RMVPE），标出 `pitch?` / `octave?` | 网格零点与偏移搜索范围、量化单位、截取区间 |
| `lyric_check.py` | 把每个音的识别音节和官方读音（UtaTen 注音页，只在内存里解析）做半全局对齐，列出不一致；终端只打印音类 | 歌词来源与解析方式；中文歌改成逐字对照 |
| `score_review.py` | 按十六分网格点列出参考人声的音节起点证据（能量凹陷、清音间隙、高频突增、前后音高），人工决定拆音和对位 | 原唱不在网格上时（真人演唱）这套证据要放宽 |
| `vowel_check.py` | 长音核对：官方写成两个元音（o→u、e→i）的地方，原唱是唱出后一个元音还是只拉长（MFCC 近邻投票） | 只用于日语长音 |
| `apply_score_fixes.py` | 套用 `score_fixes.json`（改音节、助词、音高、拆音、促音时值）→ 谱面 v1，并自检：官方每个音节都落在一个音上或写明并入的理由 | 调性检查（写死降 B 大调）、修正内容 |
| `score_fixes.json` | 上面那份修正的格式示例（只有序号，没有歌词） | — |
| `mix_1min.py` | 一分钟版混音：结尾按下一段人声的弱起定、伴奏再降 dB、乐句结尾硬切淡出。通用的 `mix_vocals.py` 已经吸收了这些选项（`--end-at`、`--inst-db`、`--end-fade-ms`），回归验证里两者输出逐字节相同 | — |

## `ust_妄想感傷代償連盟/`（日语，UST 谱面，220 BPM）

| 脚本 | 做什么 | 新歌要改什么 |
|---|---|---|
| `build_score.py` | 从 UST 截出试验段，换到 ACE 时间轴，写单轨谱面 `pilot_score.json` | 截取的音符序号 `MAIN_RANGE` 等、`target=False` 的判断、meta 里的来源说明 |
| `build_score_full.py` | 同上，主唱 + 和声两条轨（`tracks`），带和声改音（`hamo_check.py` 的结果） | 同上 |
| `apply_na_fix.py` | 交付后改歌词：16 个音改「呐」、4 个音改延长音「-」，读回逐音核对，另存新工程 | 要改的音、新歌词、延长音的位置 |
| `ra_fix_check.py` | 改歌词后的核对：各组音的电平、没改的段与对照的差信号、交界处断开深度、辅音段 1–5 kHz 比元音低多少（分辨 n / l） | 分组用的音符序号、对照版本 |
| `mix_diff.py` | 两版成品逐段比较：每段求单一增益后剩下的差信号（只差总增益时很低） | 分段（按音符序号写死） |
| `r3_*.py` | 第 3 轮“干脆”轮：只用力度做音间断开和长音尾部下收的标定、求解、写入、实测校正 | 目标指标、音符分组；方法见 `references/round3-expression.md` |

## `ustx_超级超级超级讨厌/`（日语，USTX 谱面，130 BPM）

| 脚本 | 做什么 |
|---|---|
| `ustx_inspect.py` | 打印 USTX 的速度、拍号、轨道、声部、音符范围。USTX 要用 YAML 1.2（ruamel.yaml）读：PyYAML 会把歌词 `no` 读成 False |
| `extract_pilot_notes.py` | 从指定声部截取试验窗口的音符 |
| `note_corrections.py` | 按定死的规则给出音高修正候选（八度段、单音错音） |
| `octave_probe.py` | 八度判定：比较候选基频 f 的奇次谐波与偶次谐波能量，判断原唱真在 f 还是 2f |
| `build_pilot_score.py` | 截取的音符 + 修正 + 罗马音→假名（UTAU 写法：`a t`→っ、`i n`→ん、`si`→すぃ），写成试验谱面 |

## `pocket_singer_反乌托邦/`（中文，PaiMe 的 Pocket Singer 工程，120 BPM）

| 脚本 | 做什么 |
|---|---|
| `inspect_ps_project.py` | 读 `.ps_project`（WinZip AES 加密的 zip，用 LibreSVIP 2.9.0 的 ps_project 插件），导出内嵌伴奏、转成 `.acep` |
| `export_paime_notes.py` | 把转好的 `.acep` 里的音符和音高曲线导成 JSON |
| `build_score_v2.py` | 两位原唱的谱面怎么排：主旋律轨 + 重叠处的第二声部轨；齐唱只唱一遍 |
| `make_reference.py` | 参考人声 = 官方音轨 − g × 工程内嵌的去人声伴奏（两者对齐到同一个 0 s） |
| `tempo_check.py` | 用伴奏的节拍跟踪核对速度和拍点相位，前后半段分别算，看有没有漂移 |
| `round3_calib_locked.py`、`round3_targets.py`、`round3_lock.py`、`round3_eval.py` | 第 3 轮表情参数（力度、张力、气声、假声）：锁定后标定 → 按音区求倍率 → 锁成绝对值曲线写入 → 测量。方法与教训见 `references/round3-expression.md` |

原项目（脚本的上下文、数据和报告）都还在本机：

- `D:\自媒体\超级超级超级讨厌_天依阿绫PV_20261018\vocal_pilot\`
- `D:\自媒体\反乌托邦_调教试验_20261019\`（`work/` 已被清理过，标定数据只剩文档）
- `D:\自媒体\妄想感伤代偿联盟_调教试验_20261021\`
- `D:\自媒体\绯红_洛天依翻唱_20261024\`（一分钟版 v2 交付后用户还没回复选哪一版伴奏电平）
