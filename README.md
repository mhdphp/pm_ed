# Project Management MVP

## Local run (Docker)

- Mac: scripts/start-mac.sh
- Linux: scripts/start-linux.sh
- Windows: scripts/start-windows.ps1

The backend will be available at http://localhost:8000

Board data is stored in the Docker volume `pm-data` and survives restarts. To reset it, stop the container and run `docker volume rm pm-data`.

## Stop container

- Mac: scripts/stop-mac.sh
- Linux: scripts/stop-linux.sh
- Windows: scripts/stop-windows.ps1

## Integration tests

Set PM_BASE_URL to the running backend URL (for example http://localhost:8000) before running integration tests.
