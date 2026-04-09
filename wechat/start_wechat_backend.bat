@echo off
title Used Car Appraisal Mini-Program Backend

echo ============================================================
echo  Used Car Appraisal Mini-Program Backend Service
echo  Port: 8003
echo  API Docs: http://127.0.0.1:8003/docs
echo  Test Token: http://127.0.0.1:8003/api/test/token
echo ============================================================
echo.

:: Switch to backend directory
cd /d "%~dp0backend"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please ensure Python is installed and in PATH.
    pause
    exit /b 1
)

:: Install dependencies
echo [INFO] Checking and installing dependencies...
pip install fastapi uvicorn[standard] PyJWT python-multipart scipy xgboost scikit-learn

echo [INFO] Starting service...
echo [INFO] Press Ctrl+C to stop the service
echo.

python main.py

pause
