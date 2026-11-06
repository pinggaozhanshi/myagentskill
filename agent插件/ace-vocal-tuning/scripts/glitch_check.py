"""两项信号检查（不是听感）：
1. 大偏差帧（与目标差 > 600 音分）聚成几段、在哪个音符；
2. 元音内部断声：音符中间 60% 里，参考有声而合成连续无声 ≥ 20 ms 的地方。

用法：python -I glitch_check.py <target_f0.json> <pilot_score.json> <ref_clip_voiced_from: praat_full_5ms.npy> <label>=<praat_5ms.npy> ...
时间都按片段起点为 0；打印时换算成音轨秒（+ 片段起点秒）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402

HOP = 0.005


def clusters(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def main():
    tgt = json.load(open(sys.argv[1], encoding="utf-8"))
    tm = np.array([np.nan if v is None else v for v in tgt["midi"]], dtype=float)
    score = json.load(open(sys.argv[2], encoding="utf-8"))
    clip0 = score["meta"]["clip_start_tick"]
    off = common.t2s(clip0)
    k0 = int(round(off / HOP))
    ref_voiced = ~np.isnan(np.load(sys.argv[3])[k0:k0 + len(tm)])
    notes = score["notes"]
    span = [(common.t2s(n["tick"] - clip0), common.t2s(n["tick"] + n["dur"] - clip0)) for n in notes]

    def note_at(k):
        t = k * HOP
        for n, (a, b) in zip(notes, span):
            if a <= t < b:
                return n["idx"]
        return None

    for item in sys.argv[4:]:
        label, npy = item.split("=", 1)
        sm = 69 + 12 * np.log2(np.load(npy)[:len(tm)] / 440.0)
        d = np.abs(sm - tm) * 100
        gross = clusters(np.nan_to_num(d, nan=0) > 600)
        print(f"{label}: gross >600c frames {sum(b - a for a, b in gross)} in {len(gross)} clusters: " +
              ", ".join(f"{off + a * HOP:.2f}s(#{note_at(a)},{(b - a) * 5}ms,{np.nanmedian((sm - tm)[a:b]):+.1f}st)" for a, b in gross[:12]))
        syn_voiced = ~np.isnan(sm)
        drops = []
        for n, (a, b) in zip(notes, span):
            if not n.get("target", True):
                continue
            lo, hi = int((a + 0.2 * (b - a)) / HOP), int((a + 0.8 * (b - a)) / HOP)
            m = np.zeros(len(tm), bool)
            m[lo:hi] = ref_voiced[lo:hi] & ~syn_voiced[lo:hi]
            end = int(b / HOP)
            for x, y in clusters(m):
                if (y - x) * HOP >= 0.020:
                    # 断声之后到音符结束都不再有声 → 是下一字辅音提前开始（间隙边缘），不是元音中间断开
                    edge = not syn_voiced[y:end].any()
                    drops.append((edge, f"{off + x * HOP:.2f}s(#{n['idx']},{(y - x) * 5}ms)"))
        inner = [s for e, s in drops if not e]
        print(f"{label}: dropouts >=20 ms in note middle: {len(drops)} | at gap edge {len(drops) - len(inner)} | "
              f"voiced on both sides (true interior) {len(inner)} -> {', '.join(inner)}")


if __name__ == "__main__":
    main()
