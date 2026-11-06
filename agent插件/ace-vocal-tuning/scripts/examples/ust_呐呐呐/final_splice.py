"""只把改过的乐句从新渲染换进上一版干声：其余部分和上一版逐采样相同，接口落在休止里。

python -I scripts/final_splice.py <notes.json> <ticks.json> <base_state.json> <new_state.json> <out_state.json> <out_dir> <report.json>

ticks.json：{"miku": [改动起点 tick, ...], "rin": [...], "harm": [...]}。
替换段是含这些音、前后 tick 相连的整串音；休止短于 MIN_REST 时再并下一串。ACE 2.1.9 的休止是数字静音，
接口在休止中点做 20 ms 余弦交叉淡化，要求淡化范围内两版都低于 −50 dBFS。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import numpy as np
import soundfile as sf

ROOT = Path(common.ROOT)
SR = 48000
XF = .020
MIN_REST = .060
MAX_DB = -50.


def read_i32(p):
    x, sr = sf.read(p, dtype="int32", always_2d=True)
    assert sr == SR and x.shape[1] == 1, (p, sr, x.shape)
    return x[:, 0].astype(np.int64)


def runs(rows):
    out, cur = [], [rows[0]]
    for a, b in zip(rows, rows[1:]):
        if common.t2s(b["tick"]) - common.t2s(a["tick"] + a["dur"]) < MIN_REST:
            cur.append(b)
        else:
            out.append(cur)
            cur = [b]
    out.append(cur)
    return out


def level_db(x):
    return 20 * np.log10(np.max(np.abs(x)) / 2 ** 31 + 1e-12)


def quiet(base, new, a, b, h):
    """休止 [a, b] 秒里，淡化范围内两版峰值最小的采样位置（每 1 ms 试一次）。"""
    best, pos = None, None
    for s in range(int(a * SR) + h, int(b * SR) - h, SR // 1000):
        v = max(np.max(np.abs(base[s - h:s + h])), np.max(np.abs(new[s - h:s + h])))
        if best is None or v < best:
            best, pos = v, s
    assert pos is not None, (a, b)
    return pos


def main():
    notes_p, ticks_p, base_p, new_p, out_state, out_dir, rep_p = sys.argv[1:8]
    table = json.loads(Path(notes_p).read_text(encoding="utf-8"))
    ticks = json.loads(Path(ticks_p).read_text(encoding="utf-8"))
    base_st = json.loads(Path(base_p).read_text(encoding="utf-8"))
    new_st = json.loads(Path(new_p).read_text(encoding="utf-8"))
    out = ROOT / out_dir
    out.mkdir(parents=True, exist_ok=True)
    report = {"tracks": {}}
    paths = []
    for t, bp, np_ in zip(base_st["tracks"], base_st["render_paths"], new_st["render_paths"]):
        role = t["role"]
        base, new = read_i32(bp), read_i32(np_)
        n = min(len(base), len(new))
        assert abs(len(base) - len(new)) < 2 and not np.any(new[n:]) and not np.any(base[n:])
        base, new = base[:n], new[:n]
        rows = sorted(table[role], key=lambda r: r["tick"])
        rs = runs(rows)
        want = set(ticks.get(role, []))
        h = int(XF * SR) // 2
        ramp = .5 - .5 * np.cos(np.linspace(0, np.pi, 2 * h))
        w = np.zeros(n)
        segs = []
        for i, r in enumerate(rs):
            if not any(x["tick"] in want for x in r):
                continue
            s_end = common.t2s(rs[i - 1][-1]["tick"] + rs[i - 1][-1]["dur"]) if i else 0.
            s_begin = common.t2s(r[0]["tick"])
            e_begin = common.t2s(r[-1]["tick"] + r[-1]["dur"])
            e_end = common.t2s(rs[i + 1][0]["tick"]) if i + 1 < len(rs) else n / SR
            # 句前的辅音和句尾余音都在休止里，接口取休止里两版都最安静的位置
            s = quiet(base, new, s_end, s_begin, h) if i else 0
            e = quiet(base, new, e_begin, e_end, h) if i + 1 < len(rs) else n
            ls = max(level_db(base[s - h:s + h]), level_db(new[s - h:s + h])) if s else None
            le = max(level_db(base[e - h:e + h]), level_db(new[e - h:e + h])) if e < n else None
            assert (ls is None or ls <= MAX_DB) and (le is None or le <= MAX_DB), (role, s / SR, e / SR, ls, le)
            w[s + h if s else 0:e - h if e < n else n] = 1.
            if s:
                w[s - h:s + h] = ramp
            if e < n:
                w[e - h:e + h] = ramp[::-1]
            segs.append({"from_sec": round(s / SR, 3), "to_sec": round(e / SR, 3), "notes": len(r), "level_at_from_dbfs": None if ls is None else round(ls, 1),
                         "level_at_to_dbfs": None if le is None else round(le, 1)})
        mix = (1 - w) * base + w * new
        y = (np.round(mix / 256.) * 256).astype(np.int64)
        dst = out / Path(np_).name.replace("r5_", "r5s_")
        sf.write(dst, y.astype(np.int32), SR, subtype="PCM_24")
        back = read_i32(dst)
        keep, take = w == 0, w == 1
        chk = {"samples": n, "from_base": int(keep.sum()), "from_new": int(take.sum()), "crossfaded": int(n - keep.sum() - take.sum()),
               "base_identical_outside": bool(np.array_equal(back[keep], base[keep])), "new_identical_inside": bool(np.array_equal(back[take], new[take])),
               "render_changed_outside_segments_samples": int(np.sum(base[keep] != new[keep]))}
        assert chk["base_identical_outside"] and chk["new_identical_inside"], chk
        report["tracks"][role] = {"segments": segs, "check": chk, "path": str(dst)}
        paths.append(str(dst).replace("\\", "/"))
        print(role, len(segs), "段", json.dumps(chk, ensure_ascii=False), [(g["from_sec"], g["to_sec"]) for g in segs], flush=True)
    st = dict(new_st)
    st["render_paths"] = paths
    st["spliced_from"] = {"base": base_p, "new": new_p}
    Path(out_state).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(rep_p).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
