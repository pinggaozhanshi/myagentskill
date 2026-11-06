"""写 V1 表情参数的包络层（倍率，1 = 不改）或 direct 层（绝对值覆盖），并读回核对。被 round3_*.py 调用。

- 标定用 envelope 层（官方建议多数情况只改包络）。
- 第 3 轮成品用 direct 层：标定时发现，改任何一个包络后 ACE 会把四个参数的 AI 生成值（baseline）重算一遍，
  数值和原来不完全一样（对照渲染的响度差中位 0.7 dB）。direct 层画过的地方不随 AI 重算，
  所以把 r2 当时的 AI 生成值 × 倍率写进 direct 层，等于“先锁住 r2，再只改倍率”。
每次写之前先读一次拿 fingerprint，用 --if-match 防止和界面里的手动改动撞车；写完读回，逐 tick 比较。
"""
import base64
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402

import numpy as np  # noqa: E402

PARAMS = ["energy", "tension", "air", "falsetto"]
RANGES = {"energy": (0.0, 2.0), "tension": (0.3, 2.5), "air": (0.2, 2.5), "falsetto": (0.3, 3.0)}  # vocalparam layers 报的包络范围


def _decode(points):
    if isinstance(points, dict):
        return np.frombuffer(base64.b64decode(points["data"]), dtype="<f8").copy()
    return np.array([np.nan if v is None else v for v in points], dtype=float)


def read_layers(clip_uuid, param):
    r = cli("vocalparam", "read", "--clip-uuid", clip_uuid, "--param", param, "--encoding", "base64", timeout=300)
    lay = {x["layer"]: _decode(x["points"]) for x in r["layers"] if x.get("shape") == "dense"}
    return r["posBegin"], r["count"], r["fingerprint"], lay


def write_envelope(clip_uuid, param, values, pos_begin=0, tol=1e-4):
    """values：从 pos_begin 起每 tick 一个倍率。返回读回后与目标的最大差（不计两端各 2 tick，见 help vocalparam write 的边缘说明）。"""
    lo, hi = RANGES[param]
    v = np.asarray(values, dtype="<f8")
    if not np.all(np.isfinite(v)):
        raise ValueError("包络层不稀疏，不能写空值")
    if v.min() < lo - 1e-9 or v.max() > hi + 1e-9:
        raise ValueError(f"{param} 包络超出范围 [{lo}, {hi}]：{v.min():.3f}–{v.max():.3f}")
    pb, count, fp, _ = read_layers(clip_uuid, param)
    payload = {"dtype": "f64le", "count": int(len(v)), "data": base64.b64encode(v.tobytes()).decode("ascii")}
    fd, tmp = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    try:
        cli("vocalparam", "write", "--clip-uuid", clip_uuid, "--param", param, "--layer", "envelope",
            "--pos-begin", pos_begin, "--points", "@" + tmp, "--encoding", "base64", "--if-match", fp,
            "--wait-busy", "60s", timeout=300)
    finally:
        os.remove(tmp)
    pb2, count2, _, lay = read_layers(clip_uuid, param)
    got = lay["envelope"][pos_begin - pb2: pos_begin - pb2 + len(v)]
    err = float(np.max(np.abs(got[2:-2] - v[2:-2].astype(np.float32))))
    if err > tol:
        raise RuntimeError(f"{param} 包络读回不一致，最大差 {err}")
    return err


def write_direct(clip_uuid, param, values, pos_begin, hi=1.2):
    """direct 层：从 pos_begin 起每 tick 一个绝对值（不允许空值）。返回读回的 effective 与目标的最大差（不计两端各 2 tick）。"""
    v = np.asarray(values, dtype="<f8")
    if not np.all(np.isfinite(v)) or v.min() < 0 or v.max() > hi:
        raise ValueError(f"{param} direct 值越界或有空值：{np.nanmin(v):.3f}–{np.nanmax(v):.3f}")
    pb, count, fp, _ = read_layers(clip_uuid, param)
    payload = {"dtype": "f64le", "count": int(len(v)), "data": base64.b64encode(v.tobytes()).decode("ascii")}
    fd, tmp = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    try:
        cli("vocalparam", "write", "--clip-uuid", clip_uuid, "--param", param, "--layer", "direct",
            "--pos-begin", pos_begin, "--points", "@" + tmp, "--encoding", "base64", "--if-match", fp,
            "--wait-busy", "60s", timeout=300)
    finally:
        os.remove(tmp)
    r = cli("vocalparam", "read", "--clip-uuid", clip_uuid, "--param", param, "--encoding", "base64",
            "--range-begin", pos_begin, "--range-end", pos_begin + len(v), timeout=300)
    eff = _decode(r["effective"]["points"])
    return float(np.max(np.abs(eff[2:-2] - v[2:-2].astype(np.float32))))


def baselines(clip_uuid):
    return {p: read_layers(clip_uuid, p)[3]["baseline"] for p in PARAMS}


def same_baselines(a, b, tol=1e-6):
    return {p: float(np.nanmax(np.abs(a[p] - b[p]))) for p in PARAMS if np.nanmax(np.abs(a[p] - b[p])) > tol}
