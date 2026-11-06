"""任意 wav → Praat F0 网格（Hz，NaN=无声），5 ms 一帧，t=0 为文件起点；或把 RMVPE 的 JSON（10 ms）换成同样的网格。

用法：python -I f0_grid.py <in.wav> <out.npy>
      python -I f0_grid.py --rmvpe <rmvpe.json> <duration_sec> <out.npy>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005


def rmvpe_to_grid(path, duration):
    fr = json.load(open(path, encoding="utf-8"))["frames"]
    t = np.array([f["time_sec"] for f in fr])
    hz = np.array([f["f0_hz"] if f["voiced"] else np.nan for f in fr], dtype=float)
    tk = np.arange(int(np.ceil(duration / HOP)) + 1) * HOP
    j = np.clip(np.searchsorted(t, tk) - 1, 0, len(t) - 2)
    w = np.clip((tk - t[j]) / (t[j + 1] - t[j]), 0, 1)
    a, b = hz[j], hz[j + 1]
    g = np.where(np.isfinite(a) & np.isfinite(b), np.exp((1 - w) * np.log(a) + w * np.log(b)), np.nan)
    g = np.where(~np.isfinite(g) & np.isfinite(a) & (w <= 0.5), a, g)
    g = np.where(~np.isfinite(g) & np.isfinite(b) & (w > 0.5), b, g)
    return g


def main():
    if sys.argv[1] == "--rmvpe":
        g = rmvpe_to_grid(sys.argv[2], float(sys.argv[3]))
        out = sys.argv[4]
    else:
        x, sr = sf.read(sys.argv[1], always_2d=True)
        g = common.praat_grid(x.mean(axis=1), sr, HOP)
        out = sys.argv[2]
    np.save(out, g)
    print(out, "frames", len(g), "voiced", int(np.sum(~np.isnan(g))))


if __name__ == "__main__":
    main()
