"""给干声做 EQ 提亮（混音处理，不是 ACE 调教）：一个峰形 EQ（2.5–5 kHz）+ 一个高架 EQ（8 kHz 以上）。

用法：python -I eq_brighten.py <in.wav> <out.wav> <ltas.json> [bell_hz bell_q bell_db shelf_hz shelf_db] [--labels=<版本>[,<第二份参考>]]
- 默认参数：峰形 3300 Hz、Q 1.0、+3.3 dB；高架 8000 Hz、+6.5 dB（RBJ cookbook，斜率 S = 1）——《妄想感傷代償連盟》的值，新歌按频谱差重定。
- 目标（《妄想感傷代償連盟》用户 2026-10-21 同意的做法）：把调教版与原唱的长期平均频谱差在这两段各补一半。
  ltas.json 由 ltas_compare.py 生成（第一个 label 是原唱参考）；--labels 给调教版的 label（默认 r2），
  再给第二份参考（默认 refmix，原样分离的人声）时取两份参考的平均差。
  运行时打印每个 1/3 倍频程频点上“实际增益 / 想要增益”，供核对。
- 因果 IIR（与插件 EQ 相同），float64 计算，24-bit 写出；不做响度归一（A/B 时统一对齐），只报告峰值。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import sosfilt, sosfreqz  # noqa: E402

DEFAULT = (3300.0, 1.0, 3.3, 8000.0, 6.5)


def peaking(f0, q, gain_db, sr):
    a = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / (2 * q)
    b = [1 + al * a, -2 * np.cos(w), 1 - al * a]
    aa = [1 + al / a, -2 * np.cos(w), 1 - al / a]
    return np.array(b + aa) / aa[0]


def high_shelf(f0, gain_db, sr, s=1.0):
    a = 10 ** (gain_db / 40)
    w = 2 * np.pi * f0 / sr
    al = np.sin(w) / 2 * np.sqrt((a + 1 / a) * (1 / s - 1) + 2)
    c = np.cos(w)
    b0 = a * ((a + 1) + (a - 1) * c + 2 * np.sqrt(a) * al)
    b1 = -2 * a * ((a - 1) + (a + 1) * c)
    b2 = a * ((a + 1) + (a - 1) * c - 2 * np.sqrt(a) * al)
    a0 = (a + 1) - (a - 1) * c + 2 * np.sqrt(a) * al
    a1 = 2 * ((a - 1) - (a + 1) * c)
    a2 = (a + 1) - (a - 1) * c - 2 * np.sqrt(a) * al
    return np.array([b0, b1, b2, a0, a1, a2]) / a0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--labels=")]
    labels = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--labels=")), "r2,refmix").split(",")
    src, dst, ltas_p = args[0:3]
    bf, bq, bg, sf_, sg = map(float, args[3:8]) if len(args) >= 8 else DEFAULT
    if os.path.exists(dst):
        raise SystemExit(f"已存在：{dst}")
    x, sr = sf.read(src, always_2d=True, dtype="float64")
    sos = np.vstack([peaking(bf, bq, bg, sr), high_shelf(sf_, sg, sr)])
    y = sosfilt(sos, x, axis=0)
    peak = float(20 * np.log10(np.max(np.abs(y)) + 1e-12))
    if peak > -0.1:
        raise SystemExit(f"提亮后峰值 {peak:.2f} dBFS，会削波")
    sf.write(dst, y if y.shape[1] > 1 else y[:, 0], sr, subtype="PCM_24")
    lt = json.load(open(ltas_p, encoding="utf-8"))
    cs = np.array(lt["centers_hz"], dtype=float)
    d = np.array(lt["diff_db"][labels[0]])
    gap = d if len(labels) == 1 else (d + (d - np.array(lt["diff_db"][labels[1]]))) / 2  # 一份参考就是它的差；两份取平均
    want = -gap / 2
    _, h = sosfreqz(sos, worN=cs, fs=sr)
    got = 20 * np.log10(np.abs(h))
    print(f"EQ: bell {bf:.0f} Hz Q {bq} {bg:+.1f} dB | high shelf {sf_:.0f} Hz {sg:+.1f} dB | peak {peak:.2f} dBFS")
    for c, g, w in zip(cs, got, want):
        if c >= 1000:
            print(f"  {c:7.0f} Hz  actual {g:+5.1f} dB   wanted (half gap) {w:+5.1f} dB")
    json.dump({"params": {"bell_hz": bf, "bell_q": bq, "bell_db": bg, "shelf_hz": sf_, "shelf_db": sg, "shelf_slope": 1.0},
               "sos": sos.tolist(), "sr": sr, "peak_dbfs": peak,
               "response_db": {str(int(round(c))): round(float(g), 2) for c, g in zip(cs, got)},
               "wanted_half_gap_db": {str(int(round(c))): round(float(w), 2) for c, w in zip(cs, want)}},
              open(dst.replace(".wav", "_eq.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
