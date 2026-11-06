"""按明确规则给出音符音高修正候选（基线前的“谱面核对”，不是调教）。

用法：python -I note_corrections.py <note_pitch_check.json> <praat_grid.npy> <rmvpe_grid.npy> <ref_offset_sec> <octave_from_tick> <out.json>

规则：
- octave_from_tick 之后（两种提取器一致判为低八度的段落）：整体 -12。
- 其余音符只在同时满足以下条件时改音高：两种提取器差 <0.5 半音；两者有声比例 ≥0.75；
  音符中段 60% 的 F0 四分位距 ≤1 半音（稳定、不是滑音）；|参考 - 谱面| ≥2.5 半音。
  新音高 = round(参考众数 + 全局偏差)，全局偏差 = 匹配良好音符（|差|<1）上 tone-参考 的中位数。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_common  # noqa: E402,F401

import numpy as np  # noqa: E402

HOP = 0.01


def main():
    table_p, praat_p, rmvpe_p, off, oct_tick, out = sys.argv[1:7]
    off, oct_tick = float(off), int(oct_tick)
    rows = json.load(open(table_p, encoding="utf-8"))
    notes = json.load(open(table_p.replace("note_pitch_check.json", "pilot_notes_ustx_raw.json"), encoding="utf-8"))["notes"]
    with np.errstate(divide="ignore", invalid="ignore"):
        mp = 69 + 12 * np.log2(np.load(praat_p) / 440.0)
        mr = 69 + 12 * np.log2(np.load(rmvpe_p) / 440.0)
    good = [r["tone"] - r["praat_mode"] for r in rows
            if r["tick"] < oct_tick and r["praat_mode"] is not None and r["rmvpe_mode"] is not None
            and abs(r["praat_mode"] - r["rmvpe_mode"]) < 0.5 and abs(r["tone"] - r["praat_mode"]) < 1.0]
    bias = float(np.median(good))
    print(f"global bias (tone - ref) on {len(good)} well-matched notes: {bias:+.2f} semitone")
    decisions = []
    for r, n in zip(rows, notes):
        d = {"idx": r["idx"], "tick": r["tick"], "ustx_tone": r["tone"], "ustx_lyric": r["ustx_lyric"], "new_tone": r["tone"], "reason": ""}
        if r["ustx_lyric"] == "R":
            d.update(new_tone=None, reason="UTAU 休止符 R，删除")
        elif r["tick"] >= oct_tick:
            modes = [m for m in (r["praat_mode"], r["rmvpe_mode"]) if m is not None]
            ref = float(np.mean(modes)) if modes else None
            if ref is None or abs(ref - (r["tone"] - 12)) < abs(ref - r["tone"]):
                d.update(new_tone=r["tone"] - 12, reason="段落整体低八度（两种提取器一致，奇次谐波强）")
            else:
                d.update(reason=f"八度段内例外：参考 {ref:.2f} 更接近原音高 {r['tone']}，不降八度")
                print(f"#{d['idx']:>3} tick {d['tick']} {d['ustx_lyric']:<4} keeps {r['tone']} (ref {ref:.2f})")
        else:
            pm, rm = r["praat_mode"], r["rmvpe_mode"]
            if None not in (pm, rm) and abs(pm - rm) < 0.5 and r["voiced_praat"] >= 0.75 and r["voiced_rmvpe"] >= 0.75:
                ia, ib = int(round((n["start"] - off) / HOP)), int(round((n["end"] - off) / HOP))
                k = (ib - ia) // 5
                core = mp[ia + k: ib - k]
                core = core[~np.isnan(core)]
                iqr = float(np.subtract(*np.percentile(core, [75, 25]))) if len(core) >= 4 else 99.0
                ref = (pm + rm) / 2
                if iqr <= 1.0 and abs(ref - r["tone"]) >= 2.5:
                    new = int(round(ref + bias))
                    d.update(new_tone=new, reason=f"两提取器一致 {pm:.2f}/{rm:.2f}，中段 IQR {iqr:.2f}，差 {ref - r['tone']:+.2f}")
                d["core_iqr"] = round(iqr, 2)
        decisions.append(d)
        if d["new_tone"] != d["ustx_tone"] and d["tick"] < oct_tick:
            print(f"#{d['idx']:>3} tick {d['tick']} {d['ustx_lyric']:<4} {d['ustx_tone']} -> {d['new_tone']}  {d['reason']}")
    changed_oct = sum(1 for d in decisions if d["tick"] >= oct_tick and d["new_tone"] is not None)
    print(f"octave-shifted notes: {changed_oct}; removed: {sum(1 for d in decisions if d['new_tone'] is None)}")
    json.dump({"bias": bias, "octave_from_tick": oct_tick, "decisions": decisions}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
