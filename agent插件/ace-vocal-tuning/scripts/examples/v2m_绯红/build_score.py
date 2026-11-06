"""一分钟版谱面初稿：Vocal to MIDI 音符 → 量化到原曲十六分网格 → 对参考人声音高逐音核对。

用法：python -I build_score.py <v2m_notes.json> <praat_5ms.npy> <rmvpe_5ms.npy> <t_from> <t_to> <out.json> [fixes.json]
- 原唱是 VOCALOID（初音ミク），音符本来就在网格上；Vocal to MIDI 的起点有时按辅音、有时按元音，两簇差约 40 ms，
  都在同一个十六分音符内，所以就近量化到十六分（120 tick）。网格零点 = 第 0 小节（ACE 节拍分析 + 逐拍拟合 0.9647 s）
  再加一个整体偏移：在 ±40 tick 内搜，取起点落在网格 ±20 tick 内最多的那个。
- 相邻音符原本首尾相接（Vocal to MIDI 默认连唱）的，量化后仍首尾相接；量化后长度为 0 的标“collapsed”。
- 参考音高：量化后音符中间 50% 的 Praat、RMVPE 中位数（MIDI）；两者差 < 0.5 取均值，否则取离谱面近的。
  |偏差| ≥ 0.6 半音标“pitch?”，接近 ±12 标“octave?”（只标记，改不改看 fixes.json）。
- fixes.json（人工核对后的决定）：{"pitch": {"序号": 新音高}, "lyric": {"序号": "假名"}, "merge": [[序号, 序号]], ...}，序号是本段的 0 起编号。
- 输出含歌词，只放 work/。打印的表不含歌词。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402

HOP = 0.005
Q = 120
FIRST_DOWNBEAT_SEC = 0.9647
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def name(p):
    return f"{NAMES[int(p) % 12]}{int(p) // 12 - 1}"


def midi(hz):
    return 69 + 12 * np.log2(hz / 440.0)


def main():
    v2m_p, pr_p, rm_p, t_from, t_to, out = sys.argv[1:7]
    t_from, t_to = float(t_from), float(t_to)
    fixes = json.load(open(sys.argv[7], encoding="utf-8")) if len(sys.argv) > 7 else {}
    src = [n for n in json.load(open(v2m_p, encoding="utf-8"))["notes"] if t_from <= n["start"] < t_to]
    base = int(round(FIRST_DOWNBEAT_SEC * common.TICKS_PER_SEC))
    on = np.array([n["tick"] for n in src], float)
    scores = []
    for off in range(-40, 41):
        r = (on - base - off) % Q
        r = np.minimum(r, Q - r)
        scores.append((int(np.sum(r <= 20)), -abs(off), off))
    hits, _, off = max(scores)
    g0 = base + off
    print(f"grid zero = {g0} tick ({common.t2s(g0):.4f} s, offset {off:+d} t); onsets within ±20 t: {hits}/{len(src)}")
    pr, rm = midi(np.load(pr_p)), midi(np.load(rm_p))

    def qz(t):
        return g0 + int(round((t - g0) / Q)) * Q

    notes = []
    for k, n in enumerate(src):
        qs, qe = qz(n["tick"]), qz(n["tick"] + n["dur"])
        notes.append({"idx": k, "v2m_tick": n["tick"], "v2m_dur": n["dur"], "tick": qs, "end_tick": qe, "pitch": n["pitch"],
                      "v2m_pitch": n["pitch"], "lyric": n["lyric"], "res_on": n["tick"] - qs, "res_off": n["tick"] + n["dur"] - qe,
                      "legato_next": k + 1 < len(src) and src[k + 1]["tick"] == n["tick"] + n["dur"]})
    for a, b in zip(notes, notes[1:]):
        if a["legato_next"]:
            a["end_tick"] = b["tick"]
    for k, v in fixes.get("pitch", {}).items():
        notes[int(k)]["pitch"] = v
    for k, v in fixes.get("lyric", {}).items():
        notes[int(k)]["lyric"] = v
    for k, v in fixes.get("tick", {}).items():
        notes[int(k)]["tick"] = v
    for k, v in fixes.get("end_tick", {}).items():
        notes[int(k)]["end_tick"] = v
    drop = {int(k) for k in fixes.get("drop", [])}
    notes = [n for n in notes if n["idx"] not in drop]
    rows = []
    for n in notes:
        n["dur"] = n["end_tick"] - n["tick"]
        s, e = common.t2s(n["tick"]), common.t2s(n["end_tick"])
        n["start"], n["end"] = round(s, 4), round(e, 4)
        lo, hi = int(np.ceil((s + 0.25 * (e - s)) / HOP)), int(np.floor((s + 0.75 * (e - s)) / HOP)) + 1
        p, r = pr[lo:hi], rm[lo:hi]
        mp = float(np.nanmedian(p)) if np.any(~np.isnan(p)) else None
        mr = float(np.nanmedian(r)) if np.any(~np.isnan(r)) else None
        if mp is not None and mr is not None:
            ref = (mp + mr) / 2 if abs(mp - mr) < 0.5 else min((mp, mr), key=lambda v: abs(v - n["pitch"]))
        else:
            ref = mp if mp is not None else mr
        n["ref_praat"] = None if mp is None else round(mp, 2)
        n["ref_rmvpe"] = None if mr is None else round(mr, 2)
        n["voiced"] = round(float(np.mean(~np.isnan(r))) if len(r) else 0.0, 2)
        dev = None if ref is None else round(ref - n["pitch"], 2)
        n["dev"] = dev
        flag = []
        if n["dur"] <= 0:
            flag.append("collapsed")
        if dev is not None and abs(abs(dev) - 12) < 1.0:
            flag.append("octave?")
        elif dev is not None and abs(dev) >= 0.6:
            flag.append("pitch?")
        if abs(n["res_on"]) > 40:
            flag.append("onset?")
        n["flag"] = " ".join(flag)
        rows.append(n)
    bar_t = 4 * Q * 4
    for n in rows:
        rel = n["tick"] - g0
        n["pos_bar"] = f"{rel // bar_t}:{(rel % bar_t) // (4 * Q) + 1}:{(rel % (4 * Q)) // Q + 1}"
    pcs = np.zeros(12)
    for n in rows:
        if n["dev"] is not None:
            pcs[int(round(n["pitch"] + n["dev"])) % 12] += n["dur"]
    print("pitch-class weight (by duration):", {NAMES[i]: int(pcs[i]) for i in np.argsort(-pcs)})
    devs = np.array([n["dev"] for n in rows if n["dev"] is not None and not n["flag"]])
    print(f"notes {len(rows)} | with ref {sum(n['dev'] is not None for n in rows)} | clean |dev| median {np.median(np.abs(devs)):.2f} "
          f"p90 {np.percentile(np.abs(devs), 90):.2f} | flagged {sum(bool(n['flag']) for n in rows)}")
    for n in rows:
        if n["flag"] or "--all" in sys.argv:
            print(f"#{n['idx']:>3} {n['start']:7.3f}s {n['pos_bar']:>7} dur {n['dur'] // 30:>2}/32 {name(n['pitch']):>4} "
                  f"ref {n['ref_praat']}/{n['ref_rmvpe']} v{n['voiced']} dev {n['dev']} res {n['res_on']:+d}/{n['res_off']:+d} {n['flag']}")
    meta = {"bpm": common.BPM, "tpq": common.TPQ, "grid_zero_tick": g0, "grid_offset_tick": off, "quantum": Q,
            "source": "ACE Vocal to MIDI（去混响分离人声，日语，apply-pitch false）", "section_sec": [t_from, t_to],
            "fixes": fixes}
    json.dump({"meta": meta, "notes": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
