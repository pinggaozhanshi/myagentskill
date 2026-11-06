"""找出 Stem Splitter 生成的分轨文件、分清哪组是去混响，解码成 48 kHz / 24-bit WAV。

用法：python -I stems_collect.py <split_state.json> <out_dir>
分轨音频存在分离工程的 Samples/Processed/*.ogg（Opus）。`--wait` 的返回值不带 trackUuids，
而第二次分离的轨插在原曲轨正下方、把第一次的挤到下面，所以不能按轨序认；这里按文件生成时间
对应两次任务的完成时间（work/ace_calls.jsonl 里 stem-splitter 调用的记录时间）。
"""
import glob
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import LOG, cli  # noqa: E402


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def main():
    st_p, out_dir = sys.argv[1:3]
    st = json.load(open(st_p, encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    calls = [json.loads(l) for l in open(LOG, encoding="utf-8")]
    done = [c for c in calls if c["args"][:2] == ["generative", "stem-splitter"] and c["exit"] == 0]
    labels = ["basic_dereverb" if "--remove-reverb" in c["args"] else "basic" for c in done]
    import datetime
    t_done = [datetime.datetime.fromisoformat(c["time"]).timestamp() for c in done]
    proj_dir = os.path.dirname(st["project"]["savedPath"])
    files = sorted(glob.glob(os.path.join(proj_dir, "Samples", "Processed", "*.ogg")))
    tracks = cli("track", "list")["tracks"]
    by_path = {}
    for t in tracks:
        for c in cli("clip", "list", "--track-uuid", t["trackUuid"]).get("clips", []):
            sp = (c.get("audioMedia") or {}).get("sourcePath")
            if sp:
                by_path[os.path.normcase(os.path.abspath(sp))] = (t["trackIndex"], t["trackName"], t["trackUuid"])
    out = []
    for f in files:
        mt = os.path.getmtime(f)
        k = min(range(len(done)), key=lambda i: abs(t_done[i] - mt))
        assert abs(t_done[k] - mt) < 5, f"{f} 的时间对不上任何一次分离"
        kind = "vocal" if f.endswith("_vocal.ogg") else "instrumental"
        wav = os.path.join(out_dir, f"{labels[k]}_{kind}.wav")
        if os.path.exists(wav):
            raise SystemExit(f"已存在：{wav}")
        subprocess.run(["ffmpeg", "-v", "error", "-n", "-i", f, "-ar", "48000", "-c:a", "pcm_s24le", wav], check=True)
        tr = by_path.get(os.path.normcase(os.path.abspath(f)))
        out.append({"label": labels[k], "kind": kind, "ogg": f, "ogg_sha256": sha256(f), "ogg_bytes": os.path.getsize(f),
                    "track": tr, "wav": wav, "wav_sha256": sha256(wav)})
        print(labels[k], kind, os.path.basename(f), "track", tr, "->", os.path.basename(wav))
    st["stems"] = out
    json.dump(st, open(st_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
