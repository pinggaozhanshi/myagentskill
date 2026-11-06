"""从 UST 截出试验段，换到 ACE 时间轴（官方音轨放在 0 s），写成试验谱面 pilot_score.json。

用法：python -I build_score.py <ust_main.json> <ust_aiyaiya.json> <offset_tick> <out.json>
试验段（用户 2026-10-21 选定“第一遍副歌＋前一句”）：
  - main.ust #316–#423：副歌前一句铺垫 + 第一遍副歌 6 句；
  - 愛や厭.ust #288–#292：副歌结尾紧接的第一声「あいやいや」（与 main 最后一个音首尾相接，不重叠）。
ACE tick = UST tick + offset_tick（UST 的 tick 0 在官方音轨里的位置，由 align_ust.py 求得）。
片段前后各留 1 s。音高、歌词照搬 UST（note_check.py 核对后无需修正，见 docs/score-decisions.md）。
「あいやいや」5 个音 target=False：去混响分离几乎把这声喊删掉了（加过效果的人声），原样分离里又叠着低八度，
参考不可靠——照唱，但不写目标音高、不计入评估。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

MAIN_RANGE = (316, 423)
SHOUT_RANGE = (288, 292)
MARGIN = common.s2t(1.0)


def pick(path, lo, hi, src):
    notes = json.load(open(path, encoding="utf-8"))["notes"]
    return [dict(n, src=src) for n in notes if lo <= n["idx"] <= hi and not n["rest"]]


def main():
    main_p, shout_p, offset, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    seq = pick(main_p, *MAIN_RANGE, "main") + pick(shout_p, *SHOUT_RANGE, "愛や厭")
    seq.sort(key=lambda n: n["tick"])
    for a, b in zip(seq, seq[1:]):
        assert a["tick"] + a["dur"] <= b["tick"], f"重叠：{a['src']}#{a['idx']} / {b['src']}#{b['idx']}"
    c0 = seq[0]["tick"] + offset - MARGIN
    c1 = seq[-1]["tick"] + seq[-1]["dur"] + offset + MARGIN
    assert c0 >= 0
    notes = []
    for k, n in enumerate(seq):
        tick = n["tick"] + offset
        notes.append({"idx": k, "ust_src": n["src"], "ust_idx": n["idx"], "ust_tick": n["tick"], "tick": tick, "pos": tick - c0,
                      "dur": n["dur"], "pitch": n["pitch"], "lyric": n["lyric"], "target": n["src"] == "main",
                      "start": round(common.t2s(tick), 4), "end": round(common.t2s(tick + n["dur"]), 4)})
    meta = {"bpm": common.BPM, "tpq": common.TPQ, "offset_tick": offset, "clip_start_tick": c0, "clip_end_tick": c1,
            "clip_sec": [round(common.t2s(c0), 4), round(common.t2s(c1), 4)],
            "window_sec": [notes[0]["start"], notes[-1]["end"]], "language": "Japanese", "voice": "singer:18 洛天依 (Verse23)",
            "source": "沙羅 UST（BowlRoll 120915）main.ust #316–#423 + 愛や厭.ust #288–#292"}
    json.dump({"meta": meta, "notes": notes}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    print("notes:", len(notes), "| pitch range", min(n["pitch"] for n in notes), max(n["pitch"] for n in notes),
          "| shortest", min(n["dur"] for n in notes), "t")


if __name__ == "__main__":
    main()
