"""新建 ACE 基线工程：project.json 的速度、歌手、语言；谱面每条轨一条人声轨，共用片段范围；伴奏与参考人声（参考静音）放在 0 s。

用法：python -I ace_build.py <score.json> <save_as.acep> <inst.wav> <ref_vocal.wav> <out_state.json>
- 谱面两种写法：单轨 {"meta", "notes"}；多轨 {"meta", "tracks": [{"role", "name", "notes"}, ...]}，第一条是主唱。
  音符位置按工程 tick 换算成片段内 tick（common.clip_pos；谱面可以不写 pos）。
- state：第一条轨 vocal_track_uuid / clip_uuid / track_index / note_count，第二条轨同名加 second_ 前缀
  （ace_readback、ace_export、param_read 加 --second 读它）；另有 clip_begin / clip_end、inst_track_uuid、ref_track_uuid。
- 当前工程有未保存改动、或不是空临时工程 / 本项目的工程时直接退出，不替用户保存或丢弃（ace.require_safe_project）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli, require_safe_project  # noqa: E402


def main():
    score_p, save_as, inst, ref, out_state = sys.argv[1:6]
    score = json.load(open(score_p, encoding="utf-8"))
    c0, c1 = score["meta"]["clip_start_tick"], score["meta"]["clip_end_tick"]
    tracks = score.get("tracks") or [{"role": "main", "name": common.CONFIG.get("track_name", "主唱"), "notes": score["notes"]}]
    clip_name = score["meta"].get("clip_name", "pilot")
    require_safe_project()
    print("new:", cli("project", "new"))
    cli("tempo", "set", "--points", json.dumps([{"pos": 0, "value": common.BPM}]))
    state = {}
    for k, t in enumerate(tracks):
        tr = cli("track", "create", "--type", "sing", "--name", t["name"])
        cli("voice", "load", "--track-uuid", tr["trackUuid"], "--source", common.SINGER)
        cli("track", "set-language", "--track-uuid", tr["trackUuid"], "--language", common.LANGUAGE)
        notes = [{"pos": common.clip_pos(n, c0), "dur": n["dur"], "pitch": n["pitch"], "lyric": n["lyric"]} for n in t["notes"]]
        clip = cli("clip", "create", "--type", "sing", "--track-index", tr["trackIndex"], "--pos", f"{c0}t",
                   "--dur", f"{c1 - c0}t", "--name", clip_name if len(tracks) == 1 else f"{t['role']}_{clip_name}",
                   "--notes", json.dumps(notes, ensure_ascii=False))
        print(t["role"], "track", tr["trackIndex"], tr["trackUuid"], "| clip", clip["clipUuid"], clip["clipBegin"], clip["clipEnd"], clip["noteCount"])
        key = "" if k == 0 else "second_"
        state.update({f"{key}vocal_track_uuid": tr["trackUuid"], f"{key}clip_uuid": clip["clipUuid"],
                      f"{key}track_index": tr["trackIndex"], f"{key}note_count": clip["noteCount"]})
        state["clip_begin"], state["clip_end"] = clip["clipBegin"], clip["clipEnd"]
    saved = cli("project", "save-as", os.path.abspath(save_as))
    print("saved:", saved["savedPath"])
    a1 = cli("import", "file", "--path", os.path.abspath(inst), "--pos", "0t")
    a2 = cli("import", "file", "--path", os.path.abspath(ref), "--pos", "0t")
    cli("track", "rename", "--track-uuid", a1["trackUuid"], "--new-name", common.CONFIG.get("inst_track_name", "INST_伴奏"))
    cli("track", "rename", "--track-uuid", a2["trackUuid"], "--new-name", common.CONFIG.get("ref_track_name", "REF_参考人声(静音)"))
    cli("track", "set", "--track-uuid", a2["trackUuid"], "--mute", "true")
    print("save:", cli("project", "save")["savedPath"])
    state.update({"project": saved, "inst_track_uuid": a1["trackUuid"], "ref_track_uuid": a2["trackUuid"]})
    json.dump(state, open(out_state, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps([(t["trackIndex"], t["trackName"], t["trackType"]) for t in cli("track", "list")["tracks"]], ensure_ascii=False))


if __name__ == "__main__":
    main()
