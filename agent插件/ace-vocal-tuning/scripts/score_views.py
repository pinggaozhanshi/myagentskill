"""把两轨的完整谱面拆成单轨视图（meta + notes），供按单轨写的脚本（note_check、g2p_check、timing_voicing、
build_target_f0、pitch_eval、glitch_check、crisp_metrics）直接使用。

用法：python -I score_views.py <score_full.json> <out_main.json> <out_harmony.json> [--no-timing-src <ust_src> ...]
--no-timing-src：来源（音符的 ust_src）是这些的音加 "timing": False（timing_voicing.py 跳过），用在参考人声测不准时值的段落。
例：《妄想感傷代償連盟》副歌后「あいやいや／らら」整段（ust_src = 愛や厭）：去混响参考在这一段很弱，
Praat 多数音测不到有声（note_check：voiced 0.0），间隙量不准；这一段只做音高轮（RMVPE 测得到）。
"""
import json
import sys


def main():
    full = json.load(open(sys.argv[1], encoding="utf-8"))
    skip = {a for i, a in enumerate(sys.argv) if i > 0 and sys.argv[i - 1] == "--no-timing-src"}
    for t, out in zip(full["tracks"], sys.argv[2:4]):
        notes = [dict(n, timing=False) if n.get("ust_src") in skip else n for n in t["notes"]]
        meta = dict(full["meta"], role=t["role"], track_name=t["name"])
        json.dump({"meta": meta, "notes": notes}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(t["role"], len(notes), "->", out)


if __name__ == "__main__":
    main()
