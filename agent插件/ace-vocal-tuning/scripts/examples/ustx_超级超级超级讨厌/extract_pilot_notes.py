"""从 USTX 指定声部截取试验窗口的音符（保留原始 tick、音高、歌词），并生成诊断图 spec。

用法：python -I extract_pilot_notes.py <ustx> <part> <tick0> <tick1> <out_notes.json> <ref_f0.npy> <ref_offset_sec> <out_spec.json>
ref_offset_sec：官方 WAV 0 点在 ACE/USTX 时间轴上的位置（秒）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_common  # noqa: E402,F401
from vp_common import load_ustx, tempo_map, tick_to_sec  # noqa: E402


def main():
    ustx, part, k0, k1, out_notes, ref_npy, ref_off, out_spec = sys.argv[1:9]
    part, k0, k1, ref_off = int(part), int(k0), int(k1), float(ref_off)
    p = load_ustx(ustx)
    res = int(p["resolution"])
    tmap = tempo_map(p)
    vp = p["voice_parts"][part]
    pos0 = int(vp.get("position", 0))
    notes = []
    for n in sorted(vp["notes"], key=lambda n: n["position"]):
        a = pos0 + n["position"]
        if a < k0 or a >= k1:
            continue
        notes.append({"tick": a, "dur": n["duration"], "tone": n["tone"], "ustx_lyric": n["lyric"],
                      "start": round(tick_to_sec(a, tmap, res), 6),
                      "end": round(tick_to_sec(a + n["duration"], tmap, res), 6)})
    meta = {"source": os.path.basename(ustx), "part": part, "tick_range": [k0, k1],
            "tempo": tmap, "resolution": res, "count": len(notes)}
    json.dump({"meta": meta, "notes": notes}, open(out_notes, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    t0 = tick_to_sec(k0, tmap, res) - 0.3
    t1 = tick_to_sec(k1, tmap, res) + 0.3
    spec = {"title": "诊断：官方初音清唱 F0（Praat）vs USTX 声部 0 音符（未修正）",
            "t0": t0, "t1": t1, "row_sec": 4.7,
            "notes": [{"start": n["start"], "end": n["end"], "midi": n["tone"], "label": n["ustx_lyric"]} for n in notes],
            "notes_label": "USTX 音符（mothman）",
            "series": [{"label": "官方初音清唱 F0", "npy": ref_npy, "time_offset": ref_off, "slot": 1}]}
    json.dump(spec, open(out_spec, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(notes)} notes, {t0:.2f}-{t1:.2f}s")


if __name__ == "__main__":
    main()
