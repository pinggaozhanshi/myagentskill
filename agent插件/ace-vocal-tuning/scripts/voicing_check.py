"""找出被 ACE 清化（判成无声）、但原唱实打实唱出来的元音段，给出要强制有声的片段内 tick 区间。

用法：python -I voicing_check.py <score.json> <voicing.json> <ref_clip.wav> <ref_praat_full_5ms.npy> <out_plan.json>
- voicing.json：`acestudio-cli vocalpitch voicing --json` 的输出。vocalpitch write 会把写入当时 ACE 自己的有声 / 无声判断固定在曲线下，
  所以 spans 里的 unvoiced 段就是 ACE 判成无声的地方（清辅音、休止，也包括它清化掉的元音）。
- 原唱“唱出来”：Praat 有声，且电平不低于所在音符中位电平 −12 dB（排除混响残留、辅音）。
- 计划：每个 unvoiced 段与“原唱唱出来”的帧取交集，连续 ≥ 30 ms 的部分记为要强制有声的区间（片段内 tick，5 ms 帧对齐）；
  只在音高曲线覆盖（support）之内，超出的裁掉。原唱的辅音本来就是无声，不会被选上。
终端只打印序号、时间、长度，不打印歌词。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
MIN_MS = 30


def main():
    score_p, voi_p, ref_w, ref_pr_p, out = sys.argv[1:6]
    score = json.load(open(score_p, encoding="utf-8"))
    notes, c0 = score["notes"], score["meta"]["clip_start_tick"]
    off = common.t2s(c0)
    k0 = int(round(off / HOP))
    voi = json.load(open(voi_p, encoding="utf-8"))
    x, sr = sf.read(ref_w, always_2d=True)
    x = x.mean(axis=1)
    w = int(HOP * sr)
    m = len(x) // w
    env = 10 * np.log10(np.mean(x[:m * w].reshape(m, w) ** 2, axis=1) + 1e-12)
    rv = ~np.isnan(np.load(ref_pr_p)[k0:k0 + m])
    loud = np.zeros(m, bool)
    for n in notes:
        a, b = int((n["start"] - off) / HOP), min(int((n["end"] - off) / HOP), m)
        if b > a:
            loud[a:b] = env[a:b] > np.median(env[a:b]) - 12
    sung = rv & loud
    tps = common.TICKS_PER_SEC
    support = [(s["begin"], s["end"]) for s in voi["support"]]

    def note_at(t):
        for k, n in enumerate(notes):
            if n["start"] - off <= t < n["end"] - off:
                return k
        return None

    plan = []
    for s in voi["spans"]:
        if s["mode"] != "unvoiced":
            continue
        fa, fb = int(np.ceil(s["begin"] / tps / HOP)), int(np.floor(s["end"] / tps / HOP))
        k = fa
        while k < fb:
            if sung[k]:
                j = k
                while j < fb and sung[j]:
                    j += 1
                if (j - k) * HOP * 1000 >= MIN_MS:
                    b0, b1 = max(s["begin"], k * HOP * tps), min(s["end"], j * HOP * tps)
                    for sa, sb in support:
                        lo, hi = max(b0, sa), min(b1, sb)
                        if hi - lo >= MIN_MS / 1000 * tps:
                            plan.append({"begin": round(lo, 1), "end": round(hi, 1), "ms": round((hi - lo) / tps * 1000),
                                         "t": round(off + lo / tps, 3), "note": note_at(lo / tps), "span": [s["begin"], s["end"]]})
                k = j
            else:
                k += 1
    tot = sum(p["ms"] for p in plan)
    print(f"unvoiced spans {sum(1 for s in voi['spans'] if s['mode'] == 'unvoiced')}; sung by the original but pinned unvoiced "
          f"(>= {MIN_MS} ms): {len(plan)} spans, {tot} ms")
    for p in plan:
        print(f"  #{p['note']} at {p['t']:.3f}s  {p['ms']:4d} ms  ticks [{p['begin']}, {p['end']})")
    json.dump({"plan": plan}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
