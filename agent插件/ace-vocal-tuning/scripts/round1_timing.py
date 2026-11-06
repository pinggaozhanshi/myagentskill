"""第 1 轮（时值）：只改清声母的辅音长度与句尾释放；歌词、音高、参数不动。

用法：python -I round1_timing.py <ace_state.json> <timing_r0.json> <pilot_score.json> <save_as.acep> <out_plan.json> [--apply] [--skip <序号,...>]
--skip：人工排除的音（谱面 idx），它的辅音长度和时值（句尾释放）都不改，计划里记为“人工排除”。
  用在促音、短休止前的句尾释放：《绯红》#179 后面 147 ms 的促音休止，延长 24 tick 后被 ACE 整个唱过去。先不带 --apply 看计划，再带 --skip 重跑。
规则（运行前定死）：
  A. 清声母音符（不在休止后）：diff = 合成间隙 − 参考间隙，|diff| < 15 ms 不改。
     - diff > 0（合成间隙偏长）：diff ≤ 当前辅音长 − 15 ms 时，新长度 = max(20 ms, 当前 − diff)；否则记为非时值原因。
     - diff < 0（合成间隙偏短，前一字被拖长）：新长度 = 当前 + |diff|，不超过 MAX_CONS；超过则记为非时值原因。
  B. 休止后的音符：prev_end_delta = 合成前一元音结束 − 参考。|Δ| ≥ 30 ms 时调整前一音符终点，
     不得与后一音符重叠，至少保留 60 tick。片段第一个音符没有前一音符，不适用。
  C. 相邻两个清声母音符量到的是同一段无声间隙时，只改后一个。
  D.（本曲新增）220 BPM 下十六分音符只有 68 ms：拉长辅音时，新长度不得超过前一个音时长的 MAX_PREV_FRAC，否则记为非时值原因。
不带 --apply 只打印计划。（沿用《反乌托邦》的版本；“清声母”在本曲指日语清辅音，判定在 timing_voicing.py。）
--apply 前先确认 ACE 里开着的是 state 里那个已保存的工程，不是就停；另存出的 r1 不写 state，
用打印的 savedPath 跑 state_with_project.py 得到 ace_state_r1.json。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli  # noqa: E402

MAX_CONS = 0.200
# 规则 B 的上限（2026-10-19 扩展到 64 s 时加）：句尾释放差超过 300 ms 不是时值问题——实测是参考在长休止里
# 只有零星有声帧（分离残留），被当成了“前一元音结束”，会把 0.25 s 的字拉长到 1.6 s。
MAX_RELEASE = 0.300
MAX_PREV_FRAC = 0.7


def consonant_lengths(st):
    ph = cli("phoneme", "list", "--clip", st["clip_uuid"], "--range-begin", f"{st['clip_begin']}t",
             "--range-end", f"{st['clip_end']}t", "--with-timings=durations")
    out = {}
    for n in ph["notes"]:
        cons = [t for t in n.get("timings", []) if not t["isVowel"]]
        if cons:
            c = cons[0]
            out[n["pos"]] = {"uuid": n["noteUuid"], "index": c["index"], "name": c["name"],
                             "stored": c.get("durationSec"), "effective": c.get("effectiveDurationSec", c.get("durationSec"))}
    return out


def main():
    st_p, tv_p, score_p, save_as, plan_p = sys.argv[1:6]
    apply = "--apply" in sys.argv
    skip = {int(x) for x in sys.argv[sys.argv.index("--skip") + 1].split(",") if x} if "--skip" in sys.argv else set()
    st = json.load(open(st_p, encoding="utf-8"))
    tv = json.load(open(tv_p, encoding="utf-8"))["rows"]
    score = json.load(open(score_p, encoding="utf-8"))["notes"]
    clip0 = st["clip_begin"]
    cl = consonant_lengths(st)
    nc = cli("clip", "note-content", "--track-index", 0, "--clip-index", 0)
    by_pos = {n["pos"]: n for n in nc["notes"]}
    plan = {"consonants": [], "releases": [], "skipped": []}
    for k, r in enumerate(tv):
        n = score[k]
        local = n["tick"] - clip0
        if r.get("method") != "voicing":
            continue
        if not r["after_rest"] and r["lyric_class"] == "voiceless":
            if r["idx"] in skip:
                plan["skipped"].append({"idx": r["idx"], "why": "人工排除（--skip）"})
                continue
            c = cl.get(local)
            if c is None or c["effective"] is None:
                plan["skipped"].append({"idx": r["idx"], "why": "无可写辅音"})
                continue
            diff = (r["syn_gap_ms"] - r["ref_gap_ms"]) / 1000.0
            cur = c["effective"]
            if abs(diff) < 0.015:
                continue
            if diff > 0 and diff > cur - 0.015:
                plan["skipped"].append({"idx": r["idx"], "why": f"间隙偏长 {1000*diff:.0f} ms，超出辅音 {c['name']} 当前 {1000*cur:.0f} ms 可解释范围"})
                continue
            new = max(0.020, cur - diff)
            if new > MAX_CONS:
                plan["skipped"].append({"idx": r["idx"], "why": f"需把 {c['name']} 从 {1000*cur:.0f} 拉到 {1000*new:.0f} ms，超过 {1000*MAX_CONS:.0f} ms 上限"})
                continue
            prev_sec = common.t2s(score[k - 1]["dur"]) if k > 0 else None
            if new > cur and prev_sec is not None and new > MAX_PREV_FRAC * prev_sec:
                plan["skipped"].append({"idx": r["idx"], "why": f"需把 {c['name']} 拉到 {1000*new:.0f} ms，超过前一个音（{1000*prev_sec:.0f} ms）的 "
                                        f"{int(MAX_PREV_FRAC*100)}%"})
                continue
            plan["consonants"].append({"idx": r["idx"], "tick": n["tick"], "note": c["uuid"], "index": c["index"], "phoneme": c["name"],
                                       "cur_ms": round(1000 * cur, 1), "new_ms": round(1000 * new, 1),
                                       "ref_gap_ms": r["ref_gap_ms"], "syn_gap_ms": r["syn_gap_ms"]})
        elif r["after_rest"] and k > 0:
            d = r["prev_end_delta_ms"] / 1000.0
            if abs(d) < 0.030:
                continue
            if abs(d) > MAX_RELEASE:
                plan["skipped"].append({"idx": score[k - 1]["idx"], "why": f"释放差 {1000*d:+.0f} ms 超过 {1000*MAX_RELEASE:.0f} ms 上限，"
                                        "不是句尾时值问题（参考休止里的零星有声帧）"})
                continue
            prev = score[k - 1]
            if prev["idx"] in skip:
                plan["skipped"].append({"idx": prev["idx"], "why": f"释放差 {1000*d:+.0f} ms，人工排除（--skip）"})
                continue
            dt = common.s2t(d)
            new_dur = prev["dur"] - dt
            if new_dur < 60 or prev["tick"] + new_dur > n["tick"]:
                plan["skipped"].append({"idx": prev["idx"], "why": f"释放差 {1000*d:+.0f} ms，调整后时值 {new_dur}t 越界"})
                continue
            plan["releases"].append({"idx": prev["idx"], "tick": prev["tick"], "note": by_pos[prev["tick"] - clip0]["noteUuid"],
                                     "cur_dur": prev["dur"], "new_dur": new_dur, "release_delta_ms": r["prev_end_delta_ms"]})
    gaps = {r["idx"]: (r.get("ref_prev_end"), r.get("syn_prev_end")) for r in tv if r.get("method") == "voicing"}
    keep = []
    for c in plan["consonants"]:
        later = next((d for d in plan["consonants"] if d["idx"] == c["idx"] + 1), None)
        if later and gaps.get(later["idx"]) == gaps.get(c["idx"]):
            plan["skipped"].append({"idx": c["idx"], "why": f"与 #{later['idx']} 共用同一无声间隙，只改后者"})
            continue
        keep.append(c)
    plan["consonants"] = keep
    json.dump(plan, open(plan_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for c in plan["consonants"]:
        print(f"cons  #{c['idx']:>3} {c['phoneme']:<3} {c['cur_ms']:6.1f} -> {c['new_ms']:6.1f} ms  (gap ref {c['ref_gap_ms']} / syn {c['syn_gap_ms']})")
    for r in plan["releases"]:
        print(f"rel   #{r['idx']:>3} dur {r['cur_dur']} -> {r['new_dur']}t  (release Δ {r['release_delta_ms']:+.0f} ms)")
    for s in plan["skipped"]:
        print(f"skip  #{s['idx']:>3} {s['why']}")
    if not apply:
        return
    d = cli("project", "dirty")  # 另存之前确认开着的就是 state 里那个已保存的工程（不替用户保存或丢弃）
    if d.get("dirty") or os.path.normcase(os.path.abspath(d.get("projectPath") or "")) != os.path.normcase(
            os.path.abspath(st["project"]["savedPath"])):
        raise SystemExit(f"当前工程不是已保存的 {st['project']['savedPath']}，停止：{d}")
    saved = cli("project", "save-as", os.path.abspath(save_as))
    print("saved as:", saved["savedPath"])
    for c in plan["consonants"]:
        w = cli("phoneme", "set-consonant-timing", "--note", c["note"], "--index", c["index"], "--length", f"{c['new_ms']:.1f}ms")
        c["write"] = w.get("writes")
    for r in plan["releases"]:
        r["write"] = cli("note", "resize", "--note-uuid", r["note"], "--dur", f"{r['new_dur']}t")
    cli("project", "save")
    st["project"] = saved
    json.dump(plan, open(plan_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("applied", len(plan["consonants"]), "consonant lengths,", len(plan["releases"]), "releases")


if __name__ == "__main__":
    main()
