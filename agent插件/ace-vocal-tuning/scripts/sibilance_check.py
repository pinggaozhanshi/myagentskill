"""齿音检查（提亮后会不会比原唱还刺）：清擦音 / 塞擦音开头的音（common.FRICATIVE_INIT，按 project.json 的语言）的辅音段高频峰值，
相对后面元音的电平。

用法：python -I sibilance_check.py <pilot_score.json> <g2p.json> <out.json> <label>=<clip.wav> ...
第一个 label 当参考。辅音段 = 音符起点前 90 ms 到起点后 20 ms；高频 = 5–12 kHz（10 ms 窗、5 ms 一帧的最大值）；
元音电平 = 音符 30%–80% 段的全频带中位数。差值越大越“刺”。逐音与参考配对比较。信号指标，不是听感。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import butter, sosfiltfilt  # noqa: E402

HOP = 0.005
FRIC = common.FRICATIVE_INIT


def env_db(x, sr, w=0.010):
    n = int(w * sr)
    hop = int(round(HOP * sr))
    pad = np.concatenate([np.zeros(n // 2), x, np.zeros(n)])
    fr = np.lib.stride_tricks.sliding_window_view(pad, n)[::hop]
    return 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-20)


def main():
    score_p, g2p_p, out = sys.argv[1:4]
    score = json.load(open(score_p, encoding="utf-8"))
    c0 = score["meta"]["clip_start_tick"]
    heads = common.head_consonants(score["notes"], g2p_p)
    idx = [k for k, n in enumerate(score["notes"]) if n["target"] and heads.get(k) in FRIC]
    res = {}
    for item in sys.argv[4:]:
        label, wav = item.split("=", 1)
        x, sr = sf.read(wav, always_2d=True)
        x = x.mean(axis=1)
        hf = sosfiltfilt(butter(4, [5000, 12000], btype="band", fs=sr, output="sos"), x)
        e_all, e_hf = env_db(x, sr), env_db(hf, sr)
        rows = {}
        for k in idx:
            n = score["notes"][k]
            s = common.t2s(n["tick"] - c0)
            d = common.t2s(n["dur"])
            a, b = int((s - 0.09) / HOP), int((s + 0.02) / HOP)
            v0, v1 = int((s + 0.3 * d) / HOP), int((s + 0.8 * d) / HOP)
            rows[n["idx"]] = {"head": heads[k], "sib_db": float(e_hf[a:b].max() - np.median(e_all[v0:v1]))}
        res[label] = rows
    labels = list(res)
    ref = labels[0]
    summary = {}
    for lab in labels:
        v = [r["sib_db"] for r in res[lab].values()]
        summary[lab] = {"n": len(v), "median": round(float(np.median(v)), 2)}
        if lab != ref:
            d = np.array([res[lab][i]["sib_db"] - res[ref][i]["sib_db"] for i in res[ref]])
            summary[lab].update({f"minus_{ref}_median": round(float(np.median(d)), 2), f"minus_{ref}_max": round(float(d.max()), 2),
                                 "notes_over_ref_by_3db": [int(i) for i, dd in zip(res[ref], d) if dd > 3]})
        print(lab, summary[lab])
    json.dump({"summary": summary, "rows": res}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
