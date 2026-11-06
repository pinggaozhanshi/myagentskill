"""用 ACE 自己的 G2P（语言按 project.json）逐音读出试验谱面的音素，并按首辅音分出清音 / 浊音，供时值轮使用。

用法：python -I g2p_check.py <pilot_score.json> <out.json>
ACE 必须在运行；只调用 phoneme g2p（不读写工程），不看上下文。延长音「-」不送 G2P（它延续前一个音节，没有自己的读音）；
其他脚本用 common.head_consonants 把音节对回音符。终端只打印不重复的“字 → 音素”表，不打印整句歌词。
- 日语：UST 写的是读音假名（は→わ、を→お、长音并进前一个音），核对的是“假名 → 音素”这一步；
- 中文：逐字读音，多音字（中、的、还、为、长……）要对照歌词语境逐个看。G2P 不看上下文，
  建完工程还要用 ace_readback 的音素逐字核对，读错的用 `phoneme set` 覆盖（见 references/score-and-reference.md）。
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from ace import cli  # noqa: E402


def main():
    score = json.load(open(sys.argv[1], encoding="utf-8"))
    kana = [n["lyric"] for n in score["notes"] if n["lyric"] != "-"]
    args = ["phoneme", "g2p", "--language", common.LANGUAGE]
    for k in kana:
        args += ["--grapheme", k]
    res = cli(*args)
    json.dump(res, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    syl = res["syllables"]
    print("contextSupported:", res.get("contextSupported"), "| syllables:", len(syl), "of", len(kana))
    table = collections.OrderedDict()
    for s in syl:
        table.setdefault(s["grapheme"], (" ".join(s["phonemes"]), s.get("headConsonants"), s.get("resolved")))
    for g, (ph, head, ok) in table.items():
        print(f"{g:<3} -> {ph:<10} head={head} {'' if ok else 'UNRESOLVED'}")
    heads = collections.Counter((s.get("headConsonants") or [""])[0] for s in syl)
    print("head consonants:", dict(heads))
    unresolved = [s["index"] for s in syl if not s.get("resolved")]
    print("unresolved:", unresolved)
    if unresolved or len(syl) != len(kana):
        raise SystemExit("G2P 有解析不了的音节（或音节数和送去的字数对不上）：先改谱面的歌词")


if __name__ == "__main__":
    main()
