"""重复句和模板句的距离：音高（音分）、音量包络（dB）、对数频谱，逐句逐轨报出来，不判好坏。

python -I scripts/final_phrase_match.py <spec.json> <out.json> <标签>:<role>=<wav> [...]
spec.json：{"template": {"wav": ..., "tick": 493, "len": 1440, "pre": 120},
            "items": [{"name": "A1", "role": "rin", "tick": 61933, "transpose": 0, "harm_map": [[..]]}, ...]}
template 是听感基准（用户点名的那一句）。和声的音高比较先把模板映射到和声的音符上。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import numpy as np
import soundfile as sf
from scipy.signal import stft

SR = 48000
HOP = .005


def seg(x, tick, pre, length):
    a = common.t2s(tick - pre)
    s = int(round(a * SR))
    e = s + int(round(common.t2s(pre + length) * SR))
    if s < 0:
        return np.pad(x[:e], (-s, 0))
    return x[s:e]


def env(x):
    h = int(HOP * SR)
    m = len(x) // h
    return 10 * np.log10(np.mean(x[:m * h].reshape(m, h) ** 2, axis=1) + 1e-12)


def f0(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        g = common.praat_grid(x, SR, HOP)
        return 69 + 12 * np.log2(g / 440)


def spec(x):
    f, _, z = stft(x, SR, nperseg=2048, noverlap=2048 - 240)
    return f, 20 * np.log10(np.abs(z) + 1e-6)


def compare(a, b, tp, hmap):
    """a 是模板，b 是这一句。"""
    fa, fb = f0(a), f0(b)
    n = min(len(fa), len(fb))
    fa, fb = fa[:n], fb[:n]
    if hmap:
        xs, ys = zip(*hmap)
        fa = np.interp(fa, xs, ys, left=np.nan, right=np.nan)
    both = np.isfinite(fa) & np.isfinite(fb)
    d = (fb - tp - fa)[both] * 100
    ea, eb = env(a), env(b)
    m = min(len(ea), len(eb))
    act = (ea[:m] > -45) | (eb[:m] > -45)
    off = float(np.median((eb[:m] - ea[:m])[act]))
    fq, sa = spec(a)
    _, sb = spec(b)
    k = min(sa.shape[1], sb.shape[1])
    band = (fq >= 200) & (fq <= 8000)
    frames = (10 * np.log10(np.mean(10 ** (sa[:, :k] / 10), axis=0)) > -70) | (10 * np.log10(np.mean(10 ** (sb[:, :k] / 10), axis=0)) > -70)
    dist = float(np.sqrt(np.mean((sa[band][:, frames] - sb[band][:, frames]) ** 2)))
    return {"pitch_med_c": round(float(np.median(np.abs(d))), 1), "pitch_p90_c": round(float(np.percentile(np.abs(d), 90)), 1),
            "voiced_frames": int(both.sum()), "level_offset_db": round(off, 2),
            "env_med_db": round(float(np.median(np.abs(eb[:m] - ea[:m] - off)[act])), 2), "spec_rms_db": round(dist, 2)}


def main():
    sp = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tpl = sp["template"]
    x, _ = sf.read(tpl["wav"], always_2d=True)
    a = seg(x.mean(axis=1), tpl["tick"], tpl.get("pre", 120), tpl["len"])
    wavs = {}
    for s in sys.argv[3:]:
        head, path = s.split("=", 1)
        label, role = head.split(":")
        y, _ = sf.read(path, always_2d=True)
        wavs[(label, role)] = y.mean(axis=1)
    labels = sorted({k[0] for k in wavs}, key=[k[0] for k in wavs].index)
    rep = []
    print(f"{'句':<4}{'轨':<6}" + "".join(f"| {lb}: 音高中位/p90  电平差  包络差  频谱差 " for lb in labels))
    for it in sp["items"]:
        row = {"name": it["name"], "role": it["role"]}
        cells = []
        for lb in labels:
            if (lb, it["role"]) not in wavs:
                continue
            b = seg(wavs[(lb, it["role"])], it["tick"], tpl.get("pre", 120), tpl["len"])
            r = compare(a, b, it.get("transpose", 0), it.get("harm_map"))
            row[lb] = r
            cells.append(f"| {r['pitch_med_c']:6.1f}/{r['pitch_p90_c']:6.1f} {r['level_offset_db']:6.2f} {r['env_med_db']:5.2f} {r['spec_rms_db']:6.2f} ")
        rep.append(row)
        print(f"{it['name']:<4}{it['role']:<6}" + "".join(cells), flush=True)
    Path(sys.argv[2]).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
