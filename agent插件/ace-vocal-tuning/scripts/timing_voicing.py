"""以有声/无声边界度量时值（比强制对齐稳健）：清辅音或休止前后的“元音结束→元音到达”间隙。

用法：python -I timing_voicing.py <pilot_score.json> <g2p.json> <ref_clip.wav> <syn_clip.wav> <out.json>
两个 wav 都从片段起点（clip_start_tick）开始。对每个首辅音为清音、或前面是休止的音符 i：
  - 清音按 ACE G2P 的音素名，表在 common.VOICELESS_INIT（按 project.json 的语言；日语 k ky kw s sh t ch ts h hy f p py，
    中文 b p f d t g k h j q x zh ch sh z c s）；
  - 元音到达：音符起点附近 [-70, +90] ms 内、连续无声段之后的首个有声帧；
  - 前一元音结束：该无声段开始处；
  - 间隙 = 到达 - 结束（含闭塞、爆破、擦音或休止）。
浊辅音（日语 b d g j m n r w y，中文 m n l r 等）与只有元音的音符本法测不到，记为不可测。
pilot_score 里 target=False（参考不可靠）或 timing=False（参考在这一段测不准）的音符不测。
G2P 音节按 common.head_consonants 对回音符（延长音「-」不送 G2P）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
VOICELESS_INIT = common.VOICELESS_INIT


def voiced_track(wav):
    x, sr = sf.read(wav, always_2d=True)
    return ~np.isnan(common.praat_grid(x.mean(axis=1), sr, HOP, 100.0, 1300.0))


def gap_near(v, t_note, lo=-0.07, hi=0.09, min_unvoiced=2):
    """返回 (prev_vowel_end, vowel_arrival)；找不到则 None。"""
    a, b = max(int((t_note + lo) / HOP), 1), min(int((t_note + hi) / HOP), len(v) - 1)
    best = None
    for i in range(a, b):
        if v[i] and not v[i - 1]:
            j = i - 1
            while j > 0 and not v[j]:
                j -= 1
            if i - 1 - j >= min_unvoiced:
                cand = (j + 1) * HOP, i * HOP
                if best is None or abs(cand[1] - t_note) < abs(best[1] - t_note):
                    best = cand
    return best


def main():
    score_p, g2p_p, ref_w, syn_w, out = sys.argv[1:6]
    score = json.load(open(score_p, encoding="utf-8"))
    notes, clip0 = score["notes"], score["meta"]["clip_start_tick"]
    init = common.head_consonants(notes, g2p_p)
    vr, vs = voiced_track(ref_w), voiced_track(syn_w)
    rows = []
    for k, n in enumerate(notes):
        ns, ne = common.t2s(n["tick"] - clip0), common.t2s(n["tick"] + n["dur"] - clip0)
        prev_end = None if k == 0 else common.t2s(notes[k - 1]["tick"] + notes[k - 1]["dur"] - clip0)
        after_rest = prev_end is None or ns - prev_end > 1e-6
        cls = "voiceless" if init.get(k) in VOICELESS_INIT else "voiced"
        row = {"idx": n["idx"], "tick": n["tick"], "initial": init.get(k), "lyric_class": cls, "after_rest": after_rest,
               "note_start": round(ns, 4), "note_end": round(ne, 4), "method": None}
        if n.get("target", True) and n.get("timing", True) and (cls == "voiceless" or after_rest):
            gr, gs = gap_near(vr, ns), gap_near(vs, ns)
            if gr and gs:
                row.update(method="voicing", ref_prev_end=round(gr[0], 4), ref_arrival=round(gr[1], 4),
                           syn_prev_end=round(gs[0], 4), syn_arrival=round(gs[1], 4),
                           arrival_delta_ms=round(1000 * (gs[1] - gr[1]), 1),
                           prev_end_delta_ms=round(1000 * (gs[0] - gr[0]), 1),
                           ref_gap_ms=round(1000 * (gr[1] - gr[0]), 1), syn_gap_ms=round(1000 * (gs[1] - gs[0]), 1))
        rows.append(row)
    vo = [r for r in rows if r["method"] == "voicing"]
    ad = np.array([r["arrival_delta_ms"] for r in vo])
    pe = np.array([r["prev_end_delta_ms"] for r in vo])
    gd = np.array([r["syn_gap_ms"] - r["ref_gap_ms"] for r in vo])
    summary = {"notes": len(rows), "candidates": sum(1 for r in rows if r["lyric_class"] == "voiceless" or r["after_rest"]),
               "measured": len(vo),
               "arrival_abs_median_ms": float(np.median(np.abs(ad))), "arrival_signed_median_ms": float(np.median(ad)),
               "arrival_abs_p90_ms": float(np.percentile(np.abs(ad), 90)),
               "prev_end_abs_median_ms": float(np.median(np.abs(pe))), "prev_end_signed_median_ms": float(np.median(pe)),
               "gap_diff_signed_median_ms": float(np.median(gd)), "gap_diff_abs_p90_ms": float(np.percentile(np.abs(gd), 90))}
    json.dump({"summary": summary, "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, indent=1))
    for r in sorted(vo, key=lambda r: -abs(r["syn_gap_ms"] - r["ref_gap_ms"]))[:15]:
        print(f"#{r['idx']:>3} {r['initial'] or '-':<2} rest={r['after_rest']!s:<5} arrivalΔ {r['arrival_delta_ms']:+6.1f}  "
              f"prevEndΔ {r['prev_end_delta_ms']:+6.1f}  gap ref {r['ref_gap_ms']:5.1f} syn {r['syn_gap_ms']:5.1f}")


if __name__ == "__main__":
    main()
