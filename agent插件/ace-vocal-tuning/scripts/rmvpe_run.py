"""在没有 torchaudio 的 Python313 里跑研究目录的 rmvpe_local_extract.py（RMVPE 音高，10 ms 一帧）。

那个脚本只用 E2E0 模型、MelSpectrogram 和 librosa 重采样；torchaudio 只是被 SOFA 的 modules/rmvpe/__init__.py
顺带导入（inference.py 的 Resample，本流程不调用）。这里先放一个只占名字的替身，一被调用就报错，计算路径和权重都不变。
用法（不加 -I，要用户 site 里的 torch、librosa）：python -X utf8 rmvpe_run.py <audio.wav> <out.json>
之后用 f0_grid.py --rmvpe <out.json> <时长秒> <out.npy> 换成 5 ms 网格。提取脚本的位置：project.json 的 rmvpe_extract。
（来自《绯红》：研究目录的 .venv 没有 torch，Python313 有 torch 没有 torchaudio。）
"""
import os
import runpy
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

EXTRACT = common.CONFIG.get("rmvpe_extract") or r"C:\Users\lenovo\Documents\自媒体\调教Agent研究\rmvpe_local_extract.py"


class Resample:
    def __init__(self, *a, **k):
        raise RuntimeError("torchaudio 替身：Resample 不应被调用")


def main():
    ta = types.ModuleType("torchaudio")
    tr = types.ModuleType("torchaudio.transforms")
    tr.Resample = Resample
    ta.transforms = tr
    sys.modules["torchaudio"] = ta
    sys.modules["torchaudio.transforms"] = tr
    sys.argv = [EXTRACT, sys.argv[1], sys.argv[2], "--offset", "0"]
    runpy.run_path(EXTRACT, run_name="__main__")


if __name__ == "__main__":
    main()
