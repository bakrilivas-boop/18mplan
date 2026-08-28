@echo off
chcp 65001 >nul
title Google One / Jio 18个月 AI Pro 激活链接检测器 - 桌面版

echo =======================================================
echo   正在启动 Google One 激活链接检测工具 (桌面版)...
echo =======================================================
echo.

python gui.py

if %errorlevel% neq 0 (
    echo.
    echo 启动出现异常，请按任意键退出...
    pause >nul
)
