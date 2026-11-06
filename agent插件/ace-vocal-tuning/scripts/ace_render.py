"""触发并等待合成：静音伴奏 → 从片段起点播放（播放触发渲染）→ 播放头越过片段终点且不在合成 → 停止 → 还原伴奏静音状态。

用法：python -I ace_render.py <ace_state.json> [timeout_sec]
V1（Verse23）只带辅音长度，phoneme list 的 span 恒为 not-synthesized，不能当判据；改用播放头越过终点。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402


def main():
    st = json.load(open(sys.argv[1], encoding="utf-8"))
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 600
    inst_muted = cli("track", "get", "--track-uuid", st["inst_track_uuid"])["mixer"]["mute"]
    cli("track", "set", "--track-uuid", st["inst_track_uuid"], "--mute", "true")
    cli("track", "set", "--track-uuid", st["vocal_track_uuid"], "--mute", "false")
    begin_sec = cli("convert", "tick-to-time", "--tick", st["clip_begin"]).get("time")
    end_sec = cli("convert", "tick-to-time", "--tick", st["clip_end"]).get("time")
    t0 = time.time()
    try:
        cli("transport", "seek", "--time", f"{begin_sec}s")
        cli("transport", "play")
        while True:
            syn = cli("project", "synthesis-status").get("isSynthesizing")
            tr = cli("transport", "state")
            print(f"{time.time() - t0:6.1f}s synthesizing={syn} transport={tr.get('status')} @{tr.get('position')}")
            if tr.get("status") == "playing" and tr.get("position", 0) > end_sec + 0.3 and not syn:
                break
            if time.time() - t0 > timeout:
                raise SystemExit("合成等待超时")
            time.sleep(3)
    finally:
        cli("transport", "stop")
        cli("track", "set", "--track-uuid", st["inst_track_uuid"], "--mute", "true" if inst_muted else "false")
    print(f"render ready after {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
