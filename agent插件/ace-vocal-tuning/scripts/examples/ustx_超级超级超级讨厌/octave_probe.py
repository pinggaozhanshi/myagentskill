"""八度判定：在指定时刻取 80 ms 窗，比较候选基频 f 的奇次谐波（f, 3f, 5f）与偶次谐波（2f, 4f）能量。
若真实基频是 2f，则 f、3f、5f 处几乎没有能量；若真实基频是 f，奇次谐波明显存在。

用法：python -I octave_probe.py <wav> <official_offset_sec_of_wav_start> <t_official> <f_low_hz> [<t> <f> ...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_common  # noqa: E402,F401

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402


def band_db(spec, freqs, f, width=0.04):
    m = (freqs > f * (1 - width)) & (freqs < f * (1 + width))
    return 10 * np.log10(spec[m].max() + 1e-12)


def main():
    path, wav0 = sys.argv[1], float(sys.argv[2])
    pairs = list(zip(map(float, sys.argv[3::2]), map(float, sys.argv[4::2])))
    x, sr = sf.read(path, always_2d=True, dtype="float64")
    x = x.mean(axis=1)
    win = int(0.08 * sr)
    for t, f in pairs:
        i = int((t - wav0) * sr)
        seg = x[i - win // 2: i + win // 2] * np.hanning(win)
        n = 1 << 16
        spec = np.abs(np.fft.rfft(seg, n)) ** 2
        freqs = np.fft.rfftfreq(n, 1 / sr)
        floor = 10 * np.log10(np.median(spec[(freqs > 100) & (freqs < 6000)]) + 1e-12)
        odd = [band_db(spec, freqs, k * f) - floor for k in (1, 3, 5)]
        even = [band_db(spec, freqs, k * f) - floor for k in (2, 4, 6)]
        verdict = "基频≈f（低八度）" if min(odd[:2]) > 15 else ("基频≈2f（高八度）" if max(odd[:2]) < 8 else "不确定")
        print(f"t={t:7.3f}s f={f:6.1f}Hz  odd(f,3f,5f) dB above floor: {odd[0]:5.1f} {odd[1]:5.1f} {odd[2]:5.1f} | even(2f,4f,6f): {even[0]:5.1f} {even[1]:5.1f} {even[2]:5.1f} → {verdict}")


if __name__ == "__main__":
    main()
