"""把第 3 轮的四个参数目标写成 ACE 片段的绝对值曲线（realEnergy / realTension / realBreathiness / realFalsetto），
并清空四个包络曲线（energy / tension / breathiness / falsetto，空 = 全 1）。研究 .venv（LibreSVIP 2.9.0）运行：

python -I patch_params.py <src.acep> <dst.acep> <targets.npz> <track_uuid> <clip_uuid> <offset_tick> <report.json>
targets.npz：energy / tension / air / falsetto 四条逐 tick 目标值（片段内 tick 0 起），只写 offset_tick 起到数组末尾前 2 tick。
为什么离线写：命令行的 direct 层只收 ≥0.3 的张力 / 假声值，而 r2 里 65–73% 的有声 tick 低于 0.3；
ACE 的 AI 参数不存进工程，每次编辑都会在附近乐句重新生成，不锁住就没法保证“只改了倍率”。
写完重新解包：改动的 8 个字段以外与源工程逐字段相同才算成功。
"""
import copy
import json
import pathlib
import sys

import numpy as np
from libresvip.plugins.acep.acep_io import compress_ace_studio_project, decompress_ace_studio_project
from libresvip.plugins.acep.options import AcepSerialization

REAL = {"energy": "realEnergy", "tension": "realTension", "air": "realBreathiness", "falsetto": "realFalsetto"}
ENV = {"energy": "energy", "tension": "tension", "air": "breathiness", "falsetto": "falsetto"}


def main():
    src, dst, tgt_p, track_uuid, clip_uuid, off, rep_p = sys.argv[1:8]
    src, dst, off = pathlib.Path(src), pathlib.Path(dst), int(off)
    if dst.exists():
        raise SystemExit(f"目标已存在：{dst}")
    raw = decompress_ace_studio_project(src)
    pats = [p for t in raw["tracks"] if t.get("uuid") == track_uuid and t.get("type") == "sing"
            for p in t["patterns"] if p.get("uuid") == clip_uuid]
    assert len(pats) == 1 and pats[0].get("timeUnit") == "tick", "需要唯一的 tick 片段"
    tg = np.load(tgt_p)
    changed = copy.deepcopy(raw)
    tp = next(p for t in changed["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    report = {"offset": off, "params": {}}
    for p, key in REAL.items():
        vals = np.asarray(tg[p], dtype=float)[off:len(tg[p]) - 2]
        if not np.all(np.isfinite(vals)) or vals.min() < 0:
            raise SystemExit(f"{p} 目标有空值或负值")
        tp["parameters"][key] = [{"type": "data", "offset": off, "values": [round(float(v), 7) for v in vals]}]
        tp["parameters"][ENV[p]] = []
        report["params"][p] = {"field": key, "n": int(len(vals)), "min": float(vals.min()), "median": float(np.median(vals)),
                               "max": float(vals.max()), "frac_below_0.3": float(np.mean(vals < 0.3))}
    compress_ace_studio_project(changed, dst, AcepSerialization.CBOR)
    check = decompress_ace_studio_project(dst)
    cp = next(p for t in check["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    ok = True
    for p, key in REAL.items():
        w = cp["parameters"][key]
        want = tp["parameters"][key][0]["values"]
        ok &= len(w) == 1 and w[0]["offset"] == off and len(w[0]["values"]) == len(want) and \
            max(abs(x - y) for x, y in zip(w[0]["values"], want)) < 1e-5
    report["roundtrip_values_equal"] = bool(ok)
    orig = copy.deepcopy(raw)
    op = next(p for t in orig["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    for p in REAL:
        for key in (REAL[p], ENV[p]):
            op["parameters"][key] = None
            cp["parameters"][key] = None
    report["other_fields_identical"] = check == orig
    print(json.dumps(report, indent=1, ensure_ascii=False))
    json.dump(report, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not (report["roundtrip_values_equal"] and report["other_fields_identical"]):
        dst.unlink()
        raise SystemExit("回读校验失败，已删除输出")


if __name__ == "__main__":
    main()
