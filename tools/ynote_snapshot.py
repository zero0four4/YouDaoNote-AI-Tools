#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ynote_snapshot.py — 把有道云笔记全库「文字」拉成本地 md 快照

定位：
  * 安全网：云端随手改坏了，至少还有一份文字可查（**图片、脑图、白板、附件必然丢**，
    真正的兜底请用有道客户端的「笔记历史」）
  * 检索底座：本地 md 可以直接 grep，AI 也能一次读进来
  * 与「原地改富文本」无关：有道不提供 update 富文本的接口，这个脚本只读

用法：
  python ynote_snapshot.py                  # 输出到 <本包>\\snapshot\\<时间戳>\\
  python ynote_snapshot.py --out D:\\tmp\\snap
  python ynote_snapshot.py --root <dirId>   # 只抓某个目录

产物：
  <out>\\<目录镜像>\\<标题>.md   每篇一篇，头部有 fileId 与抓取时间
  <out>\\index.csv              fileId / 标题 / 相对路径 / 字符数 / 抓取时间
  <out>\\_SUMMARY.txt           统计与失败清单
"""
import argparse
import csv
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ynote  # noqa: E402

BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')


def safe_name(name, fallback="untitled"):
    name = BAD_CHARS.sub("_", name).strip().strip(".")
    name = name or fallback
    if len(name) > 120:
        name = name[:120]
    return name


def md_filename(note_name):
    """把笔记标题变成 .md 文件名，避免 xxx.note.md 这种双后缀。"""
    base = note_name
    for suffix in (".note", ".md", ".txt", ".html", ".htm"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
            break
    return safe_name(base) + ".md"


def now_stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def collect(folder_id=ynote.ROOT_ID, parts=(), depth=0, max_depth=8):
    """递归收集 (相对目录list, 标题, fileId)。"""
    for item in ynote.list_dir(folder_id):
        if item["is_dir"]:
            if depth + 1 >= max_depth:
                continue
            yield from collect(item["id"], parts + (item["name"],), depth + 1, max_depth)
        else:
            yield parts, item["name"], item["id"]


def main():
    ap = argparse.ArgumentParser(description="有道笔记文字快照")
    ap.add_argument("--out", default=None)
    ap.add_argument("--root", default=ynote.ROOT_ID)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = args.out or os.path.join(PKG_ROOT, "snapshot", stamp)
    os.makedirs(out_root, exist_ok=True)

    rows, failures = [], []
    total_chars = 0

    for parts, name, fid in collect(args.root):
        rel_dir = os.path.join(*parts) if parts else ""
        dest_dir = os.path.join(out_root, *[safe_name(p) for p in parts]) \
            if parts else out_root
        os.makedirs(dest_dir, exist_ok=True)
        target = os.path.join(dest_dir, md_filename(name))
        try:
            text = ynote.read_note(fid)
        except Exception as exc:  # noqa: BLE001
            failures.append("%s (%s): %s" % (name, fid, exc))
            if not args.quiet:
                print("[FAIL] %s  %s" % (name, exc))
            continue
        header = (
            "<!-- 有道快照\n"
            "  fileId: %s\n"
            "  标题: %s\n"
            "  目录: %s\n"
            "  抓取: %s\n"
            "  说明: 仅文字；图片/脑图/表格结构不保留\n"
            "-->\n\n" % (fid, name, rel_dir or "(根目录)", now_stamp())
        )
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(header)
            f.write(text)
        rows.append(
            {
                "fileId": fid,
                "标题": name,
                "相对路径": os.path.relpath(target, out_root),
                "字符数": len(text),
                "抓取时间": now_stamp(),
            }
        )
        total_chars += len(text)
        if not args.quiet:
            print("[OK] %-40s %6d 字  %s" % (name[:40], len(text), fid))

    csv_path = os.path.join(out_root, "index.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fileId", "标题", "相对路径", "字符数", "抓取时间"])
        w.writeheader()
        w.writerows(rows)

    summary = [
        "有道笔记文字快照",
        "输出目录: %s" % out_root,
        "笔记数: %d" % len(rows),
        "总字符: %d" % total_chars,
        "失败: %d" % len(failures),
    ] + (["", "失败清单:"] + failures if failures else [])
    with open(os.path.join(out_root, "_SUMMARY.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")

    print("\n".join(summary))
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
