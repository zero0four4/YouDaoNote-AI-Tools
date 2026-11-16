#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup.py — 一键准备有道云笔记 CLI（给拿到这个文件夹的人用）

做四件事：
  1. 检查 Python 版本
  2. 把官方 CLI 放到 <本包>\\bin\\youdaonote.exe（已有就跳过；也可以用 --exe 指过去）
  3. 配置 API Key（写 %USERPROFILE%\\.youdaonote.json）
  4. 自检：能列出根目录就算成功

用法：
  python tools\\setup.py                     # 交互式（会问 key）
  python tools\\setup.py --api-key xxxx
  python tools\\setup.py --exe "D:\\youdaonote\\windows-x64\\youdaonote.exe"
  python tools\\setup.py --skip-download     # 只想改 key
"""
import argparse
import getpass
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
BIN_DIR = os.path.join(PKG_ROOT, "bin")
EXE = os.path.join(BIN_DIR, "youdaonote.exe")
CONF = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".youdaonote.json")

WIN_X64 = ("https://artifact.lx.netease.com/download/youdaonote-cli/"
           "youdaonote-cli-windows-x64.tar.gz")
WIN_X64_BASELINE = ("https://artifact.lx.netease.com/download/youdaonote-cli/"
                    "youdaonote-cli-win-x64-bl.tar.gz")

KEY_URL = "https://mopen.163.com/#/dashboard"


def log(msg):
    print("[setup] " + msg)


def check_python():
    if sys.version_info < (3, 9):
        raise SystemExit("需要 Python 3.9+，当前 %s" % sys.version.split()[0])
    log("Python %s OK" % sys.version.split()[0])


def find_exe():
    if os.path.isfile(EXE):
        return EXE
    found = shutil.which("youdaonote")
    if found:
        log("用 PATH 里的 CLI：%s" % found)
        return found
    return None


def download(force_baseline=False):
    url = WIN_X64_BASELINE if force_baseline else WIN_X64
    os.makedirs(BIN_DIR, exist_ok=True)
    log("下载 CLI：%s" % url)
    data = urllib.request.urlopen(url, timeout=600).read()
    log("下载完成 %.1f MB，解压…" % (len(data) / 1048576.0))
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = [m for m in tf.getmembers()
                   if m.isfile() and os.path.basename(m.name) in ("youdaonote.exe", "youdaonote")]
        if not members:
            raise SystemExit("压缩包里没找到 youdaonote.exe，手动下载后解压到 bin\\ 即可")
        with open(EXE, "wb") as out:
            out.write(tf.extractfile(members[0]).read())
    log("已放到 %s" % EXE)
    os.chmod(EXE, 0o755)
    return EXE


def _run(cmd, **kw):
    """跑子进程，强制 UTF-8 解码（中文 Windows 默认 cp936 会炸）。"""
    return subprocess.run(cmd, capture_output=True, encoding="utf-8",
                          errors="replace", **kw)


def fix_integrity(exe):
    """从低完整性来源拷来的 exe 会写不了用户目录（EPERM），把标签提到 Medium。"""
    if os.name != "nt":
        return
    try:
        out = _run(["icacls", exe]).stdout or ""
    except Exception:  # noqa: BLE001
        return
    if "Low Mandatory Level" in out:
        r = _run(["icacls", exe, "/setintegritylevel", "Medium"])
        if r.returncode == 0:
            log("完整性标签 Low → Medium（否则 CLI 写配置会报 EPERM）")
        else:
            log("警告：改不了完整性标签（需要管理员/更高权限），"
                "若后面报 EPERM 请用管理员 CMD 跑一次：")
            log('  icacls "%s" /setintegritylevel Medium' % exe)


def read_conf():
    if not os.path.isfile(CONF):
        return {}
    try:
        with open(CONF, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def set_key(exe, key):
    code = _run([exe, "config", "set", "apiKey", key])
    if code.returncode == 0:
        log("API Key 已写入 %s（用 CLI 自己写）" % CONF)
        return
    conf = read_conf()
    conf.setdefault("backend", "mcp")
    conf.setdefault("mcp", {"server": "https://open.mail.163.com/api/ynote/mcp/sse",
                            "apiKey": ""})
    conf["mcp"]["apiKey"] = key
    if not conf.get("mcp", {}).get("server"):
        conf["mcp"]["server"] = "https://open.mail.163.com/api/ynote/mcp/sse"
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)
    log("CLI 写配置失败，已直接写 %s" % CONF)


def verify(exe):
    r = _run([exe, "list", "-f", "0"])
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip()[:800])
    if r.returncode == 0:
        log("自检通过：能列出根目录")
        return True
    if "apiKey" in out or "unauthorized" in out.lower() or "401" in out:
        log("自检失败：key 不对或没生效，去 %s 重新复制" % KEY_URL)
    else:
        log("自检失败（退出码 %d）" % r.returncode)
    return False


def main():
    ap = argparse.ArgumentParser(description="准备有道云笔记 CLI")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--exe", default=None, help="已有 youdaonote.exe，复制到 bin\\")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--baseline", action="store_true",
                    help="老 CPU（无 AVX2）用 baseline 包")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    check_python()

    exe = find_exe()
    if args.exe:
        os.makedirs(BIN_DIR, exist_ok=True)
        shutil.copy2(args.exe, EXE)
        exe = EXE
        log("已从 %s 复制到 bin\\" % args.exe)
    if not exe:
        if args.skip_download:
            raise SystemExit("还没装 CLI，去掉 --skip-download 重跑")
        exe = download(args.baseline)
    fix_integrity(exe)

    key = args.api_key
    if not key:
        current = (read_conf().get("mcp") or {}).get("apiKey") or ""
        if current:
            log("已有 key（%s…），要换直接 Ctrl+C 后用 --api-key 重跑" % current[:8])
        else:
            print("去 %s 创建 API Key（有道账号需先绑手机号）" % KEY_URL)
            key = getpass.getpass("粘贴 API Key（回车跳过）：").strip()
    if key:
        set_key(exe, key)

    if not args.no_verify:
        verify(exe)
    log("完成。试一下：python tools\\ynote.py list -f 0")


if __name__ == "__main__":
    main()
