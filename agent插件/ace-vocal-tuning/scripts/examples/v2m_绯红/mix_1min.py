"""一分钟版混音：洛天依主唱（ACE 干声，效果链停用导出）+ ACE 分离伴奏 → 成品 WAV / MP3，另附同区间的干声。

用法：python -I mix_1min.py <score.json> <main_dry.wav> <inst_full.wav> <vocal_stem_full.wav> <ref_praat_full_5ms.npy> <out_dir> <name>
                          [--inst-db <dB>] [--end-fade-ms <ms>] [--suffix <s>]
- 区间：主唱第一个非静音帧（5 ms 均方根 > −80 dBFS）前 20 ms 开始、10 ms 淡入（不留 27 秒钢琴前奏，开头就是人声）；
  结束在第二段主歌的弱起（参考人声 78 s 之后第一段 ≥ 50 ms 的有声）之前 70 ms，最后 3 s 淡出。
- 主唱：100 Hz 二阶高通 → 压缩（RMS 5 ms、阈值 = 有声段电平中位数、3:1、6 dB 软拐点、启动 5 ms、释放 80 ms）。
  不提亮：之前三次盲听都选了不提亮的版本。
- 混响：300 Hz–8 kHz 带通后卷积合成的立体声混响（T60 1.4 s、预延迟 25 ms，固定种子），比干声低 15 dB（LUFS）。
- 延迟：5 kHz 低通，八分音符（294 ms）左右交替 3 次，比干声低 22 dB。
- 电平：人声总线对伴奏的响度差 = 原曲同一段（第一个音到最后一个音）里不去混响分离人声对分离伴奏的差；
  --inst-db 再把伴奏相对人声调低 / 调高（负数 = 伴奏更小；用户 2026-10-24 听 v1：“音乐有点响”）。
- --end-fade-ms：干声里在 10 ms 内掉到数字静音的乐句结尾（ACE 2.1.9 渲染的硬切；原唱在同一处是 30–60 ms 的平滑衰减），
  在掉落点之前加这么长的余弦淡出；交付的干声也带这个淡出。
- 母带：整体到约 −10 LUFS，前瞻 5 ms 限幅（4 倍过采样测峰），峰值 ≤ −1 dBTP。
输出：<out_dir>/<name>_混音.wav（48 kHz / 24-bit 立体声）与 .mp3（320 kbps）；<name>_干声.wav / .mp3（同区间、单声道、不加处理）；
人声总线 .wav；mix_report.json。
（由《妄想感傷代償連盟》的 mix_chorus.py 改写：去掉和声，结尾按下一段弱起定；处理函数直接复用。）
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from mix_chorus import (CEIL_DBTP, PRE_ROLL, SR, compressor, fade, hpf, limiter, lpf, pingpong, reverb_ir,  # noqa: E402
                        true_peak_db, vocal_onset)

import numpy as np  # noqa: E402
import pyloudnorm as pyln  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import fftconvolve  # noqa: E402

TARGET_LUFS = -10.0
FADE_OUT = 3.0
END_GUARD = 0.070


def hard_end_fades(y, fade_ms, hop=0.005):
    """找出 5 ms 帧电平从 > −55 dBFS 落到 ≤ −55、随后两帧 ≤ −100 dBFS 的位置（硬切），在它之前加余弦淡出。返回 (新信号, 位置秒)。"""
    w = int(hop * SR)
    m = len(y) // w
    e = 10 * np.log10(np.mean(y[:m * w].reshape(m, w) ** 2, axis=1) + 1e-12)
    out, at = y.copy(), []
    n = int(fade_ms / 1000 * SR)
    for k in range(20, m - 4):
        if e[k] > -55 and e[k + 1] <= -55 and np.all(e[k + 2:k + 4] <= -100):
            end = (k + 1) * w
            nz = np.nonzero(np.abs(y[k * w:end]) > 1e-7)[0]
            end = k * w + (nz[-1] + 1 if len(nz) else 0)
            a = max(0, end - n)
            out[a:end] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(end - a) / max(1, end - a))
            at.append(round(end / SR, 3))
    return out, at


def next_section_onset(praat_p, after_sec=78.0, min_run=0.05, hop=0.005):
    v = ~np.isnan(np.load(praat_p))
    k, need = int(after_sec / hop), int(min_run / hop)
    while k < len(v) - need:
        if v[k:k + need].all():
            return k * hop
        k += 1
    raise SystemExit("找不到下一段人声")


def main():
    score_p, main_p, inst_p, vstem_p, ref_pr_p, out, name = sys.argv[1:8]
    opt = sys.argv[8:]
    inst_db = float(opt[opt.index("--inst-db") + 1]) if "--inst-db" in opt else 0.0
    end_fade = float(opt[opt.index("--end-fade-ms") + 1]) if "--end-fade-ms" in opt else 0.0
    suffix = opt[opt.index("--suffix") + 1] if "--suffix" in opt else ""
    os.makedirs(out, exist_ok=True)
    score = json.load(open(score_p, encoding="utf-8"))
    clip0 = common.t2s(score["meta"]["clip_start_tick"])
    first, last_end = score["notes"][0]["start"], score["notes"][-1]["end"]
    S = vocal_onset((main_p,), clip0) - PRE_ROLL
    nxt = next_section_onset(ref_pr_p)
    E = nxt - END_GUARD
    n = int(round((E - S) * SR))
    meter = pyln.Meter(SR)
    loud = meter.integrated_loudness

    def place(path):
        x, sr = sf.read(path, always_2d=True, dtype="float64")
        assert sr == SR
        x = x.mean(axis=1)
        y = np.zeros(n)
        o = int(round((clip0 - S) * SR))
        if o < 0:  # 片段起点早于成品起点：去掉前面这段（人声在这里是静音）
            x, o = x[-o:], 0
        y[o:o + len(x)] = x[:max(0, n - o)]
        return y

    def cut(path):
        x, sr = sf.read(path, always_2d=True, dtype="float64", start=int(round(S * SR)), frames=n)
        assert sr == SR and len(x) == n
        return x if x.shape[1] == 2 else np.repeat(x, 2, axis=1)

    rep = {"window_sec": [round(S, 3), round(E, 3)], "window_start_sample": int(round(S * SR)), "duration_sec": round(n / SR, 3),
           "next_section_vocal_onset_sec": round(nxt, 3), "fade_in_sec": 0.010, "fade_out_sec": FADE_OUT,
           "first_note_sec": first, "last_note_end_sec": last_end}
    raw = place(main_p)
    if end_fade > 0:
        raw, fades = hard_end_fades(raw, end_fade)
        rep["end_fades"] = {"fade_ms": end_fade, "at_sec_in_file": fades, "at_sec_original": [round(S + t, 3) for t in fades]}
    main_v = hpf(raw, 100)
    e = 10 * np.log10(np.convolve(main_v ** 2, np.ones(240) / 240, mode="same")[::240] + 1e-20)
    main_c, rep["comp_main"] = compressor(main_v, float(np.median(e[e > -50])))
    dup = lambda v: np.repeat(v[:, None], 2, axis=1)  # noqa: E731
    ld = loud(dup(main_c))
    send = lpf(hpf(main_c, 300), 8000)
    rev = fftconvolve(send[:, None], reverb_ir(), axes=0)[:n]
    rev *= 10 ** ((ld - 15 - loud(rev)) / 20)
    dl = pingpong(lpf(main_c, 5000), 60.0 / common.BPM / 2)
    dl *= 10 ** ((ld - 22 - loud(dl)) / 20)
    vbus = dup(main_c) + rev + dl
    inst, vstem = cut(inst_p), cut(vstem_p)
    a, b = int((first - S) * SR), int((last_end - S) * SR)
    ratio = loud(vstem[a:b]) - loud(inst[a:b])
    vbus *= 10 ** ((loud(inst[a:b]) + ratio - inst_db - loud(vbus[a:b])) / 20)
    rep["original_vocal_minus_inst_lufs"] = round(ratio, 2)
    rep["inst_db_vs_original"] = inst_db
    rep["vocal_minus_inst_lufs_target"] = round(ratio - inst_db, 2)
    fo = E - S - FADE_OUT
    mix = fade(inst + vbus, 0.010, fo, FADE_OUT)
    vbus_f = fade(vbus, 0.010, fo, FADE_OUT)
    g = 10 ** ((TARGET_LUFS - loud(mix)) / 20)
    mix, vbus_f = mix * g, vbus_f * g
    rep["pre_limiter_true_peak_dbtp"] = round(true_peak_db(mix), 2)
    mix, rep["limiter"] = limiter(mix, CEIL_DBTP)
    off = cut(os.path.join(os.path.dirname(os.path.abspath(inst_p)), "..", "audio", "official_full_48k.wav"))
    rep.update({"final_lufs": round(loud(mix), 2), "final_true_peak_dbtp": round(true_peak_db(mix), 2),
                "official_same_window_lufs": round(loud(off), 2), "official_same_window_true_peak_dbtp": round(true_peak_db(off), 2)})
    base = os.path.join(out, name)
    targets = [base + s + suffix for s in ("_混音", "_干声")]
    targets = [t + ext for t in targets for ext in (".wav", ".mp3")]
    for p in targets:
        if os.path.exists(p):
            raise SystemExit(f"已存在：{p}")
    sf.write(base + "_混音" + suffix + ".wav", mix, SR, subtype="PCM_24")
    sf.write(base + "_干声" + suffix + ".wav", raw, SR, subtype="PCM_24")
    sf.write(os.path.join(out, "人声总线_主唱混响延迟" + suffix + ".wav"), vbus_f, SR, subtype="PCM_24")
    for stem in ("_混音", "_干声"):
        subprocess.run(["ffmpeg", "-v", "error", "-n", "-i", base + stem + suffix + ".wav", "-c:a", "libmp3lame", "-b:a", "320k",
                        base + stem + suffix + ".mp3"], check=True)
    json.dump(rep, open(os.path.join(out, "mix_report" + suffix + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
