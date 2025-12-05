@echo off
title Servidor Chat Oposición
cd /d "%~dp0"

:: === Activa entorno virtual si existe ===
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: === Elegir clave OpenAI ===
:seleccion_clave
echo Selecciona la clave OpenAI a usar:
echo 1. clave_oposicion
echo 2. clave_personal
set /p clave_opcion=Introduce 1 o 2: 

if "%clave_opcion%"=="1" (
    set OPCION=1
) else if "%clave_opcion%"=="2" (
    set OPCION=2
) else (
    echo Opcion invalida. Intenta de nuevo.
    goto seleccion_clave
)

echo 🚀 Iniciando servidor Flask en http://localhost:5050 con la clave seleccionada...
python chat_proxy_server.py %OPCION%

:: Mantener la ventana abierta
pause
