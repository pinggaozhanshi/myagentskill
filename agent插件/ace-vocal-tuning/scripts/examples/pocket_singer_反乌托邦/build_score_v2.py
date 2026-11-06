"""扩展谱面（16.0–64.1 s，到“1 分钟那句”唱完）：主旋律轨 + 重叠处的第二声部轨，都由洛天依唱。

用法：python -I build_score_v2.py <paime_notes.json> <description.txt> <praat_full.npy> <rmvpe_full.npy> <out_score.json>
- 主旋律 = PaiMe 轨 0 的全部音符 + 轨 1 中不与轨 0 重叠的音符；第二声部 = 轨 1 中与轨 0 重叠的音符（ACE 人声轨只能单音）。
- 逐音符核对参考 F0（音符中间 50% 的 Praat / RMVPE 中位数）；两人同唱段打印两种提取器各自更接近哪个声部。
- 歌词：主旋律逐字与官方歌词开头比较；只打印不一致的位置，不打印歌词。
- target：主旋律在两人同唱段只在参考跟的是主旋律时写目标（逐帧判，见 build_target_f0_v2.py）；第二声部默认不写目标。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402

HOP = 0.005
T0, T1 = 15360, 61536  # 16.0–64.1 s（音符起点在此范围内）
CLIP = (13440, 63360)  # 14.0–66.0 s


def midi(hz):
    return 69 + 12 * np.log2(hz / 440.0)


def overlaps(a, b):
    return a["tick"] < b["tick"] + b["dur"] and b["tick"] < a["tick"] + a["dur"]


def ref_stats(n, pr, rm):
    s, e = common.t2s(n["tick"]), common.t2s(n["tick"] + n["dur"])
    lo, hi = int(np.ceil((s + 0.25 * (e - s)) / HOP)), int(np.floor((s + 0.75 * (e - s)) / HOP)) + 1
    p, r = pr[lo:hi], rm[lo:hi]
    mp = float(np.nanmedian(p)) if np.mean(~np.isnan(p)) > 0 else None
    mr = float(np.nanmedian(r)) if np.mean(~np.isnan(r)) > 0 else None
    return mp, mr, float(np.mean(~np.isnan(p)))


def main():
    paime_p, desc_p, pr_p, rm_p, out = sys.argv[1:6]
    d = json.load(open(paime_p, encoding="utf-8"))
    pr, rm = midi(np.load(pr_p)), midi(np.load(rm_p))
    t0 = [dict(n, src_track=0) for n in d["tracks"][0]["notes"] if T0 <= n["tick"] < T1]
    t1 = [dict(n, src_track=1) for n in d["tracks"][1]["notes"] if T0 <= n["tick"] < T1]
    harmony = [n for n in t1 if any(overlaps(n, m) for m in t0)]
    main_line = sorted(t0 + [n for n in t1 if n not in harmony], key=lambda n: n["tick"])
    clash = [(a["tick"], b["tick"]) for a, b in zip(main_line, main_line[1:]) if a["tick"] + a["dur"] > b["tick"]]
    print(f"main {len(main_line)} notes (track0 {len(t0)} + track1 solo {len(t1) - len(harmony)}), harmony {len(harmony)} notes, "
          f"main-line overlaps {clash if clash else 'none'}")
    print("harmony phrases:", sorted({round(common.t2s(n['tick']), 1) for n in harmony})[:3], "...",
          f"{common.t2s(harmony[0]['tick']):.2f}-{common.t2s(harmony[-1]['tick'] + harmony[-1]['dur']):.2f} s")
    # 歌词核对
    body = open(desc_p, encoding="utf-8").read().split("---", 1)[1].split("词：", 1)[1].split("=====", 1)[0]
    official = re.sub(r"[\s　，。！？、,.!?]", "", body)
    # 唱出来的字序：主旋律 + 主旋律唱不到的第二声部（同一时刻开始时第二声部在前，即先“己”后“只”）
    def lyric_differs(h):
        m = max((m for m in main_line if overlaps(h, m)),
                key=lambda m: min(h["tick"] + h["dur"], m["tick"] + m["dur"]) - max(h["tick"], m["tick"]))
        return m["lyric"] != h["lyric"]
    extra = [h for h in harmony if lyric_differs(h)]
    sung = sorted([(n["tick"], 1, n["lyric"]) for n in main_line] + [(n["tick"], 0, n["lyric"]) for n in extra])
    lyr = "".join(c for _, _, c in sung)
    mism = [i for i, (a, b) in enumerate(zip(lyr, official)) if a != b]
    print(f"sung lyrics {len(lyr)} chars (main {len(main_line)} + second {len(extra)}) vs official: mismatches at {mism if mism else 'none'}")
    # 音高核对
    rows = []
    for role, notes in (("main", main_line), ("harmony", harmony)):
        for i, n in enumerate(notes):
            mp, mr, vp = ref_stats(n, pr, rm)
            partner = None
            if role == "main":
                partner = next((h for h in harmony if overlaps(n, h)), None)
            else:
                partner = next((m for m in t0 if overlaps(n, m)), None)
            rows.append({"role": role, "i": i, "tick": n["tick"], "dur": n["dur"], "pitch": n["pitch"], "lyric": n["lyric"],
                         "src_track": n["src_track"], "start": round(common.t2s(n["tick"]), 4), "end": round(common.t2s(n["tick"] + n["dur"]), 4),
                         "ref_praat": None if mp is None else round(mp, 2), "ref_rmvpe": None if mr is None else round(mr, 2),
                         "voiced": round(vp, 2), "duet": partner is not None, "partner_pitch": None if partner is None else partner["pitch"]})
    solo = [r for r in rows if r["role"] == "main" and not r["duet"] and r["ref_praat"] is not None]
    dv = np.array([r["ref_praat"] - r["pitch"] for r in solo])
    print(f"main solo notes {len(solo)}: dev median {np.median(dv):+.2f}, |dev| median {np.median(np.abs(dv)):.2f}, p90 {np.percentile(np.abs(dv), 90):.2f}")
    for r in solo:
        dvv = r["ref_praat"] - r["pitch"]
        if abs(dvv) >= 1.5 and r["start"] >= 39.4:
            print(f"  main #{r['i']} t {r['start']:.2f} pitch {r['pitch']} praat {r['ref_praat']} rmvpe {r['ref_rmvpe']} dev {dvv:+.2f}")
    duet = [r for r in rows if r["duet"] and r["ref_praat"] is not None]
    for role in ("main", "harmony"):
        rr = [r for r in duet if r["role"] == role]
        if not rr:
            continue
        def follows(key):
            own = sum(1 for r in rr if r[key] is not None and abs(r[key] - r["pitch"]) < abs(r[key] - r["partner_pitch"]) and abs(r[key] - r["pitch"]) < 1.0)
            other = sum(1 for r in rr if r[key] is not None and abs(r[key] - r["partner_pitch"]) < abs(r[key] - r["pitch"]) and abs(r[key] - r["partner_pitch"]) < 1.0)
            return own, other
        iv = np.array([r["partner_pitch"] - r["pitch"] for r in rr])
        print(f"duet {role}: {len(rr)} notes | interval to partner median {np.median(iv):+.0f} st | "
              f"praat follows own/partner {follows('ref_praat')} | rmvpe follows own/partner {follows('ref_rmvpe')}")
    # 第二声部只保留主旋律唱不到的内容：与重叠的主旋律音符歌词不同的音（“己”与“只因为”同时开始）。
    # 与主旋律完全相同的齐唱音、单独一个和声音、多拖 120 tick 的音都不单独唱（同一歌手完全相同的复制轨只会相位叠加）。
    second, skipped = [], []
    for h in harmony:
        m = max((m for m in main_line if overlaps(h, m)),
                key=lambda m: min(h["tick"] + h["dur"], m["tick"] + m["dur"]) - max(h["tick"], m["tick"]))
        if m["lyric"] != h["lyric"]:
            second.append(h)
        elif m["pitch"] != h["pitch"]:
            skipped.append({"tick": h["tick"], "why": f"齐唱中单独一个和声音（{h['pitch']} 对主旋律 {m['pitch']}），单独唱会突兀"})
        elif (m["tick"], m["dur"]) != (h["tick"], h["dur"]):
            skipped.append({"tick": h["tick"], "why": f"与主旋律同音同字，只是多拖 {h['dur'] - m['dur']} tick"})
        else:
            skipped.append({"tick": h["tick"], "why": "齐唱，与主旋律完全相同"})
    print(f"second voice: {len(second)} notes {[(n['tick'], n['pitch']) for n in second]} | skipped {len(skipped)} "
          f"(unison {sum(1 for s in skipped if s['why'].startswith('齐唱，'))})")
    roles = {"main": main_line, "second": second}
    tracks = []
    for role, notes in roles.items():
        tracks.append({"role": role, "name": "洛天依_主旋律" if role == "main" else "洛天依_第二声部",
                       "notes": [{"idx": i, "tick": n["tick"], "pos": n["tick"] - CLIP[0], "dur": n["dur"], "pitch": n["pitch"],
                                  "lyric": n["lyric"], "src_track": n["src_track"], "start": round(common.t2s(n["tick"]), 4),
                                  "end": round(common.t2s(n["tick"] + n["dur"]), 4),
                                  "duet": any(overlaps(n, o) for o in (harmony if role == "main" else main_line)),
                                  # 第二声部的“己”被另一位原唱的“只因为”盖住，参考不可靠，不写目标
                                  "target": role == "main"}
                                 for i, n in enumerate(notes)]})
    meta = {"bpm": common.BPM, "tpq": common.TPQ, "clip_start_tick": CLIP[0], "clip_end_tick": CLIP[1],
            "clip_sec": [common.t2s(CLIP[0]), common.t2s(CLIP[1])], "window_sec": [16.0, 64.1], "language": "Chinese",
            "voice": "洛天依 singer:18 (Verse23, V1)", "source": "PaiMe 工程轨 0 / 轨 1，音高与时间原样"}
    meta["second_voice_skipped"] = skipped
    json.dump({"meta": meta, "tracks": tracks, "check_rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 每条轨单独一份与单轨脚本（timing_voicing / build_target_f0 / pitch_eval / glitch_check）兼容的谱面
    for t in tracks:
        json.dump({"meta": dict(meta, role=t["role"], track_name=t["name"]), "notes": t["notes"]},
                  open(out.replace(".json", f"_{t['role']}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written", out)


if __name__ == "__main__":
    main()
