"""音高评估：各版本合成 F0 与参考目标的偏差（音分），逐音符偏差，颤音叠加检查。

用法：python -I pitch_eval.py <target_f0.json> <pilot_score.json> <out.json> <label>=<f0_5ms.npy> ...
- 只在“参考目标有值且合成有声”的帧上比较；|偏差| > 600 音分记为八度/错音帧，单独计数，不进中位数。
- 逐音符：target=False 的音符不计；第一个 label 当基准，统计后面最后一个 label 比它好 / 差 >30 音分的音符数。
- 颤音检查：目标连续段 ≥ 250 ms 内，F0 去趋势后 4–9 Hz 带通的均方根（音分）；合成明显大于目标即疑似叠加颤音。
F0 网格都以片段起点为 t=0（导出时间轴）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
from scipy.signal import butter, sosfiltfilt  # noqa: E402

HOP = 0.005


def band_rms(x):
    sos = butter(2, [4, 9], btype="band", fs=1 / HOP, output="sos")
    return float(np.sqrt(np.mean(sosfiltfilt(sos, x - np.mean(x)) ** 2)) * 100)


def main():
    tgt_p, score_p, out = sys.argv[1:4]
    tgt = json.load(open(tgt_p, encoding="utf-8"))
    tm = np.array([np.nan if v is None else v for v in tgt["midi"]], dtype=float)
    score = json.load(open(score_p, encoding="utf-8"))
    clip0 = score["meta"]["clip_start_tick"]
    notes = [n for n in score["notes"] if n.get("target", True)]
    runs = [r for r in tgt["runs"] if r[1] - r[0] >= 0.25]
    res = {"versions": {}, "vibrato_target_cents": round(float(np.median(
        [band_rms(tm[int(round(a / HOP)):int(round(b / HOP)) + 1]) for a, b in runs])), 1)}
    per_note = {}
    for item in sys.argv[4:]:
        label, npy = item.split("=", 1)
        sm = 69 + 12 * np.log2(np.load(npy) / 440.0)
        n = min(len(sm), len(tm))
        d = (sm[:n] - tm[:n]) * 100
        both = ~np.isnan(d)
        gross = both & (np.abs(d) > 600)
        ad = np.abs(d[both & ~gross])
        sv = []
        for a, b in runs:
            seg = sm[int(round(a / HOP)):int(round(b / HOP)) + 1]
            if np.mean(~np.isnan(seg)) > 0.9:
                seg = np.interp(np.arange(len(seg)), np.where(~np.isnan(seg))[0], seg[~np.isnan(seg)])
                sv.append(band_rms(seg))
        res["versions"][label] = {
            "compared_frames": int(both.sum()), "target_frames": int(np.sum(~np.isnan(tm[:n]))),
            "gross_err_frames_gt_600c": int(gross.sum()),
            "abs_err_median_c": round(float(np.median(ad)), 1), "abs_err_p90_c": round(float(np.percentile(ad, 90)), 1),
            "within_50c": round(float(np.mean(ad <= 50)), 3), "within_100c": round(float(np.mean(ad <= 100)), 3),
            "vibrato_band_rms_median_c": round(float(np.median(sv)), 1) if sv else None}
        pn = []
        for nt in notes:
            a, b = int(common.t2s(nt["tick"] - clip0) / HOP), int(common.t2s(nt["tick"] + nt["dur"] - clip0) / HOP)
            seg = d[a:b]
            seg = seg[~np.isnan(seg) & (np.abs(seg) <= 600)]
            pn.append(None if len(seg) < 3 else round(float(np.median(np.abs(seg))), 1))
        per_note[label] = pn
        print(label, json.dumps(res["versions"][label], ensure_ascii=False))
    print("target vibrato-band rms (median over runs >=250 ms):", res["vibrato_target_cents"], "c")
    res["per_note_abs_err_median_c"] = per_note
    labels = list(per_note)
    if len(labels) >= 2:
        a, b = labels[0], labels[-1]
        pairs = [(notes[k]["idx"], per_note[a][k], per_note[b][k]) for k in range(len(notes))
                 if per_note[a][k] is not None and per_note[b][k] is not None]
        better = sum(1 for _, x, y in pairs if y < x - 30)
        worse = [(i, x, y) for i, x, y in pairs if y > x + 30]
        res["notes_better_than_first_by_30c"] = better
        res["notes_worse_than_first_by_30c"] = worse
        print(f"{b} vs {a}: notes better by >30c: {better}; worse by >30c: {len(worse)} -> {worse}")
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
