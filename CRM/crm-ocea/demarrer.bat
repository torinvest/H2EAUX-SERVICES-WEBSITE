@echo off
cd /d "%~dp0"
echo.
echo  ========================================
echo   CRM H2EAUX SERVICES - Entreprise OCEA
echo   Comptages immobiliers et maintenances
echo  ========================================
echo.
echo  Ouverture sur http://127.0.0.1:8080
echo.
python -m uvicorn app:app --host 127.0.0.1 --port 8080 --reload
