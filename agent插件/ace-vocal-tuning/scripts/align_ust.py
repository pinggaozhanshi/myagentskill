"""求 UST 的 tick 0 落在官方音轨的第几秒：把 UST 音高轮廓与参考人声 F0 逐个偏移比对，取吻合帧最多的偏移。

用法：python -I align_ust.py <ust_main.json> <ref_vocal.wav> <out.json> [lo_sec hi_sec]
F0 用 Praat（common.praat_grid，5 ms）；UST 每个音只取去掉首尾各 40 ms 的中段，避开滑音与辅音。
吻合 = 参考有声且与 UST 音高相差 < 0.75 半音。先在 [lo, hi]（默认 -5..15 s）里以 5 ms 步长全搜，
再把 UST 有音的时间范围三等分，前、中、后段各自搜一次（±0.5 s 内），看偏移是否一致
（不一致说明速度不是精确的 project.json 的 bpm，或中途有变速）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
TRIM = 0.040


def ust_frames(notes):
    idx, val = [], []
    for n in notes:
        if n["rest"]:
            continue
        a = common.t2s(n["tick"]) + TRIM
        b = common.t2s(n["tick"] + n["dur"]) - TRIM
        k = np.arange(int(np.ceil(a / HOP)), int(np.floor(b / HOP)) + 1)
        idx.append(k)
        val.append(np.full(len(k), float(n["pitch"])))
    return np.concatenate(idx), np.concatenate(val)


def score(ref_midi, k, v, shift):
    j = k + shift
    ok = (j >= 0) & (j < len(ref_midi))
    r = ref_midi[j[ok]]
    good = np.isfinite(r) & (np.abs(r - v[ok]) < 0.75)
    return int(good.sum()), int(np.isfinite(r).sum()), int(ok.sum())


def search(ref_midi, k, v, lo, hi):
    best = None
    for s in range(int(round(lo / HOP)), int(round(hi / HOP)) + 1):
        sc = score(ref_midi, k, v, s)
        if best is None or sc[0] > best[1][0]:
            best = (s, sc)
    return best


def main():
    ust_p, ref_w, out = sys.argv[1:4]
    lo, hi = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (-5.0, 15.0)
    notes = json.load(open(ust_p, encoding="utf-8"))["notes"]
    x, sr = sf.read(ref_w, always_2d=True)
    hz = common.praat_grid(x.mean(axis=1), sr, HOP)
    ref_midi = 69 + 12 * np.log2(hz / 440.0)
    k, v = ust_frames(notes)
    s, sc = search(ref_midi, k, v, lo, hi)
    res = {"offset_sec": s * HOP, "offset_tick": common.s2t(s * HOP), "matched": sc[0], "ref_voiced": sc[1], "ust_frames": sc[2],
           "match_rate": round(sc[0] / sc[2], 4), "segments": []}
    # 分段复核
    t_frames = k * HOP
    edges = np.linspace(t_frames.min(), t_frames.max() + HOP, 4)
    for name, a, b in zip(("前段", "中段", "后段"), edges[:-1], edges[1:]):
        sel = (t_frames >= a) & (t_frames < b)
        if sel.sum() < 200:
            continue
        ss, ssc = search(ref_midi, k[sel], v[sel], s * HOP - 0.5, s * HOP + 0.5)
        res["segments"].append({"segment": name, "ust_sec": [round(float(a), 2), round(float(b), 2)], "offset_sec": round(ss * HOP, 3),
                                "match_rate": round(ssc[0] / ssc[2], 4), "frames": int(sel.sum())})
    # 吻合率随偏移的形状（±60 ms），看峰是否尖
    res["curve_ms"] = {str(int(round(d * HOP * 1000))): round(score(ref_midi, k, v, s + d)[0] / sc[2], 4) for d in range(-12, 13, 2)}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
