"""列出谱面里重复的句子：开头连续几个音的歌词、时值、音程都相同（可以移调），并标出哪一次没有别的声部盖着。

用法：python -I repeat_phrases.py <score.json> [--role 名字] [--others 名字,名字] [--min-notes 3] [--min-ms 500] [--rest-ms 120]
score.json：{"notes": [...]}（单轨）或 {"轨名": [...], ...}（多轨，用 --role 选一轨）；音符要有 tick、dur、pitch、lyric。
--others 给和声等其他声部的轨名：和这一轨同时、音高不同的音算“被盖着”。
用途：写音高目标前先跑。原唱是 VOCALOID 时，重复句常常是同一条曲线复制的；挑最干净的一次当模板，抄到其他几次
（《呐呐呐》：7 处同谱面的句子，只有独唱的那次保住了滑音，见 references/round2-pitch.md 的“重复句”）。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def runs(notes, rest_ticks):
    out, cur = [], [notes[0]]
    for a, b in zip(notes, notes[1:]):
        if b["tick"] - (a["tick"] + a["dur"]) < rest_ticks:
            cur.append(b)
        else:
            out.append(cur)
            cur = [b]
    out.append(cur)
    return out


def shape(notes):
    p0 = next(n["pitch"] for n in notes)
    return [(n["lyric"], n["dur"], n["pitch"] - p0) for n in notes]


def covered(run, others):
    """这串音和其他声部同时、音高不同的时长占比。"""
    total = sum(n["dur"] for n in run)
    hit = 0
    for n in run:
        for o in others:
            lap = min(n["tick"] + n["dur"], o["tick"] + o["dur"]) - max(n["tick"], o["tick"])
            if lap > 0 and o["pitch"] != n["pitch"]:
                hit += lap
    return min(1., hit / total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("score")
    ap.add_argument("--role")
    ap.add_argument("--others", default="")
    ap.add_argument("--min-notes", type=int, default=3)
    ap.add_argument("--min-ms", type=float, default=500)
    ap.add_argument("--rest-ms", type=float, default=120)
    a = ap.parse_args()
    data = json.load(open(a.score, encoding="utf-8"))
    tracks = {"notes": data["notes"]} if "notes" in data else data
    role = a.role or next(iter(tracks))
    notes = sorted(tracks[role], key=lambda n: n["tick"])
    others = [n for r in a.others.split(",") if r for n in tracks[r]]
    rs = runs(notes, common.s2t(a.rest_ms / 1000))
    buckets = {}
    for r in rs:
        if len(r) >= a.min_notes:
            buckets.setdefault(tuple(shape(r)[:a.min_notes]), []).append(r)
    groups = []
    for inst in buckets.values():
        if len(inst) < 2:
            continue
        k = a.min_notes
        while all(len(r) > k for r in inst) and len({tuple(shape(r)[:k + 1]) for r in inst}) == 1:
            k += 1
        ms = common.t2s(sum(n["dur"] for n in inst[0][:k])) * 1000
        if ms < a.min_ms:
            continue
        rows = [{"tick": r[0]["tick"], "sec": round(common.t2s(r[0]["tick"]), 3), "transpose": r[0]["pitch"] - inst[0][0]["pitch"],
                 "covered": round(covered(r[:k], others), 2)} for r in inst]
        groups.append({"notes": k, "ms": round(ms), "lyrics": "".join(n["lyric"] for n in inst[0][:k]), "instances": rows})
    groups.sort(key=lambda g: -g["ms"] * len(g["instances"]))
    for g in groups:
        best = min(g["instances"], key=lambda r: r["covered"])
        print(f"{len(g['instances'])} 次，{g['notes']} 音 {g['ms']} ms：模板候选 {best['sec']} s（被盖 {best['covered']:.0%}）")
        print("   " + "  ".join(f"{r['sec']} s{r['transpose']:+d}/{r['covered']:.0%}" for r in g["instances"]))
    print(len(groups), "组重复句")


if __name__ == "__main__":
    main()
