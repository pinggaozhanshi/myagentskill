"""把 PaiMe 工程（已转成 .acep）里的音符和音高曲线导成 JSON，供后续核对与建谱。

用法（研究 venv，需要 libresvip）：python -I export_paime_notes.py <paime.acep> <out.json>
输出每条轨的音符（tick、时长、音高、歌词、读音）和音高曲线点（tick, 值）。歌词只写进文件，不打印。
"""
import json
import sys
from pathlib import Path

from libresvip.extension.manager import plugin_manager


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    acep = plugin_manager.plugins["svs"]["acep"]
    p = acep.load(Path(sys.argv[1]), acep.input_option_cls())
    out = {"tempos": [(t.position, t.bpm) for t in p.song_tempo_list], "tracks": []}
    for ti, tr in enumerate(p.track_list):
        notes = [{"track": ti, "tick": n.start_pos, "dur": n.length, "pitch": n.key_number,
                  "lyric": n.lyric, "pron": getattr(n, "pronunciation", None)} for n in tr.note_list]
        pitch = getattr(getattr(tr, "edited_params", None), "pitch", None)
        raw = getattr(pitch.points, "root", pitch.points) if pitch is not None else []
        pts = [(int(pt[0]), int(pt[1])) for pt in raw]  # (tick, MIDI×100)，-100 = 无音高
        out["tracks"].append({"index": ti, "notes": notes, "pitch_points": pts})
        print(f"track {ti}: {len(notes)} notes, {len(pts)} pitch points, pron set on {sum(1 for n in notes if n['pron'])} notes")
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
