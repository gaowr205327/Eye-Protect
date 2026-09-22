@echo off
rem ============================================
rem  一键打包脚本：生成图标 -> PyInstaller 打包
rem
rem  用法：
rem    build.bat              单文件版 -> dist\护眼助手.exe
rem                           优点：单个 exe，分发方便
rem                           缺点：每次启动要解压，约 30 秒
rem    build.bat --onedir     目录版   -> dist\护眼助手\护眼助手.exe
rem                           优点：启动约 2~3 秒
rem                           缺点：产物是一个文件夹
rem    build.bat --no-pause   供自动化调用，结束不暂停（可与上面任意组合）
rem
rem  重要：必须使用带 tkinter 的 Python 解释器。
rem  说明：刻意不使用 --clean。本机沙箱的 safe-delete 拦截会把
rem        PyInstaller 清理缓存的动作判为 EPERM，导致构建随机失败；
rem        不清理缓存反而更快，PyInstaller 会自行判断哪些步骤需重建。
rem        WorkBuddy 托管 Python 不含 tkinter，用它打出的 exe 启动即崩。
rem
rem  字体：assets\fonts\ 下的像素字体（Fusion Pixel 12px，OFL 授权）
rem        会随 --add-data 打进包里；缺失时程序自动回落系统字体。
rem
rem  注意：本文件以 GBK/CP936 编码保存，并显式执行 chcp 936。
rem        原因：cmd 按「当前代码页」解码批处理文件。若文件是 UTF-8 而
rem        代码页为 936，中文行会被错误解码，参数也会一并传坏 —— 实测
rem        PyInstaller 收到乱码名称，产物变成 0 字节的乱码 exe。
rem        保持文件编码与代码页一致即可彻底避免该类问题。
rem ============================================
chcp 936 >nul
cd /d "%~dp0"

rem ---- 解析参数（最多两个，顺序不限）----
set "MODE=-F"
set "LABEL=单文件版"
set "NOPAUSE="
if /i "%~1"=="--onedir" (set "MODE=-D" & set "LABEL=目录版")
if /i "%~2"=="--onedir" (set "MODE=-D" & set "LABEL=目录版")
if /i "%~1"=="--no-pause" set "NOPAUSE=1"
if /i "%~2"=="--no-pause" set "NOPAUSE=1"

rem ---- 选择解释器：优先系统 Python，其次 PATH 中的 python ----
set "PY=C:\Program Files\Python314\python.exe"
if not exist "%PY%" set "PY=python"

rem ---- 依赖自检：tkinter 是硬性要求 ----
"%PY%" -c "import tkinter, PyInstaller, PIL, pystray" 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 解释器 "%PY%" 缺少打包所需依赖。
    echo        需要同时具备：tkinter / PyInstaller / Pillow / pystray
    echo        最常见的坑：用了 WorkBuddy 托管 Python，它不含 tkinter。
    echo        请改用系统 Python，如 C:\Program Files\Python314\python.exe
    echo.
    if not defined NOPAUSE pause
    exit /b 1
)
echo 使用解释器：%PY%
echo 打包模式：%LABEL%

echo [1/2] 生成应用图标...
"%PY%" "scripts\make_icon.py"
if errorlevel 1 (
    echo.
    echo 打包失败：应用图标生成失败，请检查上方错误信息。
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "assets\fonts\fusion-pixel-12px-zh_hans.ttf" (
    echo [警告] 未找到像素字体 assets\fonts\fusion-pixel-12px-zh_hans.ttf
    echo        程序仍可正常打包运行，但界面会回落到系统字体。
)

echo [2/2] PyInstaller 打包...
"%PY%" -m PyInstaller %MODE% -w -n 护眼助手 ^
  --icon "%~dp0assets\icon.ico" ^
  --hidden-import pystray._win32 ^
  --collect-all pystray ^
  --collect-all PIL ^
  --add-data "%~dp0assets\fonts;assets\fonts" ^
  --distpath dist ^
  --workpath build ^
  --specpath build ^
  -y ^
  "src\main.py"
if errorlevel 1 (
    echo.
    echo 打包失败，请检查上方错误信息。
    if not defined NOPAUSE pause
    exit /b 1
)

echo.
if "%MODE%"=="-F" echo 打包完成：dist\护眼助手.exe
if "%MODE%"=="-D" echo 打包完成：dist\护眼助手\护眼助手.exe
if not defined NOPAUSE pause
exit /b 0
