"""第四次试验《绯红》（ACE 2.1.9 / acestudio-cli 0.18.7）的回归验证：《绯红》项目里的原版脚本和本工作流的通用版各跑一遍，逐项比对。

用法：python run_regression_feihong.py <out_dir> [--only name1,name2]
- 纯信号脚本：两版输出必须完全一致；另记原版这次的输出与《绯红》当时的存档是否一致（看可复现性）。
- 混音：原版 mix_1min.py 与通用版 mix_vocals.py（--cut-to-vocal --end-at --inst-db −4 --end-fade-ms 35）的混音、干声、人声总线逐字节比，
  并和交付的 v2 成品比。
- RMVPE：两版 rmvpe_run.py 在 r3 干声上各跑一次（真的模型，不加 -I），输出与存档比。
- patch_consonants.py（与原版逐字节相同）：在《绯红》留下的 r3 补丁前工程上重跑，输出工程与存档逐字节比。
- 要连 ACE 的脚本：两版都接 fake_ace_cli.py（0.18 的 vocalpitch、vocal-to-midi 等按《绯红》实测行为模拟），比对命令序列和写出的文件。
结果写进 <out_dir>/regression_results.json；任何一项不一致时退出码为 1。只读《绯红》的数据，不写回那个项目。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_regression as rr  # noqa: E402

PY, PKG, FAKE = rr.PY, rr.PKG, rr.FAKE
VENV_PY = r"C:\Users\lenovo\Documents\自媒体\调教Agent研究\.venv\Scripts\python.exe"
D = Path(r"D:\自媒体\绯红_洛天依翻唱_20261024")
W, E = D / "work", D / "exports"
S, G = W / "score_v1.json", W / "g2p_japanese.json"
REF = W / "ref" / "ref_vocal_clip_48k.wav"
PRF, RMF = W / "f0" / "ref_dereverb_praat_5ms.npy", W / "f0" / "ref_dereverb_rmvpe_5ms.npy"
INST, VSTEM, REFV = W / "stems" / "basic_instrumental.wav", W / "stems" / "basic_vocal.wav", W / "stems" / "basic_dereverb_vocal.wav"
V2 = E / "成品_1分钟_v2"
NAME = "绯红_ルルージュ_1分钟_洛天依"

PROJECT = {
    "title": "绯红 一分钟版（回归验证用）",
    "bpm": 102.0, "tpq": 480, "language": "Japanese",
    "singer": "singer:18", "track_name": "洛天依_主唱",
    "inst_track_name": "INST_分离伴奏", "ref_track_name": "REF_参考人声(静音)",
    "downbeat_tick": 786, "mix_name": NAME + "_混音",
    "ace_cli": [PY, str(FAKE)],
}

# 与《绯红》原版逐字节相同的脚本（后四个是《绯红》新写的，其余三次试验以来没变、在 0.18.7 上真跑过）
VERBATIM = ["vowel_coverage.py", "voicing_check.py", "patch_consonants.py", "vocal_sections.py",
            "ace_export.py", "ace_render.py", "compare_timing.py", "f0_grid.py", "glitch_check.py", "make_reference.py",
            "pitch_eval.py", "splice_main.py", "state_with_project.py", "stems_collect.py"]


def wav(k):
    return E / k / f"{k}_洛天依_主唱_洛天依_主唱.wav"


def f0(k, kind):
    return W / "f0" / f"{k}_{kind}_5ms.npy"


def next_section_onset(after_sec=78.0, min_run=0.05, hop=0.005):
    """与 mix_1min.py 同一算法：参考人声 78 s 之后第一段 ≥ 50 ms 的有声。"""
    v = ~np.isnan(np.load(PRF))
    k, need = int(after_sec / hop), int(min_run / hop)
    while k < len(v) - need:
        if v[k:k + need].all():
            return k * hop
        k += 1
    raise SystemExit("找不到下一段人声")


def signal_cases():
    vs = json.load(open(W / "vocal_sections.json", encoding="utf-8"))
    end_at = next_section_onset() - 0.070
    cov = [f"{k}={wav(d)},{f0(d, 'praat')},{f0(d, 'rmvpe')}" for k, d in (("r2", "r2_pitch"), ("r3", "r3_endings"))]
    return [
        *[dict(name=f"timing_voicing_{k}", script="timing_voicing.py", args=[S, G, REF, wav(d), f"{{OUT}}/timing_{k}.json"],
               outputs=[f"timing_{k}.json"], stored={f"timing_{k}.json": W / f"timing_{k}.json"})
          for k, d in (("r0", "r0_baseline"), ("r1", "r1_timing"), ("r2", "r2_pitch"), ("r3", "r3_endings"))],
        dict(name="compare_timing", args=[W / "timing_r0.json", W / "timing_r1.json", W / "round1_plan.json", "{OUT}/cmp.json"],
             outputs=["cmp.json"], stored={"cmp.json": W / "compare_r0_r1.json"}),
        dict(name="build_target_f0", args=[S, PRF, RMF, "{OUT}/target_f0.json"], outputs=["target_f0.json", "target_f0_hz.npy"],
             stored={"target_f0.json": W / "target_f0.json"}),
        dict(name="pitch_eval", args=[W / "target_f0.json", S, "{OUT}/pe.json",
                                      *[f"{k}={f0(d, 'praat')}" for k, d in (("r0", "r0_baseline"), ("r2", "r2_pitch"), ("r3", "r3_endings"))]],
             outputs=["pe.json"], stored={"pe.json": W / "pitch_eval_r3_praat.json"}),
        dict(name="ending_check_r2", script="ending_check.py",
             args=[S, G, W / "target_f0.json", REF, wav("r2_pitch"), PRF, f0("r2_pitch", "praat"), f0("r2_pitch", "rmvpe"), "{OUT}/ending.json"],
             outputs=["ending.json"], stored={"ending.json": W / "ending_r2.json"}),
        dict(name="ending_check_r3", script="ending_check.py",
             args=[S, G, W / "target_f0.json", REF, wav("r3_endings"), PRF, f0("r3_endings", "praat"), f0("r3_endings", "rmvpe"),
                   "{OUT}/ending.json", "--curve", W / "round3_plan.json"],
             outputs=["ending.json"], stored={"ending.json": W / "ending_r3.json"}),
        dict(name="voicing_check", args=[S, W / "r2_voicing.json", REF, PRF, "{OUT}/voicing_plan.json"], outputs=["voicing_plan.json"],
             stored={"voicing_plan.json": W / "voicing_plan_r3.json"}),
        dict(name="endings_plan", script="round3_plan.py", new_script="endings_plan.py",
             args=[S, W / "r3_phonemes.json", W / "target_f0.json", REF, PRF, W / "voicing_plan_r3.json", W / "round1_plan.json",
                   "{OUT}/plan.json"], outputs=["plan.json"], stored={"plan.json": W / "round3_plan.json"}),
        dict(name="vowel_coverage", args=[S, REF, PRF, *cov], outputs=[], stdout=True),
        dict(name="vocal_sections", args=[REFV, repr(vs["first_downbeat_sec"]), "{OUT}/sections.json"], outputs=["sections.json"],
             stored={"sections.json": W / "vocal_sections.json"}),
        dict(name="mix", script="mix_1min.py", new_script="mix_vocals.py",
             args=[S, wav("r3_endings"), INST, VSTEM, PRF, "{OUT}", NAME, "--inst-db", "-4", "--end-fade-ms", "35", "--suffix", "_v2"],
             new_args=[S, wav("r3_endings"), "-", INST, VSTEM, "{OUT}", "--cut-to-vocal", "--end-at", repr(end_at), "--inst-db", "-4",
                       "--end-fade-ms", "35", "--suffix", "_v2", "--official", W / "audio" / "official_full_48k.wav"],
             outputs=[(f"{NAME}_混音_v2.wav", f"{NAME}_混音_v2.wav"), (f"{NAME}_干声_v2.wav", f"{NAME}_干声_v2.wav"),
                      ("人声总线_主唱混响延迟_v2.wav", "人声总线_v2.wav")],
             report=("mix_report_v2.json", "mix_report_v2.json"),
             stored={f"{NAME}_混音_v2.wav": V2 / f"{NAME}_混音_v2.wav", f"{NAME}_干声_v2.wav": V2 / f"{NAME}_干声_v2.wav",
                     "人声总线_主唱混响延迟_v2.wav": V2 / "人声总线_主唱混响延迟_v2.wav", "mix_report_v2.json": V2 / "mix_report_v2.json"}),
    ]


def run_signal(case, orig_dir, new_dir, out):
    res = rr.run_signal(case, orig_dir, new_dir, out)
    if res.get("ok") and "report" in case:  # 两版报告的共同字段要相同
        a, b = case["report"]
        ja = json.load(open(out / "orig" / case["name"] / a, encoding="utf-8"))
        jb = json.load(open(out / "new" / case["name"] / b, encoding="utf-8"))
        keys = sorted(set(ja) & set(jb))
        diff = [k for k in keys if ja[k] != jb[k]]
        res["checks"].append({"output": f"混音报告共同字段（{len(keys)} 个）", "same": not diff, "why": f"不同：{diff}" if diff else ""})
        res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_mix_check(orig_dir, new_dir, out):
    """原版 mix_check.py 把结果写在混音文件旁边，所以先把 v2 成品拷进各自的输出目录再跑。"""
    name = "mix_check"
    res = {"case": name, "checks": []}
    paths = {}
    for side in ("orig", "new"):
        o = out / side / name / "in"
        o.mkdir(parents=True)
        for f in (f"{NAME}_混音_v2.wav", "人声总线_主唱混响延迟_v2.wav", "mix_report_v2.json"):
            shutil.copy2(V2 / f, o / f)
        paths[side] = o
    o, n = paths["orig"], paths["new"]
    rc1, so1, se1 = rr.run(orig_dir / "mix_check.py", [S, o / f"{NAME}_混音_v2.wav", o / "人声总线_主唱混响延迟_v2.wav", INST, VSTEM, RMF,
                                                        W / "mix" / "inst_window_rmvpe.json", o.parent / "png"])
    rc2, so2, se2 = rr.run(new_dir / "mix_check.py", [S, n / f"{NAME}_混音_v2.wav", n / "人声总线_主唱混响延迟_v2.wav", n / "mix_report_v2.json",
                                                       INST, VSTEM, RMF, W / "mix" / "inst_window_rmvpe.json", n.parent,
                                                       "--sections", "主歌=start-48.0,铺垫=48.0-55.0,副歌=55.0-end"])
    res.update(orig_rc=rc1, new_rc=rc2)
    if rc1 or rc2:
        res.update(ok=False, error=(se1 if rc1 else se2)[-1500:])
        return res
    ok, why = rr.same_file(o / "mix_check_v2.json", n.parent / f"{NAME}_混音_v2_检查.json", [o, n])
    res["checks"].append({"output": "mix_check_v2.json / 检查.json", "same": ok, "why": why})
    ok2, why2 = rr.same_file(o / "mix_check_v2.json", V2 / "mix_check_v2.json", [o])
    res["orig_matches_archive"] = {"mix_check_v2.json": ok2 if ok2 else why2}
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_rmvpe(orig_dir, new_dir, out):
    """真的 RMVPE（Python313、不加 -I）：两版各跑一次 r3 干声，比 JSON，并和《绯红》存档比。"""
    res = {"case": "rmvpe_run", "checks": []}
    outs = {}
    for side, sdir in (("orig", orig_dir), ("new", new_dir)):
        o = out / side / "rmvpe_run"
        o.mkdir(parents=True)
        p = subprocess.run([PY, "-X", "utf8", str(sdir / "rmvpe_run.py"), str(wav("r3_endings")), str(o / "r3_rmvpe.json")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode:
            res.update(ok=False, error=f"{side}: {p.stderr[-1500:]}")
            return res
        outs[side] = o / "r3_rmvpe.json"
    ok, why = rr.same_file(outs["orig"], outs["new"], [])
    res["checks"].append({"output": "r3_rmvpe.json", "same": ok, "why": why})
    ok2, why2 = rr.same_file(outs["orig"], W / "f0" / "r3_endings_rmvpe.json", [])
    res["orig_matches_archive"] = {"r3_endings_rmvpe.json": ok2 if ok2 else why2}
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_patch_consonants(new_dir, out):
    """通用版与原版逐字节相同，所以只跑通用版：在《绯红》留下的补丁前工程上重做，输出与存档比。"""
    o = out / "new" / "patch_consonants"
    o.mkdir(parents=True)
    st = json.load(open(W / "ace_state_r3.json", encoding="utf-8"))
    p = subprocess.run([VENV_PY, "-I", str(new_dir / "patch_consonants.py"), str(W / "r3.before_consonant_patch.acep"), str(o / "r3.patched.acep"),
                        st["vocal_track_uuid"], st["clip_uuid"], str(W / "round3_offline_consonants.json"), str(o / "report.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    res = {"case": "patch_consonants", "new_rc": p.returncode, "checks": []}
    if p.returncode:
        res.update(ok=False, error=p.stderr[-1500:])
        return res
    for a, b in (("r3.patched.acep", W / "r3.patched.acep"), ("report.json", W / "round3_offline_report.json")):
        ok, why = rr.same_file(o / a, b, [o])
        res["checks"].append({"output": f"{a} 与存档", "same": ok, "why": why})
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def g2p_table():
    return {s["grapheme"]: s["phonemes"] for s in json.load(open(G, encoding="utf-8"))["syllables"]}


def fake_state(**kw):
    st = {"tracks": [], "notes": {}, "clips": {}, "saved": "", "fx_off": [], "unknown": []}
    st.update(kw)
    return st


def score_notes(c0, uuids=None):
    notes = json.load(open(S, encoding="utf-8"))["notes"]
    return [{"pos": n["tick"] - c0, "dur": n["dur"], "pitch": n["pitch"], "lyric": n["lyric"],
             "noteUuid": (uuids or {}).get(n["tick"] - c0, f"N0_{k}")} for k, n in enumerate(notes)]


def prep_round1(o, side):
    st = json.load(open(W / "ace_state_r0.json", encoding="utf-8"))
    json.dump(fake_state(notes={"0": score_notes(st["clip_begin"])}, clips={st["clip_uuid"]: {"track": 0, "begin": st["clip_begin"]}},
                         saved=st["project"]["savedPath"]), open(o / "fake_state.json", "w", encoding="utf-8"), ensure_ascii=False)


def run_round1_skip(new_dir, out, fixture):
    """--skip 是通用版新加的：同一份 r0 数据，不加 / 加 --skip 179 各出一次计划（不 --apply），
    只有 #179 的句尾释放从计划里移到“人工排除”；句尾释放的决定（与假 CLI 无关）还要和《绯红》真跑的 round1_plan 相同。"""
    o = out / "new" / "round1_skip"
    o.mkdir(parents=True)
    fx = o / "fixture.json"
    json.dump(fixture, open(fx, "w", encoding="utf-8"), ensure_ascii=False)
    prep_round1(o, "new")
    env = dict(os.environ, FAKE_ACE_LOG=str(o / "calls.jsonl"), FAKE_ACE_STATE=str(o / "fake_state.json"), FAKE_ACE_FIXTURE=str(fx))
    res = {"case": "round1_skip", "checks": []}
    plans = {}
    for tag, extra in (("plain", []), ("skip", ["--skip", "179"])):
        rc, so, se = rr.run(new_dir / "round1_timing.py", [W / "ace_state_r0.json", W / "timing_r0.json", S, o / "r1.acep",
                                                          o / f"plan_{tag}.json", *extra], env=env)
        if rc:
            res.update(ok=False, error=se[-1500:])
            return res
        plans[tag] = json.load(open(o / f"plan_{tag}.json", encoding="utf-8"))
    a, b = plans["plain"], plans["skip"]
    rel = lambda p: [{k: r[k] for k in ("idx", "tick", "cur_dur", "new_dur", "release_delta_ms")} for r in p["releases"]]  # noqa: E731
    real = json.load(open(W / "round1_plan.json", encoding="utf-8"))
    added = [s for s in b["skipped"] if s not in a["skipped"]]
    res["checks"] += [
        {"output": "不加 --skip：句尾释放的决定与《绯红》真跑的计划相同", "same": rel(a) == rel(real)},
        {"output": "加 --skip 179：#179 不在句尾释放里", "same": 179 in [r["idx"] for r in a["releases"]] and 179 not in [r["idx"] for r in b["releases"]]},
        {"output": "加 --skip 179：只多一条 #179 的人工排除，其余计划不变",
         "same": len(added) == 1 and added[0]["idx"] == 179 and "--skip" in added[0]["why"] and a["consonants"] == b["consonants"]
         and [r for r in a["releases"] if r["idx"] != 179] == b["releases"]},
    ]
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_tempo_fit(new_dir, out):
    """tempo_fit.py 是新写的：《绯红》的节拍分析上重算，对照《绯红》文档里记的数（拟合 101.998 BPM，按 102 残差中位 6 ms、最大 40 ms，
    网格零点 0.9647 s；当时是临时算的，三段的分法不同，所以三段只看都在 ±2.5 ms 内）。"""
    o = out / "new" / "tempo_fit"
    o.mkdir(parents=True)
    rc, so, se = rr.run(new_dir / "tempo_fit.py", [W / "tempo_analysis_official.json", "102", o / "tempo.json"])
    res = {"case": "tempo_fit", "checks": []}
    if rc:
        res.update(ok=False, error=se[-1500:])
        return res
    t = json.load(open(o / "tempo.json", encoding="utf-8"))
    res["checks"] += [
        {"output": f"拟合 BPM {t['fit_bpm']}（文档 101.998）", "same": t["fit_bpm"] == 101.998},
        {"output": f"残差中位 {t['residual_abs_median_ms']} ms / 最大 {t['residual_abs_max_ms']} ms（文档 6 / 40）",
         "same": abs(t["residual_abs_median_ms"] - 6) <= 0.5 and abs(t["residual_abs_max_ms"] - 40) <= 0.5},
        {"output": f"三段平均残差 {t['thirds_mean_residual_ms']} ms 都在 ±2.5 内", "same": all(abs(v) <= 2.5 for v in t["thirds_mean_residual_ms"])},
        {"output": f"拍 0 在 {t['beat0_sec_at_candidate']} s（文档网格零点 0.9647 s）", "same": abs(t["beat0_sec_at_candidate"] - 0.9647) <= 0.001},
    ]
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def prep_round2(o, side):
    st = json.load(open(W / "ace_state_r1.json", encoding="utf-8"))
    notes = score_notes(st["clip_begin"])
    notes[179]["dur"] = 144  # r1 里 #179 被句尾释放规则延长成 144 tick
    json.dump(fake_state(notes={"0": notes}, clips={st["clip_uuid"]: {"track": 0, "begin": st["clip_begin"]}},
                         saved=st["project"]["savedPath"]), open(o / "fake_state.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"179": [144, 120]}, open(o / "revert.json", "w", encoding="utf-8"))


def prep_endings(o, side):
    st = json.load(open(W / "ace_state_r2.json", encoding="utf-8"))
    ph = {r["pos"]: r["noteUuid"] for r in json.load(open(W / "r3_phonemes.json", encoding="utf-8"))["notes"]}
    r3 = o / "ace" / "r3" / "r3.acep"
    r3.parent.mkdir(parents=True)
    json.dump(fake_state(notes={"0": score_notes(st["clip_begin"], ph)}, clips={st["clip_uuid"]: {"track": 0, "begin": st["clip_begin"]}},
                         saved=str(r3)), open(o / "fake_state.json", "w", encoding="utf-8"), ensure_ascii=False)


def prep_v2m(o, side):
    sp = json.load(open(W / "split_state.json", encoding="utf-8"))
    v = json.load(open(W / "v2m" / "v2m_notes.json", encoding="utf-8"))
    tracks = [{"trackIndex": i, "trackName": nm, "trackType": ty, "trackUuid": u} for i, nm, ty, u in sp["tracks"]]
    json.dump(fake_state(tracks=tracks, saved=sp["project"]["savedPath"],
                         clip_lists={v["source_track"]: [{"clipUuid": v["source_clip"], "clipType": "audio", "clipBegin": 0}]}),
              open(o / "fake_state.json", "w", encoding="utf-8"), ensure_ascii=False)


def v2m_fixture():
    v = json.load(open(W / "v2m" / "v2m_notes.json", encoding="utf-8"))
    clips = []
    for cid, cpos in sorted({(n["clip"], n["clip_pos"]) for n in v["notes"]}, key=lambda c: c[1]):
        clips.append({"clipUuid": cid, "clipBegin": cpos,
                      "notes": [{"pos": n["tick"] - cpos, "dur": n["dur"], "pitch": n["pitch"], "lyric": n["lyric"], "syllable": n["syllable"],
                                 "language": n["language"]} for n in v["notes"] if n["clip"] == cid]})
    return {"trackUuid": v["sing_track"], "job": v["job"], "clips": clips}


def ace_cases():
    base = {"ticks_per_sec": 816.0, "language": "Japanese", "g2p": g2p_table()}
    rep3 = json.load(open(W / "round3_report.json", encoding="utf-8"))
    build = [
        dict(script="ace_build.py", args=[S, "{OUT}/ace/r0.acep", INST, REFV, "{OUT}/state_r0.json"], outputs=["state_r0.json"]),
        dict(script="g2p_check.py", args=[S, "{OUT}/g2p.json"], outputs=["g2p.json"]),
        dict(script="ace_readback.py", args=["{OUT}/state_r0.json", S, "{OUT}/readback.json"], outputs=["readback.json"]),
    ]
    round1 = [
        dict(script="round1_timing.py", args=[W / "ace_state_r0.json", W / "timing_r0.json", S, "{OUT}/ace/r1.acep", "{OUT}/round1_plan.json",
                                              "--apply"], outputs=["round1_plan.json"]),
    ]
    round2 = [
        dict(script="round2_pitch.py", new_script="round2_pitch_online.py",
             args=[W / "ace_state_r1.json", "{OUT}/ace/r2.acep", W / "target_f0.json", S, "{OUT}/state_r2.json", "{OUT}/report.json"],
             new_args=[W / "ace_state_r1.json", "{OUT}/ace/r2.acep", W / "target_f0.json", S, "{OUT}/state_r2.json", "{OUT}/report.json",
                       "--revert", "{OUT}/revert.json"],
             outputs=["state_r2.json", "report.json", "round2_pitch_points.json"],
             archive={"report.json": (W / "round2_report.json", ["anchors_written", "gap_markers", "runs", "readback_points",
                                                                 "max_tick_diff", "max_value_diff", "gap_markers_match", "notes_changed_vs_r1"])}),
    ]
    endings = [
        dict(script="round3_apply.py", new_script="endings_apply.py",
             args=[W / "ace_state_r2.json", "{OUT}/ace/r3/r3.acep", W / "round3_plan.json", "{OUT}/state_r3.json", "{OUT}/report.json"],
             outputs=["state_r3.json", "report.json", "round3_pitch_points.json"],
             archive={"report.json": (W / "round3_report.json", ["deferred", "pitch", "consonant_readback_mismatch",
                                                                 "voicing_spans_after_clear", "notes_identical_to_r2"])}),
    ]
    v2m = [dict(script="ace_v2m.py", args=[W / "split_state.json", "{OUT}/v2m_notes.json"], outputs=["v2m_notes.json"],
                archive={"v2m_notes.json": (W / "v2m" / "v2m_notes.json", None)})]
    fx_end = dict(base, timings_unavailable=[c["note"] for c in rep3["deferred"]],
                  pinned_after_write=[{"begin": 0, "end": 1200, "mode": "unvoiced"}])
    return [("feihong_build", build, base, None), ("feihong_round1", round1, base, prep_round1),
            ("feihong_round2_online", round2, base, prep_round2),
            ("feihong_endings_apply", endings, fx_end, prep_endings), ("feihong_v2m", v2m, dict(base, v2m=v2m_fixture()), prep_v2m)]


EXTRA_CALLS = {"feihong_round1": [(["project", "dirty"], ["project", "save-as"])]}  # round1_timing.py --apply 前的工程检查


def ace_session(label, steps, orig_dir, new_dir, out, fixture, prepare=None):
    res = {"case": label, "checks": []}
    traces, outs = {}, {}
    for side, sdir in (("orig", orig_dir), ("new", new_dir)):
        o = out / side / label
        o.mkdir(parents=True)
        fx = o / "fixture.json"
        json.dump(fixture, open(fx, "w", encoding="utf-8"), ensure_ascii=False)
        if prepare:
            prepare(o, side)
        env = dict(os.environ, FAKE_ACE_LOG=str(o / "calls.jsonl"), FAKE_ACE_STATE=str(o / "fake_state.json"), FAKE_ACE_FIXTURE=str(fx))
        for st in steps:
            script = st.get(f"{side}_script", st["script"])
            args = st.get(f"{side}_args", st["args"])
            rc, so, se = rr.run(sdir / script, rr.subst(args, o), env=env)
            if rc:
                res.update(ok=False, error=f"{side} {script}: {se[-1500:]}")
                return res
        traces[side] = [json.loads(line) for line in open(o / "calls.jsonl", encoding="utf-8")]
        fs = json.load(open(o / "fake_state.json", encoding="utf-8"))
        if fs["unknown"]:
            res.update(ok=False, error=f"{side} 用了假 CLI 没覆盖的命令：{fs['unknown'][:3]}")
            return res
        outs[side] = o
    roots = [outs["orig"], outs["new"]]

    def clean(tr):
        t = rr.norm(tr, roots)
        for call in t:
            if call[:2] == ["clip", "create"] and "--name" in call:
                call[call.index("--name") + 1] = "<clip>"
        return t

    extra = EXTRA_CALLS.get(label, [])
    new_trace, dropped = rr.drop_extra(clean(traces["new"]), extra)
    same = clean(traces["orig"]) == new_trace
    res["checks"].append({"output": f"ACE 命令序列（{len(traces['orig'])} / {len(traces['new'])} 条）", "same": same})
    if extra:
        res["allowed_extra_calls"] = dropped
        res["checks"].append({"output": f"通用版多出的检查调用 {len(dropped)} / {len(extra)} 条", "same": len(dropped) == len(extra)})
    for st in steps:
        for item in st.get("outputs", []):
            a, b = item if isinstance(item, tuple) else (item, item)
            ok, why = rr.same_file(outs["orig"] / a, outs["new"] / b, roots)
            res["checks"].append({"output": b, "same": ok, "why": why})
        for name, (ref, keys) in st.get("archive", {}).items():
            ja = rr.norm(json.load(open(outs["orig"] / name, encoding="utf-8")), roots)
            jb = json.load(open(ref, encoding="utf-8"))
            if keys:
                ja, jb = {k: ja.get(k) for k in keys}, {k: jb.get(k) for k in keys}
            res.setdefault("orig_matches_archive", {})[name] = ja == jb or [k for k in (keys or ja) if ja.get(k) != jb.get(k)]
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_target_check(new_dir, out):
    """target_check.py 是新写的（在线写音高前的八度 / 错音检查）：四条真写进 ACE 过的目标曲线都要通过；
    把《绯红》一个长音的目标整体抬高 12 半音，必须拦下并指出这个音。《妄想感傷代償連盟》的谱面要 220 BPM，另建一个项目跑。"""
    o = out / "new" / "target_check"
    o.mkdir(parents=True)
    wx = out / "new_project_wangxiang"
    if not wx.exists():
        shutil.copytree(PKG / "scripts", wx / "scripts", ignore=shutil.ignore_patterns("examples", "__pycache__"))
        json.dump(rr.PROJECT, open(wx / "project.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    WW = rr.W
    real = [("绯红", new_dir, S, W / "target_f0.json"), ("妄想 试验段", wx / "scripts", WW / "pilot_score.json", WW / "target_f0.json"),
            ("妄想 完整副歌主唱", wx / "scripts", WW / "full" / "score_main.json", WW / "full" / "target_main.json"),
            ("妄想 完整副歌和声", wx / "scripts", WW / "full" / "score_harmony.json", WW / "full" / "target_harmony.json")]
    res = {"case": "target_check", "checks": []}
    for name, sdir, sc, tg in real:
        rc, so, se = rr.run(sdir / "target_check.py", [sc, tg, o / f"{name}.json"])
        res["checks"].append({"output": f"{name}：真写过的目标通过", "same": rc == 0, "why": "" if rc == 0 else se[-300:]})
    score = json.load(open(S, encoding="utf-8"))
    tgt = json.load(open(W / "target_f0.json", encoding="utf-8"))
    off = score["meta"]["clip_start_tick"] / 816.0  # 片段起点（秒）；《绯红》1 s = 816 tick
    k, n = max(enumerate(score["notes"]), key=lambda kv: kv[1]["dur"])
    a, b = int((n["start"] - off) / tgt["hop_sec"]), int((n["end"] - off) / tgt["hop_sec"])
    tgt["midi"] = [None if v is None else (v + 12 if a <= i < b else v) for i, v in enumerate(tgt["midi"])]
    json.dump(tgt, open(o / "bad_target.json", "w", encoding="utf-8"))
    rc, so, se = rr.run(new_dir / "target_check.py", [S, o / "bad_target.json", o / "bad.json"])
    bad = json.load(open(o / "bad.json", encoding="utf-8")) if (o / "bad.json").exists() else {}
    hit = [x["idx"] for x in bad.get("notes_with_interior_median_gt_6", [])]
    res["checks"].append({"output": f"#{n['idx']} 整体高八度：拦下（退出码 {rc}，指出的音 {hit}）", "same": rc == 1 and n["idx"] in hit})
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_voicing_clear_smoke(new_dir, out):
    """voicing_clear.py 是新写的：假 CLI 上有两段固定，清完 0 段并保存；命令序列要对。"""
    o = out / "new" / "voicing_clear_smoke"
    o.mkdir(parents=True)
    st = json.load(open(W / "ace_state_r2.json", encoding="utf-8"))
    fx = o / "fixture.json"
    json.dump({"ticks_per_sec": 816.0}, open(fx, "w", encoding="utf-8"))
    spans = [{"begin": 0, "end": 900, "mode": "unvoiced"}, {"begin": 5000, "end": 5600, "mode": "unvoiced"}]
    json.dump(fake_state(saved=st["project"]["savedPath"], voicing={st["clip_uuid"]: spans}), open(o / "fake_state.json", "w", encoding="utf-8"))
    env = dict(os.environ, FAKE_ACE_LOG=str(o / "calls.jsonl"), FAKE_ACE_STATE=str(o / "fake_state.json"), FAKE_ACE_FIXTURE=str(fx))
    rc, so, se = rr.run(new_dir / "voicing_clear.py", [W / "ace_state_r2.json"], env=env)
    res = {"case": "voicing_clear_smoke", "checks": []}
    if rc:
        res.update(ok=False, error=se[-1500:])
        return res
    calls = [json.loads(line)[:2] for line in open(o / "calls.jsonl", encoding="utf-8")]
    after = json.load(open(o / "fake_state.json", encoding="utf-8"))["voicing"][st["clip_uuid"]]
    res["checks"] += [
        {"output": "命令：查工程 → 读固定 → 清成 auto → 再读 → 保存",
         "same": calls == [["project", "dirty"], ["vocalpitch", "voicing"], ["vocalpitch", "set-voicing"], ["vocalpitch", "voicing"], ["project", "save"]]},
        {"output": "清完 0 段固定", "same": after == []},
    ]
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_endings_guard(new_dir, out):
    """endings_apply.py 收紧了未保存改动的检查：撤销记录里有用户的改动 → 停下；只有自己上次中断留下的辅音长度 → 接着做完。"""
    res = {"case": "endings_guard", "checks": []}
    rep3 = json.load(open(W / "round3_report.json", encoding="utf-8"))
    own = [{"actor": "远程控制", "applied": True, "index": i, "name": "设置辅音长度"} for i in range(3)]
    for tag, hist, want_rc in (("user_edit", own + [{"actor": "用户", "applied": True, "index": 3, "name": "移动音符"}], 1), ("own_only", own, 0)):
        o = out / "new" / "endings_guard" / tag
        o.mkdir(parents=True)
        fx = o / "fixture.json"
        json.dump({"ticks_per_sec": 816.0, "language": "Japanese", "g2p": g2p_table(), "dirty": True, "history": hist,
                   "timings_unavailable": [c["note"] for c in rep3["deferred"]]}, open(fx, "w", encoding="utf-8"), ensure_ascii=False)
        prep_endings(o, "new")
        env = dict(os.environ, FAKE_ACE_LOG=str(o / "calls.jsonl"), FAKE_ACE_STATE=str(o / "fake_state.json"), FAKE_ACE_FIXTURE=str(fx))
        rc, so, se = rr.run(new_dir / "endings_apply.py", [W / "ace_state_r2.json", o / "ace" / "r3" / "r3.acep", W / "round3_plan.json",
                                                         o / "state_r3.json", o / "report.json"], env=env)
        writes = sum(1 for line in open(o / "calls.jsonl", encoding="utf-8") if json.loads(line)[:2] == ["phoneme", "set-consonant-timing"])
        ok = rc == want_rc and (writes == 0 if want_rc else (o / "report.json").exists())
        res["checks"].append({"output": f"{tag}：退出码 {rc}（要 {want_rc}），改辅音 {writes} 次", "same": ok,
                              "why": "" if ok else (se or so)[-300:]})
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_ace_dump_smoke(new_dir, out):
    """ace_dump.py 是新写的（没有原版可比）：在假 CLI 上跑一遍，看发出的命令和写出的 JSON。"""
    o = out / "new" / "ace_dump_smoke"
    o.mkdir(parents=True)
    st = json.load(open(W / "ace_state_r2.json", encoding="utf-8"))
    fx = o / "fixture.json"
    json.dump({"ticks_per_sec": 816.0, "language": "Japanese", "g2p": g2p_table()}, open(fx, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(fake_state(notes={"0": score_notes(st["clip_begin"])}, clips={st["clip_uuid"]: {"track": 0, "begin": st["clip_begin"]}},
                         saved="x.acep", voicing={st["clip_uuid"]: [{"begin": 0, "end": 900, "mode": "unvoiced"}]}),
              open(o / "fake_state.json", "w", encoding="utf-8"), ensure_ascii=False)
    env = dict(os.environ, FAKE_ACE_LOG=str(o / "calls.jsonl"), FAKE_ACE_STATE=str(o / "fake_state.json"), FAKE_ACE_FIXTURE=str(fx))
    res = {"case": "ace_dump_smoke", "checks": []}
    for what in ("phonemes", "voicing"):
        rc, so, se = rr.run(new_dir / "ace_dump.py", [W / "ace_state_r2.json", what, o / f"{what}.json"], env=env)
        if rc:
            res.update(ok=False, error=se[-1500:])
            return res
    calls = [json.loads(line) for line in open(o / "calls.jsonl", encoding="utf-8")]
    ph = json.load(open(o / "phonemes.json", encoding="utf-8"))
    vo = json.load(open(o / "voicing.json", encoding="utf-8"))
    res["checks"] += [
        {"output": "命令", "same": [c[:2] for c in calls] == [["phoneme", "list"], ["vocalpitch", "voicing"]]
         and "--with-timings=durations" in calls[0]},
        {"output": "phonemes.json 行数 = 非延长音的音符数", "same": len(ph["notes"]) == sum(n["lyric"] != "-" for n in json.load(open(S, encoding="utf-8"))["notes"])},
        {"output": "voicing.json 的 spans", "same": vo["spans"] == [{"begin": 0, "end": 900, "mode": "unvoiced"}]},
    ]
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def main():
    out = Path(sys.argv[1]).resolve()
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"输出目录非空：{out}")
    out.mkdir(parents=True, exist_ok=True)
    orig = out / "orig_scripts_with_fake_cli" / "scripts"
    shutil.copytree(D / "scripts", orig, ignore=shutil.ignore_patterns("__pycache__"))
    (orig.parent / "work").mkdir()
    text = (orig / "ace.py").read_text(encoding="utf-8")
    patched = text.replace(r'CLI = r"C:\Program Files\ACE Studio\acestudio-cli.exe"', f"CLI = {json.dumps([PY, str(FAKE)])}") \
                  .replace("argv = [CLI, *map(str, args)]", "argv = [*CLI, *map(str, args)]")
    assert patched.count("[*CLI,") == 1 and "acestudio-cli.exe" not in patched, "原版 ace.py 的写法变了，替换失败"
    (orig / "ace.py").write_text(patched, encoding="utf-8")
    proj = out / "new_project"
    shutil.copytree(PKG / "scripts", proj / "scripts", ignore=shutil.ignore_patterns("examples", "__pycache__"))
    json.dump(PROJECT, open(proj / "project.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    new = proj / "scripts"
    want = lambda name: not only or name in only  # noqa: E731
    results = []
    for name in VERBATIM:
        if want(name):
            results.append({"case": f"verbatim:{name}", "ok": (new / name).exists() and rr.sha(new / name) == rr.sha(D / "scripts" / name)})
    for case in signal_cases():
        if want(case["name"]):
            results.append(run_signal(case, orig, new, out))
            print(json.dumps(results[-1], ensure_ascii=False)[:400], flush=True)
    base_fx = {"ticks_per_sec": 816.0, "language": "Japanese", "g2p": g2p_table()}
    for name, fn in (("mix_check", lambda: run_mix_check(orig, new, out)), ("rmvpe_run", lambda: run_rmvpe(orig, new, out)),
                     ("patch_consonants", lambda: run_patch_consonants(new, out)), ("ace_dump_smoke", lambda: run_ace_dump_smoke(new, out)),
                     ("round1_skip", lambda: run_round1_skip(new, out, base_fx)), ("tempo_fit", lambda: run_tempo_fit(new, out)),
                     ("target_check", lambda: run_target_check(new, out)), ("voicing_clear_smoke", lambda: run_voicing_clear_smoke(new, out)),
                     ("endings_guard", lambda: run_endings_guard(new, out))):
        if want(name):
            results.append(fn())
            print(json.dumps(results[-1], ensure_ascii=False)[:400], flush=True)
    for label, steps, fixture, prepare in ace_cases():
        if want(label):
            results.append(ace_session(label, steps, orig, new, out, fixture, prepare))
            print(json.dumps(results[-1], ensure_ascii=False)[:400], flush=True)
    summary = {"passed": sum(r["ok"] for r in results), "total": len(results),
               "failed": [r["case"] for r in results if not r["ok"]]}
    json.dump({"summary": summary, "results": results}, open(out / "regression_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    sys.exit(0 if not summary["failed"] else 1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
