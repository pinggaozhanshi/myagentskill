"""用 ACE Stem Splitter 基础模式（人声 + 伴奏，不扣点数，云端）分离官方音轨：原样一次、去混响一次。

用法：python -I ace_split.py <official.wav> <save_as.acep> <out_state.json>
- 要先征得用户同意：分离会把音轨上传到 ACE 的云端。
- 做两次：不去混响、去混响（--remove-reverb true）。音高、时值参考要用去混响那组（原样那组带混响、叠着低八度，
  《妄想感傷代償連盟》里 Praat 有 67% 的帧落到低八度）；原样那组是原曲里人声的实际电平，带伴奏试听用它定电平。
- 分轨文件的认领与解码用 stems_collect.py：带 --wait 的返回值不含分出来的轨的 UUID（2026-10-21 实测），
  而第二次分离的轨会插在原曲轨正下方、把第一次的挤到下面，不能按轨序认；分轨就是工程 Samples/Processed/ 里的 Opus 文件。
- 当前工程有未保存改动、或不是空临时工程 / 本项目的工程时直接退出，不替用户保存或丢弃（ace.require_safe_project）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli, require_safe_project  # noqa: E402


def main():
    wav, save_as, out_state = sys.argv[1:4]
    require_safe_project()
    print("new:", cli("project", "new"))
    cli("tempo", "set", "--points", json.dumps([{"pos": 0, "value": common.BPM}]))
    a = cli("import", "file", "--path", os.path.abspath(wav), "--pos", "0t")
    cli("track", "rename", "--track-uuid", a["trackUuid"], "--new-name", "OFFICIAL_官方音轨")
    clip_uuid = a.get("clipUuid") or a["clips"][0]["clipUuid"]
    saved = cli("project", "save-as", os.path.abspath(save_as))
    print("saved:", saved["savedPath"])
    state = {"project": saved, "official_track_uuid": a["trackUuid"], "official_clip_uuid": clip_uuid, "import": a, "splits": []}
    for label, extra in (("basic", []), ("basic_dereverb", ["--remove-reverb", "true"])):
        job = cli("generative", "stem-splitter", "--clip-uuid", clip_uuid, "--mode", "basic", *extra, "--wait", timeout=1800)
        print(label, "job:", json.dumps(job, ensure_ascii=False))
        state["splits"].append({"label": label, "job": job})
        cli("project", "save")
    print(json.dumps([(t["trackIndex"], t["trackName"], t["trackType"], t["trackUuid"]) for t in cli("track", "list")["tracks"]],
                     ensure_ascii=False))
    json.dump(state, open(out_state, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("下一步：python -I stems_collect.py", out_state, "<stems_out_dir>")


if __name__ == "__main__":
    main()
