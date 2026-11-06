"""参考人声 = 官方音轨 − g·伴奏（PaiMe 工程内嵌的去人声伴奏，与官方音轨偏移 0 s）。

用法：python -I make_reference.py <official.wav> <instrumental.wav> <out_dir> <clip_begin_tick> <clip_end_tick>
输入是 ffmpeg 解码的同采样率立体声 wav。输出：
- ref_vocal_full.wav：整首，立体声相减后取单声道，原采样率；
- ref_vocal_clip_48k.wav：片段范围（与 ACE 导出同一时间轴），48 kHz 单声道；
- inst_clip_48k.wav、official_clip_48k.wav：同一范围的伴奏与原曲（混音用）；
- make_reference.json：增益、各段残差（无人声段越低越干净）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402


def db(v):
    return float(20 * np.log10(v + 1e-12))


def main():
    off_p, inst_p, out, c0, c1 = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    a, sr = sf.read(off_p, always_2d=True, dtype="float64")
    b, sr2 = sf.read(inst_p, always_2d=True, dtype="float64")
    assert sr == sr2 and a.shape[1] == b.shape[1] == 2
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    g = float(np.sum(a * b) / np.sum(b * b))
    v = (a - g * b).mean(axis=1)
    os.makedirs(out, exist_ok=True)
    sf.write(os.path.join(out, "ref_vocal_full.wav"), v, sr, subtype="FLOAT")

    def rms(x, t0, t1):
        return db(np.sqrt(np.mean(x[int(t0 * sr):int(t1 * sr)] ** 2)))

    am = a.mean(axis=1)
    report = {"gain_inst": round(g, 5), "sr": sr,
              "residual_vs_mix_db_no_vocal_0-15s": round(rms(v, 0.5, 15.0) - rms(am, 0.5, 15.0), 1),
              "residual_vs_mix_db_no_vocal_136-150s": round(rms(v, 136.0, 150.0) - rms(am, 136.0, 150.0), 1),
              "vocal_rms_dbfs_16-40s": round(rms(v, 16.0, 40.0), 1),
              "noise_rms_dbfs_0-15s": round(rms(v, 0.5, 15.0), 1)}
    s0, s1 = int(round(common.t2s(c0) * sr)), int(round(common.t2s(c1) * sr))

    def clip48(x):
        x = x[s0:s1]
        return resample_poly(x, 160, 147, axis=0) if sr == 44100 else x

    sf.write(os.path.join(out, "ref_vocal_clip_48k.wav"), clip48(v), 48000, subtype="FLOAT")
    sf.write(os.path.join(out, "inst_clip_48k.wav"), clip48(b), 48000, subtype="FLOAT")
    sf.write(os.path.join(out, "official_clip_48k.wav"), clip48(a), 48000, subtype="FLOAT")
    report["clip_ticks"] = [c0, c1]
    report["clip_sec"] = [common.t2s(c0), common.t2s(c1)]
    json.dump(report, open(os.path.join(out, "make_reference.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
