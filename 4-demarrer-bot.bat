@echo off
chcp 65001 >nul
cd /d "%~dp0"
title APEX-SCALP - Bot en marche (DEMO)

echo ============================================================
echo   APEX-SCALP - Etape 4 : DEMARRAGE DU BOT
echo ============================================================
echo.
echo   Compte DEMO MetaQuotes (argent fictif).
echo   Le bot analyse le marche toutes les 10 secondes et
echo   envoie des ordres sur le compte demo si un signal valide.
echo.
echo   Pour ARRETER le bot : ferme cette fenetre (ou Ctrl+C).
echo.
echo   Verifie que MT5 est ouvert et connecte avant de continuer.
echo ============================================================
pause

".venv\Scripts\python.exe" -m apex.cli run --cycles 100000 --delay 10 --verbose

echo.
echo Bot arrete.
pause
