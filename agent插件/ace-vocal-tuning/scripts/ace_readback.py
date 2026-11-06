"""读回 ACE 片段：音符（位置/时值/音高/歌词）与音素，和谱面逐项比对。

用法：python -I ace_readback.py <ace_state.json> <score.json> <out.json> [--second]
- 谱面音符的片段内位置按工程 tick 换算（common.clip_pos）；--second 读第二条人声轨（ace_build 写的 second_* state），
  谱面给那条轨的单轨视图（score_views.py）。
- 延长音「-」不单独成音节：phoneme list 里没有它的行，所以音素行数 = 音符数 − 延长音数。
- 终端只打印序号和字段名，不打印歌词；读音逐字核对看输出 JSON 的 phonemes（多音字读错用 `phoneme set` 覆盖）。
（《绯红》时补了 tick 换算和延长音的行数核对。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli  # noqa: E402


def main():
    state_p, score_p, out = sys.argv[1:4]
    st = json.load(open(state_p, encoding="utf-8"))
    if "--second" in sys.argv:  # 读第二声部轨
        st = dict(st, clip_uuid=st["second_clip_uuid"], track_index=st["second_track_index"])
    sc = json.load(open(score_p, encoding="utf-8"))
    c0 = sc["meta"]["clip_start_tick"]
    score = [dict(n, pos=common.clip_pos(n, c0)) for n in sc["notes"]]
    nc = cli("clip", "note-content", "--track-index", st.get("track_index", 0), "--clip-index", 0)
    notes = nc.get("notes", [])
    mism = []
    for a, b in zip(sorted(notes, key=lambda n: n["pos"]), score):
        for k in ("pos", "dur", "pitch", "lyric"):
            if a.get(k) != b[k]:
                mism.append({"idx": b["idx"], "field": k, "ace": a.get(k), "score": b[k]})
    print("note count", len(notes), "vs", len(score), "| mismatches:", len(mism), [(m["idx"], m["field"]) for m in mism[:20]])
    ph = cli("phoneme", "list", "--clip", st["clip_uuid"], "--range-begin", f"{st['clip_begin']}t",
             "--range-end", f"{st['clip_end']}t", "--with-timings")
    rows = ph.get("notes", [])
    unresolved = [r for r in rows if not r.get("phonemes")]
    ext = sum(1 for n in score if n["lyric"] == "-")
    print("phoneme rows", len(rows), "(notes", len(score), "- extensions", ext, "=", len(score) - ext, ") languages",
          sorted({r.get("language") for r in rows}), "unresolved", len(unresolved), "| generation", ph.get("modelGeneration"))
    json.dump({"note_content": nc, "mismatches": mism, "phonemes": ph}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if mism or unresolved or len(notes) != len(score) or len(rows) != len(score) - ext:
        raise SystemExit("读回与谱面不一致")


if __name__ == "__main__":
    main()
