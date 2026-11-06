"""“干脆”度量（信号指标，不是听感）：原唱参考 vs 各合成版本，逐音符的起音、收音、音间断开、长音平稳度与音色。

用法：python -I crisp_metrics.py <pilot_score.json> <g2p.json> <out.json> <label>=<clip.wav>[,<features.npz>] ...
第一个 label 当参考（原唱，去混响分离人声），后面的与它比。所有 wav 都从片段起点开始、48 kHz。
包络：10 ms 汉宁窗均方根（dB），5 ms 一帧；有声：Praat（common.praat_grid）。
- 内部电平 L：音符 30%–80% 段的包络中位数。
- 起音（前面是休止或清辅音间隙的音）：音符起点 -60..+120 ms 内，包络首次升到 L−20 dB 到首次升到 L−3 dB 的时间。
- 收音（后面是休止或清辅音的音）：最后一次 ≥ L−3 dB 到其后首次 < L−20 dB 的时间（找不到记 None）。
- 断开（与下一个音直接相连、下一个音以浊辅音或元音开头）：交界 ±40 ms 内包络最小值 − 两个音内部电平的平均（dB，越负越断开）。
- 平稳（≥150 ms 的音）：20%–90% 段包络的标准差（dB）；尾部衰减 = 最后 25% 的均值 − 前 25% 的均值（dB）。
- 音色（可选，给 features.npz 时）：voice_features.py 的 alpha_db（亮度）、hf_db（5–12 kHz）、h1h2_db、hnr_db 在 30%–80% 段的中位数。
target=False 的音符不计。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
VOICELESS = common.VOICELESS_INIT
SPEC = ("alpha_db", "hf_db", "h1h2_db", "hnr_db")


def envelope(x, sr):
    w = int(0.010 * sr)
    hop = int(round(HOP * sr))
    n = int(np.ceil(len(x) / hop)) + 1
    pad = np.concatenate([np.zeros(w // 2), x, np.zeros(w)])
    fr = np.lib.stride_tricks.sliding_window_view(pad, w)[::hop][:n]
    win = np.hanning(w)
    return 10 * np.log10(np.mean((fr * win) ** 2, axis=1) / np.mean(win ** 2) + 1e-12)


def seg(a, b, n):
    return max(0, int(np.ceil(a / HOP))), min(n, int(np.floor(b / HOP)) + 1)


def measure(env, notes, heads, feats):
    n = len(env)
    rows = []
    for k, nt in enumerate(notes):
        s, e = nt["a"], nt["b"]
        d = e - s
        i0, i1 = seg(s + 0.3 * d, s + 0.8 * d, n)
        L = float(np.median(env[i0:i1])) if i1 > i0 else None
        prev_adj = k > 0 and abs(notes[k - 1]["b"] - s) < 1e-6
        nxt = notes[k + 1] if k + 1 < len(notes) else None
        next_adj = nxt is not None and abs(nxt["a"] - e) < 1e-6
        r = {"idx": nt["idx"], "L": L}
        if L is None or not nt["target"]:
            rows.append(r)
            continue
        # 起音
        if not prev_adj or heads[k] in VOICELESS:
            a0, a1 = seg(s - 0.06, s + 0.12, n)
            w = env[a0:a1]
            j20 = np.where(w >= L - 20)[0]
            j3 = np.where(w >= L - 3)[0]
            if len(j20) and len(j3) and j3[0] >= j20[0]:
                r["attack_ms"] = (j3[0] - j20[0]) * HOP * 1000
        # 收音
        if nxt is None or not next_adj or heads[k + 1] in VOICELESS:
            b0, b1 = seg(s + 0.3 * d, e + 0.15, n)
            w = env[b0:b1]
            j3 = np.where(w >= L - 3)[0]
            if len(j3):
                after = np.where(w[j3[-1]:] < L - 20)[0]
                if len(after):
                    r["release_ms"] = after[0] * HOP * 1000
        # 断开
        if next_adj and heads[k + 1] not in VOICELESS and nxt["target"]:
            dn = nxt["b"] - nxt["a"]
            j0, j1 = seg(nxt["a"] + 0.3 * dn, nxt["a"] + 0.8 * dn, n)
            if j1 > j0:
                L2 = float(np.median(env[j0:j1]))
                c0, c1 = seg(e - 0.04, e + 0.04, n)
                r["dip_db"] = float(env[c0:c1].min() - (L + L2) / 2)
                r["dip_next_head"] = heads[k + 1] or "(元音)"
        # 平稳
        if d >= 0.15:
            q0, q1 = seg(s + 0.2 * d, s + 0.9 * d, n)
            w = env[q0:q1]
            if len(w) >= 8:
                r["interior_std_db"] = float(np.std(w))
                m = max(1, len(w) // 4)
                r["tail_decay_db"] = float(np.mean(w[-m:]) - np.mean(w[:m]))
        if feats is not None:
            for f in SPEC:
                v = feats[f][i0:i1]
                v = v[np.isfinite(v)]
                if len(v) >= 4:
                    r[f] = float(np.median(v))
        rows.append(r)
    return rows


def main():
    score_p, g2p_p, out = sys.argv[1:4]
    score = json.load(open(score_p, encoding="utf-8"))
    clip0 = score["meta"]["clip_start_tick"]
    notes = [dict(n, a=common.t2s(n["tick"] - clip0), b=common.t2s(n["tick"] + n["dur"] - clip0)) for n in score["notes"]]
    heads = common.head_consonants(score["notes"], g2p_p)
    heads = [heads.get(k, "") for k in range(len(notes))]
    res, labels = {}, []
    for item in sys.argv[4:]:
        label, paths = item.split("=", 1)
        wav, _, npz = paths.partition(",")
        x, sr = sf.read(wav, always_2d=True)
        feats = dict(np.load(npz)) if npz else None
        res[label] = measure(envelope(x.mean(axis=1), sr), notes, heads, feats)
        labels.append(label)
    ref = labels[0]
    keys = ["attack_ms", "release_ms", "dip_db", "interior_std_db", "tail_decay_db"] + list(SPEC)
    summary = {}
    for key in keys:
        line = {}
        for lab in labels:
            v = [r[key] for r in res[lab] if r.get(key) is not None]
            line[lab] = {"n": len(v), "median": round(float(np.median(v)), 2) if v else None}
        for lab in labels[1:]:
            pair = [(a[key], b[key]) for a, b in zip(res[ref], res[lab]) if a.get(key) is not None and b.get(key) is not None]
            if pair:
                dd = np.array([y - x for x, y in pair])
                line[f"{lab}-{ref}"] = {"n": len(pair), "median": round(float(np.median(dd)), 2),
                                         "p25": round(float(np.percentile(dd, 25)), 2), "p75": round(float(np.percentile(dd, 75)), 2)}
        summary[key] = line
        print(f"{key:16s} " + " | ".join(f"{k}: {v}" for k, v in line.items()))
    json.dump({"summary": summary, "rows": res, "heads": heads}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
