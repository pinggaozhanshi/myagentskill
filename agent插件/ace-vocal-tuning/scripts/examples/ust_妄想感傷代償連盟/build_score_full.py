"""完整副歌谱面（用户 2026-10-21 选定：唱完副歌后「あいやいや／らら」，加和声）：主唱轨 + 和声轨，ACE 时间轴。

用法：python -I build_score_full.py <ust_main.json> <ust_aiyaiya.json> <ust_hamo.json> <offset_tick> <out.json> [hamo_fix.json]
- 主唱：main.ust #316–#423（副歌前一句 + 副歌）+ 愛や厭.ust #288–#363（副歌后「あいやいや／らら」整段，到原曲约 95.5 s）。
  - 改音：愛や厭 #307、#346「ら」72 → 70（两份分离参考、两个提取器都在 70.0，UST 写 72；note_check 复核）。
  - 第一声「あいやいや」（愛や厭 #288–#292）：去混响参考里几乎没有，ref="basic_fold"——目标音高改用原样分离人声的 RMVPE、
    允许折回八度（那里原样分离的值整齐地落在低八度，折回后与 UST 相差 ≤ 0.2 半音）。
- 和声：hamo.ust #316–#423（103 个音，只在副歌里），歌词与主唱相同；hamo_fix.json（hamo_check.py 的结论）里给出的改音照改。
  和声不直接对参考：音高跟主唱的调教平行移动（见 build_target_f0.py 的和声模式）。
片段：两条轨共用同一个片段范围，前后各留 1 s。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

MAIN_RANGE = (316, 423)
POST_RANGE = (288, 363)
FIRST_SHOUT = (288, 292)
PITCH_FIX = {("愛や厭", 307): 70, ("愛や厭", 346): 70}
MARGIN = common.s2t(1.0)


def pick(path, lo, hi, src):
    return [dict(n, src=src) for n in json.load(open(path, encoding="utf-8"))["notes"] if lo <= n["idx"] <= hi and not n["rest"]]


def main():
    main_p, aiya_p, hamo_p, offset, out = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
    hfix = json.load(open(sys.argv[6], encoding="utf-8")) if len(sys.argv) > 6 else {}
    seq = sorted(pick(main_p, *MAIN_RANGE, "main") + pick(aiya_p, *POST_RANGE, "愛や厭"), key=lambda n: n["tick"])
    for a, b in zip(seq, seq[1:]):
        assert a["tick"] + a["dur"] <= b["tick"], f"重叠：{a['src']}#{a['idx']} / {b['src']}#{b['idx']}"
    hamo = pick(hamo_p, *MAIN_RANGE, "hamo")
    c0 = min(seq[0]["tick"], hamo[0]["tick"]) + offset - MARGIN
    c1 = max(seq[-1]["tick"] + seq[-1]["dur"], hamo[-1]["tick"] + hamo[-1]["dur"]) + offset + MARGIN

    def conv(n, k, role):
        tick = n["tick"] + offset
        pitch = n["pitch"]
        fix = None
        if role == "main" and (n["src"], n["idx"]) in PITCH_FIX:
            pitch, fix = PITCH_FIX[(n["src"], n["idx"])], n["pitch"]
        if role == "harmony" and str(n["idx"]) in hfix.get("pitch", {}):
            pitch, fix = hfix["pitch"][str(n["idx"])], n["pitch"]
        rec = {"idx": k, "ust_src": n["src"], "ust_idx": n["idx"], "ust_tick": n["tick"], "tick": tick, "pos": tick - c0,
               "dur": n["dur"], "pitch": pitch, "lyric": n["lyric"], "target": True,
               "start": round(common.t2s(tick), 4), "end": round(common.t2s(tick + n["dur"]), 4)}
        if fix is not None:
            rec["ust_pitch"] = fix
        if role == "main" and n["src"] == "愛や厭" and FIRST_SHOUT[0] <= n["idx"] <= FIRST_SHOUT[1]:
            rec["ref"] = "basic_fold"
        return rec

    tracks = [{"role": "main", "name": "洛天依_主唱", "notes": [conv(n, k, "main") for k, n in enumerate(seq)]},
              {"role": "harmony", "name": "洛天依_和声", "notes": [conv(n, k, "harmony") for k, n in enumerate(hamo)]}]
    meta = {"bpm": common.BPM, "tpq": common.TPQ, "offset_tick": offset, "clip_start_tick": c0, "clip_end_tick": c1,
            "clip_sec": [round(common.t2s(c0), 4), round(common.t2s(c1), 4)], "language": "Japanese",
            "voice": "singer:18 洛天依 (Verse23)",
            "source": "沙羅 UST（BowlRoll 120915）main #316–#423 + 愛や厭 #288–#363；和声 hamo #316–#423",
            "pitch_fixes_main": {f"{s}#{i}": p for (s, i), p in PITCH_FIX.items()}, "harmony_fixes": hfix}
    json.dump({"meta": meta, "tracks": tracks}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for t in tracks:
        ps = [n["pitch"] for n in t["notes"]]
        print(t["role"], len(t["notes"]), "notes | pitch", min(ps), "–", max(ps), "| first", t["notes"][0]["start"], "s, last end",
              t["notes"][-1]["end"], "s")
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
