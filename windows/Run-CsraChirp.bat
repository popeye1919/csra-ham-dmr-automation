@echo off
REM ============================================================================
REM CSRA PHREAK & PACKET UNDERGROUND // WINDOWS INTERACTIVE LAUNCHER
REM DE KR4JLC (3221824) // THE KNIGHTS WHO SAY "73" (--... ...--)
REM ============================================================================
title CSRA HAM & DMR Radio Automation [2600 Hz // DE KR4JLC]
color 0B

:MENU
cls
echo  ._________________________________________________________________________.
echo  ^|  ____ ____ ____    _      ____  _   _ ____  _____    _    _  __         ^|
echo  ^| / ___/ ___^|  _ \  / \    ^|  _ \^| ^| ^| ^|  _ \^| ____^|  / \  ^| ^|/ /         ^|
echo  ^|^| ^|   \___ \ ^|_) ^|/ _ \   ^| ^|_) ^| ^|_^| ^| ^|_) ^|  _^|   / _ \ ^| ' /   [2600] ^|
echo  ^|^| ^|___ ___) ^|  _ ^< ___ \  ^|  __/^|  _  ^|  _ ^<^| ^|___ / ___ \^| . \   [ Hz ] ^|
echo  ^| \____^|____/^|_^| \_\_/ \_\ ^|_^|   ^|_^| ^|_^|_^| \_\_____/_/   \_\_^|\_\  [WIN ] ^|
echo  ^|-------------------------------------------------------------------------^|
echo  ^|  * RULE #1: WE ALWAYS BACK UP YOUR RADIO BEFORE UPLOADING A NEW IMAGE!  ^|
echo  ^|  * CW: -.-. --.-  -.. .  -.- .-. ....- .--- .-.. -.-.  --... ...--      ^|
echo  `-------------------------------------------------------------------------'
echo.
echo   [1] Detect Radio USB/COM Ports ^& CHIRP Installation
echo   [2] Backup Radio EEPROM Only (Saves to windows\backups\ with SHA-256)
echo   [3] SAFE FLASH: Mandatory Pre-Flash Backup + Upload CSRA W4DV Codeplug
echo   [4] ROLLBACK: Restore Latest Pre-Flash Backup Image to Radio
echo   [5] Launch CHIRP GUI (chirpw.exe) with CSRA CSV ^& Latest Backup
echo   [6] Sync Latest W4DV / ICS-217 / TGIF Data ^& Rebuild Codeplugs
echo   [7] Quit ("73 de KR4JLC SK")
echo.
set /p CHOICE="Select an option [1-7]: "

if "%CHOICE%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-CsraChirp.ps1" -Action Detect
    pause
    goto MENU
)
if "%CHOICE%"=="2" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-CsraChirp.ps1" -Action Backup
    pause
    goto MENU
)
if "%CHOICE%"=="3" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-CsraChirp.ps1" -Action Flash
    pause
    goto MENU
)
if "%CHOICE%"=="4" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-CsraChirp.ps1" -Action Restore
    pause
    goto MENU
)
if "%CHOICE%"=="5" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-CsraChirp.ps1" -Action LaunchGui
    pause
    goto MENU
)
if "%CHOICE%"=="6" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Invoke-CsraChirp.ps1" -Action SyncAndBuild
    pause
    goto MENU
)
if "%CHOICE%"=="7" (
    echo.
    echo --... ...-- / -.. . / -.- .-. ....- .--- .-.. -.-. / ... -.- (73 de KR4JLC!)
    exit /b 0
)
goto MENU
