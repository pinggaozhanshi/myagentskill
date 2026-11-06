"""把一个片段音高曲线下的有声 / 无声固定全部清成 auto，读回为 0 段后保存工程（CLI 0.18 起）。

用法：python -I voicing_clear.py <ace_state.json> [--second]
在线写音高（round2_pitch_online.py）会把写入当时 ACE 的有声判断固定在曲线下。做了音节结尾轮时 endings_apply.py 会清；
结尾检查没问题、不做那一轮时，用这个清掉，免得以后改辅音时元音仍被固定成无声。
当前工程必须是 state 里那个已保存的工程，否则停下（不替用户保存或丢弃）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402


def main():
    st = json.load(open(sys.argv[1], encoding="utf-8"))
    if "--second" in sys.argv:
        st = dict(st, clip_uuid=st["second_clip_uuid"])
    d = cli("project", "dirty")
    if d.get("dirty") or os.path.normcase(os.path.abspath(d.get("projectPath") or "")) != os.path.normcase(
            os.path.abspath(st["project"]["savedPath"])):
        raise SystemExit(f"当前工程不是已保存的 {st['project']['savedPath']}，停止：{d}")
    before = cli("vocalpitch", "voicing", "--clip-uuid", st["clip_uuid"]).get("spans", [])
    cli("vocalpitch", "set-voicing", "--clip-uuid", st["clip_uuid"], "--begin", 0, "--end", st["clip_end"] - st["clip_begin"],
        "--mode", "auto")
    after = cli("vocalpitch", "voicing", "--clip-uuid", st["clip_uuid"]).get("spans", [])
    print(f"voicing overrides {len(before)} (unvoiced {sum(s.get('mode') == 'unvoiced' for s in before)}) -> {len(after)}")
    if after:
        raise SystemExit("清完还有固定段，没保存")
    cli("project", "save")


if __name__ == "__main__":
    main()
