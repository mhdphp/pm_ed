# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Project Management MVP web app with a Kanban board and AI chat assistant. Users sign in, view/manage a Kanban board with drag-and-drop, and interact with an AI that can create/edit/move/delete cards.

**Stack:** Next.js 16 frontend (React 19, TypeScript, Tailwind v4, @dnd-kit) + Python FastAPI backend + SQLite, all packaged in one Docker image. AI via OpenRouter using `openai/gpt-oss-120b`. `OPENROUTER_API_KEY` lives in `.env` at the repo root (passed to the container via `--env-file`).

**MVP constraints:** Hardcoded login (`user`/`password`), one board per user, local Docker deployment only. The DB schema supports multiple users for the future.

## Commands

### Running the app (Docker)
```bash
scripts/start-mac.sh | scripts/start-linux.sh | scripts/start-windows.ps1   # build image + run container "pm-app" (foreground)
scripts/stop-mac.sh  | scripts/stop-linux.sh  | scripts/stop-windows.ps1
```
App served at http://localhost:8000. For running tests against a live container, start it detached instead:
```bash
docker build -t pm-app . && docker rm -f pm-app; docker run -d --name pm-app --env-file .env -p 8000:8000 pm-app
curl -sf http://127.0.0.1:8000/health   # wait for readiness
```

### Frontend (from `frontend/`)
```bash
npm run dev          # Dev server (API calls go to NEXT_PUBLIC_API_BASE, default same-origin)
npm run build        # Static export to frontend/out
npm run lint
npm run test:unit    # Vitest (src/**/*.test.tsx)
npx vitest run src/components/ChatSidebar.test.tsx   # Single unit test file
npm run test:e2e     # Playwright (tests/), runs against http://127.0.0.1:8000
npm run test:all
```
Playwright's `webServer` invokes the platform start script and reuses an already-running server on port 8000, so E2E tests always exercise the backend-served static build, not `next dev`.

### Backend (from `backend/`)
Tests import `app.*`, so `backend/` must be on the import path; `python -m pytest` from `backend/` handles that. Dependencies are in `backend/requirements.txt` (installed with `uv` in Docker).
```bash
python -m pytest                              # All tests
python -m pytest tests/test_board_api.py      # Single file
python -m pytest -k "test_name"               # Single test
PM_BASE_URL=http://127.0.0.1:8000 python -m pytest tests/test_integration.py   # Against running container
```
Unit tests isolate the DB by setting `PM_DB_PATH` to a tmp file and calling `init_db()` before creating a `TestClient`.

## Architecture

**Request flow:** The Next.js app is built as a static export (`output: "export"`) and copied into the image at `/app/frontend/out`. FastAPI serves it: `/_next` and `/static` are mounted as StaticFiles, and a catch-all route in `routes/static.py` serves files or falls back to `index.html`. API routes are registered before the catch-all, so new API routes must go in `api_router`.

**Backend (`backend/app/`):**
- `main.py` - app, lifespan (`init_db()` creates tables on startup), `/health`, router registration
- `config.py` - env config (`PM_DB_PATH`, `PM_STATIC_DIR`, `OPENROUTER_*`), loads repo-root `.env`, seed board data
- `database.py` - schema (users, boards, columns, cards), `fetch_board()` (seeds default board on first access), `resequence_positions()`
- `routes/board.py` - board/column/card CRUD; `routes/chat.py` - AI chat
- `ai.py` - OpenRouter call, prompt building, and `apply_actions()` which applies AI actions to the DB
- `models.py` - Pydantic request models and the discriminated-union `ChatAction` (create/update/move/delete card)

**User scoping:** Auth is frontend-only. The backend identifies the user via the `X-User` header (defaults to `user`), and every query is scoped by joining through `columns.board_id` to that user's board.

**Ordering:** Columns and cards have an integer `position`. Every insert/move/delete rebuilds the ordered id list in Python and calls `resequence_positions()` to rewrite positions 0..n. Follow this pattern rather than doing position arithmetic in SQL.

**AI chat (`/api/chat`):** Sends the current board JSON + conversation history to OpenRouter with a system prompt requiring JSON `{"reply", "actions"}`. The response is parsed (with a fallback that extracts the outermost `{...}`), validated against `StructuredChatOutput`, applied via `apply_actions()` when `apply_updates` is true, and returned with the refreshed board. Invalid action targets are silently skipped. Schema doc: `docs/ai-structured-output.json`.

**Frontend (`frontend/src/`):**
- `app/page.tsx` - the stateful container: login (credentials checked client-side), `board` and chat state, and all API-calling handlers (rename, add/delete/move card, send chat). The board returned by `/api/chat` replaces `board` state.
- `components/KanbanBoard.tsx` - renders the board and handles drag-and-drop (dnd-kit); applies optimistic updates via `onBoardChange` and calls the page's handlers
- `components/ChatSidebar.tsx` - presentational chat UI (messages, `onSend`), rendered inside KanbanBoard's `sidebar` slot
- `lib/api.ts` - API client; `toBoardData()` converts backend payloads to frontend `BoardData`
- `lib/kanban.ts` - types and `moveCard()`

**ID prefixing:** The backend uses numeric ids (returned as strings). The frontend prefixes them as `col-<id>` / `card-<id>` (`toColumnId`/`toCardId`) for drag-and-drop stability and strips them (`fromColumnId`/`fromCardId`) before API calls.

## Color Scheme
- Accent Yellow: `#ecad0a` (accent lines, highlights)
- Blue Primary: `#209dd7` (links, key sections)
- Purple Secondary: `#753991` (submit buttons, important actions)
- Dark Navy: `#032147` (main headings)
- Gray Text: `#888888` (supporting text, labels)

## Development Guidelines

- Keep it simple. No over-engineering, no extra features, no unnecessary defensive programming.
- Identify root cause before fixing issues. Prove with evidence, then fix.
- Work incrementally with small steps. Validate each increment.
- Use latest library APIs.
- Keep README minimal. No emojis ever.
- Planning docs are in `docs/` (`PLAN.md`, `DB_MODEL.md`, schema JSON files). Per-area notes are in `AGENTS.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`.

## DETAILED PLAN

@docs/PLAN.md
