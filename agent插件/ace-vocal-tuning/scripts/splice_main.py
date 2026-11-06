"""把改过歌词的乐句从新渲染里换进交付版主唱：交付版其余部分逐采样不动，接口放在休止处的静音里。

用法：python -I splice_main.py <score_main.json> <ra_fix.json> <base.wav> <new.wav> <out.wav> <out.json>
为什么：ACE 同一个工程每次重新打开、重新渲染，结果都会变（r2 原样重渲染一次，副歌各音电平差 p90 1.5 dB、最大 8.7 dB，
波形完全不同）；把表情参数锁回去也回不到交付版（r3c）。所以不整条重渲染，只替换改过的乐句。
- 替换段：含改过的音、且前后紧接（tick 相连）的整串音；起止各落在前后的休止里（最后一串到片段末尾）。
- 接口：休止内（两端各让开 20 ms）找 20 ms 淡化范围内两版包络最大值最小的位置，在那里做余弦交叉淡化；
  休止里不是数字静音（两版都有约 −50～−60 dBFS 的底噪），要求淡化范围内两版都低于 −45 dBFS（比人声低 25 dB 以上）。
- 检查：写出后读回，替换段以外与交付版逐采样相同，替换段内（淡化以外）与新渲染逐采样相同。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import crisp_metrics as cm  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

HOP = cm.HOP
XF = 0.020
MARGIN = 0.020
MAX_DB = -45.0


def read_i32(p):
    x, sr = sf.read(p, dtype="int32", always_2d=True)
    if sr != 48000 or x.shape[1] != 1:
        raise SystemExit(f"需要 48 kHz 单声道：{p} {sr} Hz {x.shape[1]} 声道")
    return x[:, 0].astype(np.int64), sr


def runs(notes):
    out, cur = [], [notes[0]]
    for x, y in zip(notes, notes[1:]):
        if x["tick"] + x["dur"] == y["tick"]:
            cur.append(y)
        else:
            out.append(cur)
            cur = [y]
    out.append(cur)
    return out


def main():
    score_p, fix_p, base_p, new_p, out_p, rep_p = sys.argv[1:7]
    score = json.load(open(score_p, encoding="utf-8"))
    c0 = common.t2s(score["meta"]["clip_start_tick"])
    notes = score["notes"]
    edited = {r["idx"] for r in json.load(open(fix_p, encoding="utf-8"))["rows"]}
    base, sr = read_i32(base_p)
    new, _ = read_i32(new_p)
    if len(base) != len(new):
        raise SystemExit(f"两版长度不同：{len(base)} / {len(new)}")
    eb, en = cm.envelope(base / 2.0 ** 31, sr), cm.envelope(new / 2.0 ** 31, sr)
    n = len(base)
    h = int(XF * sr) // 2
    rs = runs(notes)

    def cut(a, b):
        """休止 [a, b]（片段内秒）里的接口帧。"""
        k0, k1 = int(np.ceil((a + MARGIN) / HOP)), int(np.floor((b - MARGIN) / HOP))
        if k1 <= k0:
            raise SystemExit(f"休止太短：{a + c0:.3f}–{b + c0:.3f} s")
        r = int(round(h / (HOP * sr)))
        both = np.maximum(eb, en)
        win = [float(both[k - r:k + r + 1].max()) for k in range(k0, k1 + 1)]
        k = k0 + int(np.argmin(win))
        lvl = min(win)
        if lvl > MAX_DB:
            raise SystemExit(f"接口处不够安静：{k * HOP + c0:.3f} s {lvl:.1f} dBFS")
        return int(round(k * HOP * sr)), lvl

    hit = [i for i, r in enumerate(rs) if any(x["idx"] in edited for x in r)]
    groups = []  # 相邻的几串之间只隔休止、中间没有没改的串时，并成一段，不在中间切回交付版
    for i in hit:
        if groups and groups[-1][1] == i - 1:
            groups[-1][1] = i
        else:
            groups.append([i, i])
    segs = []
    for i, j in groups:
        prev, nxt = rs[i - 1][-1] if i > 0 else None, rs[j + 1][0] if j + 1 < len(rs) else None
        s, ls = cut(prev["end"] - c0, rs[i][0]["start"] - c0) if prev else (0, None)
        e, le = cut(rs[j][-1]["end"] - c0, nxt["start"] - c0) if nxt else (n, None)
        segs.append({"notes": f"#{rs[i][0]['idx']}–#{rs[j][-1]['idx']}", "from_sample": s, "to_sample": e,
                     "from_sec": round(s / sr + c0, 3), "to_sec": round(e / sr + c0, 3),
                     "level_at_from_dbfs": None if ls is None else round(ls, 1),
                     "level_at_to_dbfs": None if le is None else round(le, 1)})
    w = np.zeros(n)  # 1 = 用新渲染
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, 2 * h))
    for g in segs:
        s, e = g["from_sample"], g["to_sample"]
        w[s + h if s > 0 else 0:e - h if e < n else n] = 1.0
        if s > 0:
            w[s - h:s + h] = ramp
        if e < n:
            w[e - h:e + h] = ramp[::-1]
    mix = (1 - w) * base + w * new
    out = (np.round(mix / 256.0) * 256).astype(np.int64)  # 24-bit 只留高 24 位
    os.makedirs(os.path.dirname(os.path.abspath(out_p)), exist_ok=True)
    sf.write(out_p, out.astype(np.int32), sr, subtype="PCM_24")
    back, _ = read_i32(out_p)
    keep, take = w == 0, w == 1
    chk = {"samples": n, "from_base": int(keep.sum()), "from_new": int(take.sum()), "crossfaded": int(n - keep.sum() - take.sum()),
           "base_identical_outside_segments": bool(np.array_equal(back[keep], base[keep])),
           "new_identical_inside_segments": bool(np.array_equal(back[take], new[take]))}
    if not (chk["base_identical_outside_segments"] and chk["new_identical_inside_segments"]):
        raise SystemExit(f"读回不一致：{chk}")
    rep = {"base": os.path.abspath(base_p), "new": os.path.abspath(new_p), "out": os.path.abspath(out_p),
           "crossfade_sec": XF, "segments": segs, "check": chk}
    json.dump(rep, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for g in segs:
        print(f"{g['notes']}: 原曲 {g['from_sec']:.3f}–{g['to_sec']:.3f} s，接口电平 {g['level_at_from_dbfs']} / {g['level_at_to_dbfs']} dBFS")
    print(json.dumps(chk, ensure_ascii=False))


if __name__ == "__main__":
    main()
