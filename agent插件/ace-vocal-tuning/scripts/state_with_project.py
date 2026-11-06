"""复制一份 ACE 状态文件，只换工程路径（save-as 之后轨道、片段 UUID 不变）。

用法：python -I state_with_project.py <in_state.json> <acep_path> <out_state.json>
"""
import json
import sys


def main():
    st = json.load(open(sys.argv[1], encoding="utf-8-sig"))
    p = sys.argv[2].replace("\\", "/")
    st["project"] = {"savedPath": p, "projectPath": p}
    json.dump(st, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("state ->", sys.argv[3])


if __name__ == "__main__":
    main()
