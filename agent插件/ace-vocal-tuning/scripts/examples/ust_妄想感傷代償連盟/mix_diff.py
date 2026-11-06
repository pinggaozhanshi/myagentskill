"""两版成品逐段比较（信号指标，不是听感）：每段先求让 B 最贴近 A 的单一增益，再算剩下的差信号能量（相对 A，dB）。
只差一个总增益时差信号会很低；内容真变了的段会高。

用法：python -I mix_diff.py <score_full.json> <mix_a.wav> <mix_b.wav> <out.json>
分段同 mix_check.py：副歌前一句、副歌、副歌后段。两版的起点可以不同（v3 剪掉了前奏），各自从同目录的 mix_report.json 取。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402,F401
from mix_chorus import SR, bar_time  # noqa: E402

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402


def main():
    score_p, a_p, b_p, out = sys.argv[1:5]
    def start(p):
        """成品第一个采样在原曲里的位置（秒）。window_sec 只留到毫秒，起点不同的两版要按采样对齐。"""
        rep = json.load(open(os.path.join(os.path.dirname(p), "mix_report.json"), encoding="utf-8"))
        if "window_start_sample" in rep:
            return rep["window_start_sample"] / SR
        if rep.get("cut_to_vocal"):
            raise SystemExit(f"{p} 的报告没有 window_start_sample，起点对不准")
        return int(round(bar_time(rep["bars"][0]) * SR)) / SR  # 旧版按小节起点

    Sa, Sb = start(a_p), start(b_p)
    a, sr = sf.read(a_p, always_2d=True)
    b, _ = sf.read(b_p, always_2d=True)
    notes = json.load(open(score_p, encoding="utf-8"))["tracks"][0]["notes"]
    secs = {"副歌前一句": (notes[0]["start"], notes[19]["start"]),
            "副歌": (notes[20]["start"], notes[101]["end"]), "副歌后段": (notes[102]["start"], notes[-1]["end"])}
    res = {}
    for k, (s, e) in secs.items():
        m = int((e - s) * sr)
        ia, ib = int(round((s - Sa) * sr)), int(round((s - Sb) * sr))
        x, y = a[ia:ia + m], b[ib:ib + m]
        g = float(np.sum(x * y) / np.sum(y * y))
        r = x - g * y
        res[k] = {"gain_b_to_a_db": round(20 * np.log10(g), 3),
                  "residual_db_re_a": round(float(10 * np.log10(np.sum(r ** 2) / np.sum(x ** 2) + 1e-30)), 1)}
        print(f"{k}: B 乘 {res[k]['gain_b_to_a_db']:+.3f} dB 后，剩下的差 {res[k]['residual_db_re_a']:.1f} dB（相对 A）")
    json.dump({"a": os.path.abspath(a_p), "b": os.path.abspath(b_p), "sections": res}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
