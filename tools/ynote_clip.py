#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ynote_clip.py — 把 HTML 片段写进 Windows 剪贴板（CF_HTML + CF_UNICODETEXT）

为什么不用 PowerShell 的 Set-Clipboard -AsHtml：
  实测 PS 5.1 的 -AsHtml 会把中文写成乱码（有道的粘贴端按非 UTF-8 解读），
  英文数字正常、中文全变 ◆。这里自己按 CF_HTML 规范拼字节，
  显式带 <meta charset="utf-8">，中文已验证正常。

用法：
  python ynote_clip.py --html-file 片段.html
  python ynote_clip.py --html "<p>内容</p>"
  python ynote_clip.py --html-file 片段.html --verify

注意：CF_HTML 的 StartHTML/EndHTML/StartFragment/EndFragment 是**字节偏移**，
  不是字符数；中文按 UTF-8 编码后每字 3 字节，必须用 len(bytes) 计算。
"""
import argparse
import ctypes
import re
import sys
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t


def build_cf_html(fragment: str) -> bytes:
    """拼出符合 CF_HTML 0.9 规范的字节串（偏移全部按 UTF-8 字节算）。"""
    head_tpl = (
        "Version:0.9\r\n"
        "StartHTML:{sh:010d}\r\n"
        "EndHTML:{eh:010d}\r\n"
        "StartFragment:{sf:010d}\r\n"
        "EndFragment:{ef:010d}\r\n"
    )
    pre = '<html><head><meta charset="utf-8"></head><body>\r\n'
    post = "\r\n</body></html>"

    head_len = len(head_tpl.format(sh=0, eh=0, sf=0, ef=0).encode("utf-8"))
    pre_b = pre.encode("utf-8")
    frag_b = fragment.encode("utf-8")
    post_b = post.encode("utf-8")

    start_html = head_len
    start_frag = start_html + len(pre_b)
    end_frag = start_frag + len(frag_b)
    end_html = end_frag + len(post_b)

    head = head_tpl.format(
        sh=start_html, eh=end_html, sf=start_frag, ef=end_frag
    ).encode("utf-8")
    assert len(head) == head_len, "头部长度不稳定，检查模板"
    return head + pre_b + frag_b + post_b


def html_to_plain(fragment: str) -> str:
    """粗糙的 HTML → 纯文本，只作为 CF_UNICODETEXT 兜底。"""
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", fragment)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|blockquote|pre)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", "", s)
    s = (
        s.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _alloc_and_fill(payload: bytes):
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not handle:
        raise OSError("GlobalAlloc 失败: %d" % ctypes.get_last_error())
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        raise OSError("GlobalLock 失败: %d" % ctypes.get_last_error())
    ctypes.memmove(ptr, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    return handle


def set_clipboard(fragment: str) -> None:
    html_bytes = build_cf_html(fragment)
    plain = html_to_plain(fragment)
    text_bytes = plain.encode("utf-16-le") + b"\x00\x00"

    if not user32.OpenClipboard(None):
        raise OSError("OpenClipboard 失败: %d" % ctypes.get_last_error())
    try:
        if not user32.EmptyClipboard():
            raise OSError("EmptyClipboard 失败: %d" % ctypes.get_last_error())
        fmt_html = user32.RegisterClipboardFormatW("HTML Format")
        if not user32.SetClipboardData(fmt_html, _alloc_and_fill(html_bytes)):
            raise OSError("SetClipboardData(HTML) 失败: %d" % ctypes.get_last_error())
        if not user32.SetClipboardData(CF_UNICODETEXT, _alloc_and_fill(text_bytes)):
            raise OSError("SetClipboardData(TEXT) 失败: %d" % ctypes.get_last_error())
    finally:
        user32.CloseClipboard()


def read_back() -> str:
    fmt = user32.RegisterClipboardFormatW("HTML Format")
    if not user32.OpenClipboard(None):
        raise OSError("OpenClipboard 失败: %d" % ctypes.get_last_error())
    try:
        handle = user32.GetClipboardData(fmt)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        size = kernel32.GlobalSize(handle)
        data = ctypes.string_at(ptr, size)
        kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    return data.decode("utf-8", "replace").rstrip("\x00")


def main() -> int:
    ap = argparse.ArgumentParser(description="把 HTML 写进剪贴板（CF_HTML, UTF-8）")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--html", help="直接给 HTML 片段")
    src.add_argument("--html-file", help="从文件读 HTML 片段")
    ap.add_argument("--verify", action="store_true", help="写入后读回并打印校验信息")
    args = ap.parse_args()

    if args.html_file:
        with open(args.html_file, "r", encoding="utf-8") as f:
            fragment = f.read()
    else:
        fragment = args.html

    set_clipboard(fragment)
    print("已写入剪贴板：HTML %d 字节, 纯文本 %d 字"
          % (len(build_cf_html(fragment)), len(html_to_plain(fragment))))

    if args.verify:
        back = read_back()
        print("读回 HTML 长度: %d" % len(back))
        print("读回含中文: %s" % ("是" if re.search(r"[\u4e00-\u9fff]", back) else "否"))
        print("--- 读回尾部 160 字 ---")
        print(back[-160:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
