"""和声轨核对：UST 和声音高 vs 原曲（原样分离人声，叠着主唱、低八度与和声）里的谐波证据。信号指标，不是听感。

用法：python -I hamo_check.py <score_full.json> <ref_vocal_mix_full.wav> <out_fix.json> <out_report.json>
对每个与主唱不同音（且不是八度）的和声音：取音符中间 60%（不足 4096 点时以中点取 4096 点），16384 点补零 FFT；
候选音高 p = UST − 2 … UST + 2；第 h 次谐波（h = 1…6，≤ 5 kHz）的“突出度” = ±25 音分内峰值 − 周围 1/3 倍频程的中位电平；
离主唱或低八度（主唱频率的 0.5 倍整数倍）任一谐波 40 音分以内的谐波不用；可用谐波少于 2 个记为“判不了”。
S(p) = 可用谐波突出度的平均。中声道（L+R）与侧声道（L−R）各算一次。
改音条件（运行前定死）：两个声道的最佳候选相同、都不是 UST 音高、且都比 UST 音高高出 ≥ 4 dB。其余一律保留 UST。
另列不在本曲调式（project.json 的 scale_pitch_classes，0 = C；没写就不查调式）里的和声音，只报告不改。
补充（《妄想感傷代償連盟》看到第一次结果后加）：改后离主唱只有 1–2 个半音、或改到调式外的不改——主唱从下往上滑时，能量正好落在
主唱谐波下方 100–200 音分处，会被误当成和声（第一次结果里 #82 G→A 就是这样，A 比主唱 B♭ 只低半音）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

NFFT = 16384
SCALE = set(common.CONFIG.get("scale_pitch_classes", range(12)))  # 例：E♭ 大调 / C 小调 = [3, 5, 7, 8, 10, 0, 2]
MARGIN_DB = 4.0


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def salience(mag_db, freqs, p, main_p):
    fm = hz(main_p)
    avoid = np.array([fm * 0.5 * k for k in range(1, 40)])
    vals = []
    for h in range(1, 7):
        f = hz(p) * h
        if f > 5000:
            break
        if np.min(np.abs(1200 * np.log2(avoid / f))) < 40:
            continue
        pk = (freqs > f * 2 ** (-25 / 1200)) & (freqs < f * 2 ** (25 / 1200))
        nb = (freqs > f * 2 ** (-1 / 6)) & (freqs < f * 2 ** (1 / 6)) & ~((freqs > f * 2 ** (-40 / 1200)) & (freqs < f * 2 ** (40 / 1200)))
        if pk.sum() and nb.sum():
            vals.append(mag_db[pk].max() - np.median(mag_db[nb]))
    return (float(np.mean(vals)), len(vals)) if len(vals) >= 2 else (None, len(vals))


def main():
    score_p, wav, fix_p, rep_p = sys.argv[1:5]
    score = json.load(open(score_p, encoding="utf-8"))
    main_notes = score["tracks"][0]["notes"]
    hamo = score["tracks"][1]["notes"]
    x, sr = sf.read(wav, always_2d=True)
    chans = {"mid": x.mean(axis=1), "side": (x[:, 0] - x[:, -1]) / 2}
    freqs = np.fft.rfftfreq(NFFT, 1 / sr)
    rows, fixes = [], {}
    for h in hamo:
        ov = [m for m in main_notes if m["tick"] < h["tick"] + h["dur"] and h["tick"] < m["tick"] + m["dur"]]
        if not ov:
            continue
        m = max(ov, key=lambda m: min(m["tick"] + m["dur"], h["tick"] + h["dur"]) - max(m["tick"], h["tick"]))
        iv = h["pitch"] - m["pitch"]
        row = {"idx": h["idx"], "ust_idx": h["ust_idx"], "lyric": h["lyric"], "start": h["start"], "pitch": h["pitch"],
               "main_pitch": m["pitch"], "interval": iv, "in_scale": (h["pitch"] % 12) in SCALE}
        if iv == 0 or abs(iv) == 12:
            row["status"] = "同音或八度，不核对"
            rows.append(row)
            continue
        s, e = h["start"], h["end"]
        a, b = s + 0.2 * (e - s), s + 0.8 * (e - s)
        if (b - a) * sr < 4096:
            c = (a + b) / 2
            a, b = c - 2048 / sr, c + 2048 / sr
        best = {}
        for name, sig in chans.items():
            seg = sig[int(a * sr):int(b * sr)]
            seg = seg * np.hanning(len(seg))
            mag = 20 * np.log10(np.abs(np.fft.rfft(seg, NFFT)) + 1e-12)
            sc = {p: salience(mag, freqs, p, m["pitch"]) for p in range(h["pitch"] - 2, h["pitch"] + 3)}
            ok = {p: v for p, (v, n) in sc.items() if v is not None}
            row[f"{name}_S"] = {str(p): (None if v is None else round(v, 1)) for p, (v, n) in sc.items()}
            if h["pitch"] in ok and ok:
                bp = max(ok, key=ok.get)
                best[name] = (bp, ok[bp] - ok[h["pitch"]])
        row["best"] = {k: [v[0], round(v[1], 1)] for k, v in best.items()}
        if len(best) < 2:
            row["status"] = "判不了"
        elif best["mid"][0] == best["side"][0] == h["pitch"]:
            row["status"] = "吻合"
        elif best["mid"][0] == best["side"][0] != h["pitch"] and min(best["mid"][1], best["side"][1]) >= MARGIN_DB:
            bp = int(best["mid"][0])
            if abs(bp - m["pitch"]) in (1, 2) or (bp % 12) not in SCALE:
                row["status"] = f"证据指向 {bp}，但离主唱 {bp - m['pitch']:+d} 半音或在调式外，保留"
            else:
                row["status"] = f"改为 {bp}"
                fixes[str(h["ust_idx"])] = bp
        else:
            row["status"] = "不一致，保留"
        rows.append(row)
    stat = {}
    for r in rows:
        k = "改音" if r["status"].startswith("改为") else ("证据指向别的音但不合理，保留" if r["status"].startswith("证据指向") else r["status"])
        stat[k] = stat.get(k, 0) + 1
    out_of_scale = [(r["idx"], r["pitch"]) for r in rows if not r["in_scale"]]
    print("harmony notes:", len(hamo), "| status:", stat, "| out of scale:", out_of_scale)
    for r in rows:
        if r["status"] not in ("吻合", "同音或八度，不核对"):
            print(f"  #{r['idx']:>3} (hamo#{r['ust_idx']}) {r['lyric']} {r['start']:6.2f}s pitch {r['pitch']} main {r['main_pitch']} "
                  f"iv {r['interval']:+d} best {r.get('best')} -> {r['status']}")
    json.dump({"pitch": fixes}, open(fix_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"summary": stat, "out_of_scale": out_of_scale, "rows": rows}, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
