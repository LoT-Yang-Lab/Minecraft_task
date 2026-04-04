@echo off
REM ================================================================
REM  open_session.bat — 直接打开某个 session 的 xlsx 数据文件
REM
REM  用法:
REM    open_session.bat 1              打开最新实验的 session 1
REM    open_session.bat 3              打开最新实验的 session 3
REM    open_session.bat 1 proposal5_navigation_first_20260404_205458
REM                                   打开指定实验目录的 session 1
REM ================================================================

setlocal enabledelayedexpansion

set "SESSION_NUM=%~1"
set "EXPERIMENT_DIR=%~2"

if "%SESSION_NUM%"=="" (
    echo 用法: open_session.bat ^<session_number^> [experiment_dir_name]
    echo.
    echo 示例:
    echo   open_session.bat 1              打开最新实验的 session 1
    echo   open_session.bat 3              打开最新实验的 session 3
    echo   open_session.bat 1 proposal5_navigation_first_20260404_205458
    exit /b 1
)

REM 零填充 session 编号（01, 02, ...）
if %SESSION_NUM% LSS 10 (
    set "SESSION_PAD=0%SESSION_NUM%"
) else (
    set "SESSION_PAD=%SESSION_NUM%"
)

REM 定位 data/raw/trajectory 目录（相对于本脚本所在目录）
set "SCRIPT_DIR=%~dp0"
set "TRAJ_DIR=%SCRIPT_DIR%data\raw\trajectory"

if not exist "%TRAJ_DIR%" (
    echo [错误] 数据目录不存在: %TRAJ_DIR%
    exit /b 1
)

REM 如果未指定实验目录，则自动找最新的 proposal5_ 目录
if "%EXPERIMENT_DIR%"=="" (
    set "LATEST="
    for /d %%D in ("%TRAJ_DIR%\proposal5_*") do (
        set "LATEST=%%D"
    )
    if "!LATEST!"=="" (
        echo [错误] 未找到 proposal5_* 实验目录，请在 %TRAJ_DIR% 中确认。
        exit /b 1
    )
    set "EXP_PATH=!LATEST!"
) else (
    set "EXP_PATH=%TRAJ_DIR%\%EXPERIMENT_DIR%"
)

if not exist "%EXP_PATH%" (
    echo [错误] 实验目录不存在: %EXP_PATH%
    exit /b 1
)

REM 查找匹配的 session xlsx 文件
set "FOUND="
for %%F in ("%EXP_PATH%\session_%SESSION_PAD%_*.xlsx") do (
    set "FOUND=%%F"
)

if "%FOUND%"=="" (
    echo [错误] 未找到 session %SESSION_NUM% 的 xlsx 文件。
    echo 目录: %EXP_PATH%
    echo.
    echo 可用文件:
    dir /b "%EXP_PATH%\*.xlsx" 2>nul
    exit /b 1
)

echo 正在打开: %FOUND%
start "" "%FOUND%"
