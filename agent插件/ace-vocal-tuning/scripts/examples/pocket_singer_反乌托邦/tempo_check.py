"""核对速度与拍点相位：伴奏的节拍跟踪 vs 120 BPM、从 0 s 起的网格。

用法（研究 venv，需要 librosa）：python -I tempo_check.py <instrumental.wav>
输出：librosa 估的 BPM；拍点相对 0.5 s 网格的偏移（中位数、四分位）；前后半段分别算，看有没有漂移。
"""
import sys

import librosa
import numpy as np


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    y, sr = librosa.load(sys.argv[1], sr=22050, mono=True)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=256, start_bpm=120, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    period = 60.0 / 120.0
    ph = (beats + period / 2) % period - period / 2  # 相对最近网格点的偏移，-0.25..0.25 s
    half = len(beats) // 2
    q = lambda a: [round(float(np.percentile(a, p)) * 1000, 1) for p in (25, 50, 75)]
    print(f"librosa tempo: {tempo:.2f} BPM | beats: {len(beats)} ({beats[0]:.2f}..{beats[-1]:.2f} s)")
    print(f"beat offset vs 120 BPM grid from 0 s (ms, p25/p50/p75): all {q(ph)} | first half {q(ph[:half])} | second half {q(ph[half:])}")
    ibi = np.diff(beats)
    print(f"inter-beat interval median {np.median(ibi) * 1000:.1f} ms -> {60 / np.median(ibi):.2f} BPM")


if __name__ == "__main__":
    main()
