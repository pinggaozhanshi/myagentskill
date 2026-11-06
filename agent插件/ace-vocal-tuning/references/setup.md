# 环境、项目结构与要先问用户的事

## 先问清、先征得同意

开工前和用户确认这些，每一条都记进项目的 `README.md`「已确认」表（写明来源：用户原话或你的决定）：

| 项 | 例 |
|---|---|
| 曲目和试验段 | 先做 15–30 秒（一段副歌或主歌），通过后再推广 |
| 声库、模型代 | 洛天依 `singer:18`，Verse23 = V1（ACE 里只有这一个版本，`voice list` 2026-10-19） |
| 歌词语言 | 日语原词 / 中文原词；日语对洛天依是跨语种，读音自然度只能靠听 |
| 下载 | 每样素材单独确认：文件名、来源、大小、条款（谱面作者的使用条件、官方二创规约） |
| 云端上传 | ACE Stem Splitter 会把音轨传到 ACE 云端（基础模式不扣点数），要用户同意 |
| ACE 谁来开 | 用户自己开，或允许你开；ACE 必须在运行，命令行才连得上 |

没征得同意不下载、不上传、不发布。用户在 ACE 里自己动过的工程，不替他保存、也不丢弃。

## 软件与依赖（本机 2026-10 的实况）

| 用途 | 位置 / 版本 | 说明 |
|---|---|---|
| ACE Studio | 2.1.9，`C:/Program Files/ACE Studio/acestudio-cli.exe`（CLI 0.18.7，2026-10-24 `--version`） | 用 `acestudio-cli help <命令>` 查当前语法，`--json` 取机器可读输出。前三次试验在 2.1.8 / CLI 0.17.0 上做，《绯红》在 2.1.9 / 0.18.7 上做；在线写音高（`vocalpitch`）要 0.18 起 |
| 系统 Python | `C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe`（3.13） | numpy、scipy、praat-parselmouth 0.4.7、torch 2.11（CUDA）、ruamel.yaml、matplotlib 在系统 site-packages；librosa、pyloudnorm 在用户 site-packages（`-I` 下由 `common.py` 加回来）。没有 torchaudio |
| LibreSVIP 2.9.0 | `C:\Users\lenovo\Documents\自媒体\调教Agent研究\.venv\Scripts\python.exe`（3.12） | 只用来离线读写 `.acep`（`patch_pitch.py`、`patch_params.py`、`patch_consonants.py`）和读 Pocket Singer 工程；这个环境里没有 torch |
| RMVPE 音高提取 | 研究目录的 `rmvpe_local_extract.py`，权重 `backends\models\rmvpe-rvc.pt` | 用 `scripts/rmvpe_run.py` 跑：`python -X utf8 scripts/rmvpe_run.py <in.wav> <out.json>`（系统 Python，不加 `-I`）。提取脚本经 SOFA 的 rmvpe 包顺带导入 torchaudio，系统 Python 没有，包装脚本放一个只占名字的替身（计算不用它）。输出 10 ms 一帧，再用 `f0_grid.py --rmvpe` 换成 5 ms 网格。回归验证里同一份干声重跑与存档逐帧相同（见 `evidence/validation.md`）。研究目录的 `.sofa-venv`（torch 2.5.1 CPU + torchaudio）也能直接跑，没验证过和上面结果一致 |
| SOFA 日语强制对齐（可选） | 研究目录 `.sofa-venv` | 只在第一次试验用过，时值测量后来改用有声/无声边界，更稳 |
| ffmpeg、yt-dlp | PATH 上 | 解码、MP3 编码；下载官方音轨（要用户同意） |

工作流的脚本一律用 `python -I scripts/<脚本>.py ...` 运行：`-I` 隔离模式不读环境变量、不加当前目录，`common.py` 再把用户 site-packages 加回来、把输出改成 UTF-8（控制台默认 GBK）。

## 新项目目录

在 `D:\自媒体\` 下新建 `<曲名>_调教试验_<日期>\`，**开工前先 `git init`**（`D:\自媒体\AGENTS.md` 的规定）：

```
docs/       决定、来源台账、调教记录、报告（进 Git）
scripts/    从本工作流复制的脚本 + 这首歌自己的谱面脚本（进 Git）
project.json  项目设置（进 Git）
sources/    下载的原始素材（不进 Git，SHA-256 记在 docs/source-ledger.md）
work/       解码、分离、F0、中间 JSON、盲听答案（不进 Git，可重建）
ace/        ACE 工程，每轮一个独立工程（不进 Git）
exports/    ACE 导出、A/B、盲听包、成品（不进 Git）
reports/    对比图 PNG（不进 Git，可由脚本重画）
```

步骤：

1. 复制本工作流的 `scripts/`（不含 `examples/`）到项目 `scripts/`。
2. 复制 `templates/` 里的文件：
   - `project.json`、`README.md` 放项目根目录；
   - `gitignore.txt` 改名成 `.gitignore` 放项目根目录；
   - 其余 md（来源台账、谱面决定、调教记录、试验报告）放进 `docs/`。
3. 填 `project.json`（字段见下）。
4. 第一次提交。

含歌词的谱面数据放 `work/`，歌词原文不抄进 Git（谱面作者和原曲的权利）。文档、提交说明、终端输出里只写音符序号、时间、音素或音类，
不写整句歌词（《绯红》起的做法；工具脚本也都只打印序号）。

## project.json 字段

| 字段 | 必填 | 含义 |
|---|---|---|
| `bpm` | 是 | 单一速度。有变速的歌不在本工作流验证范围内 |
| `tpq` | 否 | tick / 四分音符，默认 480。**只用 480**：ACE 的 tick 就是 480 / 四分音符，`patch_pitch.py` 也按 480 算 |
| `language` | 是 | ACE 轨道语言：`Chinese` / `Japanese`；决定 G2P 和清辅音表 |
| `singer` | 否 | 默认 `singer:18`（洛天依） |
| `track_name` | 否 | 单轨谱面时人声轨的名字 |
| `inst_track_name` / `ref_track_name` | 否 | 伴奏、参考人声轨的名字（不写时 `INST_伴奏`、`REF_参考人声(静音)`；模板里写的 `INST_分离伴奏` 是伴奏来自分离时的叫法） |
| `voiceless_initials` / `fricative_initials` / `voiced_stop_initials` | 否 | 覆盖默认的清辅音表、擦音表、浊塞音表（ACE G2P 的音素名；浊塞音表只给音节结尾轮用，中文默认为空） |
| `downbeat_tick` | 混音时 | 第 0 小节强拍的 ACE tick（成品混音按小节定区间） |
| `beats_per_bar` | 否 | 默认 4 |
| `mix_name` | 混音时 | 成品文件名（不带扩展名） |
| `scale_pitch_classes` | 和声核对时 | 本曲调式的音级（0 = C），和声改音不改到调式外 |
| `own_ace_dirs` | 否 | 除本项目 `ace/` 以外，也算“自己的”工程目录（接着上一个试验开着的工程时用） |
| `ace_cli` | 否 | CLI 路径；可写成列表（回归测试接假的 CLI 用） |
| `libresvip_python` | 否 | 装了 LibreSVIP 的解释器，默认研究目录的 `.venv` |
| `rmvpe_extract` | 否 | RMVPE 提取脚本的位置，默认研究目录的 `rmvpe_local_extract.py` |
| `v2m_language` | 否 | Vocal to MIDI 的语言参数（`chinese` / `japanese` / `english` …），默认 `language` 的小写 |
| `user_site` | 否 | 用户 site-packages，默认 `site.getusersitepackages()` |

## 安全规则（脚本已经内置，手动操作也要照做）

- **动工程前查状态**：`ace.require_safe_project()`。
  - 当前工程有未保存改动 → 停；
  - 既不是空的临时工程、也不是本项目 `ace/` 下的工程 → 停，先问用户。
- **用户在 ACE 里有没保存的改动**：从开着的工程**另存为新工程**把改动带过去，原文件不动（《妄想感傷代償連盟》v3 的 `full_r4`、《反乌托邦》的 `r2_pitch_未保存改动`）。不替用户保存，也不丢弃。
- **每一轮一个独立工程**：`ace/r0_baseline/`、`ace/r1_timing/`、`ace/r2_pitch/`……，基线和各轮都不覆盖。
- **路径一律绝对路径**：ACE 会按它自己的安装目录解析相对路径。
- **ACE 另存会再套一层同名文件夹**：`save-as ace/r1_timing.acep` 实际写到 `ace/r1_timing/r1_timing.acep`，以返回的 `savedPath` 为准。
- **不覆盖输出**：脚本遇到已有的输出文件、非空的盲听目录会停下，换个名字。
- **交接时**写明 ACE 里现在开着哪个工程、是否已保存（下一个 agent 或用户接手时要知道）。
- 所有 CLI 调用记在 `work/ace_calls.jsonl`，出问题时先看这里。
