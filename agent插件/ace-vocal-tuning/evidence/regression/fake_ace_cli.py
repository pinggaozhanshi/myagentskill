"""回归测试用的假 acestudio-cli：记录每一次调用，按命令回答确定的 JSON，不碰真正的 ACE。

环境变量：FAKE_ACE_LOG（调用记录 jsonl）、FAKE_ACE_STATE（会话状态 json）、FAKE_ACE_FIXTURE（可选：音素、tick 换算、
Vocal to MIDI 的结果、读不出辅音时长的音符、工程是否有未保存改动及其撤销记录等）。
只覆盖调教脚本用到的命令；没见过的命令回答 {} 并在状态里记下来，测试据此报错。
0.18 起的命令（vocalpitch write / read / voicing / set-voicing、vocal-to-midi、clip list、history list）按《绯红》实测的行为模拟：
断开标记存在两段之间的中点；写进去的辅音长度、音符时值在读回里看得到；fixture 的 timings_unavailable 里的音符拒绝改辅音长度
（PHONEME_TIMINGS_UNAVAILABLE，退出码 1）。
"""
import json
import math
import os
import struct
import sys
import wave


def load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (FileNotFoundError, TypeError):
        return default


def opt(args, name, default=None):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default


def opts(args, name):
    return [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]


def write_wav(path, sec, sr=48000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = int(sec * sr)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * k / sr))) for k in range(n)))


def phonemes_for(lyric, fx):
    table = fx.get("g2p", {})
    if lyric in table:
        return table[lyric]
    return ["k", "a"]


def find_note(st, uuid):
    for notes in st["notes"].values():
        for n in notes:
            if n.get("noteUuid") == uuid:
                return n
    return None


def main():
    args = [a for a in sys.argv[1:] if a != "--json"]
    with open(os.environ["FAKE_ACE_LOG"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args, ensure_ascii=False) + "\n")
    st_p = os.environ["FAKE_ACE_STATE"]
    st = load(st_p, {"tracks": [], "notes": {}, "clips": {}, "saved": "", "fx_off": [], "unknown": []})
    for k in ("cons", "pitch", "voicing", "clip_lists"):
        st.setdefault(k, {})
    fx = load(os.environ.get("FAKE_ACE_FIXTURE"), {})
    tps = fx.get("ticks_per_sec", 1760.0)
    cmd = tuple(args[:2])
    out, err, code = {}, "", 0
    if cmd == ("project", "dirty"):
        out = {"dirty": bool(fx.get("dirty", False)), "isTempProject": not st["saved"], "projectPath": st["saved"]}
    elif cmd == ("track", "list"):
        out = {"tracks": st["tracks"]}
    elif cmd == ("project", "new"):
        st.update(tracks=[], notes={}, clips={}, saved="")
        out = {"projectName": "Untitled"}
    elif cmd == ("track", "create"):
        t = {"trackIndex": len(st["tracks"]), "trackUuid": f"T{len(st['tracks'])}", "trackName": opt(args, "--name"),
             "trackType": opt(args, "--type")}
        st["tracks"].append(t)
        out = dict(t)
    elif cmd == ("import", "file"):
        k = len(st["tracks"])
        st["tracks"].append({"trackIndex": k, "trackUuid": f"A{k}", "trackName": os.path.basename(opt(args, "--path")),
                             "trackType": "audio"})
        out = {"trackUuid": f"A{k}", "trackIndex": k, "clipUuid": f"AC{k}"}
    elif cmd == ("track", "rename"):
        for t in st["tracks"]:
            if t["trackUuid"] == opt(args, "--track-uuid"):
                t["trackName"] = opt(args, "--new-name")
    elif cmd == ("clip", "create"):
        ti = int(opt(args, "--track-index"))
        pos, dur = int(opt(args, "--pos").rstrip("t")), int(opt(args, "--dur").rstrip("t"))
        notes = json.loads(opt(args, "--notes"))
        st["notes"][str(ti)] = [dict(n, noteUuid=f"N{ti}_{k}") for k, n in enumerate(notes)]
        st["clips"][f"C{ti}"] = {"track": ti, "begin": pos, "end": pos + dur}
        out = {"clipUuid": f"C{ti}", "clipBegin": pos, "clipEnd": pos + dur, "noteCount": len(notes)}
    elif cmd == ("project", "save-as"):
        p = args[2]
        stem = os.path.splitext(os.path.basename(p))[0]
        st["saved"] = os.path.join(os.path.dirname(p), stem, os.path.basename(p))
        out = {"savedPath": st["saved"], "projectPath": st["saved"]}
    elif cmd == ("project", "save"):
        out = {"savedPath": st["saved"]}
    elif cmd == ("project", "open"):
        st["saved"] = args[2]
        out = {"projectName": os.path.basename(args[2])}
    elif cmd == ("clip", "note-content"):
        ti, ci = opt(args, "--track-index"), opt(args, "--clip-index", "0")
        out = {"notes": st["notes"].get(f"{ti}:{ci}", st["notes"].get(ti, []))}
    elif cmd == ("clip", "list"):
        out = {"clips": st["clip_lists"].get(opt(args, "--track-uuid"), [])}
    elif cmd == ("phoneme", "list"):
        clip = st["clips"].get(opt(args, "--clip"), {"track": 0, "begin": 0})
        rows = []
        for n in st["notes"].get(str(clip["track"]), []):
            if n["lyric"] in ("-", ""):
                continue
            ph = phonemes_for(n["lyric"], fx)
            set_len = st["cons"].get(n["noteUuid"], {})
            timings = [{"index": i, "name": p, "isVowel": p in "aiueo",
                        "durationSec": set_len.get(str(i), 0.08), "effectiveDurationSec": set_len.get(str(i), 0.08)}
                       for i, p in enumerate(ph)]
            start = (clip["begin"] + n["pos"]) / tps - clip["begin"] / tps
            rows.append({"pos": n["pos"], "noteUuid": n["noteUuid"], "phonemes": ph, "language": fx.get("language", "Japanese"),
                         "startSec": round(start, 6), "endSec": round(start + n["dur"] / tps, 6), "timings": timings})
        out = {"notes": rows, "modelGeneration": "v1", "capabilities": {"consonantLengths": True}}
    elif cmd == ("phoneme", "g2p"):
        out = {"contextSupported": False, "syllables": []}
        for i, g in enumerate(opts(args, "--grapheme")):
            ph = phonemes_for(g, fx)
            out["syllables"].append({"index": i, "grapheme": g, "phonemes": ph, "resolved": True,
                                     "headConsonants": [p for p in ph[:1] if p not in "aiueo"]})
    elif cmd == ("convert", "tick-to-time"):
        out = {"time": float(opt(args, "--tick")) / tps}
    elif cmd == ("transport", "state"):
        out = {"status": "playing", "position": 1e6}
    elif cmd[0] == "transport":
        out = {}
    elif cmd == ("project", "synthesis-status"):
        out = {"isSynthesizing": False}
    elif cmd == ("track", "get"):
        out = {"mixer": {"mute": True}}
    elif cmd == ("fx", "list"):
        tu = opt(args, "--track-uuid")
        out = {"inserts": [{"instanceId": f"{tu}_fx{i}", "name": n, "enabled": f"{tu}_fx{i}" not in st["fx_off"]}
                           for i, n in enumerate(("Vocal EQ", "Little Compressor", "Little De-Esser", "Little Reverb"))]}
    elif cmd == ("fx", "disable"):
        st["fx_off"].append(opt(args, "--instance"))
    elif cmd == ("export", "audio"):
        a, b = int(opt(args, "--from").rstrip("t")), int(opt(args, "--to").rstrip("t"))
        write_wav(opt(args, "--path"), (b - a) / tps)
        out = {"paths": [opt(args, "--path")], "status": "completed"}
    elif cmd == ("phoneme", "set-consonant-timing"):
        note = opt(args, "--note")
        if note in fx.get("timings_unavailable", []):
            err, code = ("error[PHONEME_TIMINGS_UNAVAILABLE] the note carries no consonant lengths here; synthesize first"), 1
        else:
            st["cons"].setdefault(note, {})[opt(args, "--index")] = float(opt(args, "--length").rstrip("ms")) / 1000
            out = {"writes": 1}
    elif cmd == ("note", "resize"):
        n = find_note(st, opt(args, "--note-uuid"))
        if n is not None:
            n["dur"] = int(opt(args, "--dur").rstrip("t"))
    elif cmd == ("vocalpitch", "write"):
        clip = opt(args, "--clip-uuid")
        pts = json.load(open(opt(args, "--points")[1:], encoding="utf-8"))
        stored = []
        for i, (t, v) in enumerate(pts):  # ACE 把断开标记存在两段之间的中点
            if v is None and 0 < i < len(pts) - 1:
                t = (pts[i - 1][0] + pts[i + 1][0]) / 2
            stored.append([t, v])
        st["pitch"][clip] = stored
        st["voicing"][clip] = list(fx.get("pinned_after_write", []))  # 写曲线时把当时的有声判断固定下来
        out = {"written": len(pts), "fingerprint": f"fake:{len(pts)}"}
    elif cmd == ("vocalpitch", "read"):
        out = {"level": opt(args, "--level"), "points": st["pitch"].get(opt(args, "--clip-uuid"), []),
               "voicing": {"unvoiced": []}}
    elif cmd == ("vocalpitch", "set-voicing"):
        clip, mode = opt(args, "--clip-uuid"), opt(args, "--mode")
        b, e = float(opt(args, "--begin")), float(opt(args, "--end"))
        keep = [s for s in st["voicing"].get(clip, []) if s["end"] <= b or s["begin"] >= e]
        st["voicing"][clip] = keep if mode == "auto" else keep + [{"begin": b, "end": e, "mode": mode}]
        out = {"spans": [s for s in st["voicing"][clip] if not (s["end"] <= b or s["begin"] >= e)]}
    elif cmd == ("vocalpitch", "voicing"):
        clip = opt(args, "--clip-uuid")
        out = {"clipUuid": clip, "spans": st["voicing"].get(clip, []), "support": [], "unvoiced": []}
    elif cmd == ("history", "list"):
        out = {"entries": fx.get("history", [])}
    elif cmd == ("generative", "vocal-to-midi"):
        v = fx["v2m"]
        k = len(st["tracks"])
        tu = v.get("trackUuid", "{V2M-SING}")
        st["tracks"].append({"trackIndex": k, "trackUuid": tu, "trackName": "Vocal to MIDI", "trackType": "Sing"})
        st["clip_lists"][tu] = []
        for ci, c in enumerate(v["clips"]):
            st["clip_lists"][tu].append({"clipUuid": c["clipUuid"], "clipType": "sing", "clipBegin": c["clipBegin"]})
            st["notes"][f"{k}:{ci}"] = c["notes"]
        out = v["job"]
    elif cmd in {("voice", "load"), ("track", "set-language"), ("track", "set"), ("tempo", "set"), ("note", "set-grapheme")}:
        out = {}
    else:
        st["unknown"].append(args)
    json.dump(st, open(st_p, "w", encoding="utf-8"), ensure_ascii=False)
    if code:
        print(err, file=sys.stderr)
        sys.exit(code)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # 真的 acestudio-cli 输出 UTF-8；Windows 管道默认是 GBK
    sys.stderr.reconfigure(encoding="utf-8")
    main()
