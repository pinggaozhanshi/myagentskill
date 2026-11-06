"""acestudio-cli 薄封装：参数列表直传（不经 shell），--json 解析，所有调用记录到 work/ace_calls.jsonl。

CLI 位置：project.json 的 ace_cli（也可以写成列表，回归测试用它接假的 CLI），默认 ACE Studio 的安装位置。
require_safe_project()：每次新建 / 改写工程前的检查——当前工程有未保存改动，或既不是空临时工程、
也不是本项目 ace/（及 project.json 的 own_ace_dirs）下的工程时停止，不替用户保存或丢弃。
"""
import datetime
import json
import os
import subprocess

import common

CLI = common.CONFIG.get("ace_cli") or r"C:\Program Files\ACE Studio\acestudio-cli.exe"
LOG = os.path.join(common.ROOT, "work", "ace_calls.jsonl")


class AceError(RuntimeError):
    pass


def cli(*args, parse=True, check=True, timeout=600):
    argv = [*(CLI if isinstance(CLI, list) else [CLI]), *map(str, args)]
    if parse and "--json" not in args:
        argv.append("--json")
    p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    rec = {"time": datetime.datetime.now().isoformat(timespec="seconds"), "args": list(map(str, args)),
           "exit": p.returncode, "stdout": p.stdout[:4000], "stderr": p.stderr[:4000]}
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if check and p.returncode != 0:
        raise AceError(f"{' '.join(map(str, args))} -> exit {p.returncode}\n{p.stderr.strip()}")
    if not parse:
        return p.stdout
    out = p.stdout.strip()
    return json.loads(out) if out else {}


def require_safe_project():
    dirty = cli("project", "dirty")
    print("before:", dirty)
    path = os.path.normcase(os.path.abspath(dirty["projectPath"])) if dirty.get("projectPath") else ""
    own_dirs = [os.path.join(common.ROOT, "ace"), *common.CONFIG.get("own_ace_dirs", [])]
    own = bool(path) and any(path.startswith(os.path.normcase(os.path.abspath(d)) + os.sep) for d in own_dirs)
    if dirty.get("dirty"):
        raise SystemExit("当前 ACE 工程有未保存改动，停止：不替用户保存或丢弃。")
    if not (dirty.get("isTempProject") and not cli("track", "list").get("tracks")) and not own:
        raise SystemExit("当前 ACE 工程既不是空临时工程，也不是本项目 ace/ 下的工程，停止：请先让用户确认。")
    return dirty
