"""v3：副歌后段「啦」改「呐」，两处合并的地方用空音符延长前一个音（用户 2026-10-21：“把‘拉’全改成‘呐’……
断开的地方直接用空音符延长前面的音符”）。

用法：python -I apply_na_fix.py <ace_state_full_r3.json> <score_main.json> <ra_fix.json> <round1_plan.json> <save_as.acep> <out.json>
前提：ACE 开着 full_r3，可以带着用户在 ACE 里没保存的改动（用户把 #116、#145、#146 清成空音符，伴奏轨拉低试听）；
或者已经另存过、开着的就是 save_as（中途失败后接着跑）。
- 另存为新工程：用户的改动一起带进新工程，full_r3 磁盘上的文件不动（仍是 v2 的来源）。
- ra_fix.json 里 20 个音：其余 16 个改中文「呐」（G2P：n a）；#115、#116、#145、#146 是延长音。
  命令行不收空歌词，#115 保留「-」；ACE 对「-」和空音符一样处理：不单独成音节，前一个音的发音一直延到它们结束。
- 读回：162 个音逐个对照谱面（时值含第 1 轮的释放改动）——只有这 20 个音的歌词与谱面不同；「呐」的音素是 n a；
  延长音不单独成音节，前一个「呐」的发音延到最后一个延长音结束。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402

EXTEND = {115, 116, 145, 146}
EXT_LYRICS = ("-", "")
NA = "呐"


def same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def main():
    st_p, score_p, fix_p, r1_p, save_as, out_p = sys.argv[1:7]
    st = json.load(open(st_p, encoding="utf-8"))
    score = json.load(open(score_p, encoding="utf-8"))
    fix = json.load(open(fix_p, encoding="utf-8"))["rows"]
    rel = {r["idx"]: r["new_dur"] for r in json.load(open(r1_p, encoding="utf-8"))["releases"]}
    g2p = cli("phoneme", "g2p", "--language", "Chinese", "--grapheme", NA)["syllables"][0]
    if g2p["phonemes"] != ["n", "a"]:
        raise SystemExit(f"{NA} 的 G2P 不是 n a：{g2p}")
    stem = os.path.splitext(os.path.basename(save_as))[0]
    target = os.path.join(os.path.dirname(os.path.abspath(save_as)), stem, os.path.basename(save_as))  # ACE 另存时会再套一层同名文件夹
    cur = cli("project", "dirty")["projectPath"]
    if same(cur, target):
        saved = target
        print("已经是另存的工程，接着改：", saved)
    elif same(cur, st["project"]["savedPath"]):
        saved = cli("project", "save-as", os.path.abspath(save_as))["savedPath"]
        print("saved as:", saved)
    else:
        raise SystemExit(f"当前工程既不是 full_r3 也不是 {target}：{cur}")
    nb = lambda: {n["pos"]: n for n in cli("clip", "note-content", "--track-index", st["track_index"], "--clip-index", 0)["notes"]}
    before = nb()
    notes = {n["idx"]: n for n in score["notes"]}
    edited = {r["idx"] for r in fix}
    todo = [i for i in sorted(edited - EXTEND) if before[notes[i]["pos"]]["lyric"] != NA]
    res = None
    if todo:
        args = ["note", "set-grapheme"]
        for i in todo:
            args += ["--note-uuid", before[notes[i]["pos"]]["noteUuid"]]
        res = cli(*args, "--lyrics", json.dumps([NA] * len(todo), ensure_ascii=False), "--language", "CHN")
    cli("project", "save")
    after = nb()
    ph = {r["pos"]: r for r in cli("phoneme", "list", "--clip", st["clip_uuid"], "--range-begin", f"{st['clip_begin']}t",
                                    "--range-end", f"{st['clip_end']}t")["notes"]}
    bad = []
    for i, n in notes.items():
        a = after.get(n["pos"])
        if a is None:
            bad.append((i, "音符不见了"))
            continue
        if (a["dur"], a["pitch"]) != (rel.get(i, n["dur"]), n["pitch"]):
            bad.append((i, "时值或音高变了", a["dur"], a["pitch"]))
        ok = a["lyric"] in EXT_LYRICS if i in EXTEND else a["lyric"] == (NA if i in edited else n["lyric"])
        if not ok:
            bad.append((i, "歌词不对", a["lyric"]))
    rows = []
    for r in fix:
        i, p = r["idx"], notes[r["idx"]]["pos"]
        q = ph.get(p)
        row = {"idx": i, "ust_idx": r["ust_idx"], "start": r["start"], "pitch": r["pitch"],
               "lyric": after[p]["lyric"], "extend": i in EXTEND, "phonemes": q["phonemes"] if q else None}
        if i in EXTEND:
            if q is not None:
                bad.append((i, "延长音单独成了音节", q))
        elif not q or q["phonemes"] != ["n", "a"]:
            bad.append((i, "音素不对", q))
        elif i + 1 in EXTEND:
            j = i + 1
            while j + 1 in EXTEND:
                j += 1
            want_end = q["startSec"] + (notes[j]["end"] - notes[i]["start"])  # startSec 以片段起点计
            row.update(syllable_end_sec=q["endSec"], extend_to_sec=round(want_end, 4))
            if abs(q["endSec"] - want_end) > 0.002:
                bad.append((i, "发音没延到延长音结束", q["endSec"], want_end))
        rows.append(row)
    json.dump({"saved": saved, "g2p": g2p, "written_idx": todo, "result": res, "rows": rows, "problems": bad},
              open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))
    if bad:
        raise SystemExit(f"读回与预期不一致：{bad}")
    print("162 个音对照谱面：只有这 20 个音的歌词不同，其余一致")


if __name__ == "__main__":
    main()
