"""第 3 轮（“干脆”）求解：由标定灵敏度算出每个交界的凹陷倍率、每个长音的尾部倍率，写成 r3_targets.py 的 shape 选项。

用法：python -I r3_solve.py <calib_analysis.json> <crisp_refs.json> <out_options.json> [<measured_round.json> <prev_options.json>]
规则（运行前定死）：
- 目标 = 两份参考的平均：去混响分离（会放大断开 / 衰减）与原样分离（叠着低八度和混响，会填平它们）各有偏差，取中间。
- 只追 70% 的差；差不到 2 dB 的不改；只往“更断开 / 更收”的方向改。
- 断开：凹陷最低点倍率 d = exp(Δ / r)，r 是该交界在标定（×0.5）里实测的 dB/ln；实测 r < 3 时用全体中位数。d 不低于 0.3。
- 尾部：音长 25% 处到结尾力度从 1 线性降到 e；用整段力度标定的 16.7 dB/ln（慢变化）预测
  “后 25% − 前 25%”（crisp_metrics 的 20%–90% 窗口）的变化，二分求 e，不低于 0.35。
- 已经够“断”/够“收”的不动（看到第一版解之后、渲染之前补的）：当前凹陷已低于 -15 dB、尾部已衰减超过 12 dB 的，
  都接近静音（多是浊辅音闭塞或提前收尾的音），再压只添风险。
- 张力、气声、假声不改（理由见 docs/round3-crisp-report.md）。
校正（给出 measured_round.json 与上一版选项时）：对每个交界 / 长音，按“实测变化 / 预测变化”修正一次灵敏度后重解。
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

import numpy as np  # noqa: E402

TRACK = 0.7
MIN_GAP = 2.0
DIP_FLOOR, TAIL_FLOOR = 0.3, 0.35
DIP_SKIP_BELOW, TAIL_SKIP_BELOW = -15.0, -12.0


def quarter_lnm(e):
    """尾部斜坡（25%→100% 从 1 降到 e）在 crisp_metrics 窗口前 25%、后 25% 的平均 ln 倍率之差。"""
    t = np.linspace(0, 1, 2001)
    m = np.where(t < 0.25, 1.0, 1 - (1 - e) * (t - 0.25) / 0.75)
    lnm = np.log(m)
    first = (t >= 0.2) & (t < 0.375)
    last = (t >= 0.725) & (t < 0.9)
    return float(lnm[last].mean() - lnm[first].mean())


def solve_tail(delta, s):
    lo, hi = TAIL_FLOOR, 1.0
    if s * quarter_lnm(lo) > delta:  # 到下限也不够
        return lo
    for _ in range(50):
        mid = (lo + hi) / 2
        if s * quarter_lnm(mid) > delta:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def main():
    cal_p, refs_p, out_p = sys.argv[1:4]
    meas = json.load(open(sys.argv[4], encoding="utf-8")) if len(sys.argv) > 5 else None
    prev = json.load(open(sys.argv[5], encoding="utf-8")) if len(sys.argv) > 5 else None
    cal = json.load(open(cal_p, encoding="utf-8"))
    refs = json.load(open(refs_p, encoding="utf-8"))["rows"]
    ctrl = {r["idx"]: r for r in cal["rows"][cal["control"]]}
    ref = {r["idx"]: r for r in refs["ref"]}
    mix = {r["idx"]: r for r in refs["refmix"]}
    resp = {int(k): v / math.log(0.5) for k, v in cal["variants"]["cal_dips_x0.5"]["dip_by_boundary"].items()}
    r_med = float(np.median(list(resp.values())))
    s_tail = cal["variants"]["cal_energy_x0.67"]["per_ln"]["L"]
    plan = {"dips": {}, "tails": {}, "tension": {"f": 1.0}, "detail": {"dips": [], "tails": []},
            "rules": {"track": TRACK, "min_gap_db": MIN_GAP, "dip_floor": DIP_FLOOR, "tail_floor": TAIL_FLOOR,
                      "dip_skip_below_db": DIP_SKIP_BELOW, "tail_skip_below_db": TAIL_SKIP_BELOW,
                      "dip_resp_median_db_per_ln": round(r_med, 2), "tail_sens_db_per_ln": s_tail}}

    def target(key, i):
        v = [d[i].get(key) for d in (ref, mix) if i in d and d[i].get(key) is not None]
        return float(np.mean(v)) if v else None

    for i, c in ctrl.items():
        cur = c.get("dip_db")
        t = target("dip_db", i)
        if cur is None or t is None or t - cur > -MIN_GAP or cur < DIP_SKIP_BELOW:
            continue
        delta = TRACK * (t - cur)
        r = resp.get(i, r_med)
        r = r if r >= 3 else r_med
        if meas is not None and str(i) in prev["dips"]:
            got = meas["dips"].get(str(i))  # 上一版实测的断开变化（dB）
            pred = r * math.log(prev["dips"][str(i)])
            if got is not None and pred < -0.5 and got < -0.5:
                r = r * got / pred
        d = max(DIP_FLOOR, min(1.0, math.exp(delta / r)))
        plan["dips"][str(i)] = round(d, 4)
        plan["detail"]["dips"].append({"idx": i, "cur": round(cur, 2), "target": round(t, 2), "want": round(delta, 2),
                                       "resp": round(r, 2), "depth": round(d, 3)})
    for i, c in ctrl.items():
        cur = c.get("tail_decay_db")
        t = target("tail_decay_db", i)
        if cur is None or t is None or t - cur > -MIN_GAP or cur < TAIL_SKIP_BELOW:
            continue
        delta = TRACK * (t - cur)
        s = s_tail
        if meas is not None and str(i) in prev["tails"]:
            got = meas["tails"].get(str(i))
            pred = s_tail * quarter_lnm(prev["tails"][str(i)])
            if got is not None and pred < -0.5 and got < -0.5:
                s = s_tail * got / pred
        e = solve_tail(delta, s)
        plan["tails"][str(i)] = round(e, 4)
        plan["detail"]["tails"].append({"idx": i, "cur": round(cur, 2), "target": round(t, 2), "want": round(delta, 2),
                                        "sens": round(s, 2), "end": round(e, 3), "pred": round(s * quarter_lnm(e), 2)})
    json.dump(plan, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    dd = [x["depth"] for x in plan["detail"]["dips"]]
    ee = [x["end"] for x in plan["detail"]["tails"]]
    print(f"dips: {len(dd)} boundaries, depth median {np.median(dd) if dd else None:.3f}, min {min(dd) if dd else None}")
    print(f"tails: {len(ee)} notes, end median {np.median(ee) if ee else None:.3f}, min {min(ee) if ee else None}")


if __name__ == "__main__":
    main()
