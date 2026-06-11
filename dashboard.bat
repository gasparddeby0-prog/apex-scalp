@echo off
chcp 65001 >nul
cd /d "%~dp0"
title APEX-SCALP - Dashboard

echo ============================================================
echo   APEX-SCALP - Dashboard web
echo ============================================================
echo.
echo   Ouvre ton navigateur sur : http://127.0.0.1:8050
echo   Pour fermer le dashboard : ferme cette fenetre (ou Ctrl+C).
echo ============================================================
echo.

".venv\Scripts\python.exe" -m apex.cli dashboard

pause
