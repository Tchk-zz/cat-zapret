@echo off
setlocal
cd /d "%~dp0"
set "PY=C:\Users\Eliza\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
if not exist "%PY%" set "PY=C:\Users\Eliza\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=pythonw.exe"
start "" "%PY%" "%~dp0main.py"
exit
