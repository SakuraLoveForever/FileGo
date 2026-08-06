@echo off
rem FileGo 一键打包脚本
rem 依赖: PyInstaller (pip install pyinstaller)
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   FileGo 一键打包
echo ==========================================

echo [1/3] 停止正在运行的 FileGo...
taskkill /IM FileGo.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul

echo [2/3] 开始构建 EXE...
pyinstaller --noconfirm --clean FileGo-debug.spec
if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请查看上方日志。
    exit /b 1
)

echo [3/3] 构建完成！
echo 输出: %~dp0dist\FileGo.exe
endlocal
