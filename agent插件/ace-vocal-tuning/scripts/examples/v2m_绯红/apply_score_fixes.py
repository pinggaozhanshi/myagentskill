"""套用谱面修正（docs/score_fixes.json）→ 一分钟版谱面 v1，并自检。

用法：python -I apply_score_fixes.py <score_draft.json> <aligned.json> <score_fixes.json> <praat_5ms.npy> <rmvpe_5ms.npy> <out.json>
- 每个初稿音符的歌词默认取对齐到的官方音节（j）；fixes 里可改 j（"-" = 延长音，不成新音节）、标助词（は→わ、へ→え、を→お）、
  改音高、改时值（end16，十六分个数）、拆分（split：从第 at16 个十六分起另成一个音，给 j 和音高；不给音高就取参考人声中位数取整）。
- 自检：官方这一段的每个音节要么正好落在一个音符上（顺序单调），要么列在 absorb（长音、促音停顿等，写明理由）；
  音符不重叠、时值为正；逐音对参考音高，|偏差| ≥ 0.6 半音的列出来；列出降 B 大调以外的音。
- 输出含歌词，只放 work/；终端不打印歌词。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402

HOP = 0.005
Q = 120
PARTICLE = {"は": "わ", "へ": "え", "を": "お"}
KEY_PCS = {10, 0, 2, 3, 5, 7, 9}  # 降 B 大调
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MARGIN = common.s2t(1.0)


def name(p):
    return f"{NAMES[int(p) % 12]}{int(p) // 12 - 1}"


def main():
    draft_p, al_p, fix_p, pr_p, rm_p, out = sys.argv[1:7]
    draft = json.load(open(draft_p, encoding="utf-8"))
    al = json.load(open(al_p, encoding="utf-8"))
    fx = json.load(open(fix_p, encoding="utf-8"))
    official = al["official"]
    dp_j = {r["note"]: r["j"] for r in al["rows"] if r["note"] is not None and r.get("j") is not None}
    section_j = [r["j"] for r in al["rows"] if r.get("j") is not None]
    j_lo, j_hi = min(section_j), max(section_j)
    pr = 69 + 12 * np.log2(np.load(pr_p) / 440.0)
    rm = 69 + 12 * np.log2(np.load(rm_p) / 440.0)

    def ref_pitch(t0, t1):
        a, b = int(np.ceil((t0 + 0.25 * (t1 - t0)) / HOP)), int(np.floor((t0 + 0.75 * (t1 - t0)) / HOP)) + 1
        for arr in (rm, pr):
            seg = arr[a:b]
            seg = seg[~np.isnan(seg)]
            if len(seg):
                return float(np.median(seg))
        return None

    def lyric_of(j, particle):
        if j == "-":
            return "-"
        m = official[j]
        return PARTICLE.get(m, m) if particle else m

    outn = []
    for n in draft["notes"]:
        k = n["idx"]
        spec = fx["notes"].get(str(k), {})
        j = spec.get("j", dp_j.get(k))
        if j is None:
            raise SystemExit(f"#{k} 没有对上官方音节，也没在 fixes 里指定")
        pitch = spec.get("pitch", fx["pitch"].get(str(k), n["pitch"]))
        total16 = n["dur"] // Q
        assert n["dur"] % Q == 0, f"#{k} 时值不是十六分的整数倍"
        cuts = [0] + [s["at16"] for s in spec.get("split", [])]
        ends16 = cuts[1:] + [spec.get("end16", total16)]
        segs = [{"j": j, "pitch": pitch, "particle": spec.get("particle", False)}] + spec.get("split", [])
        for s, c0, c1 in zip(segs, cuts, ends16):
            assert c1 > c0, f"#{k} 拆分位置不对"
            tick, end = n["tick"] + c0 * Q, n["tick"] + c1 * Q
            t0, t1 = common.t2s(tick), common.t2s(end)
            ref = ref_pitch(t0, t1)
            p = s.get("pitch")
            auto = p is None
            if auto:
                p = int(round(ref))
            outn.append({"src_idx": k, "seg": cuts.index(c0), "tick": tick, "dur": end - tick, "pitch": p, "pitch_auto": auto,
                         "j": s["j"], "particle": s.get("particle", False), "lyric": lyric_of(s["j"], s.get("particle", False)),
                         "start": round(t0, 4), "end": round(t1, 4), "ref": None if ref is None else round(ref, 2),
                         "v2m_pitch": n["v2m_pitch"]})
    outn.sort(key=lambda x: x["tick"])
    for i, x in enumerate(outn):
        x["idx"] = i
    for a, b in zip(outn, outn[1:]):
        assert a["tick"] + a["dur"] <= b["tick"], f"重叠：#{a['src_idx']} / #{b['src_idx']}"
    js = [x["j"] for x in outn if x["j"] != "-"]
    absorbed = sorted(int(j) for j in fx["absorb"])
    assert all(b > a for a, b in zip(js, js[1:])), "官方音节顺序不单调"
    assert not set(js) & set(absorbed), f"既分配又并入：{sorted(set(js) & set(absorbed))}"
    missing = sorted(set(range(j_lo, j_hi + 1)) - set(js) - set(absorbed))
    extra = sorted((set(js) | set(absorbed)) - set(range(j_lo, j_hi + 1)))
    print(f"notes {len(draft['notes'])} → {len(outn)} | official morae j{j_lo}–j{j_hi}: assigned {len(js)}, absorbed {len(absorbed)}, "
          f"missing {missing}, outside {extra} | extension notes '-' {sum(1 for x in outn if x['j'] == '-')}, "
          f"particles {sum(1 for x in outn if x['particle'])}")
    if missing or extra:
        raise SystemExit("官方音节没有全部对上")
    print("auto pitches (split segments without a given pitch):",
          [(x["idx"], x["src_idx"], name(x["pitch"]), x["ref"]) for x in outn if x["pitch_auto"]])
    devs = [(x, None if x["ref"] is None else x["ref"] - x["pitch"]) for x in outn]
    big = [(x["idx"], x["src_idx"], name(x["pitch"]), x["ref"], round(d, 2)) for x, d in devs if d is not None and abs(d) >= 0.6]
    clean = np.array([abs(d) for x, d in devs if d is not None and abs(d) < 0.6])
    print(f"|dev| median {np.median(clean):.2f} st over {len(clean)} notes; |dev| >= 0.6: {len(big)} -> {big}")
    print("out of B-flat major:", [(x["idx"], x["src_idx"], name(x["pitch"])) for x in outn if x["pitch"] % 12 not in KEY_PCS])
    last = outn[-1]
    v = ~np.isnan(rm)
    k1 = int(last["end"] / HOP)
    after = np.where(v[k1:k1 + 200])[0]
    print(f"last note ends {last['end']:.3f}s; reference voiced frames in the next 1 s: {len(after)}"
          f"{'' if not len(after) else f', last at {last["end"] + after[-1] * HOP:.3f}s'}")
    c0 = outn[0]["tick"] - MARGIN
    c1 = outn[-1]["tick"] + outn[-1]["dur"] + MARGIN
    meta = dict(draft["meta"], clip_start_tick=c0, clip_end_tick=c1, clip_sec=[round(common.t2s(c0), 4), round(common.t2s(c1), 4)],
                language="Japanese", voice="singer:18 洛天依 (Verse23)", fixes_file=os.path.basename(fix_p),
                official_j=[j_lo, j_hi], lyrics_source=al["url"])
    for x in outn:
        x["target"] = True
    json.dump({"meta": meta, "notes": outn}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ps = [x["pitch"] for x in outn]
    print(f"score v1: {len(outn)} notes, {name(min(ps))}–{name(max(ps))}, {outn[0]['start']:.3f}–{outn[-1]['end']:.3f}s; clip {meta['clip_sec']}")


if __name__ == "__main__":
    main()
