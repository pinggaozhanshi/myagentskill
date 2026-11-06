# <曲名> × 洛天依调教（<开始日期>）

方法：可复用工作流 `ace-vocal-tuning`（以原唱为参考，一轮只改一类东西，盲听定胜负）。

## 已确认

| 项 | 内容 | 来源（用户原话 / 我的决定） |
|---|---|---|
| 曲目与试验段 | | |
| 声库 | 洛天依 `singer:18`（Verse23 / V1） | |
| 歌词语言 | | |
| 下载（每样素材：文件名、来源、大小、条款） | | |
| 云端上传（Stem Splitter） | | |
| ACE 谁来开 | | |
| ACE / CLI 版本 | | `acestudio-cli --version` |

## 现在的状态

- 阶段：谱面核对通过 / 基线导出 / 各轮信号检查通过 / 结尾检查通过 / 用户盲听通过 / 成品混音 / 交付 / 修改中
- ACE 里开着：`<工程绝对路径>`，已保存 / 未保存
- 最新交付：`exports/<目录>/<文件>`（校验值见 `docs/source-ledger.md`）
- 没有人耳确认的：

## 目录

```
docs/        决定、来源台账、调教记录、报告（进 Git）
scripts/     工作流脚本 + 这首歌自己的谱面脚本（进 Git）
project.json 项目设置（进 Git）
sources/     原始素材（不进 Git）
work/        解码、分离、F0、中间 JSON、盲听答案（不进 Git）
ace/         ACE 工程，每轮一个（不进 Git）
exports/     导出、A/B、盲听包、成品（不进 Git）
reports/     图（不进 Git）
```

## 文档

- `docs/source-ledger.md`：来源台账（素材、条款、校验值）
- `docs/score-decisions.md`：谱面、网格、参考人声的决定
- `docs/tuning-pass-log.md`：每一轮的规则、改动和结果
- `docs/pilot-report.md`：试验报告、盲听结果和用户原话
