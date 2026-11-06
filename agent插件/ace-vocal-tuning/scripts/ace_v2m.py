"""用 ACE Vocal to MIDI（免费）把去混响分离人声转成音符初稿，在分离工程（ace_split.py 建的）里做。

用法：python -I ace_v2m.py <split_state.json> <out_notes.json>
- 找去混响人声（stems_collect 认出的 basic_dereverb vocal）那条轨的音频片段 → vocal-to-midi --language <语言>
  --apply-pitch false --wait（要干净的音符，音高曲线以后自己写）→ 读回新 Sing 轨的音符，换成工程 tick 与官方音轨秒 → 保存工程。
  语言按 project.json 的 language（小写：chinese / japanese / english …），也可以用 v2m_language 另指定。
- 《绯红》实测：音高很准（与参考偏差中位 0.02 半音），音节只对约 75%，常把两三个音节并成一个音；
  初稿必须按网格量化、逐音核对音高，并把歌词对官方读音逐拍对齐（references/score-and-reference.md）。
- 输出含歌词，只放 work/，不进 Git。当前工程必须是已保存的分离工程，否则退出。
（由《绯红》的版本通用化：语言按 project.json。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli  # noqa: E402

LANG = common.CONFIG.get("v2m_language") or common.LANGUAGE.lower()


def main():
    st_p, out = sys.argv[1:3]
    st = json.load(open(st_p, encoding="utf-8"))
    d = cli("project", "dirty")
    if d.get("dirty") or os.path.normcase(os.path.abspath(d.get("projectPath") or "")) != os.path.normcase(
            os.path.abspath(st["project"]["savedPath"])):
        raise SystemExit(f"当前工程不是已保存的分离工程：{d}")
    stem = next(s for s in st["stems"] if s["label"] == "basic_dereverb" and s["kind"] == "vocal")
    src_track = stem["track"][2]
    clips = cli("clip", "list", "--track-uuid", src_track)["clips"]
    assert len(clips) == 1 and clips[0]["clipType"] == "audio", clips
    src_clip = clips[0]["clipUuid"]
    job = cli("generative", "vocal-to-midi", "--clip-uuid", src_clip, "--language", LANG, "--apply-pitch", "false",
              "--wait", timeout=3600)
    print("job:", json.dumps(job, ensure_ascii=False)[:1500])
    tracks = cli("track", "list")["tracks"]
    sing = [t for t in tracks if t["trackType"].lower() == "sing"]
    print("sing tracks:", [(t["trackIndex"], t["trackName"], t["trackUuid"]) for t in sing])
    assert len(sing) == 1, "应只有一条 Vocal to MIDI 生成的 Sing 轨"
    t = sing[0]
    notes = []
    for ci, c in enumerate(cli("clip", "list", "--track-uuid", t["trackUuid"])["clips"]):
        nc = cli("clip", "note-content", "--track-index", t["trackIndex"], "--clip-index", ci)
        base = nc.get("pos", c["clipBegin"])
        for n in nc["notes"]:
            g = n["pos"] + base
            notes.append({"tick": g, "dur": n["dur"], "pitch": n["pitch"], "lyric": n.get("lyric"), "syllable": n.get("syllable"),
                          "language": n.get("language"), "start": round(common.t2s(g), 4),
                          "end": round(common.t2s(g + n["dur"]), 4), "clip": c["clipUuid"], "clip_pos": base})
    notes.sort(key=lambda n: n["tick"])
    print("notes:", len(notes), "| first", notes[0]["start"] if notes else None, "| last end", notes[-1]["end"] if notes else None)
    cli("project", "save")
    json.dump({"source_clip": src_clip, "source_track": src_track, "sing_track": t["trackUuid"], "job": job, "notes": notes},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
