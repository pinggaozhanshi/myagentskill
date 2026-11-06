"""元音覆盖检查：原唱“唱出来”（Praat 有声、电平不低于所在音符中位 −12 dB）的帧里，合成没有声（Praat 与 RMVPE 都无声，或低于 −60 dBFS）的有多少。

用法：python -I vowel_coverage.py <score.json> <ref_clip.wav> <ref_praat_full_5ms.npy> <label>=<syn.wav>,<syn_praat.npy>,<syn_rmvpe.npy> ...
按音符统计；列出缺了 ≥ 30 ms 的音。比的是“该唱的地方有没有唱出来”，第 3 轮针对的就是音节结尾被下一个辅音吃掉。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005


def env_db(path):
    x, sr = sf.read(path, always_2d=True)
    x = x.mean(axis=1)
    w = int(HOP * sr)
    m = len(x) // w
    return 10 * np.log10(np.mean(x[:m * w].reshape(m, w) ** 2, axis=1) + 1e-12)


def main():
    score_p, ref_w, ref_pr = sys.argv[1:4]
    score = json.load(open(score_p, encoding="utf-8"))
    notes, off = score["notes"], common.t2s(score["meta"]["clip_start_tick"])
    k0 = int(round(off / HOP))
    re_ = env_db(ref_w)
    rv = ~np.isnan(np.load(ref_pr)[k0:k0 + len(re_)])
    for item in sys.argv[4:]:
        label, paths = item.split("=", 1)
        w, pp, pr = paths.split(",")
        se = env_db(w)
        n = min(len(se), len(re_))
        sv = (~np.isnan(np.load(pp)[:n]) | ~np.isnan(np.load(pr)[:n])) & (se[:n] > -60)
        miss, rows = 0, []
        for k, x in enumerate(notes):
            a, b = int((x["start"] - off) / HOP), min(int((x["end"] - off) / HOP), n)
            if b <= a:
                continue
            sung = rv[a:b] & (re_[a:b] > np.median(re_[a:b]) - 12)
            m = int(np.sum(sung & ~sv[a:b]))
            miss += m
            if m * 5 >= 30:
                rows.append((k, round(x["start"], 3), m * 5))
        print(f"{label}: frames the original sings but the synth does not: {miss * 5} ms in total; notes missing >= 30 ms: {len(rows)}"
              + ("" if not rows else " -> " + ", ".join(f"#{k}@{t}s {ms}ms" for k, t, ms in rows)))


if __name__ == "__main__":
    main()
