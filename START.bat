@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title APEX-SCALP

echo ===============================================
echo               APEX-SCALP - Lanceur
echo ===============================================

REM --- Verifier que Python est disponible ---
where py >nul 2>nul
if errorlevel 1 (
  echo [ERREUR] Python introuvable.
  echo Installe Python 3.11 ou plus depuis https://www.python.org/downloads/
  echo en cochant "Add python.exe to PATH".
  pause
  exit /b 1
)

REM --- S'assurer que uv est installe ---
py -m uv --version >nul 2>nul
if errorlevel 1 (
  echo Installation de uv...
  py -m pip install uv
)

REM --- Creer l'environnement la premiere fois ---
if not exist ".venv\" (
  echo.
  echo Premiere utilisation : creation de l'environnement Python 3.11...
  py -m uv venv --python 3.11
  echo Installation des dependances...
  py -m uv pip install -e ".[dev]"
)

REM --- Avertir si le fichier .env est absent ---
if not exist ".env" (
  echo.
  echo [ATTENTION] Aucun fichier .env trouve dans ce dossier.
  echo Le mode LIVE a besoin d'un .env avec tes identifiants MT5.
  echo Le mode PAPER fonctionne sans.
)

:menu
echo.
echo -----------------------------------------------
echo  1^) Dashboard    (PAPER - simulation, navigateur)
echo  2^) Simulation   (PAPER - 300 cycles + resume)
echo  3^) Scan unique  (PAPER - 1 cycle, sans ordre)
echo  4^) Dashboard    (LIVE - compte MT5, Windows + terminal ouvert)
echo  5^) Quitter
echo -----------------------------------------------
set "choix="
set /p choix="Ton choix (1-5) : "

if "%choix%"=="1" goto paper_dash
if "%choix%"=="2" goto paper_run
if "%choix%"=="3" goto scan
if "%choix%"=="4" goto live_dash
if "%choix%"=="5" exit /b 0
echo Choix invalide, reessaie.
goto menu

:paper_dash
echo.
echo Lancement du dashboard PAPER... ouvre http://127.0.0.1:8050
echo (si la page ne s'affiche pas tout de suite, rafraichis dans ~5 secondes)
start "" http://127.0.0.1:8050
py -m uv run apex --mode paper dashboard --warmup 200
goto end

:paper_run
echo.
echo Simulation PAPER de 300 cycles...
py -m uv run apex --mode paper run --cycles 300 --step-bars 5 --verbose
goto end

:scan
echo.
py -m uv run apex --mode paper scan --warmup 200 --dry-run
goto end

:live_dash
echo.
echo === MODE LIVE (MT5) ===
echo Prerequis : MT5 desktop installe, OUVERT et connecte a ton compte demo,
echo et le fichier .env rempli (MT5_LOGIN / MT5_PASSWORD / MT5_SERVER / MT5_PATH).
echo.
echo Installation du module MetaTrader5 si necessaire...
py -m uv pip install -e ".[mt5]"
echo.
echo Lancement du dashboard LIVE... ouvre http://127.0.0.1:8050
start "" http://127.0.0.1:8050
py -m uv run apex --mode live dashboard
goto end

:end
echo.
echo --- Termine. Appuie sur une touche pour revenir au menu. ---
pause >nul
goto menu
