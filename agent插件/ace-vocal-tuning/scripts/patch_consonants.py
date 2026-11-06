"""离线改 ACE 工程里个别音符的辅音长度（headConsonants，秒）。研究目录 .venv（LibreSVIP 2.9.0）运行：

python -I patch_consonants.py <src.acep> <dst.acep> <track_uuid> <clip_uuid> <changes.json> <report.json>
changes.json：{"<noteUuid>": 新长度秒, ...}。
用途：前一个音只有元音时，ACE 的 phoneme set-consonant-timing 不对后一个音开放（timingKinds 为空，报 PHONEME_TIMINGS_UNAVAILABLE），
但长度就存在音符的 headConsonants 里（note-content 能读到）。只改这些音符的这一个字段；写完重新解包，
其余字段与源工程逐字段相同才算成功。ACE 必须没有打开这个工程。
"""
import copy
import json
import pathlib
import sys

from libresvip.plugins.acep.acep_io import compress_ace_studio_project, decompress_ace_studio_project
from libresvip.plugins.acep.options import AcepSerialization


def main():
    src, dst, track_uuid, clip_uuid, ch_p, rep_p = sys.argv[1:7]
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    if dst.exists():
        raise SystemExit(f"目标已存在：{dst}")
    changes = json.load(open(ch_p, encoding="utf-8"))
    raw = decompress_ace_studio_project(src)
    changed = copy.deepcopy(raw)
    pat = next(p for t in changed["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    rep = {"notes": []}
    for n in pat["notes"]:
        if n.get("uuid") in changes:
            assert len(n.get("headConsonants") or []) == 1, f"{n['uuid']} 的 headConsonants 不是单个值"
            old = n["headConsonants"][0]
            n["headConsonants"] = [float(changes[n["uuid"]])]
            rep["notes"].append({"uuid": n["uuid"], "pos": n["pos"], "old_sec": old, "new_sec": n["headConsonants"][0]})
    assert len(rep["notes"]) == len(changes), "有音符没找到"
    compress_ace_studio_project(changed, dst, AcepSerialization.CBOR)
    check = decompress_ace_studio_project(dst)
    cp = next(p for t in check["tracks"] if t.get("uuid") == track_uuid for p in t["patterns"] if p.get("uuid") == clip_uuid)
    got = {n["uuid"]: n["headConsonants"] for n in cp["notes"] if n.get("uuid") in changes}
    rep["roundtrip_values"] = {u: v for u, v in got.items()}
    rep["roundtrip_equal"] = all(abs(got[u][0] - float(changes[u])) < 1e-9 for u in changes)
    for n in cp["notes"]:
        if n.get("uuid") in changes:
            n["headConsonants"] = next(x["headConsonants"] for p in [next(p for t in raw["tracks"] if t.get("uuid") == track_uuid
                                                                          for p in t["patterns"] if p.get("uuid") == clip_uuid)]
                                       for x in p["notes"] if x["uuid"] == n["uuid"])
    rep["other_fields_identical"] = check == raw
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    json.dump(rep, open(rep_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not (rep["roundtrip_equal"] and rep["other_fields_identical"]):
        dst.unlink()
        raise SystemExit("回读校验失败，已删除输出")


if __name__ == "__main__":
    main()
