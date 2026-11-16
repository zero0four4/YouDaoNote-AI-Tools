@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === 有道云笔记工具包 · 一键安装 ===
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 没找到 python，请先装 Python 3.9+ 并勾选 Add to PATH
  pause
  exit /b 1
)
python "tools\setup.py"
echo.
echo 装完试一下:  python tools\ynote.py list -f 0
pause
