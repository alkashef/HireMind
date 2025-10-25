@echo off
REM Run local Weaviate using the provided docker-compose file.
REM Run this from the repository root.

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
