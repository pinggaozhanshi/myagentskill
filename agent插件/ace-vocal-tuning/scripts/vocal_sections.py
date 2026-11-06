"""按小节列出分离人声的有声比例，找段落（前奏、主歌、副歌、间奏）的边界，用来定一分钟版的区间。

用法：python -I vocal_sections.py <vocal.wav> <first_downbeat_sec> <out.json>
节拍网格：common.BPM、4/4，第 0 小节从 first_downbeat_sec 开始（ACE 节拍分析 + 逐拍拟合）。
有声：Praat F0 有值（common.praat_grid）且 RMS 高于整首有声帧中位 −30 dB（去掉分离残留的零星小声）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005


def main():
    wav, t0, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    x, sr = sf.read(wav, always_2d=True)
    x = x.mean(axis=1)
    f0 = common.praat_grid(x, sr, HOP)
    n = len(f0)
    w = int(HOP * sr)
    rms = np.array([np.sqrt(np.mean(x[i * w:(i + 1) * w] ** 2)) if i * w < len(x) else 0.0 for i in range(n)])
    db = 20 * np.log10(rms + 1e-9)
    voiced = ~np.isnan(f0)
    thr = np.median(db[voiced]) - 30
    act = voiced & (db > thr)
    bar = 4 * 60.0 / common.BPM
    rows = []
    k = 0
    while t0 + k * bar < len(x) / sr:
        a, b = int((t0 + k * bar) / HOP), int((t0 + (k + 1) * bar) / HOP)
        seg = act[a:min(b, n)]
        rows.append({"bar": k, "start": round(t0 + k * bar, 3), "active": round(float(seg.mean()) if len(seg) else 0.0, 3),
                     "median_midi": None if not seg.any() else round(float(np.median(69 + 12 * np.log2(f0[a:min(b, n)][seg] / 440))), 1)})
        k += 1
    pre = int(t0 / HOP)
    print(f"before bar 0 (0–{t0:.2f}s): active {act[:pre].mean():.2f}")
    for r in rows:
        bar_vis = "#" * int(round(r["active"] * 40))
        print(f"bar {r['bar']:>3} {r['start']:7.2f}s  {r['active']:.2f} {str(r['median_midi'] or ''):>5} {bar_vis}")
    json.dump({"bpm": common.BPM, "first_downbeat_sec": t0, "bar_sec": bar, "threshold_db": float(thr), "bars": rows},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
