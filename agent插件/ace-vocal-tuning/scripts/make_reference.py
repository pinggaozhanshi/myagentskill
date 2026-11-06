"""把整首参考人声（去混响分离）与分离伴奏截成试验片段（与 ACE 导出同起点、同长度），供时值与音高度量、A/B 使用。

用法：python -I make_reference.py <pilot_score.json> <ref_vocal_full.wav> <inst_full.wav> <syn_export.wav> <out_dir> [<src.wav>=<name.wav> ...]
起点 = 片段起点（clip_start_tick 换成秒，按 48 kHz 取整到样本）；长度 = ACE 导出的样本数。
输出：ref_vocal_clip_48k.wav（单声道）、inst_clip_48k.wav（立体声），都是 24-bit；后面可再列要同样截取的文件
（A/B 用：原样分离的人声 = 原曲里人声的实际电平，官方音轨 = 核对用）。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import soundfile as sf  # noqa: E402


def main():
    score_p, ref_p, inst_p, syn_p, out = sys.argv[1:6]
    meta = json.load(open(score_p, encoding="utf-8"))["meta"]
    n = sf.info(syn_p).frames
    os.makedirs(out, exist_ok=True)
    extra = [tuple(a.split("=", 1)) for a in sys.argv[6:]]
    for src, name in [(ref_p, "ref_vocal_clip_48k.wav"), (inst_p, "inst_clip_48k.wav")] + extra:
        if os.path.exists(os.path.join(out, name)) and name in ("ref_vocal_clip_48k.wav", "inst_clip_48k.wav") and extra:
            continue  # 只补截新加的文件
        info = sf.info(src)
        assert info.samplerate == 48000, src
        a = int(round(common.t2s(meta["clip_start_tick"]) * info.samplerate))
        x, sr = sf.read(src, start=a, frames=n, always_2d=True)
        assert len(x) == n, f"{src} 不够长"
        dst = os.path.join(out, name)
        sf.write(dst, x if x.shape[1] > 1 else x[:, 0], sr, subtype="PCM_24")
        print(dst, f"start {a / sr:.4f}s ({a} samples), {n / sr:.3f}s, ch {x.shape[1]}")


if __name__ == "__main__":
    main()
