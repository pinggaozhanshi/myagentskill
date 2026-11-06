"""第 3 轮标定结果：每个只改一处的变体相对锁定对照（cal_control）的逐音符变化，换算成灵敏度。

用法：python -I r3_calib_analysis.py <pilot_score.json> <g2p_japanese.json> <out.json> <label>=<wav>,<features.npz> ...
第一个 label 必须是对照（cal_control）。另需 r2=…：对照与 r2 的差就是“锁定 + 重渲”的噪声底。
度量与 crisp_metrics.py 相同（逐音符的内部电平 L、起音、收音、断开、平稳、尾部衰减、亮度 alpha、hf、h1h2、hnr）。
灵敏度 = 变化的中位数 / ln(倍率)，倍率从 label 末尾的 _x<倍率> 读。
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import crisp_metrics as cm  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

KEYS = ["L", "attack_ms", "release_ms", "dip_db", "interior_std_db", "tail_decay_db", "alpha_db", "hf_db", "h1h2_db", "hnr_db"]


def main():
    score_p, g2p_p, out = sys.argv[1:4]
    score = json.load(open(score_p, encoding="utf-8"))
    clip0 = score["meta"]["clip_start_tick"]
    notes = [dict(n, a=common.t2s(n["tick"] - clip0), b=common.t2s(n["tick"] + n["dur"] - clip0)) for n in score["notes"]]
    heads = {s["index"]: (s["headConsonants"] or [""])[0] for s in json.load(open(g2p_p, encoding="utf-8"))["syllables"]}
    heads = [heads.get(k, "") for k in range(len(notes))]
    rows = {}
    for item in sys.argv[4:]:
        label, paths = item.split("=", 1)
        wav, npz = paths.split(",")
        x, sr = sf.read(wav, always_2d=True)
        rows[label] = cm.measure(cm.envelope(x.mean(axis=1), sr), notes, heads, dict(np.load(npz)))
    labels = list(rows)
    ctrl = labels[0]
    res = {"control": ctrl, "variants": {}}
    for lab in labels[1:]:
        d = {}
        for k in KEYS:
            pair = [(a[k], b[k]) for a, b in zip(rows[ctrl], rows[lab]) if a.get(k) is not None and b.get(k) is not None]
            if pair:
                dd = np.array([y - x for x, y in pair])
                d[k] = {"n": len(pair), "median": round(float(np.median(dd)), 2), "p25": round(float(np.percentile(dd, 25)), 2),
                        "p75": round(float(np.percentile(dd, 75)), 2)}
        m = re.search(r"_x([0-9.]+)$", lab)
        if m:
            ln = math.log(float(m.group(1)))
            d["per_ln"] = {k: round(v["median"] / ln, 2) for k, v in d.items() if isinstance(v, dict) and "median" in v}
        if lab.startswith("cal_dips"):
            d["dip_by_boundary"] = {str(a["idx"]): round(b["dip_db"] - a["dip_db"], 2)
                                    for a, b in zip(rows[ctrl], rows[lab]) if a.get("dip_db") is not None and b.get("dip_db") is not None}
        res["variants"][lab] = d
        print(lab, "|", " ".join(f"{k}={v['median']:+.2f}" for k, v in d.items() if isinstance(v, dict) and "median" in v))
        if "per_ln" in d:
            print("   per ln:", d["per_ln"])
    res["rows"] = rows
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
