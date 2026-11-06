# 可选工具与宿主适配

## 可读文件入口

普通Agent：读取SKILL.md，按路由执行。支持技能注册的Agent：安装整个目录并调用`$pv-redraw-localization`（该语法取决于宿主）。Codex UI元数据只在支持它的宿主有效。

| 能力 | 可用工具举例 | 缺少时 |
|---|---|---|
| 视频探测/抽帧 | FFmpeg/ffprobe、PyAV、剪辑软件 | 索取元数据与关键切点帧，不能猜帧号 |
| 动作复杂度 | 下列 motion-profile、逐帧对照 | 抽连续帧人工数换画位，不能凭“动作多/少”的感觉定密度 |
| 原画/局部修复 | 宿主图像生成编辑工具、已授权图像API、现有PSD/PNG | 使用已有素材或列缺图，不能声称完成新作画 |
| 图层合成与编码 | NLE/AE/Blender或现有Python合成链 | 输出镜头/曝光/层序计划，不谎报成片 |
| 当前歌词 | ACE CLI/API、工程导出音符表、ASS/SRT | 读取明确的歌词真值；不能拿旧歌词默认为最新 |
| 波形对齐 | 下列可选脚本、音频编辑器、共有拍点 | 保存可核对的偏移方向和多窗口证据 |

优先当前环境已有工具和项目脚本。不要复制魔法女仆的硬编码路径或把整个旧合成链当成独立可移植程序。

## pv_tools.py

Python 3.10+。`manifest-check`不需要第三方；`audio-lag`/`compare-video`需要NumPy/PyAV，依赖列在requirements.txt。先用现有环境，不自动改系统Python。脚本写报告时拒绝覆盖已有文件。

```text
python scripts/pv_tools.py self-test
python scripts/pv_tools.py manifest-check templates/project-manifest.json
python scripts/pv_tools.py manifest-check my-project.json --reject-example
python scripts/pv_tools.py audio-lag reference.mp4 chinese-mix.wav --rate 8000 --starts 3,20,65,105,130,150 --window 3 --max-lag 2 --output lag.json
python scripts/pv_tools.py compare-video accepted.mp4 audio-replaced.mp4 --output video-check.json
python scripts/pv_tools.py compare-video accepted.mp4 audio-replaced.mp4 --decode --output pixel-check.json
python scripts/pv_tools.py motion-profile source.mp4 --start 44 --end 69 --output motion.json --csv motion.csv
python scripts/pv_tools.py motion-profile source.mp4 --manifest my-project.json --mask-model isnetis.onnx --output motion-shots.json
```

`manifest-check`只证明结构、帧范围和曝光覆盖正确，**不证明资产文件存在、姿势正确或样段好看**。示例会返回`example_only=true, ready_to_render=false`；真实工程使用`--reject-example`防止直接采用未替换的示例。该选项不替代源片实测、资产存在性和样段检查。
`audio-lag`定义“other晚于reference为正”；返回反号的建议平移量。按素材时长和有效声部选择窗口，短片不能照抄超出时长的示例窗口。相关度、窗口是否有内容、乐段重复都需检查；它不自动改音频。侧声道静音时退到mono并记录，可能更受不同人声影响。VFR不会自动按平均fps推算切点。
`compare-video`默认比较视频packet bytes、extradata、参数和packet时间，不比较音轨。`--decode`额外核查RGB像素及帧时间；不能以它代替视觉质量或歌词辨字。
`motion-profile`需要NumPy/PyAV，按实际PTS逐帧归类（保持/小变化/换画/镜头平移/回访），按`--window`秒（默认1）和可选`--manifest`镜头表给出T0/T1/T2候选、新画数与`--cells`格图集数，判据见[动作复杂度识别](motion-complexity.md)。帧号从源片第0帧起算；终端只打印摘要，逐帧结果要写`--output`/`--csv`。`--roi x,y,w,h`（画面比例）只看指定区域；`--mask-model`接动漫人物分割ONNX模型（如anime-seg的isnetis.onnx，需另装onnxruntime），只统计人物区域，CPU约0.7秒/帧，`--mask-every N`每N帧分割一次以提速。分级只是候选，不替代看帧和编码样段。

无Python库时可用FFmpeg/NLE对齐与流复制。下面是**尾部已经确认只有静音余量且画面长度必须保持**的例子，不能用来裁掉有效尾音：

```text
ffmpeg -i accepted.mp4 -i chinese-mix.wav -filter_complex "[1:a]adelay=21.338:all=1,apad[a]" -map 0:v:0 -map "[a]" -c:v copy -c:a aac -b:a 320k -t 158.992 output-new.mp4
```

这里的21.338和158.992仅演示本案例；新片必须替换为自己的测量。若多出来的音频有有效演唱/混响，不得直接套`-t`或`-shortest`；保留完整声音，并依据用户授权确定保留长音轨还是延展/重剪结尾画面。使用当前FFmpeg版本help核对小数延迟、声道与trim语义。仍需独立复核最终解码音频和视频。

## ACE CLI例

ACE可先用`acestudio-cli help project open`、`help clip get`、`help clip note-content`查询当前语法，再读取指定工程。Windows本案使用`C:/Program Files/ACE Studio/acestudio-cli.exe`，此路径只作为案例，不是跨平台前提。不要加`--discard-changes`绕过未保存工程。
