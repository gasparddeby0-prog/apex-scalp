@echo off
chcp 65001 >nul
cd /d "%~dp0"
title APEX-SCALP - Configuration

echo ============================================================
echo   APEX-SCALP - Etape 2 : Configuration (compte DEMO)
echo ============================================================
echo.
echo Creation du fichier .env avec ton compte demo MetaQuotes...

(
echo # Genere automatiquement par 2-configurer.bat - compte DEMO MetaQuotes
echo APEX_MODE=live
echo MT5_LOGIN=108249043
echo MT5_PASSWORD=D!LkCcO3
echo MT5_SERVER=MetaQuotes-Demo
echo MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe
echo.
echo # Risque ^(prudent pour la demo^)
echo APEX_RISK_PER_TRADE_PCT=0.5
echo APEX_MAX_DAILY_RISK_PCT=2.0
echo APEX_MAX_WEEKLY_RISK_PCT=5.0
echo APEX_MAX_OPEN_POSITIONS=2
echo.
echo # Symboles a scanner
echo APEX_SYMBOLS=EURUSD,GBPUSD,USDJPY,XAUUSD
echo APEX_ENTRY_SCORE=7.0
echo APEX_MIN_ALIGNED=3
echo.
echo # Dashboard
echo APEX_DASHBOARD_HOST=127.0.0.1
echo APEX_DASHBOARD_PORT=8050
) > .env

echo.
echo Fichier .env cree :
echo   - Mode      : LIVE (sur compte DEMO, donc argent fictif)
echo   - Login     : 108249043
echo   - Serveur   : MetaQuotes-Demo
echo   - Symboles  : EURUSD, GBPUSD, USDJPY, XAUUSD
echo.
echo IMPORTANT : ouvre le terminal MetaTrader 5 sur ton PC et
echo connecte-toi avec CE compte (login 108249043, MetaQuotes-Demo)
echo avant de lancer le bot.
echo.
echo Etape suivante : 3-tester-connexion.bat
echo ============================================================
pause
