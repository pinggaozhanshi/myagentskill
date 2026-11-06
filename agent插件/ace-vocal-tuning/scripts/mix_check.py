"""成品混音检查（信号指标，不是听感）：分离伴奏里的原唱残留、各段人声对伴奏的平衡、开头 2 秒、总览图。

用法：python -I mix_check.py <score.json> <mix.wav> <vocal_bus.wav> <mix_report.json> <inst_full.wav> <vocal_stem_full.wav>
                             <ref_rmvpe_full_5ms.npy> <inst_window_rmvpe.json> <out_dir> [--sections 名=开始-结束,...]
- mix / vocal_bus / mix_report：mix_vocals.py 的输出（同一个 --suffix）。
- inst_window_rmvpe.json：成品区间的伴奏（inst_full 按 mix_report 的 window_sec 截出来）跑 rmvpe_run.py 的结果。
- 原唱残留：分离伴奏（成品区间）的 RMVPE 音高与原唱参考音高相差 < 50 音分的帧占参考有声帧的比例；
  伴奏里本来就有乐器在奏旋律时也会算进来，所以只当上限看。官方伴奏不用看这项。
- 平衡：按 --sections 分段（原曲秒数；start = 第一个音起点，end = 最后一个音终点；不给就整段一段），
  成品里人声总线对伴奏的 LUFS 差，与原曲同一段里人声分轨对伴奏的差并列。
- 开头 2 秒：成品与人声总线每 0.5 s 的电平（开头 2 秒要有声音事件）。
- 总览图：成品、人声总线、伴奏的 50 ms 包络（dB）。
输出：<out_dir>/<mix 文件名>_检查.json 与 <mix 文件名>_总览.png。
（由《绯红》的 mix_check.py 通用化：段落、报告路径、输出位置改成参数。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyloudnorm as pyln  # noqa: E402
import soundfile as sf  # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f2328", "#6b7280", "#e6e6e3"
plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"], "axes.unicode_minus": False,
                     "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})


def parse_sections(spec, first, last):
    if not spec:
        return {"全段": (first, last)}
    conv = lambda x: first if x == "start" else last if x == "end" else float(x)  # noqa: E731
    out = {}
    for item in spec.split(","):
        name, rng = item.split("=", 1)
        a, b = rng.split("-", 1)
        out[name] = (conv(a), conv(b))
    return out


def main():
    score_p, mix_p, vbus_p, rep_p, inst_p, vstem_p, ref_rm_p, inst_rm_p, out = sys.argv[1:10]
    opt = sys.argv[10:]
    rep = json.load(open(rep_p, encoding="utf-8"))
    S, E = rep["window_sec"]
    mix, sr = sf.read(mix_p, always_2d=True)
    vbus, _ = sf.read(vbus_p, always_2d=True)
    inst_mix = mix - vbus  # 成品里的伴奏部分（同一母带增益与限幅前近似）
    meter = pyln.Meter(sr)
    score = json.load(open(score_p, encoding="utf-8"))
    notes = score["tracks"][0]["notes"] if "tracks" in score else score["notes"]
    secs = parse_sections(opt[opt.index("--sections") + 1] if "--sections" in opt else None, notes[0]["start"], notes[-1]["end"])
    inst_full, _ = sf.read(inst_p, always_2d=True)
    vstem_full, _ = sf.read(vstem_p, always_2d=True)
    bal, orig = {}, {}
    for k, (a, b) in secs.items():
        i, j = int((a - S) * sr), int((b - S) * sr)
        bal[k] = round(meter.integrated_loudness(vbus[i:j]) - meter.integrated_loudness(inst_mix[i:j]), 2)
        i, j = int(a * sr), int(b * sr)
        orig[k] = round(meter.integrated_loudness(vstem_full[i:j]) - meter.integrated_loudness(inst_full[i:j]), 2)

    def lvl(x, a, b):
        y = x[int(a * sr):int(b * sr)]
        return round(float(10 * np.log10(np.mean(y ** 2) + 1e-12)), 1)

    opening = {f"{a:.1f}-{a + 0.5:.1f}s": {"mix_db": lvl(mix, a, a + 0.5), "vocal_bus_db": lvl(vbus, a, a + 0.5)}
               for a in np.arange(0, 2.0, 0.5)}
    ref = 69 + 12 * np.log2(np.load(ref_rm_p) / 440.0)
    fr = json.load(open(inst_rm_p, encoding="utf-8"))["frames"]
    it = np.array([f["time_sec"] for f in fr])
    iv = np.array([69 + 12 * np.log2(f["f0_hz"] / 440.0) if f["voiced"] else np.nan for f in fr])
    k = np.round((it + S) / 0.005).astype(int)
    ok = (k >= 0) & (k < len(ref))
    r = ref[k[ok]]
    v = iv[ok]
    a0, b0 = notes[0]["start"], notes[-1]["end"]
    win = ((it[ok] + S) >= a0) & ((it[ok] + S) <= b0) & np.isfinite(r)
    leak = float(np.mean(np.abs(v[win] - r[win]) < 0.5))
    res = {"vocal_minus_inst_lufs_by_section": bal, "original_vocal_minus_inst_lufs_by_section": orig,
           "inst_pitch_matches_ref_vocal_frac": round(leak, 3), "opening_2s": opening,
           "mix_lufs": rep["final_lufs"], "mix_true_peak_dbtp": rep["final_true_peak_dbtp"]}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    hop = int(0.05 * sr)

    def env(x):
        y = x.mean(axis=1)
        m = len(y) // hop
        return 10 * np.log10(np.mean(y[:m * hop].reshape(m, hop) ** 2, axis=1) + 1e-12)

    t = S + np.arange(len(mix) // hop) * 0.05
    fig, ax = plt.subplots(figsize=(13, 3.6))
    ax.plot(t, env(mix), color=BLUE, lw=1.2, label="成品混音")
    ax.plot(t, env(vbus), color=AQUA, lw=1.0, label="人声总线（干声 + 混响 + 延迟）")
    ax.plot(t, env(inst_mix), color=ORANGE, lw=0.9, label="伴奏（成品里）", alpha=0.85)
    for kk, (a, b) in secs.items():
        ax.axvspan(a, b, color=GRID, alpha=0.35, lw=0)
        ax.text((a + b) / 2, -6, kk, ha="center", color=MUTED, fontsize=9)
    ax.set_xlim(S, E)
    ax.set_ylim(-60, 0)
    ax.set_xlabel("原曲时间（秒）")
    ax.set_ylabel("50 ms 电平（dBFS）")
    ax.set_title("成品混音总览", color=INK, loc="left", fontsize=12, pad=22)
    ax.legend(frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1.0, 1.0))
    ax.grid(axis="y", color=GRID, lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    os.makedirs(out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(mix_p))[0]
    fig.savefig(os.path.join(out, f"{stem}_总览.png"), dpi=150)
    json.dump(res, open(os.path.join(out, f"{stem}_检查.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
