@echo off
REM Run local Weaviate using the provided docker-compose file.
REM Run this from the repository root.

REM Load environment variables from config\.env (if present) so docker-compose
REM receives the same runtime configuration as the app.
setlocal EnableDelayedExpansion
set "ENVFILE=config\.env"
if exist "%ENVFILE%" (
  echo Loading environment variables from %ENVFILE%...
  set "LOADED=0"
  for /f "usebackq tokens=1* delims==" %%A in ("%ENVFILE%") do (
    set "k=%%A"
    set "v=%%B"
    if not "!k!"=="" (
      rem remove optional leading "export " if present
      if "!k:~0,6!"=="export" set "k=!k:~7!"
      set "first=!k:~0,1!"
      if NOT "!first!"=="#" if NOT "!first!"==";" (
        rem Trim leading spaces from key and value
        for /f "tokens=* delims= " %%X in ("!k!") do set "k=%%X"
        for /f "tokens=* delims= " %%Y in ("!v!") do set "v=%%Y"
        rem Remove surrounding double-quotes from value if present
        if "!v:~0,1!"=="\"" if "!v:~-1!"=="\"" set "v=!v:~1,-1!"
        rem Export into current process environment for docker-compose to use
        set "!k!=!v!"
        set /a LOADED+=1 >nul
      )
    )
  )
  echo Loaded !LOADED! variables from %ENVFILE%.
) else (
  echo Env file %ENVFILE% not found; skipping env load.
)

echo Starting local Weaviate (docker compose -f docker-compose.weaviate.yml up -d)...
docker compose -f docker-compose.weaviate.yml up -d
if %ERRORLEVEL% neq 0 (
  echo Failed to start Weaviate. Ensure Docker Desktop is running and try again.
  exit /b %ERRORLEVEL%
)

echo Waiting 3 seconds for container to initialize...
timeout /t 3 /nobreak > nul

echo Showing container status:
docker ps --filter "name=hiremind_weaviate"
echo You can view logs with: docker logs -f hiremind_weaviate
