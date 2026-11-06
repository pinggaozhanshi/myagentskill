"""读回一个片段的 V1 表情参数（气声、假声、张力、力度）各层，存成 npz 并打印摘要（只读，不改工程）。

用法：python -I param_read.py <ace_state.json> <out.npz> [--second]
每个参数存：baseline（AI 生成值）、envelope（倍率，默认 1）、direct（绝对值覆盖，未画 = NaN）、effective（引擎合成用的最终值）；
另存 posBegin（片段内 tick）、unvoiced 区间。dense 层一 tick 一个值。
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402

import numpy as np  # noqa: E402

PARAMS = ["energy", "tension", "air", "falsetto"]


def decode(points):
    if isinstance(points, dict):
        a = np.frombuffer(base64.b64decode(points["data"]), dtype="<f8").copy()
        if len(a) != points["count"]:
            raise SystemExit("base64 长度与 count 不符")
        return a
    return np.array([np.nan if v is None else v for v in points], dtype=float)


def read_param(clip_uuid, param):
    r = cli("vocalparam", "read", "--clip-uuid", clip_uuid, "--param", param, "--encoding", "base64", timeout=300)
    out = {"posBegin": r["posBegin"], "count": r["count"], "fingerprint": r.get("fingerprint"),
           "unvoiced": r.get("unvoiced", []), "valueRange": r.get("valueRange"), "scale": r.get("scale")}
    for lay in r["layers"]:
        out[lay["layer"]] = decode(lay["points"]) if lay.get("shape") == "dense" else lay.get("points")
        if lay.get("drawnRanges") is not None:
            out[lay["layer"] + "_drawn"] = lay["drawnRanges"]
    if "effective" in r and r["effective"] is not None:
        eff = r["effective"]
        out["effective"] = decode(eff["points"] if isinstance(eff, dict) and "points" in eff else eff)
    return out


def main():
    st = json.load(open(sys.argv[1], encoding="utf-8"))
    out_p = sys.argv[2]
    clip = st["second_clip_uuid"] if "--second" in sys.argv else st["clip_uuid"]
    save, meta = {}, {}
    for p in PARAMS:
        d = read_param(clip, p)
        meta[p] = {k: d[k] for k in ("posBegin", "count", "fingerprint", "unvoiced", "valueRange", "scale")}
        meta[p]["direct_drawn"] = d.get("direct_drawn")
        for lay in ("baseline", "envelope", "direct", "effective"):
            if isinstance(d.get(lay), np.ndarray):
                save[f"{p}_{lay}"] = d[lay]
        voiced = np.ones(d["count"], bool)
        for rg in d["unvoiced"]:
            a, b = (rg["begin"], rg["end"]) if isinstance(rg, dict) else rg
            voiced[max(0, a - d["posBegin"]):max(0, b - d["posBegin"])] = False
        save[f"{p}_voiced"] = voiced
        b, e = d.get("baseline"), d.get("envelope")
        line = [f"{p:9s} posBegin={d['posBegin']} count={d['count']} voiced={voiced.mean():.2f}"]
        for name, a in (("baseline", b), ("envelope", e), ("effective", d.get("effective"))):
            if isinstance(a, np.ndarray):
                v = a[voiced & np.isfinite(a)]
                line.append(f"{name}: p5 {np.percentile(v, 5):.3f} med {np.median(v):.3f} p95 {np.percentile(v, 95):.3f}" if len(v) else f"{name}: empty")
        dr = d.get("direct")
        line.append(f"direct drawn ticks: {int(np.isfinite(dr).sum()) if isinstance(dr, np.ndarray) else 'n/a'}")
        print(" | ".join(line))
    np.savez_compressed(out_p, **save)
    json.dump(meta, open(out_p.replace(".npz", "_meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved", out_p)


if __name__ == "__main__":
    main()
