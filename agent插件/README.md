# Agent插件

两个可复用工作流，都是「文档 + 脚本 + 验证记录」形式的 Agent 技能包：放进支持 Agent Skills 的宿主的技能目录即可，
不支持技能系统的 Agent 直接让它读 `SKILL.md`。

## PV重绘与本地化工作流

适用于既有动画PV的人物替换、缺姿势增绘、稳定合成、烧录歌词替换、中文演唱同步和实际编码验收。

- [Agent入口：SKILL.md](pv-redraw-localization/SKILL.md)
- [使用说明与文件索引](pv-redraw-localization/README.md)
- [完整压缩包](PV重绘与本地化工作流_20261106.zip)

普通Agent可直接读取SKILL.md；支持Agent Skills的宿主可安装整个pv-redraw-localization目录。Codex可调用`$pv-redraw-localization`。自动发现取决于宿主，媒体操作还需相应工具能力。

## ACE人声调教工作流（以原唱为参考）

适用于在 ACE Studio 里以原唱为参考调教合成人声翻唱（默认洛天依 V1）：谱面与读音核对、时值、音高曲线、音节结尾、
可选表情参数、音量对齐盲听、混音交付与交付后修改。

- [Agent入口：SKILL.md](ace-vocal-tuning/SKILL.md)
- [使用说明与文件索引](ace-vocal-tuning/README.md)
- [完整压缩包](ACE人声调教工作流_20261106.zip)

流程是基线 r0 → 第1轮时值 → 第2轮音高 → 音节结尾 → 可选表情轮 → 盲听 → 混合交付，每轮独立工程、基线永不覆盖。
脚本要复制进具体项目的 `scripts/` 并配 `project.json` 才能运行；ACE 必须由用户打开，`acestudio-cli` 才连得上。
Codex可调用`$ace-vocal-tuning`。

## 说明

两个包都只包含工作流、经验、示例与可选核查脚本，**不含**原视频、音频、人物原画、字体、模型权重或账号凭据。
包内出现的歌曲名、BPM、帧号、电平差是当时实测的案例记录，照用的是规则和阈值，不是默认值。
