"""把 ACE 里当前工程一个片段的音素时长、或音高曲线下的有声 / 无声固定存成 JSON（只读，不改工程）。

用法：python -I ace_dump.py <ace_state.json> phonemes|voicing <out.json> [--second]
- phonemes：phoneme list --with-timings=durations（每个音素的 durationSec、noteUuid、片段内 pos），endings_plan.py 要它
  读当前辅音长度。V1（Verse23）只有辅音长度；前一个音只有元音时，后一个音的辅音可能没有时长（durationSec 为空）。
- voicing：vocalpitch voicing（spans 的 mode = voiced / unvoiced、support = 有音高曲线的范围），voicing_check.py 要它。
  要 acestudio-cli 0.18 起的 vocalpitch 命令。
--second 读第二条人声轨（ace_build 写的 second_* state）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from ace import cli  # noqa: E402


def main():
    st_p, what, out = sys.argv[1:4]
    st = json.load(open(st_p, encoding="utf-8"))
    if "--second" in sys.argv:
        st = dict(st, clip_uuid=st["second_clip_uuid"])
    if what == "phonemes":
        res = cli("phoneme", "list", "--clip", st["clip_uuid"], "--range-begin", f"{st['clip_begin']}t",
                  "--range-end", f"{st['clip_end']}t", "--with-timings=durations")
        rows = res.get("notes", [])
        no_len = sum(1 for r in rows for t in r.get("timings", []) if not t.get("isVowel") and not t.get("durationSec"))
        print("phoneme rows", len(rows), "| consonants without a length", no_len)
    elif what == "voicing":
        res = cli("vocalpitch", "voicing", "--clip-uuid", st["clip_uuid"])
        spans = res.get("spans", [])
        print("voicing overrides", len(spans), "| unvoiced", sum(s.get("mode") == "unvoiced" for s in spans),
              "| curve support", len(res.get("support", [])))
    else:
        raise SystemExit("第二个参数要是 phonemes 或 voicing")
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
