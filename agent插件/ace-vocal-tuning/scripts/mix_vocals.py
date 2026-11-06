"""成品混音：ACE 主唱干声（+ 可选和声，效果链停用导出）+ 伴奏 → 成品 WAV / MP3。从《妄想感傷代償連盟》的 mix_chorus.py 通用化而来。

用法：python -I mix_vocals.py <score.json> <main.wav> <harmony.wav|-> <inst_full.wav> <vocal_stem_full.wav> <out_dir>
                             [--cut-to-vocal] [--end-at <秒>] [--inst-db <dB>] [--end-fade-ms <ms>] [--suffix <s>] [--official <wav>]
- score.json：单轨 {"meta", "notes"} 或多轨 {"meta", "tracks"}（取第一条轨的音定区间）；干声文件从片段起点（clip_start_tick）开始。
- inst_full / vocal_stem_full：整首的伴奏与原曲人声分轨（官方或分离的），只用来定“人声比伴奏”的电平，不进成品。
- 音色不做提亮（三次盲听都偏向不提亮；要提亮先单独做 EQ 盲听，见 eq_brighten.py）。
- 区间：第一个音所在小节往前再 1 小节的强拍，到最后一个音所在小节之后的强拍再加 3 s 淡出；开头 0.3 s 淡入。
  小节线：project.json 的 downbeat_tick（第 0 小节强拍的 ACE tick）、beats_per_bar（默认 4）、bpm。
- --cut-to-vocal：从人声第一个非静音帧（5 ms 均方根 > −80 dBFS）之前 20 ms 开始，淡入改成 10 ms（只为不爆音）。
- --end-at：成品在原曲这个时间结束（例如下一段人声弱起之前 70 ms），最后 3 s 淡出；不给就按小节算。
- --inst-db：伴奏相对“原曲人声比例”再调多少 dB（负数 = 伴奏更小、人声更靠前）。《绯红》用户嫌按原曲比例“音乐有点响”，
  v2 用 −4，另给 −7 的备选。
- --end-fade-ms：干声里 10 ms 内掉到数字静音的乐句结尾（ACE 2.1.9 渲染的硬切；原唱是 30–60 ms 的平滑衰减），
  在掉落点之前加这么长的余弦淡出（《绯红》用 35）；交付的干声也带这个淡出，位置写进 mix_report。
- --suffix：所有输出文件名加这个后缀（同一目录放几个版本）；--official：报告里加原曲同一区间的响度与峰值。
- 主唱：100 Hz 二阶高通 → 压缩（RMS 检测 5 ms、阈值 = 有声段电平中位数、3:1、6 dB 软拐点、启动 5 ms、释放 80 ms）。
- 和声：同样处理，响度比主唱低 8 dB，6 kHz 以上再降 2 dB 放到主唱后面。
- 混响：人声一起送，300 Hz–8 kHz 带通后卷积合成的立体声混响（T60 1.4 s、预延迟 25 ms，固定随机种子），回送比干声低 15 dB（LUFS）。
- 延迟：只送主唱，5 kHz 低通，八分音符左右交替 3 次，回送比干声低 22 dB。
- 电平：人声总线（干声 + 混响 + 延迟）对伴奏的响度差 = 原曲里人声分轨对伴奏的响度差（同一区间有人声的部分）。
- 母带：整体增益到约 −10 LUFS，前瞻 5 ms 的限幅器（4 倍过采样测峰，释放 80 ms），峰值 ≤ −1 dBTP。
输出：<out_dir>/<project.json 的 mix_name>.wav（48 kHz / 24-bit）、同名 .mp3（320 kbps）、人声总线.wav、mix_report.json，
以及同区间、不加处理的主唱干声（mix_name 末尾的“_混音”换成“_干声”，.wav / .mp3）。
（--end-at、--inst-db、--end-fade-ms、--suffix、--official 与干声输出来自《绯红》的 mix_1min.py；不给这些选项时输出与原来逐字节相同。）
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import pyloudnorm as pyln  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt  # noqa: E402

SR = 48000
BAR_SEC = common.CONFIG.get("beats_per_bar", 4) * 60.0 / common.BPM
DOWNBEAT_SEC = common.t2s(common.CONFIG.get("downbeat_tick", 0))
TARGET_LUFS = -10.0
CEIL_DBTP = -1.0
PRE_ROLL = 0.020


def bar_time(k):
    return DOWNBEAT_SEC + k * BAR_SEC


def vocal_onset(paths, clip0, thr_db=-80.0, hop=0.005):
    """各条人声干声第一个非静音帧的原曲时间，取最早的。"""
    t = []
    for p in paths:
        x, sr = sf.read(p, always_2d=True)
        x = x.mean(axis=1)
        h = int(hop * sr)
        m = len(x) // h
        e = 10 * np.log10(np.mean(x[:m * h].reshape(m, h) ** 2, axis=1) + 1e-20)
        t.append(clip0 + int(np.argmax(e > thr_db)) * hop)
    return min(t)


def hpf(x, f, order=2):
    return sosfilt(butter(order, f, btype="highpass", fs=SR, output="sos"), x, axis=0)


def lpf(x, f, order=2):
    return sosfilt(butter(order, f, btype="lowpass", fs=SR, output="sos"), x, axis=0)


def shelf_cut_above(x, f, db):
    """简单的高频降低：低通分量 + 按增益混回高频分量（相位一致的二阶分频）。"""
    lo = lpf(x, f)
    return lo + (x - lo) * 10 ** (db / 20)


def compressor(x, thr_db, ratio=3.0, knee=6.0, att_ms=5.0, rel_ms=80.0):
    hop = SR // 1000
    n = int(np.ceil(len(x) / hop))
    pad = np.concatenate([x, np.zeros(n * hop + 5 * hop - len(x))])
    p = pad ** 2
    c = np.concatenate([[0.0], np.cumsum(p)])
    idx = np.arange(n) * hop
    w = 5 * hop
    env = 10 * np.log10((c[idx + w] - c[idx]) / w + 1e-20)
    over = env - thr_db
    tgt = np.where(over <= -knee / 2, 0.0, np.where(over >= knee / 2, over * (1 - 1 / ratio),
                                                     (1 - 1 / ratio) * (over + knee / 2) ** 2 / (2 * knee)))
    a_att, a_rel = np.exp(-1 / att_ms), np.exp(-1 / rel_ms)
    g = np.empty(n)
    prev = 0.0
    for i in range(n):
        a = a_att if tgt[i] > prev else a_rel
        prev = a * prev + (1 - a) * tgt[i]
        g[i] = prev
    gain = 10 ** (-np.interp(np.arange(len(x)), idx + w / 2, g) / 20)
    return x * gain, {"thr_db": round(float(thr_db), 2), "gr_db_p50_active": round(float(np.median(g[env > thr_db - 20])), 2),
                      "gr_db_p95": round(float(np.percentile(g, 95)), 2), "gr_db_max": round(float(g.max()), 2)}


def reverb_ir(t60=1.4, predelay=0.025, length=2.4, seed=27):
    rng = np.random.default_rng(seed)
    n = int(length * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.91 * t / t60)
    ir = np.zeros((n + int(predelay * SR), 2))
    for ch in range(2):
        noise = rng.standard_normal(n)
        dark = lpf(noise, 3000)
        wmix = np.clip(t / 0.6, 0, 1)  # 越往后越暗
        tail = env * ((1 - wmix) * noise + wmix * dark * 1.6)
        for k, (d, gdb) in enumerate(((0.011, -6), (0.017, -8), (0.023, -9), (0.031, -11))):  # 早期反射
            j = int((d + 0.003 * ch * (k % 2)) * SR)
            tail[j] += 10 ** (gdb / 20) * 4
        ir[int(predelay * SR):, ch] = tail
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def pingpong(x, d_sec, gains=(0.35, 0.2, 0.1)):
    d = int(round(d_sec * SR))
    out = np.zeros((len(x) + d * len(gains), 2))
    for k, g in enumerate(gains, start=1):
        out[k * d:k * d + len(x), (k - 1) % 2] += g * x
    return out[:len(x)]


def true_peak_db(x):
    up = resample_poly(x, 4, 1, axis=0)
    return float(20 * np.log10(np.max(np.abs(up)) + 1e-12))


def limiter(x, ceil_db=CEIL_DBTP, look_ms=5.0, rel_ms=80.0):
    ceil = 10 ** (ceil_db / 20)
    up = np.max(np.abs(resample_poly(x, 4, 1, axis=0)), axis=1)
    peak = up.reshape(-1, 4).max(axis=1)[:len(x)] if len(up) >= 4 * len(x) else np.max(np.abs(x), axis=1)
    peak = np.concatenate([peak, np.zeros(len(x) - len(peak))])
    req = np.minimum(1.0, ceil / np.maximum(peak, 1e-9))
    look = int(look_ms * SR / 1000)
    from scipy.ndimage import minimum_filter1d
    req = minimum_filter1d(req, size=2 * look + 1)  # 提前 look 开始压
    hop = SR // 1000
    n = int(np.ceil(len(x) / hop))
    blk = np.array([req[i * hop:(i + 1) * hop].min() for i in range(n)])
    a_rel = np.exp(-1 / rel_ms)
    g = np.empty(n)
    prev = 1.0
    for i in range(n):
        prev = blk[i] if blk[i] < prev else a_rel * prev + (1 - a_rel) * blk[i]
        g[i] = prev
    gain = np.minimum(np.interp(np.arange(len(x)), np.arange(n) * hop + hop / 2, g), req)
    return x * gain[:, None], {"gr_db_max": round(float(-20 * np.log10(gain.min())), 2),
                               "gr_db_p95": round(float(np.percentile(-20 * np.log10(gain), 95)), 2)}


def fade(x, fin, fout_start, fout_len):
    n = len(x)
    g = np.ones(n)
    a = int(fin * SR)
    g[:a] = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    b = int(fout_start * SR)
    m = n - b
    g[b:] = 0.5 + 0.5 * np.cos(np.pi * np.arange(m) / m)
    return x * g[:, None]


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


def main():
    score_p, main_p, harm_p, inst_p, vstem_p, out = sys.argv[1:7]
    opt = sys.argv[7:]
    val = lambda name, conv: conv(opt[opt.index(name) + 1]) if name in opt else None  # noqa: E731
    end_at, inst_db, end_fade = val("--end-at", float), val("--inst-db", float), val("--end-fade-ms", float)
    suffix, official = val("--suffix", str) or "", val("--official", str)
    harm_p = None if harm_p == "-" else harm_p
    os.makedirs(out, exist_ok=True)
    score = json.load(open(score_p, encoding="utf-8"))
    meta = score["meta"]
    clip0 = common.t2s(meta["clip_start_tick"])
    notes = score["tracks"][0]["notes"] if "tracks" in score else score["notes"]
    first = notes[0]["start"]
    last_end = notes[-1]["end"]
    k_first = int(np.floor((first - DOWNBEAT_SEC) / BAR_SEC))
    S, fade_in = bar_time(k_first - 1), 0.3
    if "--cut-to-vocal" in sys.argv[7:]:
        S, fade_in = vocal_onset([p for p in (main_p, harm_p) if p], clip0) - PRE_ROLL, 0.010
    k_end = int(np.ceil((last_end - DOWNBEAT_SEC) / BAR_SEC))
    fade_start = bar_time(k_end) - S
    E = bar_time(k_end) + 3.0
    if end_at is not None:
        E = end_at
        fade_start = E - S - 3.0
    n = int(round((E - S) * SR))
    meter = pyln.Meter(SR)
    loud = meter.integrated_loudness

    def place(path):
        x, sr = sf.read(path, always_2d=True, dtype="float64")
        assert sr == SR
        x = x.mean(axis=1)
        y = np.zeros(n)
        o = int(round((clip0 - S) * SR))
        if o < 0:  # --cut-to-vocal 时片段起点早于成品起点，去掉前面这段（人声在这里是静音）
            x, o = x[-o:], 0
        y[o:o + len(x)] = x[:max(0, n - o)]
        return y

    def cut(path):
        x, sr = sf.read(path, always_2d=True, dtype="float64", start=int(round(S * SR)), frames=n)
        assert sr == SR
        return x if x.shape[1] == 2 else np.repeat(x, 2, axis=1)

    rep = {"window_sec": [round(S, 3), round(E, 3)], "window_start_sample": int(round(S * SR)),
           "bars": [k_first - 1, k_end], "fade_in_sec": fade_in,
           "cut_to_vocal": "--cut-to-vocal" in sys.argv[7:], "fade_out_from_sec": round(S + fade_start, 3)}
    if end_at is not None:
        rep["end_at_sec"] = end_at
    raw = place(main_p)
    if end_fade:
        raw, fades = hard_end_fades(raw, end_fade)
        rep["end_fades"] = {"fade_ms": end_fade, "at_sec_in_file": fades, "at_sec_original": [round(S + t, 3) for t in fades]}
    main_v = hpf(raw, 100)

    def active_level(x):
        e = 10 * np.log10(np.convolve(x ** 2, np.ones(240) / 240, mode="same")[::240] + 1e-20)
        return float(np.median(e[e > -50]))

    main_c, rep["comp_main"] = compressor(main_v, active_level(main_v))
    dup = lambda v: np.repeat(v[:, None], 2, axis=1)
    dry = main_c
    if harm_p:
        hraw = place(harm_p)
        if end_fade:
            hraw, hf = hard_end_fades(hraw, end_fade)
            rep["end_fades_harmony_original_sec"] = [round(S + t, 3) for t in hf]
        harm_v = hpf(hraw, 100)
        harm_c, rep["comp_harmony"] = compressor(harm_v, active_level(harm_v))
        harm_c = shelf_cut_above(harm_c, 6000, -2.0)
        lm = loud(dup(main_c))
        harm_c *= 10 ** ((lm - 8 - loud(dup(harm_c))) / 20)
        dry = main_c + harm_c
    ld = loud(dup(dry))
    send = lpf(hpf(dry, 300), 8000)
    rev = fftconvolve(send[:, None], reverb_ir(), axes=0)[:n]
    rev *= 10 ** ((ld - 15 - loud(rev)) / 20)
    dl = pingpong(lpf(main_c, 5000), 60.0 / common.BPM / 2)
    dl *= 10 ** ((ld - 22 - loud(dl)) / 20)
    vbus = dup(dry) + rev + dl
    inst = cut(inst_p)
    vstem = cut(vstem_p)
    a, b = int((first - S) * SR), int((last_end - S) * SR)
    ratio = loud(vstem[a:b]) - loud(inst[a:b])
    shift = inst_db or 0.0
    vbus *= 10 ** ((loud(inst[a:b]) + ratio - shift - loud(vbus[a:b])) / 20)
    rep["vocal_minus_inst_lufs_target"] = round(ratio - shift, 2)
    if inst_db is not None:
        rep["original_vocal_minus_inst_lufs"] = round(ratio, 2)
        rep["inst_db_vs_original"] = inst_db
    if harm_p:
        rep["harmony_minus_main_lufs"] = round(loud(dup(harm_c)) - lm, 2)
    mix = fade(inst + vbus, fade_in, fade_start, E - S - fade_start)
    vbus_f = fade(vbus, fade_in, fade_start, E - S - fade_start)
    g = 10 ** ((TARGET_LUFS - loud(mix)) / 20)
    mix, vbus_f = mix * g, vbus_f * g
    pre_tp = true_peak_db(mix)
    mix, rep["limiter"] = limiter(mix)
    rep.update({"pre_limiter_true_peak_dbtp": round(pre_tp, 2), "final_lufs": round(loud(mix), 2),
                "final_true_peak_dbtp": round(true_peak_db(mix), 2), "duration_sec": round(n / SR, 3)})
    if official:
        off = cut(official)
        rep.update({"official_same_window_lufs": round(loud(off), 2),
                    "official_same_window_true_peak_dbtp": round(true_peak_db(off), 2)})
    name = common.CONFIG.get("mix_name", "混音")
    base = os.path.join(out, name + suffix)
    dry_out = os.path.join(out, (name[:-len("_混音")] if name.endswith("_混音") else name) + "_干声" + suffix)
    for p in (base + ".wav", base + ".mp3", dry_out + ".wav", dry_out + ".mp3"):
        if os.path.exists(p):
            raise SystemExit(f"已存在：{p}")
    sf.write(base + ".wav", mix, SR, subtype="PCM_24")
    sf.write(dry_out + ".wav", raw, SR, subtype="PCM_24")
    sf.write(os.path.join(out, f"人声总线{suffix}.wav"), vbus_f, SR, subtype="PCM_24")
    for p in (base, dry_out):
        subprocess.run(["ffmpeg", "-v", "error", "-n", "-i", p + ".wav", "-c:a", "libmp3lame", "-b:a", "320k", p + ".mp3"], check=True)
    json.dump(rep, open(os.path.join(out, f"mix_report{suffix}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
