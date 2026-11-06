"""音量对齐的 A/B 与盲听包（ITU-R BS.1770 积分响度，pyloudnorm）。从《妄想感傷代償連盟》的 make_ab.py 通用化而来。

用法：python -I make_ab.py <ref_dir> <out_dir> <key.json> <label>=<dry.wav> <label>=<dry.wav> [...]
- ref_dir 里是 make_reference.py 截好的片段（都从片段起点开始、与 ACE 导出等长）：ref_vocal_clip_48k.wav（参考人声，单声道）必须有；
  inst_clip_48k.wav（伴奏）+ ref_vocal_mix_clip_48k.wav（原曲里人声的实际电平：官方人声或原样分离的人声）都在时做带伴奏试听；
  official_clip_48k.wav（原曲）在时一起出“带伴奏_原曲”。
- 版本按给出的顺序：第一个是基线（如 r0基线），最后一个是调教版（如 r2调教版），中间是各轮（如 r1时值），相邻两个就是一轮的 A/B。
- 干声：各版本与参考人声统一到 -20 LUFS；若峰值超过 -1 dBFS，整组一起降低。写 <out_dir>/ab_音量对齐/<序号>_<label>_干声.wav。
- 带伴奏（只做标明版本的试听，不做盲听）：伴奏原样；第一个和最后一个版本（单声道放进左右两声道）对齐到原曲人声的响度，再与伴奏相加；
  若混音峰值超过 -1 dBFS，所有带伴奏文件乘同一增益。合成干声没有混音处理，放进伴奏里仍可能被盖住（《反乌托邦》的诊断）。
- 盲听：第一个与最后一个版本随机分配甲 / 乙，写 <out_dir>/blind_test_盲听/盲听_干声_甲.wav、乙.wav；
  答案只写进 key.json（放在 work/ 里，用户判断前不读），不打印盲听文件的任何电平。
- 输出目录已有文件、或 key.json 已存在时停止，不覆盖。
"""
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401

import numpy as np  # noqa: E402
import pyloudnorm as pyln  # noqa: E402
import soundfile as sf  # noqa: E402

TARGET_LUFS = -20.0
PEAK_CEIL = 10 ** (-1.0 / 20)


def read(path, n=None, stereo=False):
    x, sr = sf.read(path, always_2d=True, dtype="float64")
    x = x if stereo else x.mean(axis=1)
    if n is not None:
        pad = [(0, max(0, n - len(x)))] + ([(0, 0)] if x.ndim == 2 else [])
        x = np.pad(x, pad)[:n]
    return x, sr


def main():
    refd, out, key_p = sys.argv[1:4]
    versions = [tuple(a.split("=", 1)) for a in sys.argv[4:]]
    if len(versions) < 2:
        raise SystemExit("至少要两个版本：第一个是基线，最后一个是调教版")
    if os.path.exists(key_p):
        raise SystemExit(f"答案文件已存在，换个名字或先确认：{key_p}")
    ref, sr = read(os.path.join(refd, "ref_vocal_clip_48k.wav"))
    n = len(ref)
    has = lambda name: os.path.exists(os.path.join(refd, name))
    meter = pyln.Meter(sr)
    loud = meter.integrated_loudness
    dup = lambda v: np.repeat(v[:, None], 2, axis=1)
    dry = {k: read(v, n)[0] for k, v in versions}
    dry["参考人声"] = ref
    raw = {k: loud(x) for k, x in dry.items()}
    gains = {k: 10 ** ((TARGET_LUFS - raw[k]) / 20) for k in dry}
    common_g = min(1.0, PEAK_CEIL / max(np.max(np.abs(dry[k])) * gains[k] for k in dry))
    matched = {k: dry[k] * gains[k] * common_g for k in dry}
    ab, blind = os.path.join(out, "ab_音量对齐"), os.path.join(out, "blind_test_盲听")
    for d in (ab, blind):
        if os.path.isdir(d) and os.listdir(d):
            raise SystemExit(f"目录非空，换个目录或先确认：{d}")
        os.makedirs(d, exist_ok=True)
    report = {"target_lufs_dry": round(TARGET_LUFS + 20 * np.log10(common_g), 2), "raw_lufs": {k: round(v, 2) for k, v in raw.items()},
              "order": [k for k, _ in versions], "files": {}}

    def write(path, x):
        sf.write(path, x, sr, subtype="PCM_24")
        report["files"][os.path.relpath(path, out)] = {"lufs": round(loud(x), 2),
                                                        "peak_dbfs": round(float(20 * np.log10(np.max(np.abs(x)) + 1e-12)), 2)}

    for i, (k, _) in enumerate(versions):
        write(os.path.join(ab, f"{i}_{k}_干声.wav"), matched[k])
    write(os.path.join(ab, "参考_原唱人声_干声.wav"), matched["参考人声"])
    first, last = versions[0][0], versions[-1][0]
    if has("inst_clip_48k.wav") and has("ref_vocal_mix_clip_48k.wav"):
        inst, _ = read(os.path.join(refd, "inst_clip_48k.wav"), n, stereo=True)
        vocal_mix, _ = read(os.path.join(refd, "ref_vocal_mix_clip_48k.wav"), n, stereo=True)
        vocal_target = loud(vocal_mix)
        report.update(inst_lufs=round(loud(inst), 2), vocal_in_mix_lufs=round(vocal_target, 2),
                      vocal_minus_inst_db=round(vocal_target - loud(inst), 2),
                      check_inst_plus_vocal_stem_lufs=round(loud(inst + vocal_mix), 2))
        mixes = {k: inst + dup(dry[k]) * 10 ** ((vocal_target - loud(dup(dry[k]))) / 20) for k in (first, last)}
        if has("official_clip_48k.wav"):
            official, _ = read(os.path.join(refd, "official_clip_48k.wav"), n, stereo=True)
            report["check_official_clip_lufs"] = round(loud(official), 2)
            mixes["原曲"] = official
        mg = min(1.0, PEAK_CEIL / max(np.max(np.abs(m)) for m in mixes.values()))
        report["mix_common_gain_db"] = round(float(20 * np.log10(mg)), 2)
        for k, m in mixes.items():
            write(os.path.join(ab, f"带伴奏_{k}.wav"), m * mg)
    pair = [first, last]
    if secrets.randbelow(2):
        pair.reverse()
    key = {}
    for name, ver in zip(("甲", "乙"), pair):
        fn = f"盲听_干声_{name}.wav"
        sf.write(os.path.join(blind, fn), matched[ver], sr, subtype="PCM_24")
        key[fn] = {"version": ver}
    os.makedirs(os.path.dirname(os.path.abspath(key_p)), exist_ok=True)
    with open(key_p, "w", encoding="utf-8") as fh:
        json.dump(key, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(ab, "loudness_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False, indent=1))
    print("labeled files:", len(report["files"]), "| blind files written:", sorted(key))


if __name__ == "__main__":
    main()
