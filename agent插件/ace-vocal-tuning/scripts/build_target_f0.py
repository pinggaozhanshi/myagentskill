"""第 2 轮目标音高：参考人声 F0 → 与已核对谱面同八度的连续曲线（导出时间轴，t=0 为片段起点，5 ms 一帧）。

用法：python -I build_target_f0.py <pilot_score.json> <praat_full_5ms.npy> <rmvpe_full_5ms.npy> <out.json> [<alt_praat.npy> <alt_rmvpe.npy>]
（完整副歌加的可选参数：ref="basic_fold" 的音改用 alt 两条 F0——原样分离人声——取值，同样允许折回八度。）
（F0 网格是整首参考人声的，t=0 为音轨 0 s；这里按片段起点截取。）
规则（与 vocal_pilot、《反乌托邦》相同，只加了“折回八度”一条）：
- 只在音符时间范围（前后各放宽 30 ms）内取值；休止中不给值（交回 AI 音高，不跨休止连线）。
- target=False 的音符（参考不可靠，本曲是结尾「あいやいや」）也不给值。
- 每帧在 Praat 与 RMVPE 中取离当前音符音高更近者；两者都偏离 >9 半音则留空。
- 折回八度（本曲新增）：原曲副歌叠着低八度人声，提取器会整段落到低八度。某个提取值离音符 >9 半音、
  平移整数个八度后离音符 ≤2 半音时，把平移后的值也当候选（同等距离时优先不平移的）。
- 有声段内 ≤40 ms 的空洞线性插值；去尖刺（与前后 35 ms 中位数差 >2.5 半音的帧换成中位数）；3 帧中值滤波。不额外加颤音。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
from scipy.ndimage import median_filter  # noqa: E402

HOP = 0.005
FOLD_FROM = 9.0
FOLD_TO = 2.0


def main():
    score_p, pr_p, rm_p, out = sys.argv[1:5]
    score = json.load(open(score_p, encoding="utf-8"))
    clip0, clip1 = score["meta"]["clip_start_tick"], score["meta"]["clip_end_tick"]
    notes = [n for n in score["notes"] if n.get("target", True)]
    k0 = int(round(common.t2s(clip0) / HOP))
    n = int(round(common.t2s(clip1 - clip0) / HOP)) + 1
    praat = 69 + 12 * np.log2(np.load(pr_p)[k0:k0 + n] / 440.0)
    rm = 69 + 12 * np.log2(np.load(rm_p)[k0:k0 + n] / 440.0)
    t = np.arange(n) * HOP
    alt_frames = 0
    if len(sys.argv) > 6:
        ap = 69 + 12 * np.log2(np.load(sys.argv[5])[k0:k0 + n] / 440.0)
        ar = 69 + 12 * np.log2(np.load(sys.argv[6])[k0:k0 + n] / 440.0)
        for nt in notes:
            if nt.get("ref") == "basic_fold":
                sel = (t >= common.t2s(nt["tick"] - clip0)) & (t <= common.t2s(nt["tick"] + nt["dur"] - clip0))
                praat[sel], rm[sel] = ap[sel], ar[sel]
                alt_frames += int(sel.sum())
    starts = np.array([common.t2s(nt["tick"] - clip0) for nt in notes])
    ends = np.array([common.t2s(nt["tick"] + nt["dur"] - clip0) for nt in notes])
    pitches = np.array([nt["pitch"] for nt in notes], dtype=float)
    dist = np.maximum(0.0, np.maximum(starts[None, :] - t[:, None], t[:, None] - ends[None, :]))
    nearest = np.argmin(dist, axis=1)
    note_pitch = np.where(dist[np.arange(n), nearest] <= 0.03, pitches[nearest], np.nan)
    excluded = [nt for nt in score["notes"] if not nt.get("target", True)]
    for nt in excluded:  # 不可靠音符所在的帧一律留空（即使离相邻音符不到 30 ms）
        a, b = common.t2s(nt["tick"] - clip0), common.t2s(nt["tick"] + nt["dur"] - clip0)
        note_pitch[(t >= a) & (t <= b)] = np.nan
    target = np.full(n, np.nan)
    src = np.zeros(n, dtype="<U12")
    for i in range(n):
        if np.isnan(note_pitch[i]):
            continue
        cands = []
        for v, s in ((praat[i], "praat"), (rm[i], "rmvpe")):
            if np.isnan(v):
                continue
            cands.append((abs(v - note_pitch[i]), v, s))
            k = int(round((note_pitch[i] - v) / 12))
            if abs(v - note_pitch[i]) > FOLD_FROM and k != 0 and abs(v + 12 * k - note_pitch[i]) <= FOLD_TO:
                cands.append((abs(v + 12 * k - note_pitch[i]) + 1e-3, v + 12 * k, s + "_fold"))
        if cands:
            d, v, s = min(cands)
            if d <= 9.0:
                target[i], src[i] = v, s
    filled, i = 0, 0
    while i < n:
        if np.isnan(target[i]):
            j = i
            while j < n and np.isnan(target[j]):
                j += 1
            if 0 < i and j < n and (j - i) * HOP <= 0.040 and not np.isnan(note_pitch[i - 1]) and not np.isnan(note_pitch[j]):
                target[i:j] = np.linspace(target[i - 1], target[j], j - i + 2)[1:-1]
                src[i:j] = "interp"
                filled += j - i
            i = j
        else:
            i += 1
    voiced = ~np.isnan(target)
    despiked = 0
    for i in np.where(voiced)[0]:
        win = target[max(0, i - 3):min(n, i + 4)]
        win = win[~np.isnan(win)]
        if len(win) >= 5:
            med = float(np.median(win))
            if abs(target[i] - med) > 2.5:
                target[i] = med
                despiked += 1
    sm = target.copy()
    sm[voiced] = median_filter(np.where(voiced, target, 0.0), size=3)[voiced]
    runs, i = [], 0
    while i < n:
        if voiced[i]:
            j = i
            while j < n and voiced[j]:
                j += 1
            runs.append([round(t[i], 4), round(t[j - 1], 4)])
            i = j
        else:
            i += 1
    stats = {"frames": int(n), "voiced_frames": int(voiced.sum()), "from_praat": int(np.sum(src == "praat")),
             "from_rmvpe": int(np.sum(src == "rmvpe")), "octave_folded": int(np.sum(np.char.endswith(src, "_fold"))),
             "alt_ref_frames": alt_frames,
             "interpolated": int(filled), "despiked": int(despiked), "runs": len(runs),
             "excluded_notes": [nt["idx"] for nt in excluded],
             "abs_dev_from_note_median": float(np.nanmedian(np.abs(sm - note_pitch))),
             "abs_dev_from_note_p95": float(np.nanpercentile(np.abs(sm - note_pitch), 95))}
    print(json.dumps(stats, indent=1))
    json.dump({"time_base": "export_seconds_from_clip_begin", "hop_sec": HOP, "clip_begin_tick": clip0,
               "midi": [None if np.isnan(v) else round(float(v), 4) for v in sm], "runs": runs, "stats": stats},
              open(out, "w", encoding="utf-8"))
    np.save(out.replace(".json", "_hz.npy"), np.where(voiced, 440.0 * 2 ** ((sm - 69) / 12), np.nan))


if __name__ == "__main__":
    main()
