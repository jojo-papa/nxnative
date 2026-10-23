@echo off
setlocal
cd /d "%~dp0..\.."
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_webui_windows.ps1" %*
set "NX_EXIT_CODE=%ERRORLEVEL%"
if "%NX_EXIT_CODE%"=="0" exit /b 0
echo.
echo WebUI startup failed. See .webui-data\startup.log for the error.
pause
exit /b %NX_EXIT_CODE%
