@echo off
REM Flush Weaviate by deleting the data folder contents
REM Reads WEAVIATE_DATA_PATH from config/.env

setlocal enabledelayedexpansion

REM Read WEAVIATE_DATA_PATH from config/.env
set "WEAVIATE_DATA_PATH="
for /f "usebackq tokens=1,* delims==" %%a in ("..\config\.env") do (
    set "line=%%a"
    if "!line:~0,18!"=="WEAVIATE_DATA_PATH" (
        set "WEAVIATE_DATA_PATH=%%b"
    )
)

REM Default to data/weaviate_data if not found
if "%WEAVIATE_DATA_PATH%"=="" (
    set "WEAVIATE_DATA_PATH=data\weaviate_data"
)

REM Convert to absolute path from repo root
set "REPO_ROOT=%~dp0.."
set "FULL_PATH=%REPO_ROOT%\%WEAVIATE_DATA_PATH%"

echo ========================================
echo Weaviate Flush Script
echo ========================================
echo Target folder: %FULL_PATH%
echo.

REM Check if folder exists
if not exist "%FULL_PATH%" (
    echo ERROR: Folder does not exist.
    echo Exiting.
    pause
    exit /b 1
)

REM Confirm deletion
set /p "CONFIRM=Are you sure you want to delete all contents? (yes/no): "
if /i not "%CONFIRM%"=="yes" (
    echo Aborted.
    pause
    exit /b 0
)

REM Delete all contents
echo Deleting folder contents...
rmdir /s /q "%FULL_PATH%" 2>nul
if errorlevel 1 (
    echo ERROR: Failed to delete folder contents.
    pause
    exit /b 1
)

REM Recreate the empty folder
mkdir "%FULL_PATH%" 2>nul

echo SUCCESS: Weaviate data folder flushed.
echo.

REM Clear CSV files
set "APPLICANTS_CSV=%REPO_ROOT%\data\applicants.csv"
set "ROLES_CSV=%REPO_ROOT%\data\roles.csv"

echo Clearing CSV files...
if exist "%APPLICANTS_CSV%" (
    type nul > "%APPLICANTS_CSV%"
    echo - applicants.csv cleared
)
if exist "%ROLES_CSV%" (
    type nul > "%ROLES_CSV%"
    echo - roles.csv cleared
)

echo.
echo All data flushed successfully.
pause
