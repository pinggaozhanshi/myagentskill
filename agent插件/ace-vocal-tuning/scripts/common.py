"""调教项目的公共函数与项目设置。脚本放在项目的 scripts/ 下，素材路径一律通过参数传入。

项目设置读 scripts/ 上一级目录的 project.json（从工作流 templates/project.json 复制后改）。
时间轴：单一速度，tick 按 project.json 的 bpm、tpq 换算（1 s = tpq × bpm / 60 tick）；参考音轨放在 ACE 的 0 s。
"""
import json
import os
import site
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "project.json")
if not os.path.exists(CONFIG_PATH):
    raise SystemExit(f"缺项目设置 {CONFIG_PATH}：从工作流的 templates/project.json 复制一份再改")
CONFIG = json.load(open(CONFIG_PATH, encoding="utf-8"))

# -I 模式不加载用户 site-packages；scipy / soundfile / parselmouth / pyloudnorm 装在这里。
USER_SITE = CONFIG.get("user_site") or site.getusersitepackages()
if USER_SITE not in sys.path:
    sys.path.append(USER_SITE)
# 控制台默认 GBK；-I 会忽略 PYTHONIOENCODING，这里直接改成 UTF-8。
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BPM = float(CONFIG["bpm"])
TPQ = int(CONFIG.get("tpq", 480))
TICKS_PER_SEC = TPQ * BPM / 60.0
LANGUAGE = CONFIG.get("language", "Chinese")  # ACE 轨道语言：Chinese / Japanese / English …
SINGER = CONFIG.get("singer", "singer:18")  # 洛天依（Verse23 / V1）

# 首辅音是这些的音才测时值（ACE G2P 的音素名）。中文的 b d g 是不送气清塞音，也算清声母。
VOICELESS = {"Japanese": ["k", "ky", "kw", "s", "sh", "t", "ch", "ts", "h", "hy", "f", "p", "py"],
             "Chinese": ["b", "p", "f", "d", "t", "g", "k", "h", "j", "q", "x", "zh", "ch", "sh", "z", "c", "s"]}
VOICELESS_INIT = set(CONFIG.get("voiceless_initials") or VOICELESS.get(LANGUAGE, []))
# 齿音检查用的清擦音 / 塞擦音开头。
FRICATIVES = {"Japanese": ["s", "sh", "ch", "ts", "f", "h", "hy"],
              "Chinese": ["s", "sh", "x", "c", "ch", "q", "z", "zh", "j", "f", "h"]}
FRICATIVE_INIT = set(CONFIG.get("fricative_initials") or FRICATIVES.get(LANGUAGE, []))
# 音节结尾轮规则 E：浊塞音 / 塞擦音只在前一个音被吃掉元音尾巴时才缩短。中文的 b d g 已算清声母，没有这一类。
VOICED_STOPS = {"Japanese": ["g", "gy", "d", "b", "by", "z", "j"], "Chinese": []}
VOICED_STOP_INIT = set(CONFIG.get("voiced_stop_initials") or VOICED_STOPS.get(LANGUAGE, []))


def t2s(tick):
    return tick / TICKS_PER_SEC


def s2t(sec):
    return int(round(sec * TICKS_PER_SEC))


def clip_pos(note, clip_start_tick):
    """音符在片段内的 tick。谱面记工程 tick（"tick"）；同时写了 "pos" 的谱面，两者必须一致。"""
    pos = note["tick"] - clip_start_tick
    if "pos" in note and note["pos"] != pos:
        raise SystemExit(f"谱面音符 #{note.get('idx')} 的 pos {note['pos']} 与 tick − 片段起点 {pos} 不一致")
    return pos


def head_consonants(notes, g2p_path):
    """G2P 结果 → {音符序号: 首辅音}。g2p_check 不送延长音「-」，音节按顺序对回非延长音的音符；
    旧的 G2P 文件（每个音都送了）音节数等于音符数，按序号直接对应。"""
    syl = json.load(open(g2p_path, encoding="utf-8"))["syllables"]
    sung = [k for k, n in enumerate(notes) if n["lyric"] != "-"]
    if len(syl) == len(notes):
        idx = list(range(len(notes)))
    elif len(syl) == len(sung):
        idx = sung
    else:
        raise SystemExit(f"G2P 音节数 {len(syl)} 与音符数 {len(notes)}（非延长音 {len(sung)}）都对不上")
    return {idx[s["index"]]: (s["headConsonants"] or [""])[0] for s in syl}


PRAAT_SILENCE = 0.005  # Praat 默认 0.03 相对整段最大振幅；轻的乐句会被误判为静音（见 vocal_pilot 的 v1→v2 返工）


def praat_grid(x, sr, hop, floor=100.0, ceiling=1300.0, voicing=0.45):
    """Praat 自相关 F0 → 以 hop 为步长、t=0 为起点的 Hz 网格（NaN=无声）。所有 Praat 调用统一走这里。"""
    import numpy as np
    import parselmouth
    p = parselmouth.Sound(np.asarray(x, dtype=np.float64), sampling_frequency=sr).to_pitch_ac(
        time_step=hop, pitch_floor=floor, pitch_ceiling=ceiling, voicing_threshold=voicing,
        silence_threshold=PRAAT_SILENCE)
    # Praat 帧时刻落在网格半步上，不能 round 到网格（会撞格留下空洞）；按时间插值到 k*hop：
    # 两侧都有声 → 对数频率线性插值；只有一侧有声且相距 ≤ hop/2 → 取该侧；否则无声。
    t = np.asarray(p.xs())
    f = np.asarray(p.selected_array["frequency"], dtype=float)
    n = int(np.ceil(len(x) / sr / hop)) + 1
    tk = np.arange(n) * hop
    j = np.clip(np.searchsorted(t, tk) - 1, 0, len(t) - 2)
    t0, t1, f0, f1 = t[j], t[j + 1], f[j], f[j + 1]
    w = np.clip((tk - t0) / (t1 - t0), 0.0, 1.0)
    g = np.full(n, np.nan)
    both = (f0 > 0) & (f1 > 0)
    g[both] = np.exp((1 - w[both]) * np.log(f0[both]) + w[both] * np.log(f1[both]))
    near0 = ~both & (f0 > 0) & (np.abs(tk - t0) <= hop / 2 + 1e-9)
    near1 = ~both & (f1 > 0) & (np.abs(t1 - tk) <= hop / 2 + 1e-9)
    g[near0] = f0[near0]
    g[near1] = f1[near1]
    g[(tk < t[0] - hop) | (tk > t[-1] + hop)] = np.nan
    return g
