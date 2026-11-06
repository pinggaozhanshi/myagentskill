"""逐帧声音特征（5 ms 网格，t=0 = 文件起点 = 片段起点），供第 3 轮表情参数的标定与目标推导用。

用法：python -I voice_features.py <in.wav> <out.npz>
特征（都是信号指标，不是听感）：
- f0：Praat（common.praat_grid），Hz，无声 = NaN。
- rms_db：30 ms 汉宁窗均方根（dBFS）。
- alpha_db：1–5 kHz 对 50 Hz–1 kHz 的能量比（dB），越大越亮 / 越“紧”。
- hf_db：5–12 kHz 对 50 Hz–5 kHz 的能量比（dB），气息噪声、齿音会抬高它。
- h1h2_db：第 1、第 2 谐波幅度差（dB，未做共振峰校正），越大越接近假声 / 气声的“基音为主”。
- hnr_db：Praat 互相关谐噪比（dB），越低越多气息噪声。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import parselmouth  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
NFFT = 2048


def features(x, sr):
    hop = int(round(HOP * sr))
    n = int(np.ceil(len(x) / hop)) + 1
    pad = np.concatenate([np.zeros(NFFT // 2), x, np.zeros(NFFT)])
    win = np.hanning(NFFT)
    frames = np.lib.stride_tricks.sliding_window_view(pad, NFFT)[::hop][:n]
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)

    def band(a, b):
        m = (freqs >= a) & (freqs < b)
        return spec[:, m].sum(axis=1) + 1e-20

    lo, mid, hi = band(50, 1000), band(1000, 5000), band(5000, 12000)
    w30 = int(0.03 * sr)
    pad2 = np.concatenate([np.zeros(w30 // 2), x, np.zeros(w30)])
    fr2 = np.lib.stride_tricks.sliding_window_view(pad2, w30)[::hop][:n]
    rms_db = 10 * np.log10(np.mean((fr2 * np.hanning(w30)) ** 2, axis=1) / np.mean(np.hanning(w30) ** 2) + 1e-20)

    f0 = common.praat_grid(x, sr, HOP)[:n]
    f0 = np.concatenate([f0, np.full(n - len(f0), np.nan)])
    h1h2 = np.full(n, np.nan)
    df = freqs[1]
    mag_db = 10 * np.log10(spec + 1e-20)
    for k in np.where(np.isfinite(f0))[0]:
        f = f0[k]
        r = max(1, int(0.25 * f / df))
        b1, b2 = int(round(f / df)), int(round(2 * f / df))
        if b2 + r >= mag_db.shape[1]:
            continue
        h1h2[k] = mag_db[k, b1 - r:b1 + r + 1].max() - mag_db[k, b2 - r:b2 + r + 1].max()

    snd = parselmouth.Sound(np.asarray(x, dtype=np.float64), sampling_frequency=sr)
    hc = snd.to_harmonicity_cc(time_step=HOP, minimum_pitch=100.0, silence_threshold=0.03, periods_per_window=1.0)
    ht = np.asarray(hc.xs())
    hv = np.asarray(hc.values[0], dtype=float)
    hv[hv < -100] = np.nan
    tk = np.arange(n) * HOP
    hnr = np.interp(tk, ht, np.nan_to_num(hv, nan=-999.0), left=-999.0, right=-999.0)
    near_nan = np.interp(tk, ht, np.isnan(hv).astype(float), left=1.0, right=1.0) > 0.01
    hnr[near_nan | (hnr < -100)] = np.nan
    return {"f0": f0, "rms_db": rms_db, "alpha_db": 10 * np.log10(mid / lo), "hf_db": 10 * np.log10(hi / (lo + mid)),
            "h1h2_db": h1h2, "hnr_db": hnr}


def main():
    src, out = sys.argv[1:3]
    x, sr = sf.read(src, always_2d=True)
    x = x.mean(axis=1)
    if sr != 48000:
        raise SystemExit(f"需要 48 kHz：{sr}")
    feats = features(x, sr)
    np.savez_compressed(out, hop=HOP, sr=sr, **feats)
    v = np.isfinite(feats["f0"])
    print(os.path.basename(src), f"frames={len(feats['f0'])} voiced={v.mean():.2f}",
          " ".join(f"{k}={np.nanmedian(feats[k][v]):.2f}" for k in ("rms_db", "alpha_db", "hf_db", "h1h2_db", "hnr_db")))


if __name__ == "__main__":
    main()
