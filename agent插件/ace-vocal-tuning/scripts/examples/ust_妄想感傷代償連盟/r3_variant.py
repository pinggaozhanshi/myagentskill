"""第 3 轮（“干脆”）的变体工程：以 r2 为底，把四个 V1 表情参数（力度、张力、气声、假声）全部锁成绝对值曲线，
只按给定的目标改动，然后渲染、导出、测量。标定和成品都走这里。

用法：python -I r3_variant.py <ace_state_r2.json> <r2.acep> <targets.npz> <label> <variants_dir> <exports_dir> <work_dir>
targets.npz：energy / tension / air / falsetto 四条逐 tick 绝对值（片段内 tick 0 起，与 param_read.py 的快照同长）。
流程（与第 2 轮写音高相同）：ACE 打开 r2 → 另存为变体（让 ACE 建好完整的工程目录）→ ACE 切回 r2 → 离线写变体
（patch_params.py，研究 venv）→ ACE 打开变体 → 读回四个参数核对 → 渲染 → 导出 → 保存 → 切回 r2。
锁定的原因见《反乌托邦》docs/round3-params-report.md：AI 参数不存进工程，任何编辑都会让附近乐句重算。
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


def run(script, *args, py=sys.executable):
    p = subprocess.run([py, "-I", "-X", "utf8", os.path.join(HERE, script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stdout[-2000:], p.stderr[-2000:])
        raise SystemExit(f"{script} 失败")
    return p.stdout


def open_clean(path):
    d = cli("project", "dirty")
    if d["dirty"]:
        raise SystemExit(f"当前工程有未保存改动，停下：{d}")
    if os.path.normcase(os.path.abspath(d["projectPath"] or "")) != os.path.normcase(os.path.abspath(path)):
        cli("project", "open", os.path.abspath(path))


def main():
    st_p, r2, tgt_p, label, vdir, exp, work = sys.argv[1:8]
    r2, tgt_p, vdir, exp, work = map(os.path.abspath, (r2, tgt_p, vdir, exp, work))
    st = json.load(open(st_p, encoding="utf-8"))
    tg = np.load(tgt_p)
    voiced = tg["energy"] > 0
    off = max(4, int(np.argmax(voiced)) - 480)
    open_clean(r2)
    saved = cli("project", "save-as", os.path.join(vdir, label, f"{label}.acep"))["savedPath"]
    cli("project", "open", r2)  # 让变体不处于打开状态
    unpatched = os.path.join(work, f"{label}.unpatched.acep")
    shutil.copy2(saved, unpatched)
    os.remove(saved)
    out = run("patch_params.py", unpatched, saved, tgt_p, st["vocal_track_uuid"], st["clip_uuid"], off,
              os.path.join(work, f"{label}_patch.json"), py=VENV_PY)
    if not os.path.exists(saved):
        shutil.copy2(unpatched, saved)
        raise SystemExit("写入失败，已恢复未改动的变体")
    cli("project", "open", saved)
    n = len(tg["energy"])
    chk = {}
    for q in pw.PARAMS:
        r = cli("vocalparam", "read", "--clip-uuid", st["clip_uuid"], "--param", q, "--encoding", "base64", timeout=300)
        eff = pw._decode(r["effective"]["points"])
        m = voiced & (tg[q] > 1e-3)
        m[:off + 2] = False
        m[n - 3:] = False
        chk[q] = float(np.percentile(np.abs(eff[m] / tg[q][m] - 1), 95))
    if max(chk.values()) > 1e-3:
        raise SystemExit(f"{label} 读回与目标不一致：{chk}")
    vst = dict(st, project={"savedPath": saved, "projectPath": saved})
    vst_p = os.path.join(work, f"ace_state_{label}.json")
    json.dump(vst, open(vst_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    run("ace_render.py", vst_p, 900)
    run("ace_export.py", vst_p, os.path.join(exp, label), label, "--disable-fx")
    cli("project", "save")
    wav = os.path.join(exp, label, f"{label}_洛天依_主唱.wav")
    print(run("voice_features.py", wav, os.path.join(work, f"feat_{label}.npz")).strip())
    cli("project", "open", r2)
    rec = {"label": label, "project": saved, "wav": wav, "features": os.path.join(work, f"feat_{label}.npz"),
           "readback_p95_rel_err": chk, "offset": off, "patch_stdout_tail": out[-600:]}
    json.dump(rec, open(os.path.join(work, f"{label}_run.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done", label, json.dumps(chk))


if __name__ == "__main__":
    main()
