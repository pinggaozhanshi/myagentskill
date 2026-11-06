"""音节结尾轮执行：在 r3（r2 的另存副本，ACE 里当前打开的就是它）里按 endings_plan.py 的计划改辅音长度 → 写补全的音高曲线 →
清掉整个片段的有声 / 无声固定。

用法：python -I endings_apply.py <ace_state_r2.json> <r3.acep> <endings_plan.json> <out_state_r3.json> <report.json>
顺序有讲究：vocalpitch write 会把写入当时 ACE 的有声判断固定在曲线下，所以先改辅音、再写曲线、最后把固定清成 auto，
让 ACE 按新的辅音长度自己判断。每一步读回核对：辅音长度、曲线逐点、固定段为 0；音符（位置 / 时值 / 音高 / 歌词）与 r2 相同。
ACE 读不出时长的辅音（PHONEME_TIMINGS_UNAVAILABLE：前一个音只有元音时常见，合成后也不开放）记为 deferred：
保存后关掉这个工程，用 patch_consonants.py 离线改那几个音的 headConsonants，再打开。
工程可以是本脚本上次中断时留下的未保存状态（撤销记录里只有“远程控制”的“设置辅音长度”，重写结果相同），其他情况一律退出。
（由《绯红》的 round3_apply.py 改名而来；未保存改动的检查从“打印后继续”收紧成“只认自己的辅音长度”。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import AceError, cli  # noqa: E402


def signature(st):
    nc = cli("clip", "note-content", "--track-index", st["track_index"], "--clip-index", 0)
    return sorted(((n["pos"], n["dur"], n["pitch"], n["lyric"]) for n in nc["notes"]), key=lambda x: x[0])


def main():
    st_p, r3, plan_p, out_st, rep_p = sys.argv[1:6]
    st = json.load(open(st_p, encoding="utf-8"))
    plan = json.load(open(plan_p, encoding="utf-8"))
    d = cli("project", "dirty")
    if os.path.normcase(os.path.abspath(d["projectPath"])) != os.path.normcase(os.path.abspath(r3)):
        raise SystemExit(f"当前工程不是 r3：{d}")
    if d["dirty"]:  # 只有本脚本上次中断时留下的辅音长度才接着做；别的未保存改动（尤其是用户的）一律停下
        applied = [e for e in cli("history", "list")["entries"] if e["applied"]]
        foreign = sorted({(e.get("actor"), e.get("name")) for e in applied if (e.get("actor"), e.get("name")) != ("远程控制", "设置辅音长度")})
        if foreign:
            raise SystemExit(f"r3 有不是本脚本留下的未保存改动，停止（不替用户保存或丢弃）：{foreign}")
        print("r3 has unsaved consonant-length edits from an interrupted run (resuming):", len(applied))
    before = signature(st)
    rep = {"consonants": [], "deferred": []}
    for c in plan["consonants"]:
        try:
            w = cli("phoneme", "set-consonant-timing", "--note", c["note"], "--index", c["index"], "--length", f"{c['new_ms']:.1f}ms")
        except AceError as e:
            if "PHONEME_TIMINGS_UNAVAILABLE" not in str(e):
                raise
            rep["deferred"].append(c)
            continue
        rep["consonants"].append({"idx": c["idx"], "phoneme": c["phoneme"], "new_ms": c["new_ms"], "writes": w.get("writes")})
    print("deferred (no timings until rendered):", [(c["idx"], c["phoneme"]) for c in rep["deferred"]])
    ph = cli("phoneme", "list", "--clip", st["clip_uuid"], "--range-begin", f"{st['clip_begin']}t", "--range-end", f"{st['clip_end']}t",
             "--with-timings=durations")
    by_uuid = {r["noteUuid"]: r for r in ph["notes"]}
    bad = []
    done = {c["idx"] for c in rep["consonants"]}
    for c in plan["consonants"]:
        if c["idx"] not in done:
            continue
        t = [x for x in by_uuid[c["note"]]["timings"] if not x["isVowel"]][0]
        got = (t.get("durationSec") or 0) * 1000
        if abs(got - c["new_ms"]) > 1.0:
            bad.append((c["idx"], c["new_ms"], round(got, 1)))
    rep["consonant_readback_mismatch"] = bad
    print(f"consonants written {len(rep['consonants'])} of {len(plan['consonants'])}, readback mismatches {bad}")
    tgt = plan["target_full"]
    hop, midi = tgt["hop_sec"], tgt["midi"]
    pts = []
    for a, b in tgt["runs"]:
        ia, ib = int(round(a / hop)), int(round(b / hop))
        run = [[int(round(i * hop * common.TICKS_PER_SEC)), round(midi[i], 4)] for i in range(ia, ib + 1)]
        if pts:
            pts.append([pts[-1][0] + 1, None])
        pts.extend(run)
    tmp = os.path.join(os.path.dirname(os.path.abspath(rep_p)), "round3_pitch_points.json")
    json.dump(pts, open(tmp, "w", encoding="utf-8"))
    cli("vocalpitch", "write", "--clip-uuid", st["clip_uuid"], "--points", "@" + tmp, timeout=900)
    got = cli("vocalpitch", "read", "--clip-uuid", st["clip_uuid"], "--level", "user", timeout=900).get("points", [])
    pairs = list(zip(got, pts))
    rep["pitch"] = {"anchors": len(pts), "readback": len(got),
                    "max_tick_diff": max(abs(a[0] - b[0]) for a, b in pairs if b[1] is not None),
                    "max_value_diff": max(abs(a[1] - b[1]) for a, b in pairs if a[1] is not None and b[1] is not None),
                    "gap_markers_between": all(pts[i - 1][0] < got[i][0] < pts[i + 1][0] for i, (a, b) in enumerate(pairs) if b[1] is None)}
    print("pitch:", rep["pitch"])
    span = st["clip_end"] - st["clip_begin"]
    cli("vocalpitch", "set-voicing", "--clip-uuid", st["clip_uuid"], "--begin", 0, "--end", span, "--mode", "auto")
    voi = cli("vocalpitch", "voicing", "--clip-uuid", st["clip_uuid"])
    rep["voicing_spans_after_clear"] = len(voi.get("spans", []))
    rep["unvoiced_ranges_after_clear"] = len(voi.get("unvoiced", []))
    print("voicing overrides after clearing:", rep["voicing_spans_after_clear"], "| unvoiced ranges:", rep["unvoiced_ranges_after_clear"])
    cli("project", "save")
    after = signature(st)
    rep["notes_identical_to_r2"] = before == after
    print("notes identical to r2:", rep["notes_identical_to_r2"])
    json.dump(rep, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = (not bad and rep["pitch"]["readback"] == len(pts) and rep["pitch"]["max_tick_diff"] == 0 and rep["pitch"]["max_value_diff"] < 1e-3
          and rep["pitch"]["gap_markers_between"] and rep["voicing_spans_after_clear"] == 0 and rep["notes_identical_to_r2"])
    if not ok:
        raise SystemExit("第 3 轮读回核对没通过")
    st["project"] = {"savedPath": d["projectPath"], "projectPath": d["projectPath"]}
    json.dump(st, open(out_st, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
