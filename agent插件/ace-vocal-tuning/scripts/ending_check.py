"""音节结尾检查（信号指标，不是听感）：每个“露出来的结尾”——后面是休止、清辅音，或是最后一个音——合成与原唱比。

用法：python -I ending_check.py <score.json> <g2p.json> <target_f0.json> <ref_clip.wav> <syn_clip.wav>
                                <ref_praat_full_5ms.npy> <syn_praat_5ms.npy> <syn_rmvpe_5ms.npy> <out.json> [--all] [--curve <curve.json>]
两个 wav 都从片段起点开始（导出时间轴）。有声 = F0 有值且该帧电平 > −60 dBFS（ACE 休止是数字静音，RMVPE 在静音里也会报音高）。
--curve：实际写进 ACE 的音高曲线（音节结尾轮补全过的，endings_plan.json 的 target_full）；不给就用 target_f0。对每个结尾给出：
- end_ms：合成元音结束减原唱元音结束，正 = 合成拖长。元音结束 = 音符末尾 40 ms 内（没有就整个音符里）最后一个有声帧
  所在那一段连续有声的终点，最多到下一个音起点后 30 ms（连唱多的歌，放宽空隙会一路连到后面几个音）；
- tail_ms / tail_dev_c：合成有声、但没有写音高曲线（交给 ACE 自己的音高）的尾巴长度，和那里离最后一个曲线值的最大偏差；
- decay：元音结束前 60 ms 内电平下降多少 dB（合成 / 原唱），看收得干不干脆。
终端只打印序号、时间和数值，不打印歌词。清辅音表按语言取 common.VOICELESS_INIT，G2P 音节用 common.head_consonants 对回音符。
（来自《绯红》。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
VOICELESS_INIT = common.VOICELESS_INIT


def env_db(path):
    x, sr = sf.read(path, always_2d=True)
    x = x.mean(axis=1)
    w = int(HOP * sr)
    m = len(x) // w
    return 10 * np.log10(np.mean(x[:m * w].reshape(m, w) ** 2, axis=1) + 1e-12)


def vowel_end(v, a, b, cap):
    """音符 [a, b) 的元音结束帧（下一帧序号）：末尾 40 ms 里（没有就整个音符里）最后一个有声帧，再顺着连续有声往后走，最多到 cap。"""
    idx = np.where(v[max(a, b - 8):b])[0]
    if len(idx):
        k = max(a, b - 8) + idx[-1]
    else:
        idx = np.where(v[a:b])[0]
        if not len(idx):
            return None
        k = a + idx[-1]
    while k + 1 < min(len(v), cap) and v[k + 1]:
        k += 1
    return k + 1


def main():
    score_p, g2p_p, tgt_p, ref_w, syn_w, ref_pr_p, syn_pr_p, syn_rm_p, out = sys.argv[1:10]
    score = json.load(open(score_p, encoding="utf-8"))
    notes, c0 = score["notes"], score["meta"]["clip_start_tick"]
    off = common.t2s(c0)
    k0 = int(round(off / HOP))
    init = common.head_consonants(notes, g2p_p)
    tm = np.array([np.nan if v is None else v for v in json.load(open(tgt_p, encoding="utf-8"))["midi"]])
    if "--curve" in sys.argv:
        cv = json.load(open(sys.argv[sys.argv.index("--curve") + 1], encoding="utf-8"))
        tm = np.array([np.nan if v is None else v for v in cv.get("target_full", cv)["midi"]])
    rp = np.load(ref_pr_p)[k0:k0 + len(tm)]
    sp = 69 + 12 * np.log2(np.load(syn_pr_p)[:len(tm)] / 440.0)
    sr = 69 + 12 * np.log2(np.load(syn_rm_p)[:len(tm)] / 440.0)
    syn = np.where(np.isnan(sp), sr, sp)
    se, re_ = env_db(syn_w), env_db(ref_w)
    n_ = min(len(syn), len(se), len(re_), len(rp))
    syn, se, re_, rp, tm = syn[:n_], se[:n_], re_[:n_], rp[:n_], tm[:n_]
    sv, rv = ~np.isnan(syn) & (se > -60), ~np.isnan(rp) & (re_ > -60)
    rows = []
    for k, n in enumerate(notes):
        nxt = notes[k + 1] if k + 1 < len(notes) else None
        if nxt is None:
            kind = "last"
        elif nxt["tick"] > n["tick"] + n["dur"]:
            kind = "rest"
        elif init.get(k + 1) in VOICELESS_INIT:
            kind = "voiceless"
        else:
            continue
        a = int((n["start"] - off) / HOP)
        b = min(int((n["end"] - off) / HOP), n_)
        cap = (int((nxt["start"] - off) / HOP) + 6) if nxt else b + 60
        e_syn = vowel_end(sv, a, b, cap)
        e_ref = vowel_end(rv, a, b, cap)
        if e_syn is None or e_ref is None:
            continue
        has_t = np.where(~np.isnan(tm[a:e_syn]))[0]
        last_t = a + has_t[-1] if len(has_t) else None
        tail = 0 if last_t is None else e_syn - (last_t + 1)
        dev = 0.0
        if tail > 0:
            dev = float(np.nanmax(np.abs(syn[last_t + 1:e_syn] - tm[last_t]))) * 100
        def drop(e, k_end):
            seg = e[max(0, k_end - 12):k_end]
            return float(seg[0] - seg[-1]) if len(seg) > 2 else np.nan
        rows.append({"note": k, "t": round(n["end"], 3), "kind": kind, "pitch": n["pitch"],
                     "end_ms": int(e_syn - e_ref) * 5, "tail_ms": int(tail) * 5, "tail_dev_c": round(dev),
                     "decay_syn_db": round(drop(se, e_syn), 1), "decay_ref_db": round(drop(re_, e_ref), 1)})
    bad = [r for r in rows if r["tail_ms"] >= 20 and r["tail_dev_c"] >= 50 or abs(r["end_ms"]) >= 40]
    print(f"endings {len(rows)} (rest {sum(r['kind'] == 'rest' for r in rows)}, voiceless {sum(r['kind'] == 'voiceless' for r in rows)}, "
          f"last {sum(r['kind'] == 'last' for r in rows)}) | end_ms median {np.median([r['end_ms'] for r in rows]):+.0f}, "
          f"|end_ms| >= 40: {sum(abs(r['end_ms']) >= 40 for r in rows)} | AI-pitch tails >=20 ms & >=50 c: "
          f"{sum(r['tail_ms'] >= 20 and r['tail_dev_c'] >= 50 for r in rows)}")
    for r in (rows if "--all" in sys.argv else bad):
        print(f"  #{r['note']:>3} {r['t']:7.3f}s {r['kind']:<9} end {r['end_ms']:+5d} ms  tail {r['tail_ms']:3d} ms / {r['tail_dev_c']:4d} c  "
              f"decay syn {r['decay_syn_db']:5.1f} ref {r['decay_ref_db']:5.1f} dB")
    json.dump({"rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
