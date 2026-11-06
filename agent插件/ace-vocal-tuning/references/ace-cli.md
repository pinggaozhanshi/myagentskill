# ACE Studio 命令行：用法与坑

本机现在是 ACE Studio 2.1.9 + acestudio-cli 0.18.7（2026-10-24 `acestudio-cli --version`）。前三次试验在 2.1.8 + 0.17.0 上做，
《绯红》在 2.1.9 + 0.18.7 上做；下表两个版本都用过的命令写法相同，标“0.18 起”的只有新版有。
语法以 `acestudio-cli help <命令>` 为准（ACE 没开时 help 也能看），版本变了先查 help，不要照抄旧参数。
所有调用经 `scripts/ace.py` 的 `cli()`：参数列表直传（不经 shell）、加 `--json`、记进 `work/ace_calls.jsonl`。

## state 文件

`ace_build.py` 写出 `ace_state_r0.json`，后面所有脚本都靠它找轨道和片段：

```json
{"project": {"savedPath": "…/ace/r0_baseline/r0_baseline/r0_baseline.acep"}, "vocal_track_uuid": "{…}", "track_index": 0,
 "clip_uuid": "{…}", "clip_begin": 93839, "clip_end": 141519, "note_count": 107, "inst_track_uuid": "{…}", "ref_track_uuid": "{…}"}
```

- 第二条人声轨同名加 `second_`；`ace_readback.py`、`ace_export.py`、`param_read.py` 加 `--second` 读它。
- 另存为新一轮工程后，轨道、片段 UUID 不变，只换工程路径：`state_with_project.py`。

## 用到的命令

| 命令 | 用途 | 注意 |
|---|---|---|
| `project dirty` | 动手前查状态：`dirty`、`isTempProject`、`projectPath` | 有未保存改动就停（`ace.require_safe_project`） |
| `project new` / `save-as <绝对路径>` / `save` / `open <路径>` | 建、存、切换工程 | `save-as` 会再套一层同名文件夹；`open` 遇到未保存改动会拒绝。**不要加 `--discard-changes`**（例外见下） |
| `tempo set --points '[{"pos":0,"value":220}]'` | 单一速度 | 谱面的 tick 与 ACE tick 一一对应（480 / 四分音符） |
| `track create --type sing --name …` | 建人声轨 | 返回 `trackUuid`、`trackIndex` |
| `voice load --track-uuid … --source singer:18` | 装洛天依 | 洛天依在 ACE 里只有 Verse23（V1） |
| `track set-language --track-uuid … --language Japanese\|Chinese` | 轨道语言 | 决定 G2P |
| `clip create --type sing --track-index … --pos <tick>t --dur <tick>t --name … --notes '<json>'` | 一次写入全部音符和歌词 | 音符 `pos` 是片段内 tick；返回 `clipUuid`、`clipBegin`、`clipEnd`、`noteCount` |
| `import file --path <绝对路径> --pos 0t` | 伴奏、参考人声放到 0 s | 参考人声轨随后 `track set --mute true` |
| `clip note-content --track-index … --clip-index 0` | 读回音符（`pos`、`dur`、`pitch`、`lyric`、`noteUuid`） | 和谱面逐项比 |
| `phoneme g2p --language … --grapheme <字> …` | 不看上下文的读音 | 多音字要自己按语境核对 |
| `phoneme list --clip … --range-begin …t --range-end …t --with-timings[=durations]` | 读回音素；`=durations` 带辅音时长（`durationSec`、`effectiveDurationSec`） | 「-」延长音没有自己的音素行；V1 的 span 恒为 not-synthesized，**不能当“已合成”的判据** |
| `phoneme set-consonant-timing --note <uuid> --index <i> --length 40.0ms` | 第 1 轮、音节结尾轮改辅音长度 | V1 只有辅音长度，没有音素时长编辑。前一个音只有元音时，后一个音常报 `PHONEME_TIMINGS_UNAVAILABLE`（“先合成”），合成后也不开放：改为离线改工程里那个音的 `headConsonants`（`patch_consonants.py`） |
| `phoneme set --note <uuid> --phoneme h uan` | 覆盖一个音的读音（多音字读错时） | 音素名用 ACE 的完整写法（`phoneme inventory --language Chinese` 可查，如 uan、uei、iou、e）；延长音「-」不收（它没有自己的音节，改前一个音）；覆盖存进工程，重开不丢，读回 `isOverride: true`；`phoneme reset-override` 撤销 |
| `note resize --note-uuid … --dur <tick>t` | 改句尾释放（音符终点） | 不与后一个音重叠 |
| `note set-grapheme --note-uuid … --lyrics '["呐"]' --language CHN` | 交付后改歌词（语言代码 `CHN`、`JPN`、`ENG`、`SPA`、`KOR`；不给就不改音符的语言） | **命令行不收空歌词**（"A lyric cannot be empty"），延长前一个音用「-」，效果和用户在 ACE 里清空歌词的“空音符”一样 |
| `fx list` / `fx disable --track-uuid … --instance …` | 停用人声轨默认效果链（Vocal EQ、Little Compressor、Little De-Esser、Little Reverb） | 用 disable，不是 bypass；基线和各轮同样处理 |
| `transport seek --time <秒>s` / `play` / `state` / `stop`、`project synthesis-status` | 触发并等待合成 | 见下面“合成” |
| `convert tick-to-time --tick …` | tick → 秒 | 片段起点秒数（写音高曲线、导出时间轴用） |
| `export audio --path <绝对路径> --scope tracks --track-uuid … --from <tick>t --to <tick>t --sample-rate 48000 --bit-depth 24 --channels 1 --wait` | 导出单条人声轨干声 | 导出成功不等于有声音：检查非静音比例（`ace_export.py` 低于 20% 就报错） |
| `vocalparam read --clip-uuid … --param energy\|tension\|air\|falsetto --encoding base64` | 读 V1 表情参数：`baseline`（AI 值）、`envelope`（倍率）、`direct`（绝对值覆盖）、`effective`（最终值），另有 `fingerprint`、`unvoiced` | `param_read.py` 存成 npz |
| `vocalparam write … --layer envelope\|direct --pos-begin … --points @<file> --encoding base64 --if-match <fingerprint> --wait-busy 60s` | 写参数 | `--if-match` 防止和界面里的手动改动撞车；写完逐 tick 读回（两端各 2 tick 除外） |
| `generative stem-splitter --clip-uuid … --mode basic [--remove-reverb true] --wait` | 分离人声 / 伴奏（云端，基础模式不扣点数） | 返回值不带分出来的轨的 UUID；分轨文件在分离工程的 `Samples/Processed/*.ogg`，用 `stems_collect.py` 按生成时间认领 |
| `generative vocal-to-midi --clip-uuid <音频片段> --language japanese\|chinese\|english\|notes-only --apply-pitch false --wait` | 没有谱面时从去混响人声出初稿（`ace_v2m.py`，免费） | 语言必填、不会自动判断；`--apply-pitch false` 要干净的音符。结果落在新的 Sing 轨上，用 `clip list --track-uuid` 找片段、`clip note-content` 读音符。音高准、音节只对约 75%（见 `score-and-reference.md`） |
| `clip list --track-uuid …` | 列一条轨的片段（`clipUuid`、`clipType`、`clipBegin`） | 找分离出来的人声片段、Vocal to MIDI 的结果 |
| `tempo analyze --file-path …` → `tempo get-analysis --id …` | 节拍分析：拍点、强拍、速度 | 《绯红》用它定 BPM（101.99 → 拟合 101.998，用 102）和第 0 小节；`tempo apply-beat-analysis` 会移动内容，调教不用 |
| `vocalpitch write --clip-uuid … --points @<file>`（0.18 起） | 在线写用户音高曲线（`round2_pitch_online.py`、`endings_apply.py`） | 点是 `[[片段内 tick, 绝对半音], …]`，严格递增；段与段之间放 `[tick, null]` 断开。读回逐点相同，断开标记被存到两段之间的中点（核对时别按 tick 严格比）。**副作用**：写入时把 ACE 当时自己的有声 / 无声判断固定在曲线下（只填还没固定的地方） |
| `vocalpitch read --clip-uuid … --level user\|ai\|combined\|final`（0.18 起） | 读音高：`user` 是画的曲线（锚点），`ai` 是渲染出来的 AI 音高 | `user` 以外是逐 tick 的稠密数组；`final` 里无声处是数字 0，不要当成音高 |
| `vocalpitch voicing` / `vocalpitch set-voicing --begin 0 --end <片段长度> --mode auto`（0.18 起） | 查看 / 清掉有声、无声的固定 | 写完曲线、改完辅音后清成 `auto`，读回 spans 应为 0（`ace_dump.py voicing` 存 JSON）。没有曲线的地方写固定会被拒绝 |
| `history list` | 撤销记录（谁、做了什么） | 判断未保存改动是不是自己造成的 |

## 合成（渲染）怎么触发、怎么判断完成

- 本机流程是**播放触发**（`ace_render.py`）：
  1. 记下伴奏轨原来的静音状态，然后把伴奏静音；
  2. 确认人声轨没被静音；
  3. 从片段起点播放；
  4. 等播放头越过片段终点、且 `synthesis-status` 不在合成；
  5. 停止，恢复伴奏原来的静音状态。
- 只有“听得见”的轨才会合成：被静音的轨、有别的轨独奏时，都不会渲染。没声音先查静音 / 独奏。
- turbo 模式 + 预渲染时编辑本身就会触发渲染；没有预渲染时由播放触发。不管哪种，导出前都按上面的流程走一遍。

### 成品导出前“重开”工程（原因见下面第 4 条）

1. `acestudio-cli project dirty --json`：有未保存改动先弄清是谁的（`history list`）；是自己的就 `project save`，是用户的就停下问。
2. `acestudio-cli project new --json`：切到一个空的临时工程（已保存的那个工程文件不受影响）。
3. `acestudio-cli project open "<rN.acep 的绝对路径>" --json`：重新打开。`open` 遇到未保存改动会报 `UNSAVED_CHANGES` 拒绝，**不要加 `--discard-changes`**。
4. `ace_render.py` → `ace_export.py --disable-fx`（state 里的轨道、片段 UUID 不变）。

刚离线改过的文件（`patch_pitch`、`patch_params`、`patch_consonants`）：在 ACE 里打开 → `project save` 让 ACE 自己写一遍 → 再按 2、3 步重开 → 渲染导出。
《妄想感傷代償連盟》的交付版就是“离线写完、第一次打开就渲染”的，之后每次重开都和它对不上（推测 ACE 保存时重写了曲线，未查证）。
《绯红》r3 也是离线补丁后第一次打开就导出的：以后要局部修改，先重开渲染一次，和那次导出比，看能不能逐采样对上。

## ACE 的几条行为（四次试验实测）

1. **按片段重新生成**：改任何一个音符、歌词、辅音长度，整个片段的 AI 音高和 AI 参数都会重算。
   - 第 1 轮只改辅音，周边乐句的 AI 音高也变了：r0→r1 逐帧中位差 22 音分，32% 的帧差 > 50 音分。
   - 所以第 1 轮的 A/B 不是纯时值对比；“基线 vs 最终调教版”不受影响。
2. **AI 参数不存进工程**：任何编辑都会让附近约十几秒的 AI 参数重算，数值会变。
   - 例：只在张力包络上写一段不改值的 1.0，力度的 AI 曲线就在约 17 秒范围内变了。
   - 参数轮必须先把四个参数都锁成绝对值曲线。
3. **direct 层只收 ≥ 0.3 的张力 / 假声**，而 AI 自己的值 65–73% 低于 0.3。
   - 锁定只能离线写工程的 `realTension` / `realFalsetto`（`patch_params.py`）；
   - ACE 能正常读，读回最大相对差 2×10⁻⁴。
4. **重开工程再渲染，结果会变**：交付版是“离线写完、ACE 第一次打开就渲染”的；同一工程一点不改、重开再渲染，副歌各音电平差 p90 1.5 dB、最大 8.7 dB。
   - 之后各次渲染彼此逐采样相同；把参数锁回去也回不到第一次的结果。
   - 对策见 `revisions.md`：成品导出前先保存、重开、再渲染；交付后的修改只拼接改动乐句。
5. **离线写出的工程**，ACE 可能当临时工程打开。渲染脚本切换静音会让它变成“未保存”。
   - 只有撤销记录里全是脚本自己的“设置轨道静音/独奏”（执行者“远程控制”）时才可以 `--discard-changes`；
   - 否则停下（见 `examples/pocket_singer_反乌托邦/round3_calib_locked.py` 的 `release_and_open`）。
   - 用户的改动永远不丢。
6. **辅音默认很长，会吃掉前一个元音**（《绯红》，日语）：清辅音默认 80–157 ms，原唱（VOCALOID）只提前 0–51 ms。
   102 BPM 的十六分音符只有 147 ms，下一个音的辅音一提前开始，前一个音的元音尾巴就变成嘶声或闭塞：原唱在唱、合成无声的帧合计 1335 ms。
   第 1 轮只改“测得到前一个元音结束”的地方，元音整个没了就测不到。对策是音节结尾轮（`round-endings.md`）。
7. **很短的休止会被唱过去**（《绯红》第 1 轮）：促音后 147 ms 的休止，按句尾释放规则把前一个音延长 24 tick 后只剩 118 ms，
   ACE 就把元音一直唱到下一个辅音，停顿从 135 ms 变成 10 ms（原唱 90 ms）。改回原时值后恢复到 140 ms。促音休止前的音不做延长释放。
8. **乐句结尾硬切**（ACE 2.1.9）：5 处乐句结尾在比乐句电平低 11–18 dB 时 10 ms 内掉到数字静音，原唱是 30–60 ms 的平滑衰减；改工程改不掉。
   2.1.8（《妄想感傷代償連盟》）休止里有 −50～−60 dB 底噪，没见过。混音时在掉落点前加 35 ms 余弦淡出（`mix_vocals.py --end-fade-ms 35`），交付的干声也带上。
9. **在线写音高会固定有声 / 无声**（0.18 的 `vocalpitch write`）：《绯红》r2 有 113 段无声被固定，其中 36 段、约 2 s 是原唱在唱的地方。
   之后再缩短辅音，固定的无声段仍把元音压成无声；最后一步一定是 `set-voicing --mode auto` 清掉。

## 离线改 `.acep`（LibreSVIP 2.9.0）

CLI 0.17 读写不了音高线，锁参数也受 0.3 下限限制，所以前三次试验这两件事都离线改工程文件（0.18 起音高可以在线写，见上表；
锁参数仍要离线）。另外，ACE 不开放时长的辅音也只能离线改（`headConsonants`，`patch_consonants.py`）：

- `decompress_ace_studio_project` 解包 → 改 → `compress_ace_studio_project(…, AcepSerialization.CBOR)` 写回 → 再解包核对：
  1. 改的值逐个一致；
  2. 改动字段以外和源工程逐字段相同。

  两条都满足才算成功，否则删掉输出。
- 片段（pattern）里的曲线是 `{"type": "data", "offset": <片段内 tick>, "values": [每 tick 一个值]}` 的列表：
  - 用户音高：`pitchDelta`，单位半音，相对 `BasePitchCurve`（由音符重建的基础音高）；
  - 绝对值参数：`realEnergy` / `realTension` / `realBreathiness` / `realFalsetto`；
  - 包络：`energy` / `tension` / `breathiness` / `falsetto`，空 = 全 1。
- 音符（`notes`）里的 `headConsonants`：首辅音长度（秒）的列表，V1 一般只有一个值。
- **写的时候这个工程不能在 ACE 里开着**，顺序是：在 r1 上另存 r2 → ACE 切回 r1 → 离线写 r2 → ACE 打开 r2 → 读回音符和 r1 一致（`round2_pitch.py`）。
