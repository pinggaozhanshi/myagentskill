"""副歌后段「ら」改「啦」、两处合并之后的核对（信号指标，不是听感）。

用法：python -I ra_fix_check.py <score_main.json> <ra_fix.json> <out.json> <对照 label>=<wav> <label>=<wav> ... [ref:<label>=<wav> ...]
第一个 label 是对照（r2，用户认可过的版本），其余逐个和它比；带 ref: 前缀的是原唱分离人声，只参与“衔接”一项。
- 电平：每个音 30–80% 处的 5 ms 包络中位数（dB），分 副歌前一句+副歌 / 副歌后段没改的音 / 改过的音 三组，给与对照的差。
- 波形：副歌前一句+副歌、副歌后段第一个「啦」之前两段，与对照的差信号能量（相对对照信号，dB）。
- 衔接：副歌后段里前后紧接、且至少一个是改过的音的每一对，交界 ±40 ms 内包络最低处减两侧音电平的平均（dB，越负断得越开）。
- 辅音：前面紧接着另一个音、自己不是延长音的每个改过的音（「啦」/「呐」），交界 −50…+30 ms 内包络最低帧的 alpha
  （1–5 kHz 对 50 Hz–1 kHz，21 ms 窗）比本音元音段（30–80%）的 alpha 低多少（dB）。鼻音 n 的声音主要从鼻腔出来、高频弱，
  这个差会比边音 l 大；只是粗略指标。延长音（「-」或空音符）按合并处理。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import crisp_metrics as cm  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = cm.HOP
NFFT = 1024


def mono(p):
    x, sr = sf.read(p, always_2d=True)
    if sr != 48000:
        raise SystemExit(f"需要 48 kHz：{p} {sr}")
    return x.mean(axis=1)


def alpha_track(x, sr):
    hop = int(round(HOP * sr))
    n = int(np.ceil(len(x) / hop)) + 1
    pad = np.concatenate([np.zeros(NFFT // 2), x, np.zeros(NFFT)])
    fr = np.lib.stride_tricks.sliding_window_view(pad, NFFT)[::hop][:n]
    spec = np.abs(np.fft.rfft(fr * np.hanning(NFFT), axis=1)) ** 2
    f = np.fft.rfftfreq(NFFT, 1 / sr)
    lo = spec[:, (f >= 50) & (f < 1000)].sum(axis=1) + 1e-20
    mid = spec[:, (f >= 1000) & (f < 5000)].sum(axis=1) + 1e-20
    return 10 * np.log10(mid / lo)


def main():
    score_p, fix_p, out = sys.argv[1:4]
    labels, refs = [], []
    for a in sys.argv[4:]:
        k, p = a.split("=", 1)
        (refs if k.startswith("ref:") else labels).append((k.removeprefix("ref:"), p))
    sr = 48000
    score = json.load(open(score_p, encoding="utf-8"))
    c0 = common.t2s(score["meta"]["clip_start_tick"])
    notes = score["notes"]
    rows = {r["idx"]: r for r in json.load(open(fix_p, encoding="utf-8"))["rows"]}
    ext = {i for i, r in rows.items() if r.get("extend") or r["lyric"] in ("-", "")}  # 延长音：「-」或空音符（v3 的 na_fix.json 也能用）
    sig = {k: mono(p) for k, p in labels + refs}
    env = {k: cm.envelope(x, sr) for k, x in sig.items()}
    base = labels[0][0]

    def win(n, a=0.3, b=0.8):
        s, d = n["start"] - c0, n["end"] - n["start"]
        return int((s + a * d) / HOP), int((s + b * d) / HOP)

    def lev(k, n):
        i, j = win(n)
        return float(np.median(env[k][i:j]))

    res = {"base": base, "levels": {}, "waveform": {}, "joins": [], "consonant": {}}
    groups = {"副歌前一句+副歌": [n for n in notes if n["idx"] <= 101],
              "副歌后段·没改的音": [n for n in notes if n["idx"] > 101 and n["idx"] not in rows],
              "副歌后段·改过的音": [n for n in notes if n["idx"] in rows]}
    first_edit = min(n["start"] for n in notes if n["idx"] in rows)
    secs = {"副歌前一句+副歌": (notes[0]["start"] - 0.5, notes[101]["end"]),
            "副歌后段·第一个「啦」之前": (notes[102]["start"], first_edit - 0.15)}
    for k, _ in labels[1:]:
        res["levels"][k] = {}
        for g, ns in groups.items():
            d = np.array([lev(k, n) - lev(base, n) for n in ns])
            w = int(np.argmax(np.abs(d)))
            res["levels"][k][g] = {"n": len(d), "median_db": round(float(np.median(d)), 2),
                                   "abs_p90_db": round(float(np.percentile(np.abs(d), 90)), 2),
                                   "abs_max_db": round(float(np.abs(d[w])), 2), "worst_idx": ns[w]["idx"]}
        res["waveform"][k] = {}
        for s, (a, b) in secs.items():
            i, j = int((a - c0) * sr), int((b - c0) * sr)
            x, y = sig[base][i:j], sig[k][i:j]
            e = np.mean((y - x) ** 2)
            res["waveform"][k][s] = None if e == 0 else round(float(10 * np.log10(e / np.mean(x ** 2))), 1)
    for x, y in zip(notes, notes[1:]):
        if x["idx"] < 102 or not (x["idx"] in rows or y["idx"] in rows) or x["tick"] + x["dur"] != y["tick"]:
            continue
        t = y["start"] - c0
        i0, i1 = int((t - 0.04) / HOP), int((t + 0.04) / HOP)
        row = {"pair": f"#{x['idx']}->#{y['idx']}", "at_sec": round(y["start"], 2), "merged": y["idx"] in ext}
        for k in env:
            row[k] = round(float(env[k][i0:i1].min() - (lev(k, x) + lev(k, y)) / 2), 1)
        res["joins"].append(row)
    alpha = {k: alpha_track(sig[k], sr) for k, _ in labels}
    for k, _ in labels:
        per = []
        for x, y in zip(notes, notes[1:]):
            if y["idx"] not in rows or y["idx"] in ext or x["tick"] + x["dur"] != y["tick"]:
                continue
            t = y["start"] - c0
            i0, i1 = int((t - 0.05) / HOP), int((t + 0.03) / HOP)
            c = i0 + int(np.argmin(env[k][i0:i1]))
            i, j = win(y)
            per.append({"idx": y["idx"], "alpha_drop_db": round(float(np.median(alpha[k][i:j]) - alpha[k][c]), 1),
                        "dip_db": round(float(env[k][c] - (lev(k, x) + lev(k, y)) / 2), 1)})
        res["consonant"][k] = {"n": len(per), "alpha_drop_median_db": round(float(np.median([p["alpha_drop_db"] for p in per])), 1),
                               "dip_median_db": round(float(np.median([p["dip_db"] for p in per])), 1), "notes": per}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res["levels"].items():
        for g, s in v.items():
            print(f"{k} vs {base} {g}: n={s['n']} 电平差中位 {s['median_db']:+.2f} dB，|差| p90 {s['abs_p90_db']:.2f}，最大 {s['abs_max_db']:.2f}（#{s['worst_idx']}）")
        print(f"{k} vs {base} 波形差（相对 {base}）:", res["waveform"][k])
    for r in res["joins"]:
        print(r["pair"], f"{r['at_sec']:.2f}s", "合并" if r["merged"] else "    ", " | ".join(f"{k} {r[k]:+6.1f}" for k in env))
    for k, v in res["consonant"].items():
        print(f"{k} 辅音段（{v['n']} 个紧接的「啦」/「ら」起头）：alpha 比元音低 中位 {v['alpha_drop_median_db']:.1f} dB，包络低 中位 {v['dip_median_db']:.1f} dB")


if __name__ == "__main__":
    main()
