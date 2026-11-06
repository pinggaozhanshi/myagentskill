"""第 3 轮（表情参数）目标：按音区解出力度、张力、气声、假声四个倍率，再展开成逐 tick 曲线。

用法：python -I round3_targets.py <score_v2_main.json> <feat_dir> <calib_analysis.json> <out_dir>
规则（运行前定死）：
1. 差 = 原唱 − r2（逐音符中位，只用两边都有声的帧）。各组（solo0 / solo1 / duet）先扣掉自己在 F#4–B4（66–71）上的差：
   这一段音符最多，歌手音色、混音均衡、齐唱造成的整体差都在这里扣掉，所以 F#4–B4 本身定为不改（倍率 1）。
2. 响度只在“高低顺序反了”的音区才当目标：原唱的人声压缩过，压缩只会把响的压轻、不会颠倒顺序；
   某音区在原唱里比 F#4–B4 响、在 r2 里却比它轻（或反过来），才认为是演唱差异。否则响度目标 = 0。
3. 每个音区用标定得到的灵敏度（dB / ln 倍率，按升、降方向分开）做有界最小二乘：
   权重 响度 1、明暗 0.5、H1−H2 0.5、谐噪比 0.3、高频 0；只追 70% 的差；倍率限制在标定过的 ×0.67–×1.5 之内；
   另加 λ=10 的小惩罚，没有证据的参数不动。
   高频（5–12 kHz）不用：原唱混音里的去齿音器会随齿音动态压低这一段，独唱组里它和 r2 的相关还是负的（−0.50）。
4. 逐音符倍率按音高在各音区中心之间线性插值（相邻音区不跳变）；时间上音符之间线性过渡，再做 40 ms 平滑。
5. 稳健性：另用 4 组权重重解一遍（记在 robustness 里）；某参数在任一组里与第一次解的方向相反（两边都超过 ±5%），
   就认为证据不足，固定为倍率 1，其余参数重解。
6. 修正一步（可选第 5 个参数 = 上一版的 round3_eval.json）：四个参数一起改时效果不是简单相加，
   用上一版“实测 − 预测”的差把目标挪回去再解一次（目标′ = 目标 − 模型误差），相当于按实测结果校正一次。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
import note_features as nf  # noqa: E402

import numpy as np  # noqa: E402
from scipy.optimize import lsq_linear  # noqa: E402

PARAMS = ["energy", "tension", "air", "falsetto"]
FEATS = ["rms_db", "alpha_db", "h1h2_db", "hnr_db", "hf_db"]
WEIGHT = {"rms_db": 1.0, "alpha_db": 0.5, "h1h2_db": 0.5, "hnr_db": 0.3, "hf_db": 0.0}
VARIANTS = {"含高频": {**WEIGHT, "hf_db": 0.3}, "不含谐噪比": {**WEIGHT, "hnr_db": 0.0},
            "只用明暗与H1-H2": {**WEIGHT, "hnr_db": 0.0}, "只用明暗": {**WEIGHT, "h1h2_db": 0.0, "hnr_db": 0.0}}
VARIANTS["只用明暗与H1-H2"]["rms_db"] = 0.0
CLOSE, LAMBDA = 0.7, 10.0
LO, HI = np.log(0.67), np.log(1.5)
ANCHOR = (66, 71)
# 音区 → 标定时的音区名
REGS = [("G3-B3", 55, 59, "G3-E4"), ("C4-E4", 60, 64, "G3-E4"), ("F#4-B4", 66, 71, "F#4-B4"),
        ("D5", 74, 74, "D5"), ("F#5-G5", 78, 79, "F#5-G5")]
SMOOTH_TICKS = 39  # 40 ms


def med(v):
    v = [x for x in v if x is not None]
    return float(np.median(v)) if v else None


def solve(S_up, S_dn, target, w, free=None):
    """有界加权最小二乘，升 / 降方向用不同灵敏度；迭代到方向不变。free：可动的参数（其余固定为倍率 1）。"""
    free = np.ones(len(PARAMS), bool) if free is None else np.asarray(free, bool)
    x = np.zeros(len(PARAMS))
    sign = np.zeros(len(PARAMS))
    for _ in range(6):
        S = np.where(sign[None, :] >= 0, S_up, S_dn)[:, free]
        lo = np.where(sign > 0, 0.0, LO)[free]
        hi = np.where(sign < 0, 0.0, HI)[free]
        A = np.vstack([np.sqrt(w)[:, None] * S, np.sqrt(LAMBDA) * np.eye(int(free.sum()))])
        b = np.concatenate([np.sqrt(w) * target, np.zeros(int(free.sum()))])
        x = np.zeros(len(PARAMS))
        x[free] = lsq_linear(A, b, bounds=(lo, hi)).x
        new = np.sign(np.where(np.abs(x) < 1e-6, 0, x))
        if np.array_equal(new, sign):
            break
        sign = new
    S = np.where(x[None, :] >= 0, S_up, S_dn)
    return x, S @ x


def main():
    score_p, fdir, calib_p, out = sys.argv[1:5]
    prev = json.load(open(sys.argv[5], encoding="utf-8")) if len(sys.argv) > 5 else None
    os.makedirs(out, exist_ok=True)
    s, notes = nf.load_score(score_p)
    fr = nf.load_feats(os.path.join(fdir, "feat_ref.npz"))
    f2 = nf.load_feats(os.path.join(fdir, "feat_r2.npz"))
    calib = json.load(open(calib_p, encoding="utf-8"))["params"]
    gap = nf.per_note(notes, f2, fr)
    ref_abs, r2_abs = nf.per_note(notes, fr), nf.per_note(notes, f2)

    anchor = {}
    for g in ("solo0", "solo1", "duet"):
        ii = [i for i, n in enumerate(notes) if n["group"] == g and gap[i] and ANCHOR[0] <= n["pitch"] <= ANCHOR[1]]
        anchor[g] = {k: med([gap[i][k] for i in ii]) for k in FEATS}
        anchor[g]["ref_rms"] = med([ref_abs[i]["rms_db"] for i in ii if ref_abs[i]])
        anchor[g]["r2_rms"] = med([r2_abs[i]["rms_db"] for i in ii if r2_abs[i]])

    res = {"rules": __doc__, "anchor_by_group": anchor, "registers": {}}
    centers, lnm = [], []
    for name, lo, hi, creg in REGS:
        ii = [i for i, n in enumerate(notes) if gap[i] and lo <= n["pitch"] <= hi]
        tgt = {k: med([gap[i][k] - anchor[notes[i]["group"]][k] for i in ii if gap[i][k] is not None]) for k in FEATS}
        # 响度顺序检验（只看有锚点的独唱组音符，与各自组的锚点比）
        dref = med([ref_abs[i]["rms_db"] - anchor[notes[i]["group"]]["ref_rms"] for i in ii if ref_abs[i]])
        dr2 = med([r2_abs[i]["rms_db"] - anchor[notes[i]["group"]]["r2_rms"] for i in ii if r2_abs[i]])
        order_reversed = bool(dref is not None and dr2 is not None and np.sign(dref) != np.sign(dr2) and abs(dref - dr2) > 2.0)
        rec = {"n": len(ii), "mean_pitch": float(np.mean([notes[i]["pitch"] for i in ii])), "target_full": tgt,
               "rms_vs_anchor": {"ref": dref, "r2": dr2, "order_reversed": order_reversed}}
        if (lo, hi) == ANCHOR:
            x, pred = np.zeros(len(PARAMS)), np.zeros(len(FEATS))
            rec["note"] = "锚点音区，按定义不改"
        else:
            t = np.array([CLOSE * (tgt[k] or 0.0) for k in FEATS])
            if not order_reversed:
                t[FEATS.index("rms_db")] = 0.0
            if prev is not None:
                err = np.array([(prev["r3_minus_r2"][name][k] or 0.0) - prev["predicted"][name][k] for k in FEATS])
                rec["model_error_prev"] = dict(zip(FEATS, map(float, err)))
                t = t - err
            S_up = np.array([[calib[p]["x1.50"][creg][k] for p in PARAMS] for k in FEATS])
            S_dn = np.array([[calib[p]["x0.67"][creg][k] for p in PARAMS] for k in FEATS])
            w = np.array([WEIGHT[k] for k in FEATS])
            x0, _ = solve(S_up, S_dn, t, w)
            rec["target_used"] = dict(zip(FEATS, map(float, t)))
            rec["first_solution"] = {p: round(float(np.exp(v)), 3) for p, v in zip(PARAMS, x0)}
            rec["robustness"] = {}
            flip = np.zeros(len(PARAMS), bool)
            for vn, wd in VARIANTS.items():
                xv, _ = solve(S_up, S_dn, t, np.array([wd[k] for k in FEATS]))
                rec["robustness"][vn] = {p: round(float(np.exp(v)), 3) for p, v in zip(PARAMS, xv)}
                f = (xv * x0 < 0) & (np.abs(xv) > 0.05) & (np.abs(x0) > 0.05)
                if wd["rms_db"] == 0:
                    f[PARAMS.index("energy")] = False  # 不约束响度时力度可以随便取，它的方向不代表证据
                flip |= f
            # 方向随权重翻转的参数证据不足：固定为 1，其余参数重解
            rec["fixed_by_robustness"] = [p for p, f in zip(PARAMS, flip) if f]
            x, pred = solve(S_up, S_dn, t, w, free=~flip)
        rec["multiplier"] = {p: round(float(np.exp(v)), 3) for p, v in zip(PARAMS, x)}
        rec["predicted_change_db"] = dict(zip(FEATS, [round(float(v), 2) for v in pred]))
        res["registers"][name] = rec
        centers.append(rec["mean_pitch"])
        lnm.append(x)
        print(f"{name:7s} n={len(ii):3d} order_rev={order_reversed!s:5s} mult " +
              " ".join(f"{p}={np.exp(v):.2f}" for p, v in zip(PARAMS, x)) +
              " | target " + " ".join(f"{k[:-3]}={rec.get('target_used', {}).get(k, 0):+.1f}" for k in FEATS) +
              " | pred " + " ".join(f"{k[:-3]}={v:+.1f}" for k, v in zip(FEATS, pred)))
        if "first_solution" in rec:
            print(f"          first solve  " + " ".join(f"{p}={rec['first_solution'][p]:.2f}" for p in PARAMS) +
                  f"  -> fixed at 1 (direction flips across weightings): {rec['fixed_by_robustness']}")
        for vn, m in rec.get("robustness", {}).items():
            print(f"          {vn:12s} " + " ".join(f"{p}={m[p]:.2f}" for p in PARAMS))

    centers, lnm = np.array(centers), np.array(lnm)
    order = np.argsort(centers)
    centers, lnm = centers[order], lnm[order]
    note_ln = np.array([[np.interp(n["pitch"], centers, lnm[:, j]) for j in range(len(PARAMS))] for n in notes])
    # 逐 tick 曲线（片段内 tick），ln 域：音符内常数，音符之间线性过渡，两端保持
    clip_len = s["meta"]["clip_end_tick"] - s["meta"]["clip_start_tick"]
    ticks = np.arange(clip_len)
    curves = {}
    for j, p in enumerate(PARAMS):
        xs, ys = [], []
        for n, v in zip(notes, note_ln[:, j]):
            xs += [n["pos"], n["pos"] + n["dur"] - 1]
            ys += [v, v]
        c = np.interp(ticks, xs, ys)
        k = np.ones(SMOOTH_TICKS) / SMOOTH_TICKS
        c = np.convolve(np.pad(c, SMOOTH_TICKS // 2, mode="edge"), k, mode="valid")[:clip_len]
        curves[p] = np.exp(c)
    np.savez_compressed(os.path.join(out, "r3_multipliers.npz"), **curves)
    res["per_note"] = [{"idx": n["idx"], "lyric": n["lyric"], "pitch": n["pitch"], "start": n["start"],
                        **{p: round(float(np.exp(v)), 3) for p, v in zip(PARAMS, row)}} for n, row in zip(notes, note_ln)]
    for p in PARAMS:
        v = np.array([r[p] for r in res["per_note"]])
        print(f"{p:9s} per-note multiplier: min {v.min():.2f} median {np.median(v):.2f} max {v.max():.2f}; notes changed >5%: {int(np.sum(np.abs(np.log(v)) > np.log(1.05)))}")
    json.dump(res, open(os.path.join(out, "r3_targets.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
