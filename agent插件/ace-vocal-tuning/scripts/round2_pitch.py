"""第 2 轮（音高曲线）编排：在 r1 基础上另存 r2 → ACE 切回 r1 → 离线写 pitchDelta → ACE 打开 r2 → 读回音符核对。

用法：python -I round2_pitch.py <ace_state_r1.json> <r1.acep> <r2_save_as.acep> <target.json> [<target_second.json>] <work_dir>
- 给两个目标时是两条轨（state 里有 second_ 的轨）：先写主唱片段、再写第二条轨（和声）片段。
- 歌词、音符、辅音长度与 r1 完全相同；只多了用户音高曲线（patch_pitch.py 在装了 LibreSVIP 2.9.0 的 Python 里写入并回读校验，
  解释器是 project.json 的 libresvip_python）。
- 写入时 r2 不能在 ACE 里打开（另存后先切回 r1）；写入失败就恢复成未改动的 r2。
- 输出：<work_dir>/<r2 名>.unpatched.acep（写入前的副本）、round2_patch_main.json（两条轨时另有 round2_patch_second.json）、
  ace_state_<r2 名>.json。
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli  # noqa: E402

VENV_PY = common.CONFIG.get("libresvip_python") or r"C:\Users\lenovo\Documents\自媒体\调教Agent研究\.venv\Scripts\python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))


def signature(st):
    keys = ["track_index"] + (["second_track_index"] if "second_track_index" in st else [])
    return [[(n["pos"], n["dur"], n["pitch"], n["lyric"]) for n in sorted(cli("clip", "note-content", "--track-index", st[k],
                                                                                  "--clip-index", 0)["notes"], key=lambda n: n["pos"])]
            for k in keys]


def patch(src, dst, tgt, track, clip, clip_sec, rep):
    p = subprocess.run([VENV_PY, "-I", "-X", "utf8", os.path.join(HERE, "patch_pitch.py"), src, dst, tgt, track, clip, str(clip_sec), rep],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(p.stdout[-1500:], p.stderr[-1500:])
    return p.returncode == 0 and os.path.exists(dst)


def main():
    args = sys.argv[1:]
    st_p, r1, save_as, tgt = args[:4]
    tgt2, work = (args[4], args[5]) if len(args) == 6 else (None, args[4])
    r1, save_as, tgt, work = map(os.path.abspath, (r1, save_as, tgt, work))
    st = json.load(open(st_p, encoding="utf-8"))
    if tgt2 and "second_vocal_track_uuid" not in st:
        raise SystemExit("给了第二个目标，但 state 里没有第二条轨")
    d = cli("project", "dirty")
    if d["dirty"] or os.path.normcase(os.path.abspath(d["projectPath"])) != os.path.normcase(r1):
        raise SystemExit(f"当前工程不是已保存的第 1 轮工程 {r1}：{d}")
    st.setdefault("track_index", 0)
    if not tgt2:
        st.pop("second_track_index", None)
    before = signature(st)
    saved = cli("project", "save-as", save_as)["savedPath"]
    print("saved r2 bundle:", saved)
    cli("project", "open", r1)  # 让 r2 不处于打开状态
    stem = os.path.basename(saved).replace(".acep", "")
    unpatched = os.path.join(work, f"{stem}.unpatched.acep")
    mid = os.path.join(work, f"{stem}.main_only.acep")
    for p in (unpatched, mid):
        if os.path.exists(p):
            os.remove(p)
    shutil.copy2(saved, unpatched)
    os.remove(saved)
    clip_sec = cli("convert", "tick-to-time", "--tick", st["clip_begin"])["time"]
    first_dst = mid if tgt2 else saved
    ok = patch(unpatched, first_dst, tgt, st["vocal_track_uuid"], st["clip_uuid"], clip_sec, os.path.join(work, "round2_patch_main.json"))
    if ok and tgt2:
        ok = patch(mid, saved, tgt2, st["second_vocal_track_uuid"], st["second_clip_uuid"], clip_sec,
                   os.path.join(work, "round2_patch_second.json"))
    if not ok:
        if os.path.exists(saved):
            os.remove(saved)
        shutil.copy2(unpatched, saved)
        raise SystemExit("写入失败，已恢复未改动的 r2")
    print("opened:", cli("project", "open", saved).get("projectName"))
    after = signature(st)
    print("notes identical to r1:", before == after, [len(x) for x in after])
    if before != after:
        raise SystemExit("音符与 r1 不一致")
    st = json.load(open(st_p, encoding="utf-8"))
    st["project"] = {"savedPath": saved, "projectPath": saved}
    json.dump(st, open(os.path.join(work, f"ace_state_{stem}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
