@echo off
chcp 65001 >nul
cd /d "%~dp0"
title APEX-SCALP - Installation

echo ============================================================
echo   APEX-SCALP - Etape 1 : Installation
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
  echo.
  echo   1^) Telecharge Python 3.11 ou plus sur :
  echo      https://www.python.org/downloads/
  echo   2^) Pendant l'installation, COCHE la case "Add Python to PATH".
  echo   3^) Relance ce fichier.
  echo.
  pause
  exit /b 1
)

echo [1/3] Creation de l'environnement virtuel (.venv)...
python -m venv .venv
if errorlevel 1 ( echo [ERREUR] Creation du venv echouee. & pause & exit /b 1 )

echo [2/3] Mise a jour de pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [3/3] Installation d'APEX-SCALP + support MetaTrader5...
".venv\Scripts\python.exe" -m pip install -e ".[mt5]"
if errorlevel 1 ( echo [ERREUR] Installation des dependances echouee. & pause & exit /b 1 )

echo.
echo ============================================================
echo   Installation terminee avec succes !
echo   Lance maintenant : 2-configurer.bat
echo ============================================================
pause
