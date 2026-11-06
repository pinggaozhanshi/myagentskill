"""和声轨的目标音高：跟主唱的目标音高平行移动（主唱怎么滑、怎么颤，和声跟着同样动），音程按和声谱面。

用法：python -I build_harmony_target.py <score_main.json> <score_harmony.json> <target_main.json> <out.json>
- 和声 102 个音与主唱同位置、同时值（hamo.ust 与 main.ust 节奏一一对应，已核对），所以每帧：
  和声目标 = 主唱目标 + （该音的和声音高 − 主唱音高）。主唱目标为空的帧（休止、无可靠参考）和声也为空，交回 AI 音高。
- 相邻两音的音程不同时，在交界前后各 15 ms 内线性过渡，避免在主唱滑音中间跳一个半音。
输出格式与 build_target_f0.py 相同（片段起点为 t=0，5 ms 一帧）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402

XFADE = 0.015


def main():
    sm_p, sh_p, tm_p, out = sys.argv[1:5]
    sm = json.load(open(sm_p, encoding="utf-8"))
    sh = json.load(open(sh_p, encoding="utf-8"))
    tm = json.load(open(tm_p, encoding="utf-8"))
    hop = tm["hop_sec"]
    clip0 = sm["meta"]["clip_start_tick"]
    main_t = np.array([np.nan if v is None else v for v in tm["midi"]], dtype=float)
    n = len(main_t)
    t = np.arange(n) * hop
    har = {x["tick"]: x for x in sh["notes"]}
    mn = sm["notes"]
    starts = np.array([common.t2s(x["tick"] - clip0) for x in mn])
    ends = np.array([common.t2s(x["tick"] + x["dur"] - clip0) for x in mn])
    # 每帧所属的主唱音（与 build_target_f0 相同：离得最近、30 ms 以内）
    dist = np.maximum(0.0, np.maximum(starts[None, :] - t[:, None], t[:, None] - ends[None, :]))
    near = np.argmin(dist, axis=1)
    ok = dist[np.arange(n), near] <= 0.03
    iv_note = np.array([har[x["tick"]]["pitch"] - x["pitch"] if x["tick"] in har else np.nan for x in mn])
    iv = np.where(ok, iv_note[near], np.nan)
    # 音程变化处 ±15 ms 线性过渡（只在两侧都有和声时）
    sm_iv = iv.copy()
    for k in range(len(mn) - 1):
        a, b = iv_note[k], iv_note[k + 1]
        if np.isnan(a) or np.isnan(b) or a == b or abs(ends[k] - starts[k + 1]) > 1e-6:
            continue
        c = ends[k]
        sel = (t >= c - XFADE) & (t <= c + XFADE)
        sm_iv[sel] = a + (b - a) * (t[sel] - (c - XFADE)) / (2 * XFADE)
    target = main_t + sm_iv
    voiced = ~np.isnan(target)
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
    vals, cnt = np.unique(iv_note[~np.isnan(iv_note)], return_counts=True)
    stats = {"frames": int(n), "voiced_frames": int(voiced.sum()), "runs": len(runs),
             "harmony_notes": len(sh["notes"]), "matched_main_notes": int(np.sum(~np.isnan(iv_note))),
             "interval_counts": {str(int(v)): int(c) for v, c in zip(vals, cnt)}}
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    json.dump({"time_base": "export_seconds_from_clip_begin", "hop_sec": hop, "clip_begin_tick": clip0,
               "midi": [None if np.isnan(v) else round(float(v), 4) for v in target], "runs": runs, "stats": stats},
              open(out, "w", encoding="utf-8"))
    np.save(out.replace(".json", "_hz.npy"), np.where(voiced, 440.0 * 2 ** ((target - 69) / 12), np.nan))


if __name__ == "__main__":
    main()
