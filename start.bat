@echo off
chcp 65001 >nul
echo ========================================
echo   图片智能识别管理系统 - 启动中...
echo ========================================

set PYTHON=C:\Users\Axuan\.workbuddy\binaries\python\envs\default\Scripts\python.exe
if not exist %PYTHON% (
    set PYTHON=D:\Anaconda\python.exe
)

echo 安装依赖中...
%PYTHON% -m pip install flask requests werkzeug -q

echo 启动服务...
echo 访问地址: http://localhost:5000
echo 按 Ctrl+C 停止服务
echo ========================================
%PYTHON% app.py
pause
