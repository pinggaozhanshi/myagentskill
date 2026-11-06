"""把一句唱得对的音高曲线抄到它的其余重复处（同谱面的句子），只动这几段，其余曲线逐点不变。

python -I scripts/final_phrase_copy.py <state.json> <spec.json> <report.json>

spec.json：
{"groups": [{"name": "...", "template": {"role": "rin", "tick": 493, "pre": 110, "len": 1440, "blend": 60},
             "copies": [{"role": "miku", "tick": 61933, "transpose": 0, "map": [[64, 60], [67, 64], [69, 66]]}, ...]}],
 "direct": [{"role": "harm", "tick": 179053, "points": [[相对 tick, 半音], ...], "blend": 60}]}
- pre：模板从音符前多少 tick 开始；len：模板到音符后多少 tick；blend：之后这么长的 tick 里淡回目标句原来的曲线。
- transpose：整句移调（半音）。map：和声这类音程不固定的声部，把模板的音高按折线映射到自己的音符上。
- direct：不抄模板，直接写给定的相对曲线（同样淡回）。
写完逐点读回；范围外的曲线必须和写之前完全相同；最后把有声 / 无声固定清成 auto。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import numpy as np
from ace import cli

ROOT = Path(common.ROOT)


def clip_at(st, role, tick):
    t = next(x for x in st["tracks"] if x["role"] == role)
    return next(c for c in t["clips"] if c["clipBegin"] <= tick < c["clipEnd"])


def read_user(clip):
    return cli("vocalpitch", "read", "--clip-uuid", clip["clipUuid"], "--level", "user")["points"]


def template_curve(st, tpl):
    """模板句的曲线，tick 相对模板音符起点。"""
    c = clip_at(st, tpl["role"], tpl["tick"])
    off = tpl["tick"] - c["clipBegin"]
    end = tpl["len"] + tpl.get("blend", 0)
    pts = [(p[0] - off, p[1]) for p in read_user(c) if p[1] is not None and -tpl["pre"] <= p[0] - off <= end + 12]
    assert pts and pts[0][0] < -tpl["pre"] + 12 and pts[-1][0] >= end, (pts[:2], pts[-2:])
    return pts


def build(new_rel, old, off, end_tick, blend):
    """new_rel：[(相对 tick, 值)]。返回写入用的片段内点；end_tick 之后 blend 内淡回 old。"""
    t = np.array([p[0] for p in old if p[1] is not None], float)
    v = np.array([p[1] for p in old if p[1] is not None], float)
    pts = []
    for rel, val in new_rel:
        tick = int(round(rel + off))
        if rel > end_tick:
            w = min(1., (rel - end_tick) / blend)
            val = (1 - w) * val + w * float(np.interp(tick, t, v))
        if pts and tick <= pts[-1][0]:
            continue
        pts.append([tick, round(float(val), 4)])
    return pts


def write_span(c, pts, tmp):
    """整段片段的曲线一次写回：只写局部时，ACE 会在写入范围的末尾断开曲线（留一个约 4 ms 的缺口）。"""
    before = read_user(c)
    a, b = pts[0][0], pts[-1][0]
    merged = [p for p in before if p[0] < a] + pts + [p for p in before if p[0] > b]
    assert all(y[0] > x[0] for x, y in zip(merged, merged[1:]))
    tmp.write_text(json.dumps(merged), encoding="utf-8")
    cli("vocalpitch", "write", "--clip-uuid", c["clipUuid"], "--points", "@" + str(tmp), "--wait-busy", "120s")
    after = read_user(c)
    assert len(after) == len(merged), (len(after), len(merged))
    worst = 0.
    for x, y in zip(after, merged):
        assert (x[1] is None) == (y[1] is None) and (y[1] is None or x[0] == y[0]), (x, y)
        if y[1] is not None:
            worst = max(worst, abs(x[1] - y[1]))
    assert worst < 2e-3, worst
    cli("vocalpitch", "set-voicing", "--clip-uuid", c["clipUuid"], "--begin", 0, "--end", c["clipEnd"] - c["clipBegin"], "--mode", "auto", "--wait-busy", "120s")
    assert not cli("vocalpitch", "voicing", "--clip-uuid", c["clipUuid"]).get("spans", [])
    return {"clip": c["clipUuid"], "from": a, "to": b, "points": len(pts), "max_readback_diff": worst}


def main():
    st = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    d = cli("project", "dirty")
    assert Path(d["projectPath"]).resolve() == Path(st["project"]["savedPath"]).resolve(), d
    tmp = ROOT / "work/final/pitch_points_tmp.json"
    report = []
    for g in spec.get("groups", []):
        tpl = g["template"]
        base = template_curve(st, tpl)
        for cp in g["copies"]:
            c = clip_at(st, cp["role"], cp["tick"])
            off = cp["tick"] - c["clipBegin"]
            vals = list(base)
            if cp.get("map"):
                xs, ys = zip(*cp["map"])
                vals = [(r, float(np.interp(v, xs, ys))) for r, v in vals]
            vals = [(r, v + cp.get("transpose", 0)) for r, v in vals]
            pts = build(vals, read_user(c), off, tpl["len"], tpl.get("blend", 60))
            rep = write_span(c, pts, tmp)
            rep.update(group=g["name"], role=cp["role"], tick=cp["tick"])
            report.append(rep)
            print(g["name"], cp["role"], cp["tick"], rep["points"], "points ok", flush=True)
    for dr in spec.get("direct", []):
        c = clip_at(st, dr["role"], dr["tick"])
        off = dr["tick"] - c["clipBegin"]
        end = dr["points"][-1][0] - dr.get("blend", 60)
        pts = build([tuple(p) for p in dr["points"]], read_user(c), off, end, dr.get("blend", 60))
        rep = write_span(c, pts, tmp)
        rep.update(group="direct", role=dr["role"], tick=dr["tick"])
        report.append(rep)
        print("direct", dr["role"], dr["tick"], rep["points"], "points ok", flush=True)
    tmp.unlink(missing_ok=True)
    cli("project", "save")
    Path(sys.argv[3]).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
