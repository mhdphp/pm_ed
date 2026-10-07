# Project Management MVP

A Kanban board web app with an AI chat assistant. Sign in, manage cards with drag-and-drop, and ask the assistant to create, edit, move, or delete cards for you.

This project is part of the course "AI Coder: Complete Claude Code & Coding Agents Course" by instructor Ed Donner.

- Frontend: Next.js 16 (static export), React 19, TypeScript, Tailwind CSS v4, dnd-kit
- Backend: Python 3.12, FastAPI, SQLite
- AI: OpenRouter, model `openai/gpt-oss-120b`
- Packaging: a single Docker image serving both frontend and API on port 8000

See [docs/APP_OVERVIEW.md](docs/APP_OVERVIEW.md) for the full architecture description.

## Requirements

- Docker
- An OpenRouter API key (only needed for the AI chat)
- For local development without Docker: Node.js 24 and Python 3.12

## Setup

Create a `.env` file in the repo root:

```
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
```

`OPENROUTER_MODEL` is optional. Without it the app uses `openai/gpt-oss-120b`, which requires paid OpenRouter credits. Free models (ids ending in `:free`) are limited to 20 requests per minute and 50 per day; pick one that supports structured outputs. Restart the container after changing `.env`.

## Run (Docker)

- Mac: `scripts/start-mac.sh`
- Linux: `scripts/start-linux.sh`
- Windows: `scripts/start-windows.ps1`

The script builds the image and runs the `pm-app` container in the foreground. Open http://localhost:8000 and sign in with `user` / `password`.

Board data is stored in the Docker volume `pm-data` and survives restarts. To reset it, stop the container and run `docker volume rm pm-data`.

## Stop

- Mac: `scripts/stop-mac.sh`
- Linux: `scripts/stop-linux.sh`
- Windows: `scripts/stop-windows.ps1`

## Tests

Backend (from `backend/`):

```bash
pip install -r requirements.txt
python -m pytest
```

Frontend (from `frontend/`):

```bash
npm install
npm run test:unit    # Vitest
npm run test:e2e     # Playwright, against the app on http://127.0.0.1:8000
```

Integration tests against a running container: start it detached, then set `PM_BASE_URL`:

```bash
docker build -t pm-app .
docker run -d --name pm-app --env-file .env -v pm-data:/app/backend/data -p 8000:8000 pm-app
cd backend && PM_BASE_URL=http://127.0.0.1:8000 python -m pytest tests/test_integration.py
```

## Project layout

```
backend/    FastAPI app (app/) and pytest tests (tests/)
frontend/   Next.js app (src/) and Playwright tests (tests/)
scripts/    Start and stop scripts per platform
docs/       Plan, database model, schemas, architecture overview
Dockerfile  Multi-stage build: frontend static export + Python runtime
```

## MVP limitations

- Login is hardcoded (`user` / `password`) and checked in the browser only; the backend identifies the user via the `X-User` header.
- One board per user.
- Local Docker deployment only.
