"""第 3 轮测量：r3 相对 r2 的逐音符特征变化（按音区），和标定预测比；锁定是否干净（倍率为 1 的音区应与 r2 相同）；
以及“原唱 − 合成”的音区差（扣掉各组 F#4–B4 的整体差）在 r2 / r3 各剩多少。都是信号指标，不是听感。

用法：python -I round3_eval.py <score_v2_main.json> <feat_dir> <r3_targets.json> <out.json> [label] [control]
feat_dir 里要有 feat_ref.npz、feat_r2.npz、feat_<label>.npz（默认 r3）、feat_<control>.npz（默认 calib_control_all1）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
import note_features as nf  # noqa: E402

import numpy as np  # noqa: E402

REGS = [("G3-B3", 55, 59), ("C4-E4", 60, 64), ("F#4-B4", 66, 71), ("D5", 74, 74), ("F#5-G5", 78, 79)]
KEYS = ["rms_db", "alpha_db", "h1h2_db", "hnr_db", "hf_db", "f0_cents"]


def med(v):
    v = [x for x in v if x is not None]
    return round(float(np.median(v)), 2) if v else None


def anchored_gap(notes, gap):
    off = {}
    for g in ("solo0", "solo1", "duet"):
        ii = [i for i, n in enumerate(notes) if n["group"] == g and gap[i] and 66 <= n["pitch"] <= 71]
        off[g] = {k: med([gap[i][k] for i in ii]) for k in nf.FEATS}
    out = {}
    for name, lo, hi in REGS:
        ii = [i for i, n in enumerate(notes) if gap[i] and lo <= n["pitch"] <= hi]
        out[name] = {k: med([gap[i][k] - off[notes[i]["group"]][k] for i in ii if gap[i][k] is not None]) for k in nf.FEATS}
    return out


def main():
    score_p, fdir, tgt_p, out_p = sys.argv[1:5]
    label = sys.argv[5] if len(sys.argv) > 5 else "r3"
    control = sys.argv[6] if len(sys.argv) > 6 else "calib_control_all1"
    _, notes = nf.load_score(score_p)
    F = {k: nf.load_feats(os.path.join(fdir, f"feat_{k}.npz")) for k in ("ref", "r2", label, control)}
    F["r3"], F["calib_control_all1"] = F[label], F[control]
    tg = json.load(open(tgt_p, encoding="utf-8"))["registers"]
    d23 = nf.per_note(notes, F["r2"], F["r3"])
    dctl = nf.per_note(notes, F["r2"], F["calib_control_all1"])
    res = {"r3_minus_r2": {}, "predicted": {}, "control_minus_r2_abs": {}, "r3_minus_r2_abs": {}}
    print("register   n | r3 − r2 (median per note)                               | predicted")
    for name, lo, hi in REGS:
        ii = [i for i, n in enumerate(notes) if d23[i] and lo <= n["pitch"] <= hi]
        res["r3_minus_r2"][name] = {k: med([d23[i][k] for i in ii]) for k in KEYS}
        res["r3_minus_r2_abs"][name] = {k: med([abs(d23[i][k]) for i in ii if d23[i][k] is not None]) for k in KEYS}
        res["control_minus_r2_abs"][name] = {k: med([abs(dctl[i][k]) for i in ii if dctl[i] and dctl[i][k] is not None]) for k in KEYS}
        res["predicted"][name] = tg[name]["predicted_change_db"]
        a = res["r3_minus_r2"][name]
        print(f"{name:7s} {len(ii):3d} | " + " ".join(f"{k[:-3] if k.endswith('_db') else k}={a[k]:+5.1f}" for k in KEYS) +
              " | " + " ".join(f"{k[:-3]}={v:+5.1f}" for k, v in tg[name]["predicted_change_db"].items()))
    print("\nlock check (register with multiplier 1): |r3 − r2| per note median", res["r3_minus_r2_abs"]["F#4-B4"],
          "\n   vs earlier unlocked control re-render |control − r2|:", res["control_minus_r2_abs"]["F#4-B4"])
    g2 = anchored_gap(notes, nf.per_note(notes, F["r2"], F["ref"]))
    g3 = anchored_gap(notes, nf.per_note(notes, F["r3"], F["ref"]))
    res["anchored_gap_ref_minus_r2"], res["anchored_gap_ref_minus_r3"] = g2, g3
    print("\nanchored gap (ref − synth − group F#4–B4 gap): r2 -> r3")
    for name, *_ in REGS:
        print(f"{name:7s} " + " ".join(f"{k[:-3]}: {g2[name][k]:+5.1f} -> {g3[name][k]:+5.1f}" for k in nf.FEATS))
    json.dump(res, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
