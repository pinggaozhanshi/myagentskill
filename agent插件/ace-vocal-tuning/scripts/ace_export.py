"""导出人声轨干声（仅人声轨，片段起止），并做文件级检查。

用法：python -I ace_export.py <ace_state.json> <out_dir> <label> [--disable-fx]
范围：片段起止（tick），48 kHz / 24-bit / 单声道。检查：能解码、时长、峰值/RMS、非静音比例；写入 <out_dir>/<label>_export.json。
--disable-fx：停用（不是旁通）人声轨默认效果链，基线与各轮同样处理。
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402


def main():
    state_p, out_dir, label = sys.argv[1:4]
    out_dir = os.path.abspath(out_dir)  # ACE 按它自己的安装目录解析相对路径
    st = json.load(open(state_p, encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    vt = st["second_vocal_track_uuid"] if "--second" in sys.argv else st["vocal_track_uuid"]
    if "--disable-fx" in sys.argv:
        for ins in cli("fx", "list", "--track-uuid", vt)["inserts"]:
            if ins["enabled"]:
                cli("fx", "disable", "--track-uuid", vt, "--instance", ins["instanceId"])
        print("fx:", [(i["name"], i["enabled"]) for i in cli("fx", "list", "--track-uuid", vt)["inserts"]])
    base = os.path.join(out_dir, f"{label}.wav")
    for old in glob.glob(os.path.join(out_dir, f"{label}*.wav")):
        raise SystemExit(f"目标已存在，换一个 label：{old}")
    res = cli("export", "audio", "--path", base, "--scope", "tracks", "--track-uuid", vt,
              "--from", f"{st['clip_begin']}t", "--to", f"{st['clip_end']}t",
              "--sample-rate", "48000", "--bit-depth", "24", "--channels", "1", "--wait", timeout=900)
    paths = res.get("paths") or glob.glob(os.path.join(out_dir, f"{label}*.wav"))
    path = paths[0]
    x, sr = sf.read(path, always_2d=True)
    x = x[:, 0]
    frame = int(0.02 * sr)
    rms_frames = np.sqrt(np.mean(x[: len(x) // frame * frame].reshape(-1, frame) ** 2, axis=1))
    info = {"path": path, "sr": sr, "duration_sec": len(x) / sr,
            "peak_dbfs": float(20 * np.log10(np.max(np.abs(x)) + 1e-12)),
            "rms_dbfs": float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)),
            "active_fraction_gt_-50dBFS": float(np.mean(20 * np.log10(rms_frames + 1e-12) > -50)),
            "clip_ticks": [st["clip_begin"], st["clip_end"]],
            "clip_begin_sec": cli("convert", "tick-to-time", "--tick", st["clip_begin"])["time"],
            "job": res}
    print(json.dumps({k: v for k, v in info.items() if k != "job"}, ensure_ascii=False, indent=1))
    if info["active_fraction_gt_-50dBFS"] < 0.2:
        raise SystemExit("导出几乎无声：检查静音/独奏、合成状态与导出范围")
    json.dump(info, open(os.path.join(out_dir, f"{label}_export.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
