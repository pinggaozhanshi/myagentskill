"""写音高曲线之前的八度 / 错音检查（在线写用；离线写由 patch_pitch.py 自己查）。round2_pitch_online.py 写之前会调用它。

用法：python -I target_check.py <score.json> <target_f0.json> [<out.json>]
两条规则与 patch_pitch.py 相同（运行前定死），只是基准换成音符音高（在线写没有 ACE 的 BasePitchCurve）：
1. 任一音符中段 60%（20%–80%）的“目标 − 音符音高”中位数绝对值 > 6 半音（八度 = 12、五度 = 7；滑音造成的整段偏离实测 ≤ 4.4）；
2. |目标 − 所在音符音高| > 9.5 半音连续超过 50 ms。音符外放宽的那几十毫秒按最近的音算。
大音程过渡、辅音闭塞处的短促下沉、句尾回落都是合理的大偏差，不在这两条里。有问题时退出码 1：先查目标曲线和谱面，不要写。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402


def check(score, tgt):
    notes = score["notes"]
    off = common.t2s(score["meta"]["clip_start_tick"])
    hop = tgt["hop_sec"]
    midi = np.array([np.nan if v is None else v for v in tgt["midi"]], dtype=float)
    t = np.arange(len(midi)) * hop
    starts = np.array([n["start"] - off for n in notes])
    ends = np.array([n["end"] - off for n in notes])
    pitch = np.array([n["pitch"] for n in notes], dtype=float)
    k = np.clip(np.searchsorted(starts, t, side="right") - 1, 0, len(notes) - 1)
    k2 = np.clip(k + 1, 0, len(notes) - 1)
    k = np.where((t >= ends[k]) & ((starts[k2] - t) < (t - ends[k])), k2, k)
    delta = midi - pitch[k]
    bad_notes = []
    for j, n in enumerate(notes):
        a, b = starts[j] + 0.2 * (ends[j] - starts[j]), starts[j] + 0.8 * (ends[j] - starts[j])
        vals = delta[(t >= a) & (t < b) & ~np.isnan(delta)]
        if len(vals) >= 5 and abs(float(np.median(vals))) > 6:
            bad_notes.append({"idx": n.get("idx", j), "pitch": n["pitch"], "median_delta": round(float(np.median(vals)), 2)})
    longest, run = 0, 0
    for big in np.abs(np.nan_to_num(delta, nan=0.0)) > 9.5:
        run = run + 1 if big else 0
        longest = max(longest, run)
    rep = {"frames_with_target": int(np.sum(~np.isnan(midi))), "abs_delta_median": round(float(np.nanmedian(np.abs(delta))), 3),
           "notes_with_interior_median_gt_6": bad_notes, "longest_run_abs_gt_9p5_ms": round(longest * hop * 1000, 1)}
    rep["ok"] = not bad_notes and rep["longest_run_abs_gt_9p5_ms"] <= 50
    return rep


def main():
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    tgt = json.load(open(sys.argv[2], encoding="utf-8"))
    rep = check(score, tgt)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    if len(sys.argv) > 3:
        json.dump(rep, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not rep["ok"]:
        raise SystemExit("疑似八度 / 错音（音符中段整体偏离或长时间大偏差），不要写这条曲线")


if __name__ == "__main__":
    main()
