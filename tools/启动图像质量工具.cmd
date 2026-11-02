@echo off
chcp 65001 >nul
set "QUALITY_PY=%LocalAppData%\Programs\Python\Python310\python.exe"
if not exist "%QUALITY_PY%" set "QUALITY_PY=python"
"%QUALITY_PY%" "%~dp0quality_workbench.py"
if errorlevel 1 pause
