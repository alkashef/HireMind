@echo off
REM Stop and remove local Weaviate containers started by the helper compose file.
REM Run this from the repository root.

echo Stopping local Weaviate (docker compose -f docker-compose.weaviate.yml down)...
docker compose -f docker-compose.weaviate.yml down
if %ERRORLEVEL% neq 0 (
  echo Failed to stop Weaviate. You may need to stop it from Docker Desktop.
  exit /b %ERRORLEVEL%
)

echo Done. You can remove persisted data by deleting the data\weaviate_data folder if desired.
