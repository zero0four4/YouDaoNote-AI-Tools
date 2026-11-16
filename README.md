# ynote-tools · 有道云笔记命令行工具包

> 把 **HTML / Markdown** 变成带格式的有道笔记，并把整个笔记库拉到本地检索。
> 基于有道官方 CLI（走官方 MCP 接口），本包只负责「装、配、用」这三件事。

简体中文 · Windows 10/11 · Python 3.9+ · 依赖有道云笔记账号（申请接口 Key 需先绑手机号）

---

## 它解决什么问题

有道官方接口只有三个原语：**读纯文本、新建富文本、搜索**。所以「用脚本/AI 改一篇手写的富文本笔记」是做不到的——读回来只剩文字，写只能新建。

这个包把能做的做顺：

| 需求 | 能不能 | 怎么做 |
|---|---|---|
| 新建一篇带格式的笔记（表格/列表/代码块/图片） | ✅ | `ynote.py save-html` |
| 把生成的内容插进**已有**笔记 | ✅ 推荐 | `ynote.py clip` 写剪贴板 → 编辑器里 `Ctrl+V` |
| 读一篇笔记的文字 | ✅ | `ynote.py read <fileId>` |
| 读一篇笔记的格式 / 图片 / 表格 | ❌ | 接口只返回纯文本，结构会丢 |
| **原地修改**一篇富文本笔记 | ❌ | 官方没有对应接口 |
| 修改 `.md` 笔记 | ✅ | `youdaonote update <fileId> --file x.md`（仅 md） |
| 全库文字快照 / 本地检索 | ✅ | `ynote_snapshot.py` → md + `index.csv` |
| 云端搜索 | ✅ | `ynote.py search 关键字`（每页 15 条） |

一句话：**新建随便玩，原地改不可能**。

---

## 快速开始

```bat
:: 1) 准备 CLI（首次约 40 MB 下载）
python tools\setup.py

:: 2) 按提示粘贴 API Key
::    在 https://mopen.163.com/#/dashboard 创建（账号需绑手机号）

:: 3) 验证：会打印你云端的根目录
python tools\ynote.py list -f 0
```

不会敲命令就双击 `install.bat`。

已经装过 CLI 的机器可以跳过下载：

```bat
python tools\setup.py --exe "D:\tools\youdaonote\windows-x64\youdaonote.exe"
```

> 老 CPU（不支持 AVX2）下载后运行会直接退出，加 `--baseline` 换兼容包。

---

## 常用命令

```bat
python tools\ynote.py tree                                  :: 全库目录树（含 fileId）
python tools\ynote.py list -f 0                             :: 根目录一层
python tools\ynote.py list -f <目录id>                       :: 某个目录
python tools\ynote.py read <fileId>                         :: 读正文（纯文本）
python tools\ynote.py search 关键字                          :: 云端搜索
python tools\ynote.py clip --html-file 片段.html             :: 写入剪贴板（然后 Ctrl+V）
python tools\ynote.py save-html --title "标题" --html-file 笔记.html
python tools\ynote.py save-html --title "标题" --html-file 笔记.html --image 图1.png --image 图2.png
python tools\ynote.py delete <fileId> --yes                 :: 删除（不可逆，去回收站找回）
python tools\ynote_snapshot.py --out D:\notes_snapshot      :: 全库文字快照
```

三种最典型用法：

**① 往已有笔记里插内容（保真度最高）**

```bat
python tools\ynote.py clip --html-file 片段.html
```

打开笔记、光标点到位、`Ctrl+V`。表格、列表、加粗、颜色、代码块、图片都能带过去。

**② 直接建一篇新笔记（可带本地图片）**

```bat
python tools\ynote.py save-html --title "调试记录" --html-file 记录.html --image 截图1.png
```

`--parent <目录id>` 可指定目录。

**③ 全库文字快照（当检索库 / 当安全网）**

```bat
python tools\ynote_snapshot.py --out D:\notes_snapshot
```

产物：`<out>\<目录>\<标题>.md` + `index.csv` + `_SUMMARY.txt`。只有文字，图片/脑图/附件不会保存。

---

## 格式保真度（实测）

| HTML 写法 | 有道里长什么样 |
|---|---|
| `<table>` | ✅ 真表格（有边框） |
| `<b> <i> <u> <s>` | ✅ 加粗 / 斜体 / 下划线 / 删除线 |
| `<span style="color:#C00000">` | ✅ 变色 |
| `<font color="red">` | ❌ 不生效（必须用 span style） |
| `<ul> <ol>` | ✅ 圆点 / 1. 2. 编号 |
| `<code>` | ✅ 灰底行内代码 |
| `<pre><code>` | ✅ 真正的代码块（自动带行号） |
| `<blockquote>` | ✅ 左侧竖线引用 |
| `<img src="data:image/png;base64,...">` | ✅ 走 `save-html --image` 上传 |
| `<h1> ~ <h3>` | ✅ 标题层级 |

`examples/format-demo.html` 把上表每种写法都写了一遍，粘进去对照即可。
`clip`（剪贴板）保真度最高；`save-html` 走官方上传链路，图片能真实显示。

---

## 常见坑（都踩过）

1. **中文变 `◆` 乱码**：PowerShell 的 `Set-Clipboard -AsHtml` 会这样。
   本包的 `ynote_clip.py` 按 UTF-8 字节计算 CF_HTML 偏移，已修好；别再用 PS 原生命令。
2. **`EPERM ... .youdaonote.json`**：下载来的 exe 带「低完整性标签」，写不了用户目录。
   `setup.py` 会自动 `icacls <exe> /setintegritylevel Medium`；没生效就用管理员 CMD 手工执行一次。
3. **`Session not found` / `HTTP 404`**：MCP 是 SSE 会话，偶尔过期，重跑一次即可（`read` 已内置重试）。
4. **标题里有 `\ / : * ? " < > |`** 服务端会拒，先替换掉。
5. **`save --json` 里的 `folderId` 会被静默忽略**，要用 `parentId`。
6. **Key 绑定账号**：拿到 Key 等于拿到笔记读写权，别提交、别外发。
7. **中文 Windows 解码**：脚本内部统一按 UTF-8 读子进程输出，自己写扩展时别用 `text=True`（会按 GBK 解码报错）。

---

## 目录结构

```
.
├─ README.md
├─ install.bat              双击安装（调 tools\setup.py）
├─ LICENSE
├─ docs\
│   └─ workflow.md          接口边界、为什么不能原地改、HTML 书写约定
├─ tools\
│   ├─ setup.py             下载/定位 CLI、修完整性标签、配置 Key、自检
│   ├─ ynote.py             list / tree / read / search / clip / save-html / delete
│   ├─ ynote_clip.py        HTML → 剪贴板（UTF-8 版 CF_HTML）
│   └─ ynote_snapshot.py    全库文字快照
├─ examples\
│   └─ format-demo.html     格式对照样例
└─ bin\                     首次 setup.py 下载的 youdaonote.exe（不入库）
```

没有第三方依赖，只用 Python 标准库；不需要 `pip install` 任何东西。

---

## 许可与免责

- 本包脚本：MIT（见 `LICENSE`），随便改、随便用、随便传。
- 有道云笔记 CLI：由网易官方发布（`artifact.lx.netease.com`），本包只负责下载与配置，未修改其二进制。
- 接口文档：`https://mopen.163.com/doc/`（MCP server，`x-api-key` 鉴权）。
- 非官方项目；接口或 CLI 行为变化可能导致脚本失效，提 issue 就好。
- 用 `delete` 前请确认——**删除没有二次确认**。
