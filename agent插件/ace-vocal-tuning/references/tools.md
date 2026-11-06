# 工具清单（`scripts/`，按使用顺序）

## 用哪个解释器

| 写法 | 解释器 | 用于 |
|---|---|---|
| `python -I scripts/<x>.py` | 系统 Python 3.13（`C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe`） | 绝大多数脚本。`-I` 隔离模式，`common.py` 把用户 site-packages 加回来、输出改 UTF-8 |
| `python -X utf8 scripts/rmvpe_run.py` | 同上，**不加 `-I`** | RMVPE 音高提取 |
| `<LibreSVIP python> -I scripts/<x>.py` | `C:\Users\lenovo\Documents\自媒体\调教Agent研究\.venv\Scripts\python.exe` | 离线改 `.acep`：`patch_pitch.py`、`patch_params.py`、`patch_consonants.py`（`round2_pitch.py` 会自己调它） |

要连 ACE 的脚本（下表“ACE”列打勾）都经 `ace.py`：ACE 必须开着；动工程前查未保存改动；每次调用记进 `work/ace_calls.jsonl`。

## 文件命名约定（脚本都靠参数传路径，名字可以改，文档按这套写）

```
work/score.json                     谱面（多轨时 score_full.json + score_views.py 拆出的单轨视图）
work/g2p.json                       g2p_check.py 的输出
work/stems/                         分离出的整首分轨（stems_collect.py）
work/f0/ref_praat_full_5ms.npy      去混响参考人声整首的 Praat F0（另有 ref_rmvpe_full_5ms.npy）
work/ref/ref_vocal_clip_48k.wav     参考人声按片段截好（make_reference.py；另有 inst_clip_48k、ref_vocal_mix_clip_48k、official_clip_48k）
work/f0/<版本>_praat_5ms.npy        各轮导出干声的 F0（另有 _rmvpe.json、_rmvpe_5ms.npy）
work/ace_state_r0.json …            各轮的 ACE 状态
exports/<版本>/                     各轮干声导出：ace_export.py 写 <out_dir>/<label>_<轨道名>.wav（例：exports/r0_baseline/r0_baseline_洛天依_主唱.wav）
```

## 准备：素材、谱面、参考

| 脚本 | ACE | 做什么 |
|---|---|---|
| `ace_split.py` | ✓ | Stem Splitter 基础模式分离两次（原样、去混响）；要用户同意上传 |
| `stems_collect.py` | | 从分离工程认领分轨、解码成 48 kHz / 24-bit WAV |
| `ace_v2m.py` | ✓ | 没有谱面时：Vocal to MIDI 出音符初稿（音节只对约 75%，要人工核对） |
| `extract_ust_zip.py`、`ust_inspect.py` | | 解压 UST 压缩包（Shift-JIS 文件名）、读成 JSON |
| `align_ust.py` | | 求谱面 tick 0 落在官方音轨第几秒（音高轮廓 × 参考 F0，分三段） |
| `tempo_fit.py` | | ACE 节拍分析的拍点 → 拟合 BPM、候选 BPM 下的残差和前中后三段漂移、第一个强拍 |
| `vocal_sections.py` | | 按小节看分离人声的有声比例，定段落和试验区间 |
| `f0_grid.py` | | 任意 wav → Praat F0（5 ms）；`--rmvpe` 把 RMVPE 的 JSON 换成同一网格 |
| `rmvpe_run.py` | | RMVPE 音高提取（10 ms 一帧） |
| `make_reference.py` | | 参考人声、伴奏按片段截成和 ACE 导出同起点同长度 |
| `note_check.py` | | 谱面 vs 参考 F0：八度候选、错音候选、整体时间偏移 |
| `hamo_check.py`、`score_views.py` | | 和声谱面核对；多轨谱面拆单轨视图 |

建谱面本身（UST / USTX / Pocket Singer / Vocal to MIDI → `score.json`）每首不同，照 `scripts/examples/` 写。

## 基线 r0

| 脚本 | ACE | 做什么 |
|---|---|---|
| `ace_build.py` | ✓ | 新建工程：速度、洛天依、语言、音符；伴奏和参考人声（静音）放在 0 s；写 `ace_state_r0.json` |
| `g2p_check.py` | ✓ | ACE 自己的 G2P 逐音读一遍（不看上下文；「-」不送） |
| `ace_readback.py` | ✓ | 读回音符、歌词、音素，与谱面逐项比；读音逐字过一遍 |
| `ace_render.py` | ✓ | 播放触发渲染并等完成 |
| `ace_export.py` | ✓ | 导出人声轨干声（`--disable-fx` 停用默认效果链），检查非静音比例 |
| `state_with_project.py` | | 另存新一轮后复制 state，只换工程路径 |

## 第 1 轮：时值

| 脚本 | ACE | 做什么 |
|---|---|---|
| `timing_voicing.py` | | 用有声 / 无声边界量“前一元音结束 → 本字元音到达”（参考和合成各一次） |
| `round1_timing.py` | ✓ | 按规则 A–D 生成计划；`--skip` 人工排除个别音；`--apply` 另存 r1 并改辅音长度、句尾释放 |
| `compare_timing.py` | | 两轮对比：被改的音更近 / 更远，没改的音有没有被带动 |
| `round1_mirror.py` | ✓ | 和声轨照抄主唱的辅音长度和释放 |

## 第 2 轮：音高

| 脚本 | ACE | 做什么 |
|---|---|---|
| `repeat_phrases.py` | | 写目标前先跑：列出谱面里歌词、时值、音程都相同的句子（可移调），标出哪一次没被别的声部盖着 |
| `build_target_f0.py` | | 参考 F0 → 目标音高（两提取器取近、折回八度、补洞、去尖刺、中值） |
| `build_harmony_target.py` | | 和声目标 = 主唱目标 + 音程 |
| `target_check.py` | | 写音高前的八度 / 错音检查（规则同 `patch_pitch.py`，基准用音符音高）；`round2_pitch_online.py` 会自己调用 |
| `round2_pitch_online.py` | ✓ | 在线写（CLI 0.18 起）：先过 `target_check`，另存 r2、可选 `--revert`、`vocalpitch write`、逐点读回 |
| `round2_pitch.py` → `patch_pitch.py` | ✓ | 离线写 `pitchDelta`（任何版本；单轨或两轨） |
| `examples/ust_呐呐呐/final_phrase_copy.py` | ✓ | 把模板句的曲线抄到其余重复处（移调、和声折线映射、淡回，整段片段写回，逐点读回）；状态文件是多轨格式，照着改 |
| `examples/ust_呐呐呐/final_phrase_match.py` | | 量每一次重复和模板的音高、电平、包络、频谱距离 |
| `pitch_eval.py` | | 音高误差、逐音好 / 差、颤音叠加 |
| `glitch_check.py` | | 断声、音高曲线断点 |

## 第 2 轮之后：结尾检查与音节结尾轮

| 脚本 | ACE | 做什么 |
|---|---|---|
| `vowel_coverage.py` | | 原唱在唱、合成没声音的帧（按音符） |
| `ace_dump.py` | ✓（只读） | 存 `phoneme list --with-timings=durations` 或 `vocalpitch voicing` 的 JSON |
| `voicing_check.py` | | 被固定成无声、原唱却在唱的段（= 被吃掉元音尾巴的音） |
| `ending_check.py` | | 每个露出来的结尾：结尾时间差、ACE 自己音高的尾巴、衰减 |
| `endings_plan.py` | | 规则 E（辅音按原唱提前量缩短）、F（音高曲线补全） |
| `endings_apply.py` | ✓ | 改辅音 → 写补全曲线 → 清固定（G），逐步读回 |
| `voicing_clear.py` | ✓ | 不做音节结尾轮时，把在线写音高留下的有声 / 无声固定清成 auto，读回 0 段后保存 |
| `patch_consonants.py` | | 离线改 ACE 不开放时长的辅音（`headConsonants`；LibreSVIP 解释器） |

## 第 3 轮（可选）：表情参数

| 脚本 | ACE | 做什么 |
|---|---|---|
| `param_read.py` / `param_write.py` | ✓ | 读 / 写 V1 四个参数（包络、direct 层） |
| `patch_params.py` | | 离线把四个参数锁成绝对值曲线（`real*`；LibreSVIP 解释器） |
| `voice_features.py` | | 逐帧特征：响度、明暗、高频、H1−H2、谐噪比 |
| `crisp_metrics.py` | | “干脆”指标：起音、收音、音间断开、长音尾部、亮度 |
| `ltas_compare.py` | | 长期平均频谱对比（亮度差在哪些频段） |

标定、求解、写入的编排每首不同，照 `examples/pocket_singer_反乌托邦/round3_*.py` 和 `examples/ust_妄想感傷代償連盟/r3_*.py`。

## A/B、混音、交付、修改

| 脚本 | ACE | 做什么 |
|---|---|---|
| `make_ab.py` | | 音量对齐的 A/B、带伴奏试听、随机盲听包（答案写进 key 文件） |
| `eq_brighten.py`、`sibilance_check.py` | | 可选的 EQ 提亮试验和齿音检查（盲听两对都没选提亮） |
| `mix_vocals.py` | | 成品混音（主唱 + 可选和声 + 伴奏），带结尾淡出、伴奏电平、区间选项 |
| `mix_check.py` | | 成品混音检查：各段人声对伴奏、原唱残留、开头 2 秒、总览图 |
| `splice_main.py` | | 交付后的局部修改：只把改动的乐句换进交付版 |
| `examples/ust_呐呐呐/final_splice.py` | | 多轨版拼接：按轨列改动的音，接口落在休止里两版都最安静的位置 |

## 回归验证

`evidence/regression/run_regression.py`（《妄想感傷代償連盟》数据）和 `run_regression_feihong.py`（《绯红》数据）：
原版脚本和本目录的通用版各跑一遍逐项比；要连 ACE 的脚本接 `fake_ace_cli.py`。改了 `scripts/` 里任何东西都重跑这两个（结果见 `evidence/validation.md`）。
