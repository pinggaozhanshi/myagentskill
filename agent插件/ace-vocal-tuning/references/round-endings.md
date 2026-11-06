# 音节结尾轮（第 2 轮之后，结尾检查发现问题时做）

来历：《绯红》（日语，102 BPM，ACE 2.1.9）第 2 轮交付成 v1 后，用户说“有些音节的结尾没处理好”。
对照原唱查出四类信号上看得到的问题，按规则改完成为 v2。**用户对 v2 还没有回复（2026-10-24）**，所以这一轮“信号上有效、人耳未确认”。
前三次试验没跑过这些检查，不知道当时有没有同样的问题；以后每首都在第 2 轮之后跑一遍检查。

## 四类问题（《绯红》r2 的数）

| 问题 | 原因 | 怎么查 | r2 |
|---|---|---|---|
| 结尾被下一个辅音吃掉（主要） | ACE 清辅音默认 80–157 ms，原唱只提前 0–51 ms；短音里下一个辅音一提前开始，前一个元音尾巴就变成嘶声、闭塞 | `vowel_coverage.py`：原唱在唱、合成没声音的帧 | 合计 1335 ms，20 个音各缺 ≥ 30 ms |
| 被固定的无声 | 在线写音高（`vocalpitch write`）把写入当时 ACE 的有声判断固定在曲线下，改辅音也解不开 | `ace_dump.py voicing` → `voicing_check.py` | 113 段固定无声里 36 段、约 2 s 是原唱在唱的地方 |
| 结尾交给 ACE 自己的音高 | 音高曲线只写在原唱有声处，合成元音更长的地方没有曲线 | `ending_check.py` 的 tail_ms / tail_dev_c | 8 处尾巴偏 0.5–3.7 个半音 |
| 乐句结尾硬切 | ACE 2.1.9 的渲染行为：比乐句电平低 11–18 dB 时 10 ms 内掉到数字静音 | 混音时 `mix_vocals.py --end-fade-ms` 自动找 | 5 处；改工程改不掉，混音时淡出 |

第一类第 1 轮测不到：它只改“测得到前一个元音结束”的辅音，元音整个没了就没有可测的边界。

## 检查（第 2 轮之后，每首都跑）

```bash
python -I scripts/vowel_coverage.py work/score.json work/ref/ref_vocal_clip_48k.wav work/f0/ref_praat_full_5ms.npy r2=<r2.wav>,<r2_praat_5ms.npy>,<r2_rmvpe_5ms.npy>
python -I scripts/ace_dump.py work/ace_state_r2.json voicing work/r2_voicing.json
python -I scripts/voicing_check.py work/score.json work/r2_voicing.json work/ref/ref_vocal_clip_48k.wav work/f0/ref_praat_full_5ms.npy work/voicing_plan.json
python -I scripts/ending_check.py work/score.json work/g2p.json work/target_f0.json work/ref/ref_vocal_clip_48k.wav <r2.wav> work/f0/ref_praat_full_5ms.npy <r2_praat_5ms.npy> <r2_rmvpe_5ms.npy> work/ending_r2.json
```

- 定义：原唱“唱出来” = Praat 有声且电平不低于所在音符中位 −12 dB；合成有声 = Praat 或 RMVPE 有声且 > −60 dBFS。
- 离线写 `pitchDelta` 的工程没有固定的无声段：`voicing_check` 得到空计划（CLI 0.17 没有 `vocalpitch voicing` 时手写 `{"plan": []}` 给 `endings_plan.py`），
  规则 E 就只按“ACE 的辅音比原唱提前量长 ≥ 30 ms”改。整个音节结尾轮写曲线用的是 `vocalpitch write`，要 CLI 0.18 起。
- 下面任一条成立就做这一轮（《绯红》定的线）：某个音缺 ≥ 30 ms；有原唱在唱却被固定成无声的段；
  结尾 AI 音高尾巴 ≥ 20 ms 且偏 ≥ 50 音分。

## 规则（`endings_plan.py`，运行前定死）

**E 辅音按原唱的提前量缩短**（只缩短，前面是休止的音不在这条规则里）：
- 在音符起点前 250 ms 到起点后 60 ms 里找原唱“没在唱”的间隙，取离起点最近的一段；它在起点之前的部分 G 就是原唱的辅音提前量。
- 新长度 = max(20 ms, G)。
- 清辅音：前一个音在 r2 里被吃掉了元音尾巴（voicing_check 列出的音）就改；否则 ACE 的辅音比 G 长 ≥ 30 ms 才改，而且第 1 轮按测量改过的不再动。
- 浊塞音 / 塞擦音（日语 g gy d b by z j；中文没有这一类）：只在前一个音被吃掉时改。鼻音、流音、半元音不动（它们有声，不吃元音）。
- ACE 读不出时长的辅音（durationSec 为空）：前一个音被吃掉时直接按 G 写一个明确长度。

**F 音高曲线补全**：相邻两段曲线之间的空隙 ≤ 300 ms 时，先保持前一段的最后一个值，到空隙末尾 min(40 ms, 空隙 / 2) 再直线过渡到后一段；
更长的空隙（休止）只在前一段后面保持 150 ms、后一段前面保持 60 ms。

**G 清掉固定**：写完曲线后把整个片段的有声 / 无声固定清成 auto，让 ACE 按新的辅音长度重新判断。

《绯红》：E 改了 34 个辅音（其中 33 个就是 r2 里吃掉前一个元音的；例如 k 92.9 → 31.5 ms），F 把 31 段曲线连成 2 段（多覆盖 587 帧，写 9462 个点）。

## 执行顺序

1. ACE 里开着已保存的 r2：`acestudio-cli project save-as <绝对路径>/ace/r3.acep`（实际写到 `ace/r3/r3.acep`，以返回的 savedPath 为准）。
2. `python -I scripts/ace_dump.py work/ace_state_r2.json phonemes work/r2_phonemes.json`（当前辅音长度；r3 刚另存，内容和 r2 相同）。
3. `python -I scripts/endings_plan.py work/score.json work/r2_phonemes.json work/target_f0.json work/ref/ref_vocal_clip_48k.wav work/f0/ref_praat_full_5ms.npy work/voicing_plan.json work/round1_plan.json work/endings_plan.json`
   ——先看打印出的计划再往下。
4. `python -I scripts/endings_apply.py work/ace_state_r2.json <r3 的 savedPath> work/endings_plan.json work/ace_state_r3.json work/endings_report.json`：
   改辅音 → 写补全的曲线 → 清固定 → 保存；每一步读回核对（辅音长度、曲线逐点、固定 0 段、音符与 r2 相同）。
   这个顺序不能换：要是先写曲线，写入时就把旧辅音长度下的无声判断固定住了，之后改辅音也解不开。
   工程有未保存改动时，只有撤销记录里全是“远程控制”的“设置辅音长度”（本脚本上次中断留下的）才接着做，否则停下。
5. 报告里的 `deferred`（ACE 报 `PHONEME_TIMINGS_UNAVAILABLE` 的辅音，前一个音只有元音时常见、合成后也不开放）离线补：
   1. `acestudio-cli project new --json` 切走（r3 已由上一步保存），让 r3 不被 ACE 占用；
   2. 把 r3.acep 复制成 `work/r3.before_consonant_patch.acep`（备份，也是补丁的输入）；
   3. 写 `work/r3_changes.json`：`{"<deferred 里的 note>": 新长度秒}`，**单位是秒**（`new_ms` / 1000）；
   4. 用 LibreSVIP 的解释器：`<LibreSVIP python> -I scripts/patch_consonants.py work/r3.before_consonant_patch.acep work/r3.patched.acep
      <ace_state_r3 的 vocal_track_uuid> <clip_uuid> work/r3_changes.json work/r3_patch_report.json`；
      它拒绝写到已存在的文件，回读不一致会删掉输出；
   5. 报告里 `roundtrip_equal`、`other_fields_identical` 都是 true、`notes` 条数对，才把 `r3.patched.acep` 复制覆盖 r3.acep；不对就停下，r3 保持原样；
   6. ACE 打开 r3，`ace_dump.py … phonemes` 确认这几个辅音的新长度。
   《绯红》2 个（157 → 78.5 ms、87 → 35.6 ms）。
6. 渲染、导出（停用效果链；做过第 5 步的，按 `ace-cli.md` 的“重开”一节先让 ACE 保存一次再重开），重跑四项检查、音高评估、时值对比；
   `ending_check.py` 这次加 `--curve work/endings_plan.json`（实际写进去的是补全后的曲线，不加会把尾巴量错）。

不做这一轮（检查都没超线）时，在线写的工程也要清固定：`python -I scripts/voicing_clear.py work/ace_state_r2.json`
（读回 0 段后保存），免得以后改辅音时元音还被固定成无声。
7. 混音加 `--end-fade-ms 35`（硬切的淡出，交付的干声也带上），报告里写清淡出加在哪几处。

## 结果（《绯红》r2 → r3）

| 检查 | r2 | r3 |
|---|---|---|
| 原唱在唱、合成没声音（合计） | 1335 ms | **225 ms** |
| 缺 ≥ 30 ms 的音 | 20 个 | 2 个（各 30 ms） |
| 结尾 AI 音高尾巴（≥ 20 ms 且 ≥ 50 音分） | 8 处 | **0** |
| 结尾时间与原唱差 ≥ 40 ms | 32 个 | 24 个 |
| 音高误差中位（Praat / RMVPE） | 2.9 / 2.8 音分 | 2.8 / 2.9 音分 |
| 偏差 > 600 音分的帧 | 13 / 8 | **1 / 0** |
| 音符中间断声（Praat） | 24 处 | **1 处** |
| 颤音带（原唱 25.1 音分） | 17.2 / 18.2 | 29.7 / 24.8 |
| 清辅音前间隙与原唱之差 中位 / p90 | +5 / 50 ms | +5 / 40 ms |

和 r0 比没有哪个音变差 30 音分以上；第 1 轮改过的辅音里 2 个略远（30 → 45 ms、30 → 60 ms）。

## 还不知道的

- 用户还没听 v2 回复：结尾问题是否听得出解决了，只有信号证据。
- 辅音缩到 20–50 ms 后清不清楚，没有人耳确认（按原唱的时值来）。
- 35 ms 淡出是按原唱衰减时间定的，没做过 A/B。
- 把规则 F、G 直接并进第 2 轮（写曲线时就补全、写完就清固定）可能省掉一轮，但没试过。
- 只在一首日语快歌上做过；中文歌的辅音提前量、慢歌是否有同样的问题都没验证。
