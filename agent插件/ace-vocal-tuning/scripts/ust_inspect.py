"""把 UST（Shift-JIS，UTAU 格式）读成 JSON：工程设置 + 每个音符的绝对 tick。

用法：python -I ust_inspect.py <in.ust> <out.json>
UST 的 Length 以 480 tick/四分音符计；Lyric 为 R 或空是休止。只做读取与统计，不改谱面。
"""
import collections
import json
import re
import sys


def parse_ust(path):
    text = open(path, "rb").read().decode("cp932")
    blocks = re.split(r"^\[#", text, flags=re.M)
    setting, notes, tick = {}, [], 0
    for b in blocks[1:]:
        head, _, body = b.partition("\n")
        name = head.strip().rstrip("]")
        kv = {}
        for line in body.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        if name == "SETTING":
            setting = kv
        elif re.fullmatch(r"\d{4}", name):
            length = int(round(float(kv["Length"])))
            lyric = kv.get("Lyric", "")
            n = {"idx": int(name), "tick": tick, "dur": length, "lyric": lyric,
                 "pitch": int(kv.get("NoteNum", "60")), "rest": lyric.strip().upper() in ("R", "")}
            for k in ("Tempo", "Intensity", "Modulation", "PreUtterance", "VoiceOverlap", "Flags", "PBS", "PBW", "PBY", "VBR", "Velocity", "StartPoint"):
                if k in kv:
                    n[k] = kv[k]
            notes.append(n)
            tick += length
        # [#PREV] [#NEXT] [#INSERT] [#DELETE] [#TRACKEND] 不含音符
    return setting, notes


def kana_kind(lyric):
    if re.fullmatch(r"[ぁ-ゖー]+", lyric):
        return "hiragana"
    if re.fullmatch(r"[ァ-ヺー]+", lyric):
        return "katakana"
    if re.fullmatch(r"[a-zA-Z]+", lyric):
        return "romaji"
    if re.fullmatch(r"[aiueonN-] .+", lyric):
        return "vcv_prefixed"
    return "other"


def main():
    src, out = sys.argv[1:3]
    setting, notes = parse_ust(src)
    sung = [n for n in notes if not n["rest"]]
    kinds = collections.Counter(kana_kind(n["lyric"]) for n in sung)
    tempos = [(n["tick"], n["Tempo"]) for n in notes if "Tempo" in n]
    info = {"source": src, "setting": setting, "n_blocks": len(notes), "n_sung": len(sung),
            "n_rest": len(notes) - len(sung), "end_tick": notes[-1]["tick"] + notes[-1]["dur"] if notes else 0,
            "pitch_range": [min(n["pitch"] for n in sung), max(n["pitch"] for n in sung)] if sung else None,
            "lyric_kinds": dict(kinds), "tempo_changes": tempos,
            "has_pitchbend": sum(1 for n in sung if "PBS" in n or "PBW" in n),
            "other_lyrics": sorted({n["lyric"] for n in sung if kana_kind(n["lyric"]) == "other"})[:40]}
    json.dump({"info": info, "notes": notes}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
