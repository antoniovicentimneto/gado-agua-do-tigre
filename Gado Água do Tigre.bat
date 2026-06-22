@echo off
rem Lancador de um clique do app Gado Agua do Tigre.
rem Inicia o servidor e abre o navegador automaticamente.
title Gado Agua do Tigre - servidor (feche esta janela para parar)

cd /d "%~dp0backend"

rem Sobe o servidor numa janela propria (minimizada).
start "Gado Agua do Tigre - servidor" /min ".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8077

rem Aguarda o servidor subir (~3s) e abre o app no navegador.
ping -n 4 127.0.0.1 >nul
start "" http://127.0.0.1:8077
