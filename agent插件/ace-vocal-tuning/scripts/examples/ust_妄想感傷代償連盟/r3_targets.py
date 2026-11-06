"""第 3 轮（“干脆”）的参数目标：由 r2 的参数快照生成标定变体或成品变体的四条绝对值曲线。

用法：python -I r3_targets.py <params_r2.npz> <pilot_score.json> <g2p_japanese.json> <kind> <out.npz> [选项 JSON]
kind：
- control：四个参数都等于 r2 的 AI 值（只锁定，不改）。
- energy_scale / tension_scale：整段 ×f（选项 {"f": 0.67}）。
- dips：在“与下一个音直接相连、下一个音以浊辅音或元音开头”的交界处，力度乘一个升余弦凹陷，
  中心在交界，半宽 = min(25 ms, 0.4 × 两侧较短的音长)；选项 {"depth": 0.5} 是凹陷最低点的倍率，
  或 {"depths": {"<音符 idx>": 倍率}} 逐个交界给（idx 是交界前那个音）。
- shape：成品用，选项里同时给 dips / tails / tension 三部分（见 round3_solve.py）：
  tails {"<idx>": m_end}：该音 25% 处到结尾力度从 1 线性降到 m_end；tension {"f": f}：整段张力 ×f。
所有改动都是对 r2 快照的倍率；倍率为 1 的地方就是 r2 原值。上限与《反乌托邦》第 3 轮相同：不把值推到 max(原值, 1) 以上。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import numpy as np  # noqa: E402

PARAMS = ["energy", "tension", "air", "falsetto"]
VOICELESS = {"k", "ky", "kw", "s", "sh", "t", "ch", "ts", "h", "hy", "f", "p", "py"}
HALF_MS = 25.0


def voiced_boundaries(score, heads):
    notes = score["notes"]
    out = []
    for k in range(len(notes) - 1):
        a, b = notes[k], notes[k + 1]
        if a["tick"] + a["dur"] == b["tick"] and heads[k + 1] not in VOICELESS and a["target"] and b["target"]:
            half = min(common.s2t(HALF_MS / 1000), int(0.4 * min(a["dur"], b["dur"])))
            out.append({"idx": a["idx"], "center": b["tick"] - score["meta"]["clip_start_tick"], "half": half})
    return out


def dip_curve(n, bounds, depths):
    m = np.ones(n)
    t = np.arange(n)
    for bd in bounds:
        d = depths.get(bd["idx"], 1.0)
        if d >= 1.0:
            continue
        c, h = bd["center"], bd["half"]
        sel = np.abs(t - c) <= h
        w = 0.5 * (1 + np.cos(np.pi * (t[sel] - c) / h))
        m[sel] = np.minimum(m[sel], 1 - (1 - d) * w)
    return m


def tail_curve(n, score, tails):
    m = np.ones(n)
    c0 = score["meta"]["clip_start_tick"]
    for nt in score["notes"]:
        e = tails.get(nt["idx"])
        if e is None or e >= 1.0:
            continue
        a = nt["tick"] - c0 + int(0.25 * nt["dur"])
        b = nt["tick"] - c0 + nt["dur"]
        m[a:b] = np.minimum(m[a:b], np.linspace(1.0, e, b - a))
    return m


def main():
    snap_p, score_p, g2p_p, kind, out = sys.argv[1:6]
    arg = sys.argv[6] if len(sys.argv) > 6 else "{}"
    opt = json.load(open(arg[1:], encoding="utf-8")) if arg.startswith("@") else json.loads(arg)  # @文件 = 从文件读选项
    snap = np.load(snap_p)
    score = json.load(open(score_p, encoding="utf-8"))
    heads = {s["index"]: (s["headConsonants"] or [""])[0] for s in json.load(open(g2p_p, encoding="utf-8"))["syllables"]}
    heads = [heads.get(k, "") for k in range(len(score["notes"]))]
    base = {p: np.maximum(snap[f"{p}_baseline"], 0.0) for p in PARAMS}
    n = len(base["energy"])
    mult = {p: np.ones(n) for p in PARAMS}
    bounds = voiced_boundaries(score, heads)
    if kind == "energy_scale":
        mult["energy"][:] = opt["f"]
    elif kind == "tension_scale":
        mult["tension"][:] = opt["f"]
    elif kind == "dips":
        depths = {int(k): v for k, v in opt.get("depths", {}).items()} or {bd["idx"]: opt["depth"] for bd in bounds}
        mult["energy"] = dip_curve(n, bounds, depths)
    elif kind == "shape":
        mult["energy"] = dip_curve(n, bounds, {int(k): v for k, v in opt.get("dips", {}).items()}) * \
            tail_curve(n, score, {int(k): v for k, v in opt.get("tails", {}).items()})
        mult["tension"][:] = opt.get("tension", {}).get("f", 1.0)
    elif kind != "control":
        raise SystemExit(f"未知 kind：{kind}")
    tg = {p: np.minimum(base[p] * mult[p], np.maximum(base[p], 1.0)) for p in PARAMS}
    np.savez_compressed(out, **tg)
    json.dump({"kind": kind, "options": opt, "boundaries": bounds}, open(out.replace(".npz", "_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    changed = {p: int(np.sum(np.abs(mult[p] - 1) > 1e-9)) for p in PARAMS}
    print(kind, "boundaries", len(bounds), "| ticks changed:", changed,
          "| energy mult min", round(float(mult["energy"].min()), 3))


if __name__ == "__main__":
    main()
