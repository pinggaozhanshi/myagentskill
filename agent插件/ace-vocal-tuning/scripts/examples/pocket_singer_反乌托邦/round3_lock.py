"""第 3 轮锁定写入（取代 round3_write.py 的包络补偿）：四个参数都写成绝对值曲线，AI 重算不再影响结果。

用法：python -I round3_lock.py <ace_state_r3.json> <params_r2_main.npz> <r3_multipliers.npz> <r2.acep> <work_dir>
流程（与第 2 轮写音高相同）：ACE 切到 r2（让 r3 不处于打开状态）→ 离线改写 r3 工程 → ACE 打开 r3 → 读回四个参数核对。
目标 = r2 的参数快照 × 倍率（不把值推到 1 以上）；倍率为 1 的地方就是 r2 原值。
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402
import param_write as pw  # noqa: E402

import numpy as np  # noqa: E402

VENV_PY = r"C:\Users\lenovo\Documents\自媒体\调教Agent研究\.venv\Scripts\python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    st_p, snap_p, mult_p, r2_acep, work = sys.argv[1:6]
    st = json.load(open(st_p, encoding="utf-8"))
    r3 = os.path.abspath(st["project"]["savedPath"])
    d = cli("project", "dirty")
    if d["dirty"] or os.path.normcase(os.path.abspath(d["projectPath"])) != os.path.normcase(r3):
        raise SystemExit(f"当前工程不是已保存的 r3：{d}")
    snap, mult = np.load(snap_p), np.load(mult_p)
    targets = {}
    for p in pw.PARAMS:
        base = snap[f"{p}_baseline"]
        t = np.minimum(base * mult[p], np.maximum(base, 1.0))
        if t.min() < -0.01:
            raise SystemExit(f"{p} 的 AI 值有明显负数：{t.min()}")
        targets[p] = np.maximum(t, 0.0)  # AI 的假声偶有 −0.003 这样的微小负值，按 0 写
    tgt_p = os.path.join(work, "r3_targets_abs.npz")
    np.savez_compressed(tgt_p, **targets)
    n = st["clip_end"] - st["clip_begin"]
    voiced = snap["energy_baseline"] > 0
    off = max(4, int(np.argmax(voiced)) - 480)

    cli("project", "open", os.path.abspath(r2_acep))  # 让 r3 不处于打开状态
    before = os.path.join(work, "1min_r3_params.before_lock.acep")
    shutil.copy2(r3, before)
    os.remove(r3)
    p = subprocess.run([VENV_PY, "-I", "-X", "utf8", os.path.join(HERE, "patch_params.py"), before, r3, tgt_p,
                        st["vocal_track_uuid"], st["clip_uuid"], str(off), os.path.join(work, "round3_lock_patch.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(p.stdout[-3000:], p.stderr[-2000:])
    if p.returncode != 0 or not os.path.exists(r3):
        shutil.copy2(before, r3)
        raise SystemExit("写入失败，已恢复写入前的 r3")
    print("opened:", cli("project", "open", r3).get("projectName"))
    rep = {"offset": off, "params": {}}
    for q in pw.PARAMS:
        r = cli("vocalparam", "read", "--clip-uuid", st["clip_uuid"], "--param", q, "--encoding", "base64", timeout=300)
        lay = {x["layer"]: pw._decode(x["points"]) for x in r["layers"]}
        eff = pw._decode(r["effective"]["points"])
        v = snap[f"{q}_voiced"]
        m = v & (targets[q] > 1e-3)
        m[:off + 1] = False
        m[n - 3:] = False
        rel = np.abs(eff[m] / targets[q][m] - 1)
        rep["params"][q] = {"direct_drawn": [x.get("drawnRanges") for x in r["layers"] if x["layer"] == "direct"],
                            "envelope_non1_ticks": int(np.sum(np.abs(lay["envelope"] - 1) > 1e-6)),
                            "eff_vs_target_rel_median": float(np.median(rel)), "p95": float(np.percentile(rel, 95)), "max": float(rel.max()),
                            "eff_min_voiced": float(eff[m].min())}
        print(q, rep["params"][q])
    json.dump(rep, open(os.path.join(work, "round3_lock_readback.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = [q for q, x in rep["params"].items() if x["p95"] > 1e-3]
    if bad:
        raise SystemExit(f"读回与目标不一致：{bad}")


if __name__ == "__main__":
    main()
