@echo off
rem FileGo one-click build script.
rem Requires: Python 3.12 + PyInstaller (py -3.12 -m pip install -r requirements.txt pyinstaller)
rem NOTE: Python 3.14 ships Tcl/Tk 9 (zipfs virtual filesystem) and PyInstaller 6.20 cannot
rem       collect its Tcl/Tk data directories, so the resulting exe fails at startup with
rem       "Tcl data directory ... not found". Build with Python 3.12 (Tcl/Tk 8.6) instead.
rem       Running from source is not affected by this.
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo   FileGo build
echo ==========================================

py -3.12 -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.12 or PyInstaller for it was not found.
    echo         Run: py -3.12 -m pip install -r requirements.txt pyinstaller
    exit /b 1
)

echo [1/3] Stopping running FileGo...
taskkill /IM FileGo.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

echo [2/3] Building EXE with Python 3.12...
py -3.12 -m PyInstaller --noconfirm --clean FileGo-debug.spec
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See the log above.
    exit /b 1
)

echo [3/3] Done!
echo Output: %~dp0dist\FileGo.exe
endlocal