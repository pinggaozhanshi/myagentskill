"""第 3 轮某一版的实测：被改的交界 / 长音，相对锁定对照的断开、尾部变化，与预测、目标比较，供 r3_solve.py 校正一次。

用法：python -I r3_measure_round.py <calib_analysis.json> <crisp_round.json> <round_label> <options.json> <out.json>
crisp_round.json 是 crisp_metrics.py 的输出，里面要有 round_label 那一列。
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from r3_solve import quarter_lnm  # noqa: E402

import numpy as np  # noqa: E402


def main():
    cal_p, crisp_p, label, opt_p, out_p = sys.argv[1:6]
    cal = json.load(open(cal_p, encoding="utf-8"))
    ctrl = {r["idx"]: r for r in cal["rows"][cal["control"]]}
    got = {r["idx"]: r for r in json.load(open(crisp_p, encoding="utf-8"))["rows"][label]}
    opt = json.load(open(opt_p, encoding="utf-8"))
    want = {("dips", d["idx"]): d["want"] for d in opt["detail"]["dips"]}
    want.update({("tails", d["idx"]): d["want"] for d in opt["detail"]["tails"]})
    res = {"dips": {}, "tails": {}, "ratio": {}}
    for kind, key in (("dips", "dip_db"), ("tails", "tail_decay_db")):
        ratios = []
        for i in map(int, opt[kind]):
            a, b = ctrl.get(i, {}).get(key), got.get(i, {}).get(key)
            if a is None or b is None:
                continue
            res[kind][str(i)] = round(b - a, 2)
            w = want[(kind, i)]
            ratios.append((b - a) / w if abs(w) > 1e-6 else np.nan)
        res["ratio"][kind] = {"n": len(ratios), "achieved_over_wanted_median": round(float(np.nanmedian(ratios)), 2),
                              "p25": round(float(np.nanpercentile(ratios, 25)), 2), "p75": round(float(np.nanpercentile(ratios, 75)), 2)}
    # 没改的交界 / 音有没有被连带改变
    touched = {int(i) for i in opt["dips"]} | {int(i) for i in opt["tails"]}
    side = [abs(got[i]["dip_db"] - c["dip_db"]) for i, c in ctrl.items()
            if i not in touched and c.get("dip_db") is not None and got.get(i, {}).get("dip_db") is not None]
    res["untouched_dip_abs_change_median"] = round(float(np.median(side)), 2) if side else None
    json.dump(res, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ("dips", "tails")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
