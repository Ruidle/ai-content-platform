@echo off
chcp 65001 >nul
title AI 内容生成平台 - 启动器
echo ============================================
echo   AI 内容生成平台 - 一键启动
echo ============================================
echo.
echo [1/2] 正在启动后端服务（后台运行）...
start "后端服务" /min cmd /k "cd /d c:\Users\86198\Desktop\动态部署\ai-content-platform\backend && py -3.13 -m uvicorn main:app --host 0.0.0.0 --port 8000"
echo       后端已启动（最小化窗口运行）
echo.
echo       等待后端就绪...
timeout /t 4 /nobreak >nul
echo.
echo [2/2] 正在启动 cloudflared 隧道（获取公网地址）...
echo.
echo ============================================
echo   公网地址在下方 "Your quick Tunnel" 处
echo   复制 https://xxx.trycloudflare.com 地址
echo   直接在浏览器打开即可使用
echo ============================================
echo.
D:\cloudflared.exe tunnel --url http://localhost:8000
pause
