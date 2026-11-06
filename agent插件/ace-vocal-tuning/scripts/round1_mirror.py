"""第 1 轮照抄到和声轨：和声与主唱同位置、同歌词的音，辅音长度设成主唱第 1 轮的新值；主唱改过释放（音符终点）的，
和声里同位置、同原时值的音也改成同样的时值（不与后一个和声音重叠）。两条轨的辅音、收尾因此对齐。

用法：python -I round1_mirror.py <ace_state.json> <round1_plan.json> <out_mirror.json>
当前 ACE 工程必须是已保存、已应用主唱第 1 轮的工程（round1_timing.py --apply 之后）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402


def main():
    st_p, plan_p, out_p = sys.argv[1:4]
    st = json.load(open(st_p, encoding="utf-8"))
    plan = json.load(open(plan_p, encoding="utf-8"))
    d = cli("project", "dirty")
    if d["dirty"]:
        raise SystemExit(f"当前工程有未保存改动：{d}")
    c0 = st["clip_begin"]
    main_nc = {n["noteUuid"]: n for n in cli("clip", "note-content", "--track-index", st["track_index"], "--clip-index", 0)["notes"]}
    har = sorted(cli("clip", "note-content", "--track-index", st["second_track_index"], "--clip-index", 0)["notes"], key=lambda n: n["pos"])
    by_pos = {n["pos"]: n for n in har}
    ph = cli("phoneme", "list", "--clip", st["second_clip_uuid"], "--range-begin", f"{c0}t", "--range-end", f"{st['clip_end']}t",
             "--with-timings=durations")
    cons = {}
    for n in ph["notes"]:
        c = [t for t in n.get("timings", []) if not t["isVowel"]]
        if c:
            cons[n["pos"]] = (n["noteUuid"], c[0]["index"], c[0]["name"])
    out = {"consonants": [], "releases": [], "skipped": []}
    for c in plan["consonants"]:
        m = main_nc.get(c["note"])
        h = by_pos.get(m["pos"]) if m else None
        if h is None or h["lyric"] != m["lyric"] or m["pos"] not in cons:
            out["skipped"].append({"main_idx": c["idx"], "why": "和声没有同位置同歌词的音"})
            continue
        uuid, index, name = cons[m["pos"]]
        if name != c["phoneme"]:
            out["skipped"].append({"main_idx": c["idx"], "why": f"辅音不同：{name} vs {c['phoneme']}"})
            continue
        w = cli("phoneme", "set-consonant-timing", "--note", uuid, "--index", index, "--length", f"{c['new_ms']:.1f}ms")
        out["consonants"].append({"main_idx": c["idx"], "pos": m["pos"], "phoneme": name, "new_ms": c["new_ms"], "write": w.get("writes")})
    for r in plan["releases"]:
        m = main_nc.get(r["note"])
        h = by_pos.get(m["pos"]) if m else None
        if h is None or h["dur"] != r["cur_dur"]:
            out["skipped"].append({"main_idx": r["idx"], "why": "和声没有同位置、同原时值的音"})
            continue
        nxt = next((n for n in har if n["pos"] > h["pos"]), None)
        if nxt is not None and h["pos"] + r["new_dur"] > nxt["pos"]:
            out["skipped"].append({"main_idx": r["idx"], "why": "改后会与后一个和声音重叠"})
            continue
        out["releases"].append({"main_idx": r["idx"], "pos": h["pos"], "new_dur": r["new_dur"],
                                "write": cli("note", "resize", "--note-uuid", h["noteUuid"], "--dur", f"{r['new_dur']}t")})
    cli("project", "save")
    json.dump(out, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("mirrored", len(out["consonants"]), "consonants,", len(out["releases"]), "releases; skipped", len(out["skipped"]), out["skipped"])


if __name__ == "__main__":
    main()
