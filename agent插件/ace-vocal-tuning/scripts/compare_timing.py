"""两轮时值对照：被改的音符（辅音长度或句尾释放）离参考更近还是更远；没改的音符有没有被连带改变。

用法：python -I compare_timing.py <timing_a.json> <timing_b.json> <round_plan.json> <out.json>
- 辅音：比较 |合成间隙 − 参考间隙|；释放：比较后一音符的 |前一元音结束差|。差 ≥ 5 ms 才算更近 / 更远。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

import numpy as np  # noqa: E402


def main():
    a = {r["idx"]: r for r in json.load(open(sys.argv[1], encoding="utf-8"))["rows"]}
    b = {r["idx"]: r for r in json.load(open(sys.argv[2], encoding="utf-8"))["rows"]}
    plan = json.load(open(sys.argv[3], encoding="utf-8"))
    res = {"consonants": [], "releases": []}
    for c in plan["consonants"]:
        ra, rb = a.get(c["idx"]), b.get(c["idx"])
        if ra and rb and ra.get("method") and rb.get("method"):
            ea, eb = abs(ra["syn_gap_ms"] - ra["ref_gap_ms"]), abs(rb["syn_gap_ms"] - rb["ref_gap_ms"])
            res["consonants"].append({"idx": c["idx"], "phoneme": c["phoneme"], "err_a": ea, "err_b": eb})
    for r in plan["releases"]:
        k = r["idx"] + 1
        ra, rb = a.get(k), b.get(k)
        if ra and rb and ra.get("method") and rb.get("method"):
            res["releases"].append({"idx": r["idx"], "err_a": abs(ra["prev_end_delta_ms"]), "err_b": abs(rb["prev_end_delta_ms"])})
    changed = {c["idx"] for c in plan["consonants"]} | {r["idx"] + 1 for r in plan["releases"]}
    un = [(abs(a[i]["syn_gap_ms"] - a[i]["ref_gap_ms"]), abs(b[i]["syn_gap_ms"] - b[i]["ref_gap_ms"]))
          for i in a if i not in changed and a[i].get("method") and b.get(i, {}).get("method")]
    for key in ("consonants", "releases"):
        rows = res[key]
        better = sum(1 for r in rows if r["err_b"] < r["err_a"] - 5)
        worse = sum(1 for r in rows if r["err_b"] > r["err_a"] + 5)
        if rows:
            print(f"{key}: {len(rows)} measured | closer {better} | further {worse} | "
                  f"|err| median {np.median([r['err_a'] for r in rows]):.1f} -> {np.median([r['err_b'] for r in rows]):.1f} ms")
        for r in rows:
            if r["err_b"] > r["err_a"] + 5:
                print(f"  further: #{r['idx']} {r.get('phoneme', 'release')} {r['err_a']:.0f} -> {r['err_b']:.0f} ms")
    if un:
        d = np.array([y - x for x, y in un])
        print(f"unchanged notes: {len(un)} | |gap err| median {np.median([x for x, _ in un]):.1f} -> {np.median([y for _, y in un]):.1f} ms | "
              f"changed by >10 ms: {int(np.sum(np.abs(d) > 10))}")
    json.dump(res, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
