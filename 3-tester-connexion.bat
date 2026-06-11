@echo off
chcp 65001 >nul
cd /d "%~dp0"
title APEX-SCALP - Test de connexion

echo ============================================================
echo   APEX-SCALP - Etape 3 : Test de connexion MetaTrader 5
echo   (analyse seulement, AUCUN ordre n'est envoye)
echo ============================================================
echo.
echo Verifie d'abord que le terminal MT5 est OUVERT et connecte
echo au compte demo 108249043 (MetaQuotes-Demo).
echo.
pause

".venv\Scripts\python.exe" -m apex.cli scan --dry-run

echo.
echo ------------------------------------------------------------
echo Si tu vois "MT5 connected" plus haut : la connexion marche !
echo Si tu vois "mt5.initialize failed" : verifie que MT5 est
echo ouvert, connecte au bon compte, et que le trading algo est
echo autorise (Outils ^> Options ^> Expert Advisors).
echo ------------------------------------------------------------
pause
