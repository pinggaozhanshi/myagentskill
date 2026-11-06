"""节拍分析结果 → 速度拟合与漂移检查（定网格用，调教前冻结）。

用法：python -I tempo_fit.py <tempo_analysis.json> [<候选 BPM>] [<out.json>]
- tempo_analysis.json：`acestudio-cli tempo analyze --file-path <官方音轨绝对路径>` 之后
  `acestudio-cli tempo get-analysis --id <analysisId> --json` 的输出（beats、downbeats 都是秒）。
- 拟合：所有拍点时间对拍序号做最小二乘直线，斜率换算成 BPM。
- 候选 BPM（不给就取拟合值四舍五入到 0.5）：固定这个速度、只求起点（残差平均为 0），报告残差绝对值的中位与最大，
  以及前、中、后三分之一拍点的平均残差。三段差得多 = 速度不对或有变速（本工作流只验证过单一速度）。
- 也列出第一个强拍（第 0 小节）的秒数；网格零点还要用谱面或 Vocal to MIDI 的起点再核一次（references/score-and-reference.md）。
只读 JSON，不连 ACE、不改工程。
"""
import json
import sys

import numpy as np


def main():
    a = json.load(open(sys.argv[1], encoding="utf-8"))
    beats = np.asarray(a["beats"], dtype=float)
    i = np.arange(len(beats))
    slope, _ = np.polyfit(i, beats, 1)
    fit_bpm = 60.0 / slope
    cand = float(sys.argv[2]) if len(sys.argv) > 2 else round(fit_bpm * 2) / 2
    period = 60.0 / cand
    t0 = float(np.mean(beats - i * period))
    r = beats - (t0 + i * period)
    parts = np.array_split(r, 3)
    res = {"beats": len(beats), "analysis_bpm": a.get("bpm"), "fit_bpm": round(float(fit_bpm), 3), "candidate_bpm": cand,
           "residual_abs_median_ms": round(float(np.median(np.abs(r))) * 1000, 1),
           "residual_abs_max_ms": round(float(np.max(np.abs(r))) * 1000, 1),
           "thirds_mean_residual_ms": [round(float(np.mean(p)) * 1000, 1) for p in parts],
           "first_downbeat_sec": (a.get("downbeats") or [None])[0], "beat0_sec_at_candidate": round(t0, 4)}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if len(sys.argv) > 3:
        json.dump(res, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
