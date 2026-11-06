"""读 Pocket Singer 工程（.ps_project）并打印结构摘要；可选导出内嵌伴奏、转成 ACE 工程（.acep）。

用法（研究 venv，需要 libresvip；pyzipper 装在本项目 work/pylib，运行时临时加载）：
python -I inspect_ps_project.py <in.ps_project> [--bgm-out <dir>] [--acep-out <file.acep>]
只打印数字和元数据（压缩包条目、config.json、轨道、歌手、音符数、音域、速度、参数曲线点数），不打印歌词。
.ps_project 是 WinZip AES 加密的 zip，用 LibreSVIP ps_project 插件自带的口令读取（与插件读取方式相同）。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "work" / "pylib"))

from libresvip.extension.manager import get_svs_plugin_by_suffix, plugin_manager  # noqa: E402
from libresvip.plugins.ps_project.pocket_singer_converter import POCKET_SIGER_PASSWORD  # noqa: E402
from pyzipper import AESZipFile  # noqa: E402


def plugin(suffix):
    return plugin_manager.plugins.get("svs", {}).get(suffix) or get_svs_plugin_by_suffix(suffix)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--bgm-out")
    ap.add_argument("--acep-out")
    a = ap.parse_args()
    src = Path(a.src)
    with AESZipFile(src) as zf:
        zf.setpassword(POCKET_SIGER_PASSWORD)
        for info in zf.infolist():
            print(f"zip entry: {info.filename} | {info.file_size:,} bytes")
        config = json.loads(zf.read("config.json"))
        print("config.json:", json.dumps(config, ensure_ascii=False))
        if a.bgm_out:
            info = config.get("bgmInfo") or {}
            bgm = info.get("fileName")
            if bgm and bgm not in zf.namelist() and info.get("fileType"):
                bgm = f"{bgm}.{info['fileType']}"
            if bgm:
                out = Path(a.bgm_out)
                out.mkdir(parents=True, exist_ok=True)
                (out / bgm).write_bytes(zf.read(bgm))
                print("bgm extracted:", out / bgm)
    inp = plugin("ps_project")
    if inp is None:
        sys.exit("ps_project plugin not loaded (pyzipper missing?)")
    proj = inp.load(src, inp.input_option_cls())
    print("tempos:", [(t.position, round(t.bpm, 3)) for t in proj.song_tempo_list][:10], "| count", len(proj.song_tempo_list))
    print("time signatures:", [(ts.bar_index, ts.numerator, ts.denominator) for ts in proj.time_signature_list])
    for i, tr in enumerate(proj.track_list):
        line = f"track[{i}] {type(tr).__name__} title={getattr(tr, 'title', '')!r} mute={getattr(tr, 'mute', None)}"
        notes = getattr(tr, "note_list", None)
        if notes is not None:
            line += f" singer={getattr(tr, 'ai_singer_name', '')!r} notes={len(notes)}"
            if notes:
                keys = [n.key_number for n in notes]
                line += f" ticks {notes[0].start_pos}..{notes[-1].start_pos + notes[-1].length} keys {min(keys)}..{max(keys)}"
            ep = getattr(tr, "edited_params", None)
            if ep is not None:
                pts = {name: len(getattr(getattr(ep, name, None), "points", None) or [])
                       for name in ("pitch", "volume", "breath", "gender", "strength")}
                line += f" param_points {pts}"
        else:
            line += f" audio={getattr(tr, 'audio_file_path', '')!r} offset={getattr(tr, 'offset', None)}"
        print(line)
    if a.acep_out:
        out = plugin("acep")
        Path(a.acep_out).parent.mkdir(parents=True, exist_ok=True)
        out.dump(Path(a.acep_out), proj, out.output_option_cls())
        back = out.load(Path(a.acep_out), out.input_option_cls())
        counts = [len(getattr(t, "note_list", []) or []) for t in back.track_list]
        print("written:", a.acep_out, "| read back note counts per track:", counts,
              "| tempo", [round(t.bpm, 3) for t in back.song_tempo_list][:3])


if __name__ == "__main__":
    main()
