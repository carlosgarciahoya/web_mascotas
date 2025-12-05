@echo off
rem Autoelevar a administrador si no lo es
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)

cd /d C:\Users\CGH\Documents\web_mascotas
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '.\.venv\Scripts\Activate.ps1'; python 'chat_python_con_ficheros.py'"

pause

Nota: Se usa una única llamada a PowerShell para “activar” y ejecutar Python dentro de la misma sesión; si se ejecutara el .ps1 por separado desde cmd, la activación no se mantendría.