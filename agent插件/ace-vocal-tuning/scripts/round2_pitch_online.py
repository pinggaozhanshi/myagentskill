"""第 2 轮（音高曲线，在线写）：r1 另存为 r2 →（可选）把个别音的时值改回去 → 用 vocalpitch write 写目标音高 → 读回核对 → 保存。
要 acestudio-cli 0.18 起的 vocalpitch 命令；更早的版本用离线的 round2_pitch.py（LibreSVIP 写 pitchDelta）。

用法：python -I round2_pitch_online.py <ace_state_r1.json> <r2_save_as.acep> <target_f0.json> <score.json> <out_state_r2.json> <report.json>
                                      [--revert <revert.json>]
- --revert：{"<谱面序号>": [r1 时值, 改回的时值], ...}（tick）。《绯红》#179 用过：第 1 轮按释放规则把它延长 24 tick 后，
  后面 118 ms 的促音休止被 ACE 整个连唱过去（下一音前的间隙 原唱 90 / r0 135 / r1 10 ms），第 2 轮开头改回原时值。
- 目标音高（build_target_f0.py）是导出时间轴（片段起点 = 0）、5 ms 一帧的 MIDI 值；每帧换成一个片段内 tick 的锚点
  （round(t × 每秒 tick 数)），连续段之间放 [tick, null] 断开，一次写入（help vocalpitch write：绝对半音、单调 Hermite 插值、读回逐点相同）。
- 写之前先过八度 / 错音检查（target_check.py，规则同 patch_pitch.py），不过就不动工程。
- 写完用 vocalpitch read --level user 读回：音高点的 tick、数值逐点相同，断开标记落在同一对点之间（ACE 把断开标记存在
  两段之间的中点，《绯红》30 个都这样），才算成功；音符（位置/时值/音高/歌词）除 --revert 的音外与 r1 相同。
- 副作用：写曲线时 ACE 把当时自己的有声 / 无声判断固定在曲线下。之后再改辅音长度，固定的无声段仍会把元音压成无声：
  先跑结尾检查（vowel_coverage.py、voicing_check.py、ending_check.py），需要时做音节结尾轮（endings_plan.py / endings_apply.py），
  最后都要把固定清成 auto。
（由《绯红》的 round2_pitch.py 通用化：要改回的音由 --revert 给出。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import target_check  # noqa: E402
from ace import cli  # noqa: E402


def signature(st):
    nc = cli("clip", "note-content", "--track-index", st["track_index"], "--clip-index", 0)
    return sorted(((n["pos"], n["dur"], n["pitch"], n["lyric"], n["noteUuid"]) for n in nc["notes"]), key=lambda x: x[0])


def main():
    st_p, save_as, tgt_p, score_p, out_st, rep_p = sys.argv[1:7]
    revert = {}  # 谱面序号: (r1 时值, 改回的时值)
    if "--revert" in sys.argv:
        spec = json.load(open(sys.argv[sys.argv.index("--revert") + 1], encoding="utf-8"))
        revert = {int(k): tuple(v) for k, v in spec.items()}
    chk = target_check.check(json.load(open(score_p, encoding="utf-8")), json.load(open(tgt_p, encoding="utf-8")))
    print("target check:", json.dumps(chk, ensure_ascii=False))
    if not chk["ok"]:
        raise SystemExit("目标音高疑似八度 / 错音，中止写入（规则见 target_check.py）")
    st = json.load(open(st_p, encoding="utf-8"))
    score = json.load(open(score_p, encoding="utf-8"))["notes"]
    d = cli("project", "dirty")
    if d["dirty"] or os.path.normcase(os.path.abspath(d["projectPath"])) != os.path.normcase(os.path.abspath(st["project"]["savedPath"])):
        raise SystemExit(f"当前工程不是已保存的 r1：{d}")
    before = signature(st)
    saved = cli("project", "save-as", os.path.abspath(save_as))["savedPath"]
    print("saved as:", saved)
    by_pos = {s[0]: s for s in before}
    for k, (cur, new) in revert.items():
        pos = score[k]["tick"] - st["clip_begin"]
        s = by_pos[pos]
        assert s[1] == cur, f"#{k} 当前时值 {s[1]}，不是预期的 {cur}"
        cli("note", "resize", "--note-uuid", s[4], "--dur", f"{new}t")
        print(f"#{k} dur {cur} -> {new}t")
    tgt = json.load(open(tgt_p, encoding="utf-8"))
    hop, midi = tgt["hop_sec"], tgt["midi"]
    assert tgt["clip_begin_tick"] == st["clip_begin"]
    pts = []
    for a, b in tgt["runs"]:
        ia, ib = int(round(a / hop)), int(round(b / hop))
        run = [[int(round(i * hop * common.TICKS_PER_SEC)), round(midi[i], 4)] for i in range(ia, ib + 1)]
        assert all(v is not None for _, v in run), "连续段内不应有空值"
        if pts:
            assert pts[-1][0] < run[0][0] - 1
            pts.append([pts[-1][0] + 1, None])
        pts.extend(run)
    ticks = [p[0] for p in pts]
    assert all(b > a for a, b in zip(ticks, ticks[1:])), "锚点 tick 必须严格递增"
    tmp = os.path.join(os.path.dirname(os.path.abspath(rep_p)), "round2_pitch_points.json")
    json.dump(pts, open(tmp, "w", encoding="utf-8"))
    w = cli("vocalpitch", "write", "--clip-uuid", st["clip_uuid"], "--points", "@" + tmp, timeout=900)
    print("write:", {k: v for k, v in w.items() if k not in ("points",)})
    rb = cli("vocalpitch", "read", "--clip-uuid", st["clip_uuid"], "--level", "user", timeout=900)
    got = rb.get("points", [])
    same_len = len(got) == len(pts)
    pairs = list(zip(got, pts))
    max_tick_diff = max((abs(a[0] - b[0]) for a, b in pairs if b[1] is not None), default=None)
    max_val_diff = max((abs(a[1] - b[1]) for a, b in pairs if a[1] is not None and b[1] is not None), default=None)
    null_match = all((a[1] is None) == (b[1] is None) for a, b in pairs) and all(
        pts[i - 1][0] < got[i][0] < pts[i + 1][0] for i, (a, b) in enumerate(pairs) if b[1] is None)
    cli("project", "save")
    after = signature(st)
    changed = [(x[0], x[1], y[1]) for x, y in zip(before, after) if x[:4] != y[:4]]
    rep = {"anchors_written": len(pts), "gap_markers": sum(1 for p in pts if p[1] is None), "runs": len(tgt["runs"]),
           "readback_points": len(got), "readback_same_length": same_len, "max_tick_diff": max_tick_diff,
           "max_value_diff": max_val_diff, "gap_markers_match": null_match, "notes_changed_vs_r1": changed,
           "voicing": rb.get("voicing", {}).get("unvoiced", [])[:5]}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    json.dump(rep, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not (same_len and max_tick_diff == 0 and (max_val_diff or 0) < 1e-3 and null_match):
        raise SystemExit("音高曲线读回与写入不一致")
    if len(changed) != len(revert):
        raise SystemExit(f"音符改动与 --revert 不符：{changed}")
    st["project"] = {"savedPath": saved, "projectPath": saved}
    json.dump(st, open(out_st, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
