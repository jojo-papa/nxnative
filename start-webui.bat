@echo off
setlocal
call "%~dp0webui\launchers\start_webui.bat" %*
exit /b %ERRORLEVEL%
