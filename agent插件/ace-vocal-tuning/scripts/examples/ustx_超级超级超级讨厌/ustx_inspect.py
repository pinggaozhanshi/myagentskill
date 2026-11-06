"""打印 USTX 结构：速度、拍号、轨道、声部、音符范围。用法：python -I ustx_inspect.py <ustx>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vp_common import load_ustx, tempo_map, tick_to_sec  # noqa: E402

p = load_ustx(sys.argv[1])
res = int(p.get("resolution", 480))
tmap = tempo_map(p)
print("top-level keys:", list(p.keys()))
print("name:", p.get("name"), "| ustx_version:", p.get("ustx_version"), "| resolution:", res)
print("tempos:", tmap[:10], "... total", len(tmap))
print("time_signatures:", p.get("time_signatures"))
print("expressions:", list((p.get("expressions") or {}).keys()))
for i, t in enumerate(p.get("tracks", [])):
    print(f"track[{i}]:", {k: t.get(k) for k in ("singer", "phonemizer", "renderer_settings", "track_name", "mute", "solo", "volume", "pan")})
for i, vp in enumerate(p.get("voice_parts", [])):
    notes = vp.get("notes", [])
    pos0 = int(vp.get("position", 0))
    if notes:
        first = min(notes, key=lambda n: n["position"])
        last = max(notes, key=lambda n: n["position"] + n["duration"])
        t0 = tick_to_sec(pos0 + first["position"], tmap, res)
        t1 = tick_to_sec(pos0 + last["position"] + last["duration"], tmap, res)
        tones = [n["tone"] for n in notes]
        rng = f"tone {min(tones)}..{max(tones)}"
    else:
        t0 = t1 = float("nan")
        rng = "-"
    print(f"voice_part[{i}] name={vp.get('name')!r} track={vp.get('track_no')} pos={pos0} dur={vp.get('duration')} notes={len(notes)} {t0:7.2f}s..{t1:7.2f}s {rng} curves={[c.get('abbr') for c in vp.get('curves', [])]}")
for i, wp in enumerate(p.get("wave_parts", [])):
    print(f"wave_part[{i}]:", {k: wp.get(k) for k in ("name", "track_no", "position", "relative_path", "skip_ms", "trim_ms")})
if p.get("voice_parts"):
    n = p["voice_parts"][0]["notes"][0]
    print("sample note keys:", list(n.keys()))
    print("sample note:", {k: n[k] for k in n if k not in ("pitch", "vibrato", "phoneme_expressions", "phoneme_overrides")})
    print("sample pitch:", n.get("pitch"))
    print("sample vibrato:", n.get("vibrato"))
