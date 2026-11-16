#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ynote.py — 有道云笔记 CLI 的薄封装（给 AI/脚本用）

它只做三件事：
  1. 屏蔽 youdaonote.exe 的路径与 UTF-8 输出问题（自动找 bin\\ / PATH / YNOTE_EXE）
  2. 把 `list` 的表格文本解析成结构化数据（id / name / is_dir）
  3. 把 clip-save 的 JSON 组装过程收进来，调用方只需要给标题 + HTML

能力边界（2026-11-16 实测，别再猜）：
  - 读富文本笔记 → 只有纯文本（服务端 getNoteTextContent 的 isRaw=false 就是"处理成纯文本"）
  - 改富文本笔记 → 不可能（updateMarkdownNote 只吃 .md）
  - 新建富文本笔记 → 只能走 clip-save（clipperSaveWithImages，接受 HTML + base64 图片）
  - save 的 type 只支持 note / md / mindmap2；type=note 要求 Bulb JSON（专有格式，不可手写）

用法：
  python ynote.py list -f 0
  python ynote.py tree
  python ynote.py read <fileId>
  python ynote.py search 关键字
  python ynote.py clip --html-file 片段.html
  python ynote.py save-html --title 标题 --html-file 片段.html [--parent <dirId>] [--image 图.png]
  python ynote.py delete <fileId> --yes
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_exe():
    """优先级：环境变量 YNOTE_EXE → 本包 bin\\ → PATH 里的 youdaonote。"""
    env = os.environ.get("YNOTE_EXE")
    if env and os.path.isfile(env):
        return env
    for name in ("youdaonote.exe", "youdaonote"):
        cand = os.path.join(PKG_ROOT, "bin", name)
        if os.path.isfile(cand):
            return cand
    found = shutil.which("youdaonote")
    if found:
        return found
    return os.path.join(PKG_ROOT, "bin", "youdaonote.exe")


EXE = _resolve_exe()
ROOT_ID = "0"
LINE_RE = re.compile(r"^(?P<emoji>\S+)\s+(?P<id>[0-9A-Za-z]+)\t(?P<name>.*)$")
FOLDER_EMOJI = "\U0001F4C1"  # 📁
NOTE_EMOJI = "\U0001F4C4"  # 📄


def _run(*args, stdin_text=None):
    """跑 CLI，返回 (returncode, stdout+stderr 文本)。CLI 输出是 UTF-8。"""
    if not os.path.isfile(EXE):
        raise FileNotFoundError(
            "找不到 CLI：%s —— 先跑一次 setup：python tools\\setup.py（会下载并配置）" % EXE
        )
    proc = subprocess.run(
        [EXE, *args],
        input=(stdin_text.encode("utf-8") if stdin_text is not None else None),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def list_dir(folder_id=ROOT_ID):
    """列出一层目录，返回 [{'id','name','is_dir'}]。"""
    code, out = _run("list", "-f", str(folder_id))
    if code != 0 and not out.strip():
        raise RuntimeError("list 失败（folder=%s）：%s" % (folder_id, out.strip()))
    items = []
    for line in out.splitlines():
        line = line.rstrip("\r")
        m = LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        emoji = m.group("emoji")
        # 以 CLI 的图标判定：📁=文件夹，📄=笔记。
        # 不能靠后缀猜：clip-save 建出来的富文本笔记标题没有 .note 后缀。
        if emoji == FOLDER_EMOJI:
            is_dir = True
        elif emoji == NOTE_EMOJI:
            is_dir = False
        else:
            is_dir = not name.lower().endswith(
                (".note", ".md", ".txt", ".html", ".htm")
            )
        items.append({"id": m.group("id"), "name": name, "is_dir": is_dir})
    return items


def read_note(file_id, retries=2):
    """读一篇笔记的文本内容（富文本会变成纯文本，结构丢失）。

    MCP 是 SSE 会话，偶尔会返回 "Session not found"，重试一次基本都能过。
    """
    last = ""
    for _ in range(retries + 1):
        code, out = _run("read", str(file_id))
        if code == 0:
            return out
        last = out.strip()
        if "Session not found" not in last and "HTTP 404" not in last:
            break
    raise RuntimeError("read 失败（%s）：%s" % (file_id, last))


def search(keyword):
    code, out = _run("search", keyword)
    if code != 0:
        raise RuntimeError("search 失败：%s" % out.strip())
    return out


def clip_html(html_fragment):
    """把 HTML 片段写进剪贴板（委托 ynote_clip.py，UTF-8 版 CF_HTML）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ynote_clip

    ynote_clip.set_clipboard(html_fragment)
    return ynote_clip.build_cf_html(html_fragment)


def new_rich_note(title, html, parent_id=None, images=None):
    """用 clip-save 新建一篇富文本笔记。

    html: HTML 字符串；images: [{'path': 本地png路径}] 或 [{'base64':..,'mime'..,'url'..}]
    返回 dict（含 fileId）。
    """
    payload = {
        "title": title,
        "bodyHtml": html,
        "sourceUrl": "https://example.com",
        "images": [],
    }
    for key, img in enumerate(images or []):
        if "path" in img:
            with open(img["path"], "rb") as f:
                import base64

                data = base64.b64encode(f.read()).decode("ascii")
            mime = img.get("mime", "image/png")
            url = img.get("url", "https://example.com/%d.png" % key)
            payload["images"].append({"url": url, "mimeType": mime, "data": data})
        else:
            payload["images"].append(img)
    if parent_id:
        payload["parentId"] = str(parent_id)

    fd, path = tempfile.mkstemp(suffix=".json", prefix="ynote_")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        code, out = _run("clip-save", "--file", path, "--json")
        if code != 0:
            raise RuntimeError("clip-save 失败：%s" % out.strip())
        return json.loads(out.strip().splitlines()[-1])
    finally:
        os.unlink(path)


def delete_note(file_id, confirm=False):
    if not confirm:
        raise RuntimeError("delete 需要 --yes 确认")
    code, out = _run("delete", str(file_id))
    if code != 0:
        raise RuntimeError("delete 失败：%s" % out.strip())
    return out


def walk(folder_id=ROOT_ID, depth=0, max_depth=6):
    """递归遍历，yield (层级, id, name, is_dir)。"""
    for item in list_dir(folder_id):
        yield depth, item["id"], item["name"], item["is_dir"]
        if item["is_dir"] and depth + 1 < max_depth:
            for sub in walk(item["id"], depth + 1, max_depth):
                yield sub


def _fmt_tree():
    for depth, fid, name, is_dir in walk():
        mark = "DIR " if is_dir else "NOTE"
        print("%s%s %-4s %s  %s" % ("  " * depth, "-", mark, name, fid))


def main():
    ap = argparse.ArgumentParser(description="有道云笔记 CLI 封装")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出一层目录")
    p_list.add_argument("-f", "--folder", default=ROOT_ID)

    sub.add_parser("tree", help="递归打印目录树")

    p_read = sub.add_parser("read", help="读一篇笔记")
    p_read.add_argument("file_id")

    p_search = sub.add_parser("search", help="搜索笔记")
    p_search.add_argument("keyword")

    p_clip = sub.add_parser("clip", help="把 HTML 写进剪贴板")
    g = p_clip.add_mutually_exclusive_group(required=True)
    g.add_argument("--html-file")
    g.add_argument("--html")

    p_save = sub.add_parser("save-html", help="新建富文本笔记（走 clip-save）")
    p_save.add_argument("--title", required=True)
    p_save.add_argument("--html-file", required=True)
    p_save.add_argument("--parent", default=None)
    p_save.add_argument("--image", action="append", default=[],
                        help="本地图片路径，可多次指定")

    p_del = sub.add_parser("delete", help="删除笔记（需 --yes）")
    p_del.add_argument("file_id")
    p_del.add_argument("--yes", action="store_true")

    args = ap.parse_args()
    try:
        if args.cmd == "list":
            for it in list_dir(args.folder):
                print(("DIR  " if it["is_dir"] else "NOTE ") + it["name"] + "  " + it["id"])
        elif args.cmd == "tree":
            _fmt_tree()
        elif args.cmd == "read":
            sys.stdout.write(read_note(args.file_id))
        elif args.cmd == "search":
            print(search(args.keyword))
        elif args.cmd == "clip":
            html = (open(args.html_file, encoding="utf-8").read()
                    if args.html_file else args.html)
            clip_html(html)
            print("已写入剪贴板（%d 字）—— 到有道笔记里按 Ctrl+V" % len(html))
        elif args.cmd == "save-html":
            html = open(args.html_file, encoding="utf-8").read()
            imgs = [{"path": p} for p in args.image]
            print(json.dumps(new_rich_note(args.title, html, args.parent, imgs),
                             ensure_ascii=False))
        elif args.cmd == "delete":
            print(delete_note(args.file_id, args.yes))
    except Exception as exc:  # noqa: BLE001 - CLI 场景下直接报错更有用
        print("[ERROR] " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
