"""把目标音高写成 ACE 片段的 pitchDelta（用户音高），只改这一个字段。研究 .venv（LibreSVIP 2.9.0）运行：

python -I patch_pitch.py <src.acep> <dst.acep> <target_f0.json> <track_uuid> <clip_uuid> <clip_begin_sec> <report.json>
- pitchDelta = 目标 MIDI - BasePitchCurve（由音符重建的 ACE 基础音高），每 tick 一个值，偏移为片段内 tick。
- 目标为空（休止、较长清辅音）的地方不写，交回 AI 音高。
- 写完重新解包，除 pitchDelta 外与源工程逐字段相同才算成功。
"""
import copy
import json
import math
import pathlib
import sys

import numpy as np
from libresvip.core.time_sync import TimeSynchronizer
from libresvip.model.base import SongTempo
from libresvip.plugins.acep.acep_io import compress_ace_studio_project, decompress_ace_studio_project
from libresvip.plugins.acep.base_pitch_curve import BasePitchCurve
from libresvip.plugins.acep.model import AcepNote
from libresvip.plugins.acep.options import AcepSerialization


def main():
    src, dst, tgt_p, track_uuid, clip_uuid, clip_sec, rep_p = sys.argv[1:8]
    src, dst, clip_sec = pathlib.Path(src), pathlib.Path(dst), float(clip_sec)
    if dst.exists():
        raise SystemExit(f"目标已存在：{dst}")
    raw = decompress_ace_studio_project(src)
    tracks = [t for t in raw["tracks"] if t.get("uuid") == track_uuid and t.get("type") == "sing"]
    assert len(tracks) == 1, "需要唯一的人声轨"
    pats = [p for p in tracks[0]["patterns"] if p.get("uuid") == clip_uuid]
    assert len(pats) == 1 and pats[0].get("timeUnit") == "tick", "需要唯一的 tick 片段"
    pat = pats[0]
    assert not pat["parameters"].get("pitchDelta"), "片段已有用户音高，拒绝覆盖"
    assert len(raw["tempos"]) == 1 and raw["tempos"][0]["position"] == 0, "仅支持单一速度"
    bpm = raw["tempos"][0]["bpm"]
    sync = TimeSynchronizer([SongTempo(position=0, bpm=bpm)])
    clip0 = int(round(pat["pos"]))
    base = BasePitchCurve([AcepNote.model_validate(n) for n in pat["notes"]], sync, clip0)
    tgt = json.load(open(tgt_p, encoding="utf-8"))
    hop = tgt["hop_sec"]
    midi = np.array([np.nan if v is None else v for v in tgt["midi"]], dtype=float)
    tt = np.arange(len(midi)) * hop
    ticks_per_sec = bpm / 60.0 * 480
    curves, deltas = [], []
    for a, b in tgt["runs"]:
        lo = math.ceil((clip_sec + a) * ticks_per_sec) - clip0
        hi = math.floor((clip_sec + b) * ticks_per_sec) - clip0
        if hi - lo < 3:
            continue
        ia, ib = int(round(a / hop)), int(round(b / hop))
        rt, rm = tt[ia:ib + 1], midi[ia:ib + 1]
        assert not np.isnan(rm).any(), "连续段内不应有空值"
        vals = []
        for tick in range(lo, hi + 1):
            ab = sync.get_actual_secs_from_ticks(tick + clip0)
            m = float(np.interp(ab - clip_sec, rt, rm))  # 只在本段内插值，两端夹取
            vals.append(round(m - base.semitone_value_at(ab), 6))
        deltas.extend(vals)
        curves.append({"type": "data", "offset": lo, "values": vals})
    deltas = np.abs(np.array(deltas))
    report = {"curves": len(curves), "samples": int(len(deltas)),
              "abs_delta_median": float(np.median(deltas)), "abs_delta_p99": float(np.percentile(deltas, 99)),
              "abs_delta_max": float(deltas.max()), "frac_abs_delta_gt_7": float(np.mean(deltas > 7))}
    # 八度/错音检查（大音程过渡、辅音闭塞处的短促下沉、句尾回落都是合理的大 delta，不在此列）：
    # 1) 任一音符中段 60% 的 delta 中位数绝对值 > 6 半音（八度=12、五度=7；滑音造成的整段偏离实测 ≤4.4）；2) |delta| > 9.5 连续超过 50 ms。
    by_tick = {}
    for c in curves:
        for j, val in enumerate(c["values"]):
            by_tick[c["offset"] + j] = val
    bad_notes = []
    for nt in pat["notes"]:
        a, b = int(nt["pos"] + 0.2 * nt["dur"]), int(nt["pos"] + 0.8 * nt["dur"])
        vals = [by_tick[k] for k in range(a, b) if k in by_tick]
        if len(vals) >= 5 and abs(float(np.median(vals))) > 6:
            bad_notes.append({"pos": nt["pos"], "pitch": nt["pitch"], "median_delta": round(float(np.median(vals)), 2)})
    longest, run = 0, 0
    for k in sorted(by_tick):
        run = run + 1 if abs(by_tick[k]) > 9.5 and (k - 1 in by_tick or run == 0) else (1 if abs(by_tick[k]) > 9.5 else 0)
        longest = max(longest, run)
    report["notes_with_interior_median_gt_6"] = bad_notes
    report["longest_run_abs_gt_9p5_ms"] = round(longest * 60.0 / bpm / 480 * 1000, 1)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if bad_notes or report["longest_run_abs_gt_9p5_ms"] > 50:
        raise SystemExit("疑似八度/错音（音符中段整体偏离），中止写入")
    changed = copy.deepcopy(raw)
    tp = next(p for t in changed["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    tp["parameters"]["pitchDelta"] = sorted(curves, key=lambda c: c["offset"])
    compress_ace_studio_project(changed, dst, AcepSerialization.CBOR)
    check = decompress_ace_studio_project(dst)
    cp = next(p for t in check["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    written = cp["parameters"]["pitchDelta"]
    report["roundtrip_curves"] = len(written)
    report["roundtrip_values_equal"] = all(
        len(w["values"]) == len(c["values"]) and max(abs(x - y) for x, y in zip(w["values"], c["values"])) < 1e-5
        for w, c in zip(written, tp["parameters"]["pitchDelta"]))
    cp["parameters"]["pitchDelta"] = []
    report["other_fields_identical"] = check == raw
    print(json.dumps({k: report[k] for k in ("roundtrip_curves", "roundtrip_values_equal", "other_fields_identical")}))
    json.dump(report, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not (report["roundtrip_values_equal"] and report["other_fields_identical"]):
        dst.unlink()
        raise SystemExit("回读校验失败，已删除输出")


if __name__ == "__main__":
    main()
