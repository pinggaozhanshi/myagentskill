"""音节结尾轮（第 2 轮之后、结尾检查发现问题时做）计划：辅音从原唱上一个元音结束处才开始；补全音高曲线，结尾不再交给 ACE 自己的音高。

用法：python -I endings_plan.py <score.json> <phonemes.json> <target_f0.json> <ref_clip.wav> <ref_praat_full_5ms.npy>
                                <voicing_plan.json> <round1_plan.json> <out_plan.json>
- phonemes.json：当前工程（r2）的 `phoneme list --with-timings=durations`（ace_dump.py phonemes）；
- voicing_plan.json：voicing_check.py 的输出（r2 里被 ACE 判成无声、原唱却唱出来的段 = 被吃掉元音尾巴的音）；
- round1_plan.json：第 1 轮的计划（round1_timing.py），第 1 轮按测量改过的辅音不再动。
来历（《绯红》，2026-10-24，用户听 v1：“有些音节的结尾没处理好”）：ACE 的辅音（80–157 ms）比原唱（约 0–50 ms）长得多，
快歌的短音（102 BPM 的十六分只有 147 ms）里，下一个音的辅音提前开始，把前一个音的元音尾巴换成无声的辅音；
第 1 轮只改测得到间隙的辅音，前一个元音整个没了的地方测不到。第 2 轮音高曲线只写在原唱有声处，合成元音更长的地方（结尾）由 ACE 自己的音高接管。
规则：
E. 前面不是休止的音（连唱）：在音符起点前 250 ms 到起点后 60 ms 里找原唱“没在唱”（Praat 无声，或低于上一个音中位电平 −12 dB）
   的那段间隙，取离起点最近的一段；它在起点之前的部分 G = 起点 − 间隙开始（原唱的辅音提前量，没有间隙则为 0）。
   ACE 的辅音（在音符起点之前）长度 L 比 G 长、新长度 = max(20 ms, G)。只缩短。适用范围：
   - 清辅音（common.VOICELESS_INIT）：前一个音在 r2 里被吃掉了元音尾巴（voicing_check）就改；否则 L − G ≥ 30 ms 才改，
     而且第 1 轮已经按测量改过的不再动；
   - 浊塞音 / 塞擦音（common.VOICED_STOP_INIT，日语 g gy d b by z j；中文没有）：只在前一个音被吃掉元音尾巴时改；
     鼻音、流音、半元音不动——它们有声，不会吃掉元音。
   - ACE 读不出时长的辅音（phoneme list 里 durationSec 为空）：前一个音被吃掉元音尾巴时，直接按原唱提前量写一个明确长度。
F. 音高曲线补全：相邻两段曲线之间的空隙 ≤ 300 ms 时，先保持前一段的最后一个值，到空隙结束前 min(40 ms, 空隙/2) 再直线过渡到后一段的第一个值；
   更长的空隙（休止）只在前一段后面保持 150 ms、后一段前面保持 60 ms。音高曲线之外不再有 ACE 自己的音高（除了乐句之间的长休止）。
G. 写完曲线后把整个片段的有声 / 无声固定清掉（auto），让 ACE 按新的辅音长度重新判断（vocalpitch write 会把写入当时的判断固定下来）。
   G 由 endings_apply.py 执行。
终端只打印序号、音素名、时长，不打印歌词。（由《绯红》的 round3_plan.py 通用化：两张辅音表按语言取自 common。）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = 0.005
MIN_CONS = 0.020
MIN_EXCESS = 0.030
VOICELESS = common.VOICELESS_INIT
VOICED_STOP = common.VOICED_STOP_INIT


def main():
    score_p, ph_p, tgt_p, ref_w, ref_pr_p, voi_p, r1_p, out = sys.argv[1:9]
    r1_done = {c["idx"] for c in json.load(open(r1_p, encoding="utf-8"))["consonants"]}
    score = json.load(open(score_p, encoding="utf-8"))
    notes, c0 = score["notes"], score["meta"]["clip_start_tick"]
    off = common.t2s(c0)
    k0 = int(round(off / HOP))
    ph = {r["pos"]: r for r in json.load(open(ph_p, encoding="utf-8"))["notes"]}
    x, sr = sf.read(ref_w, always_2d=True)
    x = x.mean(axis=1)
    w = int(HOP * sr)
    m = len(x) // w
    env = 10 * np.log10(np.mean(x[:m * w].reshape(m, w) ** 2, axis=1) + 1e-12)
    rv = ~np.isnan(np.load(ref_pr_p)[k0:k0 + m])
    eaten_notes = {p["note"] for p in json.load(open(voi_p, encoding="utf-8"))["plan"]}
    cons = []
    for k in range(1, len(notes)):
        n, prev = notes[k], notes[k - 1]
        if n["tick"] > prev["tick"] + prev["dur"]:
            continue  # 前面是休止：释放问题，不在这条规则里
        r = ph.get(n["tick"] - c0)
        t = [x for x in (r or {}).get("timings", []) if not x["isVowel"]]
        if not t:
            continue
        L = t[0].get("durationSec")
        unknown = not L
        name = t[0]["name"]
        eaten = (k - 1) in eaten_notes
        if not (name in VOICELESS or (name in VOICED_STOP and eaten)):
            continue
        T = n["start"] - off
        a, b = int((prev["start"] - off) / HOP), int((prev["end"] - off) / HOP)
        med = np.median(env[a:b]) if b > a else -60
        lo, hi = max(0, int((T - 0.25) / HOP)), min(m, int((T + 0.06) / HOP))
        quiet = ~(rv[lo:hi] & (env[lo:hi] > med - 12))
        runs, i = [], 0
        while i < len(quiet):
            if quiet[i]:
                j = i
                while j < len(quiet) and quiet[j]:
                    j += 1
                runs.append(((lo + i) * HOP, (lo + j) * HOP))
                i = j
            else:
                i += 1
        G = 0.0
        if runs:
            ga, gb = min(runs, key=lambda r: 0 if r[0] <= T <= r[1] else min(abs(r[0] - T), abs(r[1] - T)))
            G = max(0.0, T - ga) if ga <= T + 0.03 else 0.0
        new = max(MIN_CONS, G)
        if unknown:
            if not eaten:
                continue
        elif L - new < 0.005 or (not eaten and (L - new < MIN_EXCESS or k in r1_done)):
            continue
        if True:
            cons.append({"idx": k, "note": r["noteUuid"], "index": t[0]["index"], "phoneme": t[0]["name"], "cur_ms": None if unknown else round(L * 1000, 1),
                         "new_ms": round(new * 1000, 1), "ref_gap_ms": round(G * 1000), "prev_eaten_in_r2": eaten,
                         "round1_changed": k in r1_done})
    print(f"rule E: {len(cons)} consonants to shorten ({sum(c['prev_eaten_in_r2'] for c in cons)} of them after a note that lost "
          f"its vowel end in r2)")
    for c in cons:
        cur = "   ?  " if c["cur_ms"] is None else f"{c['cur_ms']:6.1f}"
        print(f"  #{c['idx']:>3} {c['phoneme']:<3} {cur} -> {c['new_ms']:5.1f} ms (original lead {c['ref_gap_ms']} ms)"
              f"{'  * prev vowel eaten in r2' if c['prev_eaten_in_r2'] else ''}{'  (round 1 had set it)' if c['round1_changed'] else ''}")
    tgt = json.load(open(tgt_p, encoding="utf-8"))
    hop = tgt["hop_sec"]
    midi = np.array([np.nan if v is None else v for v in tgt["midi"]])
    runs = [(int(round(a / hop)), int(round(b / hop))) for a, b in tgt["runs"]]
    full = midi.copy()
    filled = 0
    for (a0, a1), (b0, b1) in zip(runs, runs[1:]):
        gap = b0 - a1 - 1
        if gap <= 0:
            continue
        va, vb = midi[a1], midi[b0]
        if gap * hop <= 0.300:
            ramp = max(1, min(int(0.040 / hop), gap // 2))
            hold = gap - ramp
            full[a1 + 1:a1 + 1 + hold] = va
            full[a1 + 1 + hold:b0] = np.linspace(va, vb, ramp + 2)[1:-1]
            filled += gap
        else:
            h1, h2 = int(0.150 / hop), int(0.060 / hop)
            full[a1 + 1:a1 + 1 + h1] = va
            full[b0 - h2:b0] = vb
            filled += h1 + h2
    a0, a1 = runs[0][0], runs[-1][1]
    full[max(0, a0 - int(0.060 / hop)):a0] = midi[a0]
    full[a1 + 1:a1 + 1 + int(0.150 / hop)] = midi[a1]
    v = ~np.isnan(full)
    new_runs, i = [], 0
    while i < len(full):
        if v[i]:
            j = i
            while j < len(full) and v[j]:
                j += 1
            new_runs.append([round(i * hop, 4), round((j - 1) * hop, 4)])
            i = j
        else:
            i += 1
    print(f"rule F: target runs {len(runs)} -> {len(new_runs)}, frames {int(np.sum(~np.isnan(midi)))} -> {int(v.sum())} (+{int(v.sum()) - int(np.sum(~np.isnan(midi)))})")
    plan = {"consonants": cons,
            "target_full": {"time_base": tgt["time_base"], "hop_sec": hop, "clip_begin_tick": tgt["clip_begin_tick"],
                            "midi": [None if np.isnan(x) else round(float(x), 4) for x in full], "runs": new_runs}}
    json.dump(plan, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
