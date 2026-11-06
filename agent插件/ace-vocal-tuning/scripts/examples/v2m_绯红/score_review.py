"""谱面人工核对用：按十六分网格点列出参考人声的“音节起点证据”，旁边写出哪个音符从这里开始、识别的音节和对齐到的官方音节。

用法：python -I score_review.py <score.json> <aligned.json> <ref_vocal.wav> <praat_5ms.npy> <rmvpe_5ms.npy> <line_from> <line_to>
每个网格点 g（原唱是 VOCALOID，音节都从网格点开始）给出：
- dip：g 前后 ±50 ms 内 RMS 最低值比这一点前后 150–300 ms 的中位低多少 dB（辅音、断开）；
- gap：g 前 70 ms 到后 30 ms 里 Praat 无声帧占的毫秒数；
- p-/p+：g 前 100–20 ms、后 20–100 ms 的音高中位（RMVPE 优先）；
- flux：g ±40 ms 内 2–8 kHz 能量的最大上升（dB / 10 ms，辅音爆破、擦音）。
音节只打印音类（lyric_check.mclass），不打印歌词；j 是官方音节序号。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from lyric_check import mclass, morae  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import butter, sosfiltfilt  # noqa: E402

HOP = 0.005
Q = 120
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def name(p):
    return f"{NAMES[int(round(p)) % 12]}{int(round(p)) // 12 - 1}"


def main():
    score_p, al_p, wav, pr_p, rm_p, l0, l1 = sys.argv[1:8]
    l0, l1 = int(l0), int(l1)
    score = json.load(open(score_p, encoding="utf-8"))
    notes, g0 = score["notes"], score["meta"]["grid_zero_tick"]
    rows = json.load(open(al_p, encoding="utf-8"))["rows"]
    x, sr = sf.read(wav, always_2d=True)
    x = x.mean(axis=1)
    w = int(HOP * sr)
    nfr = len(x) // w
    rms = 20 * np.log10(np.sqrt(np.mean(x[:nfr * w].reshape(nfr, w) ** 2, axis=1)) + 1e-9)
    hi = sosfiltfilt(butter(4, [2000, 8000], btype="band", fs=sr, output="sos"), x)
    hdb = 20 * np.log10(np.sqrt(np.mean(hi[:nfr * w].reshape(nfr, w) ** 2, axis=1)) + 1e-9)
    pr = 69 + 12 * np.log2(np.load(pr_p) / 440.0)
    rm = 69 + 12 * np.log2(np.load(rm_p) / 440.0)
    by_note = {}
    pending_ins = []
    for r in rows:
        if r["note"] is None:
            pending_ins.append(r)
            continue
        by_note[r["note"]] = dict(r, ins_before=pending_ins)
        pending_ins = []
    sel = [n for n in notes if by_note.get(n["idx"], {}).get("line") and l0 <= by_note[n["idx"]]["line"] <= l1]
    if not sel:
        raise SystemExit("这几行没有对上的音符")
    t_a, t_b = sel[0]["tick"], sel[-1]["end_tick"]
    starts = {n["tick"]: n for n in notes}

    def med(a, b, arr):
        seg = arr[max(0, int(a / HOP)):int(b / HOP)]
        seg = seg[~np.isnan(seg)]
        return float(np.median(seg)) if len(seg) else np.nan

    for g in range(t_a, t_b + 1, Q):
        t = common.t2s(g)
        k = int(t / HOP)
        local = rms[max(0, k - 10):k + 11]
        ctx = np.concatenate([rms[max(0, k - 60):max(0, k - 30)], rms[k + 30:k + 60]])
        dip = float(np.min(local) - np.median(ctx)) if len(ctx) else 0.0
        gap = int(np.sum(np.isnan(pr[k - 14:k + 6])) * 5)
        pb = med(t - 0.1, t - 0.02, rm)
        pb = pb if not np.isnan(pb) else med(t - 0.1, t - 0.02, pr)
        pa = med(t + 0.02, t + 0.1, rm)
        pa = pa if not np.isnan(pa) else med(t + 0.02, t + 0.1, pr)
        fl = float(np.max(np.diff(hdb[k - 8:k + 9])) / 0.5) if k > 8 else 0.0
        rel = g - g0
        pos = f"{rel // 1920}:{(rel % 1920) // 480 + 1}:{(rel % 480) // Q + 1}"
        n = starts.get(g)
        tag = ""
        if n is not None:
            al = by_note.get(n["idx"], {})
            ins = "".join(f"[+{mclass(r['official'])} j{r['j']}]" for r in al.get("ins_before", []))
            v = None if n["lyric"].isascii() else (morae(n["lyric"]) or [None])[0]
            same = "=" if al.get("official") == v else "≠"
            tag = (f"#{n['idx']:>3} {name(n['pitch']):>4} {n['dur'] // Q:>2}/16  v2m {mclass(v):<3} {same} off {mclass(al.get('official')):<3} "
                   f"j{al.get('j')} L{al.get('line')} {ins}")
        print(f"{pos:>8} {t:7.3f}s dip {dip:6.1f} gap {gap:3d} flux {fl:5.1f} p {pb:5.1f}>{pa:5.1f}  {tag}")


if __name__ == "__main__":
    main()
