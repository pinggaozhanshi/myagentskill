"""工作流脚本的回归验证：同一份真实数据（《妄想感傷代償連盟》调教试验），原版脚本和本工作流的通用版各跑一遍，逐项比对输出。

用法：python run_regression.py <out_dir> [--only name1,name2]
- 纯信号脚本：两版输出（JSON / npy / npz / WAV / 打印）必须完全一致；另记原版这次的输出与试验当时的存档是否一致（看可复现性）。
- 要连 ACE 的脚本：两版都接到 fake_ace_cli.py，按同样的顺序跑完一个会话，比对发出的命令序列和写出的文件。
- 通用版里原样照搬的脚本：比对文件校验值。
结果写进 <out_dir>/regression_results.json；任何一项不一致时退出码为 1。只读原试验的数据，不写回原试验目录。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

PY = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python313\python.exe"
PKG = Path(__file__).resolve().parents[2]
D = Path(r"D:\自媒体\妄想感伤代偿联盟_调教试验_20261021")
W, E, F = D / "work", D / "exports", D / "work" / "full"
FAKE = Path(__file__).with_name("fake_ace_cli.py")

PROJECT = {
    "title": "妄想感傷代償連盟 调教试验（回归验证用）",
    "bpm": 220.0, "tpq": 480, "language": "Japanese",
    "singer": "singer:18", "track_name": "洛天依_主唱",
    "inst_track_name": "INST_分离伴奏", "ref_track_name": "REF_参考人声(静音)",
    "downbeat_tick": 79, "mix_name": "妄想感傷代償連盟_副歌_洛天依_混音",
    "scale_pitch_classes": [3, 5, 7, 8, 10, 0, 2],
    "ace_cli": [PY, str(FAKE)],
}

# 通用版里应与原版逐字节相同的脚本（ace_readback.py 在《绯红》后改过：tick 换算、延长音行数；round1_timing.py 加了 --skip；
# 两者由 ACE 会话覆盖）
VERBATIM = ["ace_render.py", "ace_export.py", "state_with_project.py", "extract_ust_zip.py", "ust_inspect.py",
            "f0_grid.py", "make_reference.py", "compare_timing.py", "round1_mirror.py", "build_target_f0.py",
            "build_harmony_target.py", "patch_pitch.py", "pitch_eval.py", "glitch_check.py", "param_read.py", "param_write.py",
            "patch_params.py", "voice_features.py", "ltas_compare.py", "stems_collect.py", "splice_main.py"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def norm(obj, roots):
    if isinstance(obj, str):
        for r in roots:
            for form in (str(r), str(r).replace("\\", "/")):
                obj = obj.replace(form, "{OUT}")
        return obj.replace("\\", "/")
    if isinstance(obj, list):
        return [norm(x, roots) for x in obj]
    if isinstance(obj, dict):
        return {norm(k, roots): norm(v, roots) for k, v in obj.items()}
    return obj


def drop(obj, keys):
    if isinstance(obj, dict):
        return {k: drop(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [drop(x, keys) for x in obj]
    return obj


def same_file(a, b, roots, exclude=()):
    a, b = Path(a), Path(b)
    if not a.exists() or not b.exists():
        return False, f"缺文件：{a if not a.exists() else b}"
    ext = a.suffix.lower()
    if ext == ".json":
        ja = drop(norm(json.load(open(a, encoding="utf-8")), roots), set(exclude))
        jb = drop(norm(json.load(open(b, encoding="utf-8")), roots), set(exclude))
        return ja == jb, "" if ja == jb else "JSON 内容不同"
    if ext == ".npy":
        ok = np.array_equal(np.load(a), np.load(b), equal_nan=True)
        return ok, "" if ok else "数组不同"
    if ext == ".npz":
        za, zb = np.load(a), np.load(b)
        bad = [k for k in sorted(set(za.files) | set(zb.files))
               if k not in za.files or k not in zb.files or not np.array_equal(za[k], zb[k], equal_nan=True)]
        return not bad, "" if not bad else f"npz 键不同：{bad}"
    ok = sha(a) == sha(b)
    return ok, "" if ok else "字节不同"


def run(script, args, cwd=None, env=None):
    p = subprocess.run([PY, "-I", str(script), *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=cwd, env=env)
    return p.returncode, p.stdout, p.stderr


def subst(args, out):
    return [str(a).replace("{OUT}", str(out)) if isinstance(a, (str, Path)) else a for a in args]


def wav(d):
    return E / d / f"{d}_洛天依_主唱.wav"


def signal_cases():
    S, G = W / "pilot_score.json", W / "g2p_japanese.json"
    REF, REFMIX = W / "ref" / "ref_vocal_clip_48k.wav", W / "ref" / "ref_vocal_mix_clip_48k.wav"
    PRF, RMF = W / "f0" / "basic_dereverb_vocal_praat.npy", W / "f0" / "basic_dereverb_vocal_rmvpe.npy"
    R0, R1, R2 = wav("r0_baseline"), wav("r1_timing"), wav("r2_pitch")
    F0 = {k: W / "f0" / f"{k}_praat.npy" for k in ("r0", "r1", "r2")}
    dur = sf.info(R2).frames / sf.info(R2).samplerate
    main_v3, harm_r2 = E / "full" / "v3" / "full_v3_main_洛天依_主唱.wav", E / "full" / "r2" / "full_r2_harmony_洛天依_和声.wav"
    c = [
        dict(name="ust_inspect", args=[W / "ust_extracted" / "妄想感傷代償連盟　ust" / "main.ust", "{OUT}/ust_main.json"],
             outputs=["ust_main.json"], stored={"ust_main.json": W / "ust_main.json"}),
        dict(name="align_ust", args=[W / "ust_main.json", W / "stems" / "basic_dereverb_vocal.wav", "{OUT}/align.json"],
             outputs=["align.json"], exclude=["segments"], stored={"align.json": W / "align_basic_dereverb_vocal.json"}),
        dict(name="f0_grid", args=[R2, "{OUT}/r2_praat.npy"], outputs=["r2_praat.npy"], stored={"r2_praat.npy": F0["r2"]}),
        dict(name="f0_grid_rmvpe", script="f0_grid.py", args=["--rmvpe", W / "f0" / "r2_rmvpe.json", repr(dur), "{OUT}/r2_rmvpe.npy"],
             outputs=["r2_rmvpe.npy"], stored={"r2_rmvpe.npy": W / "f0" / "r2_rmvpe.npy"}),
        dict(name="note_check", args=[S, PRF, RMF, "{OUT}/note_check.json"], outputs=["note_check.json"],
             stored={"note_check.json": W / "note_check.json"}),
        *[dict(name=f"timing_voicing_{k}", script="timing_voicing.py", args=[S, G, REF, r, f"{{OUT}}/timing_{k}.json"],
               outputs=[f"timing_{k}.json"], stored={f"timing_{k}.json": W / f"timing_{k}.json"})
          for k, r in (("r0", R0), ("r1", R1), ("r2", R2))],
        dict(name="compare_timing", args=[W / "timing_r0.json", W / "timing_r1.json", W / "round1_plan.json", "{OUT}/cmp.json"],
             outputs=["cmp.json"], stored={"cmp.json": W / "compare_r0_r1.json"}),
        dict(name="build_target_f0", args=[S, PRF, RMF, "{OUT}/target_f0.json"], outputs=["target_f0.json", "target_f0_hz.npy"],
             stored={"target_f0.json": W / "target_f0.json"}, archive_exclude=["alt_ref_frames"]),
        dict(name="pitch_eval", args=[W / "target_f0.json", S, "{OUT}/pe.json", *[f"{k}={v}" for k, v in F0.items()]],
             outputs=["pe.json"]),
        dict(name="glitch_check", args=[W / "target_f0.json", S, PRF, f"r0={F0['r0']}", f"r2={F0['r2']}"], outputs=[], stdout=True),
        dict(name="voice_features", args=[R2, "{OUT}/r2.npz"], outputs=["r2.npz"], stored={"r2.npz": W / "feat" / "r2.npz"}),
        dict(name="ltas_compare", args=["{OUT}/ltas.json", f"ref={REF}", f"r2={R2}", f"refmix={REFMIX}"], outputs=["ltas.json"]),
        dict(name="eq_brighten", args=[R2, "{OUT}/r2_eq.wav", W / "eq" / "ltas_eq.json"], outputs=["r2_eq.wav", "r2_eq_eq.json"]),
        dict(name="sibilance_check", args=[S, G, "{OUT}/sib.json", f"ref={REF}", f"r2={R2}"], outputs=["sib.json"]),
        dict(name="crisp_metrics", args=[S, G, "{OUT}/crisp.json", f"ref={REF}", f"r0={R0}", f"r2={R2}"], outputs=["crisp.json"]),
        dict(name="splice_main", args=[F / "score_main.json", F / "na_fix.json", E / "full" / "r2" / "full_r2_main_洛天依_主唱.wav",
                                       E / "full" / "r4" / "full_r4_main_洛天依_主唱.wav", "{OUT}/v3_main.wav", "{OUT}/splice.json"],
             outputs=["v3_main.wav", "splice.json"], stored={"v3_main.wav": main_v3}),
        dict(name="build_harmony_target", args=[F / "score_main.json", F / "score_harmony.json", F / "target_main.json",
                                                "{OUT}/target_harmony.json"],
             outputs=["target_harmony.json", "target_harmony_hz.npy"], stored={"target_harmony.json": F / "target_harmony.json"}),
        dict(name="hamo_check", args=[F / "score_full_nofix.json", W / "stems" / "basic_vocal.wav", "{OUT}/hamo_fix.json", "{OUT}/hamo_check.json"],
             outputs=["hamo_fix.json", "hamo_check.json"], stored={"hamo_fix.json": F / "hamo_fix.json", "hamo_check.json": F / "hamo_check.json"}),
        dict(name="score_views", args=[F / "score_full.json", "{OUT}/main.json", "{OUT}/harmony.json"],
             new_args=[F / "score_full.json", "{OUT}/main.json", "{OUT}/harmony.json", "--no-timing-src", "愛や厭"],
             outputs=["main.json", "harmony.json"], stored={"main.json": F / "score_main.json", "harmony.json": F / "score_harmony.json"}),
        dict(name="mix", script="mix_chorus.py", new_script="mix_vocals.py",
             args=[F / "score_full.json", main_v3, harm_r2, W / "stems" / "basic_instrumental.wav", W / "stems" / "basic_vocal.wav", "{OUT}",
                   "--cut-to-vocal"],
             outputs=[("妄想感傷代償連盟_副歌_洛天依_混音.wav", "妄想感傷代償連盟_副歌_洛天依_混音.wav"),
                      ("人声总线_主唱和声混响延迟.wav", "人声总线.wav"), ("mix_report.json", "mix_report.json")],
             stored={"妄想感傷代償連盟_副歌_洛天依_混音.wav": E / "成品_副歌_v3" / "妄想感傷代償連盟_副歌_洛天依_混音_v3.wav"}),
    ]
    return c


def run_signal(case, orig_dir, new_dir, out):
    o, n = out / "orig" / case["name"], out / "new" / case["name"]
    o.mkdir(parents=True)
    n.mkdir(parents=True)
    script = case.get("script", case["name"] + ".py")
    rc1, so1, se1 = run(orig_dir / script, subst(case["args"], o))
    rc2, so2, se2 = run(new_dir / case.get("new_script", script), subst(case.get("new_args", case["args"]), n))
    res = {"case": case["name"], "orig_rc": rc1, "new_rc": rc2, "checks": []}
    if rc1 or rc2:
        res["error"] = (se1 if rc1 else se2)[-1500:]
        res["ok"] = False
        return res
    roots = [o, n]
    for item in case["outputs"]:
        a, b = item if isinstance(item, tuple) else (item, item)
        ok, why = same_file(o / a, n / b, roots, case.get("exclude", ()))
        res["checks"].append({"output": b, "same": ok, "why": why})
    if case.get("stdout"):
        same = norm(so1, roots) == norm(so2, roots)
        res["checks"].append({"output": "stdout", "same": same, "why": "" if same else "打印不同"})
    for name, ref in case.get("stored", {}).items():
        ok, why = same_file(o / name, ref, [o], [*case.get("exclude", ()), *case.get("archive_exclude", ())])
        res.setdefault("orig_matches_archive", {})[name] = ok if ok else why
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def run_make_ab(orig_dir, new_dir, out):
    o, n = out / "orig" / "make_ab", out / "new" / "make_ab"
    for k, d in (("r0", "r0_baseline"), ("r1", "r1_timing"), ("r2", "r2_pitch")):
        (o / "exports" / d).mkdir(parents=True)
        shutil.copy2(wav(d), o / "exports" / d)
    (o / "work").mkdir()
    n.mkdir(parents=True)
    rc1, _, se1 = run(orig_dir / "make_ab.py", [o / "exports", W / "ref", o / "work"])
    rc2, _, se2 = run(new_dir / "make_ab.py", [W / "ref", n, n / "blind_key.json", f"r0基线={wav('r0_baseline')}",
                                               f"r1时值={wav('r1_timing')}", f"r2调教版={wav('r2_pitch')}"])
    res = {"case": "make_ab", "orig_rc": rc1, "new_rc": rc2, "checks": []}
    if rc1 or rc2:
        res.update(ok=False, error=(se1 if rc1 else se2)[-1500:])
        return res
    hs = lambda d: sorted({sha(p) for p in Path(d).glob("*.wav")})
    res["checks"].append({"output": "ab_音量对齐/*.wav（内容集合）", "same": hs(o / "exports" / "ab_音量对齐") == hs(n / "ab_音量对齐")})
    res["checks"].append({"output": "blind_test_盲听/*.wav（内容集合）", "same": hs(o / "exports" / "blind_test_盲听") == hs(n / "blind_test_盲听")})
    key = json.load(open(n / "blind_key.json", encoding="utf-8"))
    by_label = {}
    for p in (n / "ab_音量对齐").glob("*_干声.wav"):
        by_label[p.name.split("_", 1)[1].rsplit("_干声", 1)[0]] = sha(p)
    consistent = all(sha(n / "blind_test_盲听" / fn) == by_label.get(v["version"]) for fn, v in key.items())
    res["checks"].append({"output": "盲听答案与标明版本对得上", "same": consistent})
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def fixture(out):
    g2p = {}
    for p in (W / "g2p_japanese.json", F / "g2p_harmony.json", F / "g2p_main.json"):
        if p.exists():
            for s in json.load(open(p, encoding="utf-8"))["syllables"]:
                g2p.setdefault(s["grapheme"], s["phonemes"])
    fx = out / "fixture.json"
    json.dump({"ticks_per_sec": 1760.0, "language": "Japanese", "g2p": g2p}, open(fx, "w", encoding="utf-8"), ensure_ascii=False)
    return fx


# 通用版有意多出的 ACE 调用：(这条调用, 紧跟着的那条调用的开头)。比对前从通用版的命令序列里各去掉一次，并要求确实出现过。
EXTRA_CALLS = {"ace_single_track": [(["project", "dirty"], ["project", "save-as"])]}  # round1_timing.py --apply 前的工程检查


def drop_extra(trace, extra):
    t, dropped = list(trace), []
    for call, nxt in extra:
        for i in range(len(t) - 1):
            if t[i] == call and t[i + 1][:len(nxt)] == nxt:
                dropped.append(t.pop(i))
                break
    return t, dropped


def ace_session(label, steps, orig_dir, new_dir, out, fx, prepare=None):
    res = {"case": label, "checks": []}
    traces, outs = {}, {}
    for side, sdir in (("orig", orig_dir), ("new", new_dir)):
        o = out / side / label
        o.mkdir(parents=True)
        if prepare:
            prepare(o)
        env = dict(os.environ, FAKE_ACE_LOG=str(o / "calls.jsonl"), FAKE_ACE_STATE=str(o / "fake_state.json"), FAKE_ACE_FIXTURE=str(fx))
        for st in steps:
            script = st.get(f"{side}_script", st["script"])
            rc, so, se = run(sdir / script, subst(st["args"], o), env=env)
            if rc:
                res.update(ok=False, error=f"{side} {script}: {se[-1500:]}")
                return res
        traces[side] = [json.loads(l) for l in open(o / "calls.jsonl", encoding="utf-8")]
        fs = json.load(open(o / "fake_state.json", encoding="utf-8"))
        if fs["unknown"]:
            res.update(ok=False, error=f"{side} 用了假 CLI 没覆盖的命令：{fs['unknown'][:3]}")
            return res
        outs[side] = o
    roots = [outs["orig"], outs["new"]]

    def clean(tr):
        t = norm(tr, roots)
        for call in t:
            if call[:2] == ["clip", "create"] and "--name" in call:
                call[call.index("--name") + 1] = "<clip>"
        return t

    extra = EXTRA_CALLS.get(label, [])
    new_trace, dropped = drop_extra(clean(traces["new"]), extra)
    same = clean(traces["orig"]) == new_trace
    res["checks"].append({"output": f"ACE 命令序列（{len(traces['orig'])} / {len(traces['new'])} 条）", "same": same})
    if extra:
        res["allowed_extra_calls"] = dropped
        res["checks"].append({"output": f"通用版多出的检查调用 {len(dropped)} / {len(extra)} 条", "same": len(dropped) == len(extra)})
    for st in steps:
        for item in st.get("outputs", []):
            a, b = item if isinstance(item, tuple) else (item, item)
            ok, why = same_file(outs["orig"] / a, outs["new"] / b, roots)
            res["checks"].append({"output": b, "same": ok, "why": why})
    res["ok"] = all(c["same"] for c in res["checks"])
    return res


def prepare_round2(o):
    """第 2 轮从真实的 r1 工程开始：假 CLI 的“当前工程”是 r1；save-as 写出的 r2 由这里先放好（就是 r1 的副本，与 ACE 另存一致）。"""
    r1 = D / "ace" / "r1_timing" / "r1_timing" / "r1_timing.acep"
    (o / "ace" / "r1").mkdir(parents=True)
    shutil.copy2(r1, o / "ace" / "r1" / "r1.acep")
    (o / "ace" / "r2_pitch").mkdir(parents=True)
    shutil.copy2(r1, o / "ace" / "r2_pitch" / "r2_pitch.acep")
    (o / "work").mkdir()
    json.dump({"tracks": [], "notes": {}, "clips": {}, "saved": str(o / "ace" / "r1" / "r1.acep"), "fx_off": [], "unknown": []},
              open(o / "fake_state.json", "w", encoding="utf-8"), ensure_ascii=False)


def ace_cases():
    S, INST, REF = W / "pilot_score.json", W / "ref" / "inst_clip_48k.wav", W / "ref" / "ref_vocal_clip_48k.wav"
    single = [
        dict(script="ace_build.py", args=[S, "{OUT}/ace/r0_baseline.acep", INST, REF, "{OUT}/state_r0.json"], outputs=["state_r0.json"]),
        dict(script="g2p_check.py", args=[S, "{OUT}/g2p.json"], outputs=["g2p.json"]),
        dict(script="ace_readback.py", args=["{OUT}/state_r0.json", S, "{OUT}/readback.json"], outputs=["readback.json"]),
        dict(script="ace_render.py", args=["{OUT}/state_r0.json"]),
        dict(script="ace_export.py", args=["{OUT}/state_r0.json", "{OUT}/exports/r0", "r0_baseline", "--disable-fx"],
             outputs=["exports/r0/r0_baseline_export.json"]),
        dict(script="round1_timing.py", args=["{OUT}/state_r0.json", W / "timing_r0.json", S, "{OUT}/ace/r1_timing.acep",
                                              "{OUT}/round1_plan.json", "--apply"], outputs=["round1_plan.json"]),
    ]
    two = [
        dict(script="ace_build.py", orig_script="ace_build_full.py",
             args=[F / "score_full.json", "{OUT}/ace/full_r0.acep", INST, REF, "{OUT}/state_full.json"], outputs=["state_full.json"]),
        dict(script="ace_readback.py", args=["{OUT}/state_full.json", F / "score_harmony.json", "{OUT}/rb_harmony.json", "--second"],
             outputs=["rb_harmony.json"]),
        dict(script="ace_export.py", args=["{OUT}/state_full.json", "{OUT}/exports/full_r0", "full_r0_harmony", "--disable-fx", "--second"],
             outputs=["exports/full_r0/full_r0_harmony_export.json"]),
        dict(script="round1_mirror.py", args=["{OUT}/state_full.json", F / "round1_plan.json", "{OUT}/mirror.json"], outputs=["mirror.json"]),
    ]
    round2 = [
        dict(script="round2_pitch.py",
             args=[W / "ace_state_r1.json", "{OUT}/ace/r1/r1.acep", "{OUT}/ace/r2_pitch.acep", W / "target_f0.json", "{OUT}/work"],
             outputs=["ace/r2_pitch/r2_pitch.acep", "work/r2_pitch.unpatched.acep",
                      ("work/round2_patch_report.json", "work/round2_patch_main.json"),
                      ("work/ace_state_r2.json", "work/ace_state_r2_pitch.json")]),
    ]
    return [("ace_single_track", single, None), ("ace_two_tracks", two, None), ("ace_round2_pitch", round2, prepare_round2)]


def main():
    out = Path(sys.argv[1]).resolve()
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"输出目录非空：{out}")
    out.mkdir(parents=True, exist_ok=True)
    orig = out / "orig_scripts_with_fake_cli" / "scripts"
    shutil.copytree(D / "scripts", orig)
    (orig.parent / "work").mkdir()
    text = (orig / "ace.py").read_text(encoding="utf-8")
    patched = text.replace(r'CLI = r"C:\Program Files\ACE Studio\acestudio-cli.exe"', f"CLI = {json.dumps([PY, str(FAKE)])}") \
                  .replace("argv = [CLI, *map(str, args)]", "argv = [*CLI, *map(str, args)]")
    assert patched.count("[*CLI,") == 1 and "acestudio-cli.exe" not in patched, "原版 ace.py 的写法变了，替换失败"
    (orig / "ace.py").write_text(patched, encoding="utf-8")
    proj = out / "new_project"
    if not (PKG / "scripts" / "common.py").exists():
        raise SystemExit(f"工作流的通用脚本还不存在：{PKG / 'scripts'}")
    shutil.copytree(PKG / "scripts", proj / "scripts", ignore=shutil.ignore_patterns("examples", "__pycache__"))
    json.dump(PROJECT, open(proj / "project.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    new = proj / "scripts"
    results = []
    for name in VERBATIM:
        if only and name not in only:
            continue
        ok = (new / name).exists() and sha(new / name) == sha(D / "scripts" / name)
        results.append({"case": f"verbatim:{name}", "ok": ok})
    for case in signal_cases():
        if not only or case["name"] in only:
            results.append(run_signal(case, orig, new, out))
            print(json.dumps(results[-1], ensure_ascii=False)[:400], flush=True)
    if not only or "make_ab" in only:
        results.append(run_make_ab(orig, new, out))
    fx = fixture(out)
    for label, steps, prepare in ace_cases():
        if not only or label in only:
            results.append(ace_session(label, steps, orig, new, out, fx, prepare))
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
