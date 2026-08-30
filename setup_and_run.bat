@echo off
setlocal enabledelayedexpansion
title NexaHR

REM ============================================================
REM  NexaHR - local development bootstrap (Windows)
REM
REM  *** DEVELOPMENT ONLY - DO NOT RUN ON A REAL DEPLOYMENT ***
REM
REM  The setup this starts deliberately writes ENVIRONMENT=development,
REM  a fixed JWT_SECRET_KEY, SEED_DEMO_DATA=true (sample accounts whose
REM  shared password is published in the repository) and
REM  MIN_COHORT_SIZE=1, which turns OFF the suppression that keeps a
REM  three-person "unit average" from being read back as those three
REM  people's scores.
REM
REM  For a real deployment see deploy/PRODUCTION.md - it ships built
REM  container images and never puts any of the above on the server.
REM ------------------------------------------------------------
REM  This file used to be the whole setup: eight steps, then two
REM  `start ... cmd /k` windows plus this one. Three consoles, none of
REM  them controllable, and the real error always in whichever window
REM  had been minimised.
REM
REM  All of that now lives in tools\launcher, which opens ONE window
REM  and shows what is running and where. What stays here is only the
REM  part that cannot: finding a working Python. Everything else needs
REM  Python to already be there.
REM
REM  Usage:
REM     setup_and_run.bat              the window
REM     setup_and_run.bat --console    the same run, in this terminal
REM ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "LAUNCHER=%ROOT%\tools\nexahr.pyw"

set "MIN_PY_MAJOR=3"
set "MIN_PY_MINOR=11"
set /a MIN_PY_ENC=%MIN_PY_MAJOR%*1000+%MIN_PY_MINOR%

if not exist "%LAUNCHER%" (
    echo.
    echo  [X] Could not find "%LAUNCHER%"
    echo.
    echo  Keep setup_and_run.bat in the repository root, next to the
    echo  backend, frontend and tools folders.
    echo.
    pause
    exit /b 1
)

REM --- Python: must actually run, and be new enough ---------------
REM `where python` is deliberately NOT used. On a fresh Windows 11 it
REM finds %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe - an App
REM Execution Alias that opens the Microsoft Store and prints nothing.
REM It satisfies `where`, creates no venv, and the first real symptom
REM is a confusing failure several steps later. Running it and reading
REM the version back is the only check that tells the two apart.
REM
REM Detection lives in a subroutine because the probe command contains
REM parentheses - `print(...)`. Inside a parenthesised if/for block,
REM cmd matches the first `)` it sees against the block instead of the
REM command, and the line silently does the wrong thing.
call :detect_python

if not defined PYCMD (
    echo.
    echo ============================================================
    echo  [X] No working Python interpreter found.
    echo ============================================================
    echo.
    echo  If `python` opens the Microsoft Store, that is the
    echo  placeholder, not a real install:
    echo      Settings ^> Apps ^> Advanced app settings ^>
    echo      App execution aliases ^> turn OFF both "python" entries
    echo.
    echo  Otherwise install Python %MIN_PY_MAJOR%.%MIN_PY_MINOR% or newer from
    echo  https://python.org and tick "Add python.exe to PATH",
    echo  then open a NEW terminal and run this again.
    echo.
    pause
    exit /b 1
)

if !PYVER! LSS !MIN_PY_ENC! (
    set /a FOUND_MAJOR=!PYVER!/1000
    set /a FOUND_MINOR=!PYVER!%%1000
    echo.
    echo ============================================================
    echo  [X] Python !FOUND_MAJOR!.!FOUND_MINOR! is too old.
    echo ============================================================
    echo.
    echo  This project needs %MIN_PY_MAJOR%.%MIN_PY_MINOR% or newer: the backend imports
    echo  `datetime.UTC`, which only exists from 3.11 on, so an older
    echo  interpreter fails at import time - after everything else has
    echo  already reported success.
    echo.
    echo  Install it from https://python.org, then open a NEW terminal
    echo  and run this again.
    echo.
    pause
    exit /b 1
)

if /i "%~1"=="--console" (
    %PYCMD% "%LAUNCHER%" --no-gui
    REM Captured before `pause`, which overwrites errorlevel with its own.
    set "RC=!errorlevel!"
    echo.
    pause
    exit /b !RC!
)

REM pythonw.exe is python.exe without a console. Starting the launcher
REM with it is what makes this window able to close immediately - which
REM is the whole point. If it is missing for any reason, plain python
REM still works; the console just lingers behind the window.
call :detect_pythonw
if defined PYW (
    start "" "%PYW%" "%LAUNCHER%" %*
) else (
    start "" %PYCMD% "%LAUNCHER%" %*
)
exit /b 0

REM ------------------------------------------------------------
REM  :detect_python -> sets PYCMD and PYVER, or leaves both unset
REM
REM  Tries `python` first, then the `py` launcher, which is often
REM  present and working even when `python` is the Store stub.
REM  PYVER is major*1000+minor, so 3.11 -> 3011 and plain integer
REM  comparison orders correctly (3.9 -> 3009 < 3011).
REM ------------------------------------------------------------
:detect_python
set "PYVER="
for /f "usebackq delims=" %%V in (`python -c "import sys;print(sys.version_info[0]*1000+sys.version_info[1])" 2^>nul`) do set "PYVER=%%V"
if defined PYVER (
    set "PYCMD=python"
    exit /b 0
)
for /f "usebackq delims=" %%V in (`py -3 -c "import sys;print(sys.version_info[0]*1000+sys.version_info[1])" 2^>nul`) do set "PYVER=%%V"
if defined PYVER (
    set "PYCMD=py -3"
    exit /b 0
)
exit /b 1

REM ------------------------------------------------------------
REM  :detect_pythonw -> sets PYW to the console-less interpreter
REM
REM  Asked of Python itself rather than guessed from PATH: under
REM  `py -3` the launcher on PATH is not the interpreter that will
REM  run, and sys.executable is.
REM ------------------------------------------------------------
:detect_pythonw
set "PYW="
for /f "usebackq delims=" %%W in (`%PYCMD% -c "import os,sys;p=os.path.join(os.path.dirname(sys.executable),'pythonw.exe');print(p if os.path.exists(p) else '')" 2^>nul`) do set "PYW=%%W"
exit /b 0
