"""第 3 轮重新标定（锁定版）：四个参数全部写成绝对值曲线（r2 快照），每次只把一个参数整段 ×1.5 或 ×0.67。

用法：python -I round3_calib_locked.py <ace_state_r3.json> <params_r2_main.npz> <base.acep> <r2.acep> <r3.acep> <work_dir> <exports_dir>
为什么重做：第一次标定用包络层，改一个参数会让 ACE 重新生成别的参数的 AI 曲线，测到的“单个参数的效果”里混进了别的参数的漂移；
按那次标定解出的 r3 在 G3–B3 上 H1−H2 实测 +9.6 dB，预测是 −2.1 dB，方向都反了。
每个变体是 ace/1min_r3_calib/<label>/<label>.acep 一份独立工程（离线写入，同第 2 轮写音高的流程），最后 ACE 切回 r3。
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402
import param_write as pw  # noqa: E402

import numpy as np  # noqa: E402

VENV_PY = r"C:\Users\lenovo\Documents\自媒体\调教Agent研究\.venv\Scripts\python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
FACTORS = (1.5, 0.67)


def run(script, *args, py=sys.executable):
    p = subprocess.run([py, "-I", "-X", "utf8", os.path.join(HERE, script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stdout[-1500:], p.stderr[-1500:])
        raise SystemExit(f"{script} 失败")
    return p.stdout


def release_and_open(path):
    """切换工程。离线写出的标定工程 ACE 会当成临时工程打开（没有路径，保存不了）；渲染脚本切换静音会让它变“未保存”。
    只有当未保存的改动全是本脚本自己的静音切换（撤销记录里只有远程控制的“设置轨道静音/独奏”）时才丢弃，否则停下。"""
    d = cli("project", "dirty")
    if not d["dirty"]:
        cli("project", "open", path)
        return
    entries = cli("history", "list")["entries"]
    mine = all(e["actor"] == "远程控制" and e["name"] == "设置轨道静音/独奏" for e in entries if e.get("applied", True))
    if "1min_r3_calib" in d["projectPath"]:
        cli("project", "save")
        cli("project", "open", path)
    elif d.get("isTempProject") and mine:
        cli("project", "open", path, "--discard-changes")
    else:
        raise SystemExit(f"当前工程有不是本脚本造成的未保存改动，停下：{d}")


def main():
    st_p, snap_p, base_acep, r2_acep, r3_acep, work, exp = map(os.path.abspath, sys.argv[1:8])
    st = json.load(open(st_p, encoding="utf-8"))
    snap = np.load(snap_p)
    base = {p: np.maximum(snap[f"{p}_baseline"], 0.0) for p in pw.PARAMS}
    voiced = snap["energy_baseline"] > 0
    off = max(4, int(np.argmax(voiced)) - 480)
    ldir = os.path.join(work, "lcal")
    os.makedirs(ldir, exist_ok=True)
    log_p = os.path.join(ldir, "runs.json")
    runs = json.load(open(log_p, encoding="utf-8")) if os.path.exists(log_p) else []
    done = {r["label"] for r in runs}
    plan = [(None, 1.0)] + [(p, f) for p in pw.PARAMS for f in FACTORS]
    for p, f in plan:
        label = f"lcal_{p}_x{f:.2f}" if p else "lcal_control"
        if label in done:
            continue
        tg = {q: base[q].copy() for q in pw.PARAMS}
        if p:
            tg[p] = np.minimum(base[p] * f, np.maximum(base[p], 1.0))
        tgt_p = os.path.join(ldir, f"{label}_targets.npz")
        np.savez_compressed(tgt_p, **tg)
        dst = os.path.join(os.path.dirname(r3_acep).replace("1min_r3_params", "1min_r3_calib"), label, f"{label}.acep")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        release_and_open(r2_acep)  # 先让别的工程处于打开状态，再离线写
        if os.path.exists(dst):
            os.remove(dst)
        run("patch_params.py", base_acep, dst, tgt_p, st["vocal_track_uuid"], st["clip_uuid"], off,
            os.path.join(ldir, f"{label}_patch.json"), py=VENV_PY)
        cli("project", "open", dst)
        chk = {}
        for q in ([p] if p else []) + ["energy"]:
            r = cli("vocalparam", "read", "--clip-uuid", st["clip_uuid"], "--param", q, "--encoding", "base64", timeout=300)
            eff = pw._decode(r["effective"]["points"])
            m = voiced & (tg[q] > 1e-3)
            m[:off + 2] = False
            chk[q] = float(np.percentile(np.abs(eff[m] / tg[q][m] - 1), 95))
        if max(chk.values()) > 1e-3:
            raise SystemExit(f"{label} 读回不一致：{chk}")
        run("ace_render.py", st_p, 900)
        run("ace_export.py", st_p, exp, label)
        wav = os.path.join(exp, f"{label}_洛天依_主旋律.wav")
        print(run("voice_features.py", wav, os.path.join(work, f"feat_{label}.npz")).strip())
        runs.append({"label": label, "param": p, "factor": f, "project": dst, "readback_p95_rel_err": chk})
        json.dump(runs, open(log_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("done", label, flush=True)
    release_and_open(r3_acep)
    print("calibration complete; ACE back on", r3_acep)


if __name__ == "__main__":
    main()
