"""长期平均频谱（LTAS）对比：原唱参考 vs 合成版本，只用有声帧，按 1/3 倍频程汇总，看亮度差落在哪些频段。

用法：python -I ltas_compare.py <out.json> <label>=<clip.wav> ...
第一个 label 当参考。每个版本先在 300 Hz–1 kHz 上对齐到同一电平（只比形状，不比响度），再给出各频段的“版本 − 参考”（dB）。
有声帧：Praat（common.praat_grid）且该帧电平在本文件有声帧中位数 −20 dB 以内（避开弱尾音）。信号指标，不是听感。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
NFFT = 4096
CENTERS = [125 * 2 ** (k / 3) for k in range(0, 21)]  # 125 Hz … 12.7 kHz


def ltas(path):
    x, sr = sf.read(path, always_2d=True)
    x = x.mean(axis=1)
    f0 = common.praat_grid(x, sr, HOP)
    hop = int(round(HOP * sr))
    pad = np.concatenate([np.zeros(NFFT // 2), x, np.zeros(NFFT)])
    fr = np.lib.stride_tricks.sliding_window_view(pad, NFFT)[::hop][:len(f0)]
    spec = np.abs(np.fft.rfft(fr * np.hanning(NFFT), axis=1)) ** 2
    lvl = 10 * np.log10(spec.sum(axis=1) + 1e-20)
    v = np.isfinite(f0[:len(fr)])
    v &= lvl > np.median(lvl[v]) - 20
    mean = spec[v].mean(axis=0)
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    bands = []
    for c in CENTERS:
        m = (freqs >= c * 2 ** (-1 / 6)) & (freqs < c * 2 ** (1 / 6))
        bands.append(10 * np.log10(mean[m].sum() + 1e-20))
    ref_m = (freqs >= 300) & (freqs < 1000)
    return np.array(bands) - 10 * np.log10(mean[ref_m].sum() + 1e-20), int(v.sum())


def main():
    out = sys.argv[1]
    res, labels = {}, []
    for item in sys.argv[2:]:
        label, path = item.split("=", 1)
        res[label] = ltas(path)
        labels.append(label)
    ref = labels[0]
    table = {"centers_hz": [round(c) for c in CENTERS], "frames": {k: v[1] for k, v in res.items()}, "diff_db": {}}
    print("band Hz  " + " ".join(f"{round(c):>6}" for c in CENTERS))
    for lab in labels[1:]:
        d = res[lab][0] - res[ref][0]
        table["diff_db"][lab] = [round(float(v), 2) for v in d]
        print(f"{lab:<8} " + " ".join(f"{v:+6.1f}" for v in d))
    json.dump(table, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
