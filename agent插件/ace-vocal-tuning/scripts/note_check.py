"""试验谱面核对（基线之前，不是调教）：谱面音符 vs 参考人声 F0（Praat、RMVPE），以及音符与演唱的整体时间偏移。
谱面音符带 ust_src / ust_idx（来源文件与原序号）时，输出的 "ust" 栏写成「来源#序号」，方便回查原谱。

用法：python -I note_check.py <pilot_score.json> <praat_5ms.npy> <rmvpe_5ms.npy> <out.json>
- 逐音符：音符中间 50% 的参考 F0 中位数（MIDI）、有声比例、两提取器差、与谱面的偏差；|偏差| 接近 12 记为八度候选，
  两提取器一致、有声足够、偏差 ≥ 1.5 半音记为错音候选（只标记，改不改另定）。
- 时间：音符“发声掩码”与 Praat 有声掩码在 ±200 ms 内求最大重合，得到整体偏移；另列乐句首音符的有声起点差。
F0 网格的 t=0 是官方音轨 0 s（= ACE tick 0）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

import numpy as np  # noqa: E402

HOP = 0.005


def midi(hz):
    return 69 + 12 * np.log2(hz / 440.0)


def main():
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    pr, rm = midi(np.load(sys.argv[2])), midi(np.load(sys.argv[3]))
    rows = []
    for n in score["notes"]:
        s, e = n["start"], n["end"]
        lo, hi = int(np.ceil((s + 0.25 * (e - s)) / HOP)), int(np.floor((s + 0.75 * (e - s)) / HOP)) + 1
        p, r = pr[lo:hi], rm[lo:hi]
        vp, vr = float(np.mean(~np.isnan(p))), float(np.mean(~np.isnan(r)))
        mp = float(np.nanmedian(p)) if vp > 0 else None
        mr = float(np.nanmedian(r)) if vr > 0 else None
        dev = None if mp is None else round(mp - n["pitch"], 2)
        dev_r = None if mr is None else round(mr - n["pitch"], 2)
        flag = ""
        if dev is not None:
            if abs(abs(dev) - 12) < 1.0:
                flag = "octave?"
            elif abs(dev) >= 1.5 and mr is not None and abs(mp - mr) < 0.5 and vp >= 0.6:
                flag = "pitch?"
        src = f"{n.get('ust_src', '')}#{n['ust_idx']}" if "ust_idx" in n else n.get("ust_src", "")
        rows.append({"idx": n["idx"], "ust": src, "tick": n["tick"], "dur": n["dur"], "pitch": n["pitch"],
                     "lyric": n["lyric"], "start": s, "end": e,
                     "ref_praat": None if mp is None else round(mp, 2), "ref_rmvpe": None if mr is None else round(mr, 2),
                     "voiced_praat": round(vp, 2), "voiced_rmvpe": round(vr, 2), "dev": dev, "dev_rmvpe": dev_r, "flag": flag})
    devs = np.array([r["dev"] for r in rows if r["dev"] is not None and not r["flag"] and r["voiced_praat"] >= 0.6])
    print(f"notes {len(rows)} | with reference pitch {sum(r['dev'] is not None for r in rows)} | "
          f"median dev {np.median(devs):+.2f} st, |dev| median {np.median(np.abs(devs)):.2f}, p90 {np.percentile(np.abs(devs), 90):.2f}")
    for r in rows:
        if r["flag"] or (r["dev"] is not None and abs(r["dev"]) >= 1.0) or r["voiced_praat"] < 0.3:
            print(f"  #{r['idx']:>3} {r['ust']:<10} {r['lyric']:<3} {r['start']:7.3f}s dur {r['dur']:>4}t pitch {r['pitch']} "
                  f"praat {r['ref_praat']} rmvpe {r['ref_rmvpe']} voiced {r['voiced_praat']}/{r['voiced_rmvpe']} dev {r['dev']} {r['flag']}")
    t0, t1 = rows[0]["start"] - 0.5, rows[-1]["end"] + 0.5
    k0, k1 = int(t0 / HOP), int(t1 / HOP)
    mask = np.zeros(len(pr), bool)
    for r in rows:
        mask[int(r["start"] / HOP):int(r["end"] / HOP)] = True
    voiced = ~np.isnan(pr)
    best = max(((int(np.sum(mask[k0:k1] & voiced[k0 + s:k1 + s])), s) for s in range(-40, 41)))
    print(f"overall offset (voicing lags notes by): {best[1] * HOP * 1000:+.0f} ms (overlap {best[0]} frames)")
    on = []
    for prev, r in zip([None] + rows[:-1], rows):
        if prev is None or r["start"] - prev["end"] >= 0.1:
            k = int(r["start"] / HOP)
            idx = np.where(voiced[k - 30:k + 31])[0]
            if len(idx):
                on.append((r["idx"], int(round((idx[0] - 30) * HOP * 1000))))
    print("phrase-start onsets (note idx, first voiced frame minus note start, ms):", on)
    json.dump({"notes": rows, "overall_offset_ms": best[1] * HOP * 1000, "phrase_onsets_ms": on},
              open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
