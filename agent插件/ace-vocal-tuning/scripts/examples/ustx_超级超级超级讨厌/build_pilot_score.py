"""把 USTX 截取音符 + 音高修正 + 罗马音→假名 合成为 ACE 试验谱面。

用法：python -I build_pilot_score.py <pilot_notes_ustx_raw.json> <note_corrections.json> <clip_start_tick> <out_score.json>

发音规则（发音轮，基线前）：
- USTX 的 UTAU 写法换成 ACE 日语可解析的假名：'a t'→っ（ACE: cl），'i n'→ん，'si'→すぃ；'R'（休止）删除。
  （注意 USTX 须按 YAML 1.2 读，否则歌词 no 会变成布尔值。）
- 逐音符覆盖 OVERRIDES：有证据的个别修正（见 docs/pilot-score-decisions.md）。
- 音高：note_corrections.json 的 new_tone；EXCLUDE_PITCH 中的修正候选不采用（理由见文档）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vp_common  # noqa: E402,F401

KANA = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "shi": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "ji": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "chi": "ち", "tsu": "つ", "te": "て", "to": "と",
    "da": "だ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "fu": "ふ", "he": "へ", "ho": "ほ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wo": "を", "n": "ん",
    "kya": "きゃ", "kyu": "きゅ", "kyo": "きょ", "hya": "ひゃ", "hyu": "ひゅ", "hyo": "ひょ",
    "sha": "しゃ", "shu": "しゅ", "sho": "しょ", "cha": "ちゃ", "chu": "ちゅ", "cho": "ちょ",
    # UTAU / OpenUtau 写法
    "a t": "っ", "i n": "ん", "si": "すぃ",
}

# 逐音符覆盖：pilot 内序号 → 假名。
# #28/#29：USTX 写作 fu(30t)/ku(120t)，但 120t 那个音符两种提取器都判为有声（0.91/1.00），
# 而 30t 那个完全无声。「予測不能」中“く”在“ふ”前去声化，故 30t=く、120t=ふ，USTX 两字顺序颠倒。
OVERRIDES = {28: "く", 29: "ふ"}

# 不采用的音高修正候选：#21 属于四处句尾“上滑到顶再落下”的同类手势之一，
# 单改一处会让同类句尾不一致；留给音高曲线轮统一处理。
EXCLUDE_PITCH = {21}


def main():
    raw_p, corr_p, clip0, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    raw = json.load(open(raw_p, encoding="utf-8"))
    corr = {d["idx"]: d for d in json.load(open(corr_p, encoding="utf-8"))["decisions"]}
    notes, changes = [], {"pitch": [], "octave": [], "lyric": [], "removed": []}
    for i, n in enumerate(raw["notes"]):
        d = corr[i]
        if d["new_tone"] is None:
            changes["removed"].append(i)
            continue
        pitch = n["tone"] if i in EXCLUDE_PITCH else d["new_tone"]
        if pitch != n["tone"]:
            (changes["octave"] if pitch == n["tone"] - 12 else changes["pitch"]).append(i)
        lyric = OVERRIDES.get(i, KANA.get(n["ustx_lyric"]))
        if lyric is None:
            raise SystemExit(f"未知 USTX 歌词 #{i}: {n['ustx_lyric']!r}")
        if i in OVERRIDES or n["ustx_lyric"] in ("a t", "i n", "si"):
            changes["lyric"].append(i)
        notes.append({"idx": i, "tick": n["tick"], "pos": n["tick"] - clip0, "dur": n["dur"], "pitch": pitch,
                      "lyric": lyric, "ustx_tone": n["tone"], "ustx_lyric": n["ustx_lyric"],
                      "start": n["start"], "end": n["end"]})
    # 单音音轨检查：不得重叠
    for a, b in zip(notes, notes[1:]):
        assert a["tick"] + a["dur"] <= b["tick"], (a, b)
    meta = dict(raw["meta"], clip_start_tick=clip0, count=len(notes), changes=changes)
    json.dump({"meta": meta, "notes": notes}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: (v if isinstance(v, list) else v) for k, v in changes.items()}, ensure_ascii=False))
    print("notes:", len(notes), "pitch range:", min(n["pitch"] for n in notes), "-", max(n["pitch"] for n in notes))


if __name__ == "__main__":
    main()
