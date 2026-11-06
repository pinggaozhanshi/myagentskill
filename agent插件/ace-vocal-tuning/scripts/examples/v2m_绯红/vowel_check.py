"""长音核对：官方读音写成两个元音（o→u、e→i）的地方，原唱有没有真的唱出后一个元音。

用法：python -I vowel_check.py <score.json> <aligned.json> <ref_vocal.wav> <rmvpe_5ms.npy> <test.json>
test.json：[{"name": "#40/j41", "cell": "14:3:4", "prev": "14:3:3", "pair": ["o", "u"]}, ...]（小节:拍:十六分，第 0 小节起）。
- 模板：Vocal to MIDI 识别与官方读音一致的音（元音可靠），取音符中间 50% 的 MFCC 1–12 均值，按元音分组；
  只用和被测格音高相差 ≤ 5 半音的模板（高音区 MFCC 受音高影响大）。
- 被测格（跳过开头 30 ms）和它前一格（跳过开头 60 ms 的辅音）各算到两个元音模板中心的距离，并做 k=7 近邻投票。
  前一格像第一个元音、被测格像第二个元音 → 原唱唱出了第二个元音；两格都像第一个 → 只是拉长。
只打印元音字母和距离，不打印歌词。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from lyric_check import morae, vowel_of  # noqa: E402

import librosa  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 240  # 5 ms @ 48 kHz
Q = 120


def main():
    score_p, al_p, wav, rm_p, test_p = sys.argv[1:6]
    score = json.load(open(score_p, encoding="utf-8"))
    notes, g0 = score["notes"], score["meta"]["grid_zero_tick"]
    rows = {r["note"]: r for r in json.load(open(al_p, encoding="utf-8"))["rows"] if r["note"] is not None}
    x, sr = sf.read(wav, always_2d=True)
    x = x.mean(axis=1)
    mf = librosa.feature.mfcc(y=x.astype(np.float32), sr=sr, n_mfcc=13, n_fft=2048, hop_length=HOP)[1:13]
    f0 = 69 + 12 * np.log2(np.load(rm_p) / 440.0)

    def seg(a, b):
        return mf[:, int(a * sr / HOP):max(int(a * sr / HOP) + 1, int(b * sr / HOP))].mean(axis=1)

    def pitch(a, b):
        p = f0[int(a / 0.005):int(b / 0.005)]
        p = p[~np.isnan(p)]
        return float(np.median(p)) if len(p) else np.nan

    tmpl = []
    for n in notes:
        r = rows.get(n["idx"])
        if not r or r["official"] is None or n["lyric"].isascii() or (morae(n["lyric"]) or [None])[0] != r["official"]:
            continue
        v = vowel_of(r["official"])
        if r["official"] in ("ん", "っ") or v is None:
            continue
        s, e = n["start"], n["end"]
        a, b = s + 0.25 * (e - s), s + 0.75 * (e - s)
        tmpl.append((v, seg(a, b), pitch(a, b)))
    print("templates per vowel:", {v: sum(1 for t in tmpl if t[0] == v) for v in "aiueo"})

    def cell_time(pos):
        bar, beat, six = map(int, pos.split(":"))
        return common.t2s(g0 + bar * 1920 + (beat - 1) * 480 + (six - 1) * Q)

    for t in json.load(open(test_p, encoding="utf-8")):
        v1, v2 = t["pair"]
        out = [t["name"]]
        for label, pos, skip in (("prev", t["prev"], 0.06), ("cell", t["cell"], 0.03)):
            s = cell_time(pos)
            e = s + common.t2s(Q)
            m, p = seg(s + skip, e - 0.01), pitch(s + skip, e - 0.01)
            near = [tt for tt in tmpl if tt[0] in (v1, v2) and abs(tt[2] - p) <= 5]
            c = {v: np.mean([tt[1] for tt in near if tt[0] == v], axis=0) for v in (v1, v2) if any(tt[0] == v for tt in near)}
            d = {v: float(np.linalg.norm(m - cv)) for v, cv in c.items()}
            knn = sorted(near, key=lambda tt: np.linalg.norm(m - tt[1]))[:7]
            vote = {v: sum(1 for tt in knn if tt[0] == v) for v in (v1, v2)}
            n_t = {v: sum(1 for tt in near if tt[0] == v) for v in (v1, v2)}
            out.append(f"{label} {pos} p{p:5.1f} dist " + " ".join(f"{v}:{d.get(v, float('nan')):5.1f}" for v in (v1, v2)) +
                       f" knn {vote} (templates {n_t})")
        print(" | ".join(out))


if __name__ == "__main__":
    main()
