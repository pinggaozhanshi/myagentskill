"""解压 BowlRoll 下载的 UST 压缩包（文件名是 Shift-JIS，zipfile 默认按 cp437 读，要转回来）。

用法：python -I extract_ust_zip.py <zip> <out_dir>
out_dir 必须不存在或为空；只写普通文件，拒绝绝对路径和 .. 路径。
"""
import os
import sys
import zipfile


def real_name(info):
    if info.flag_bits & 0x800:  # 已是 UTF-8
        return info.filename
    return info.filename.encode("cp437").decode("cp932")


def main():
    zp, out = sys.argv[1:3]
    if os.path.isdir(out) and os.listdir(out):
        raise SystemExit(f"输出目录非空：{out}")
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        assert z.testzip() is None
        for info in z.infolist():
            name = real_name(info).replace("\\", "/")
            if info.is_dir():
                continue
            if name.startswith("/") or ".." in name.split("/"):
                raise SystemExit(f"可疑路径：{name}")
            dst = os.path.join(out, *name.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(info) as f, open(dst, "wb") as g:
                g.write(f.read())
            print(f"{info.file_size:>8}  {name}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
