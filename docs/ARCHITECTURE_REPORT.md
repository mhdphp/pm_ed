# Repository Architecture Report

Generated 2026-10-07 from the working tree. This report is descriptive; no application files were changed.

## 1. Repository structure

```text
backend/
  app/                 FastAPI application package
  tests/               pytest unit and integration tests
frontend/
  src/app/             Next.js App Router entry points and global styles
  src/components/      Kanban and chat UI components
  src/lib/             frontend types, board logic, and API client
  tests/               Playwright end-to-end tests
  package.json         Node scripts and dependencies
scripts/               platform-specific Docker start/stop scripts
docs/                  plan, schema, architecture, and review documents
Dockerfile             multi-stage frontend build plus Python runtime
README.md              setup, run, test, and layout notes
```

The project instructions describe an MVP with client-side hardcoded login (`user` / `password`), one board per user, and local Docker deployment.

## 2. Main application entry points

- **Container/runtime entry point:** `backend/app/main.py`, exporting the FastAPI instance `app`. The Docker image starts it with `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Browser entry point:** `frontend/src/app/page.tsx`, the stateful home route. `frontend/src/app/layout.tsx` supplies the app shell and `globals.css` supplies global styling.
- **Production frontend path:** Next.js is configured with `output: "export"`; Docker builds `frontend/out` and FastAPI serves that static output, including a catch-all fallback to `index.html`.

## 3. Important modules and request flow

### Backend

- `app/main.py`: creates the FastAPI app, initializes SQLite during lifespan startup, mounts static assets, and registers API/static routers.
- `app/config.py`: loads the repository `.env`, resolves database/static paths, selects the OpenRouter model, and defines initial seed data.
- `app/database.py`: creates the `users`, `boards`, `columns`, and `cards` schema; seeds a new board; scopes queries; and maintains integer ordering positions.
- `app/dependencies.py`: opens/closes SQLite connections and derives the username from `X-User` (defaulting to `user`).
- `app/routes/board.py`: board, column, and card CRUD endpoints.
- `app/routes/chat.py` and `app/ai.py`: build the board-aware prompt, call OpenRouter, validate structured JSON actions, and apply create/update/move/delete card actions.
- `app/models.py`: Pydantic request models and the discriminated union for AI actions.
- `app/routes/static.py`: serves the exported Next.js site.

### Frontend

- `src/app/page.tsx`: login state, board state, API handlers, optimistic updates, and chat integration.
- `src/components/KanbanBoard.tsx`: drag-and-drop orchestration with `@dnd-kit`, column rename, card operations, and sidebar placement.
- `KanbanColumn.tsx`, `KanbanCard.tsx`, `KanbanCardPreview.tsx`, and `NewCardForm.tsx`: board presentation and card editing/creation UI.
- `ChatSidebar.tsx`: chat presentation and message submission UI.
- `src/lib/api.ts`: fetch wrapper and conversion of backend payloads into frontend `BoardData`.
- `src/lib/kanban.ts`: board types, ID prefix conversion (`col-`/`card-`), and client-side card movement logic.

### End-to-end flow

The browser sends same-origin `/api` requests to FastAPI. FastAPI resolves the user from `X-User`, reads or updates SQLite, and returns normalized board JSON. The frontend prefixes numeric backend IDs for drag-and-drop and strips those prefixes before mutations. Chat requests include current board data and history; validated AI actions are persisted before the refreshed board is returned.

## 4. Dependency management

- **Frontend:** npm, pinned through `frontend/package-lock.json`; declared in `frontend/package.json`. Main dependencies are Next.js 16, React 19, TypeScript, Tailwind CSS 4, `@dnd-kit`, Vitest/Testing Library, and Playwright.
- **Backend:** `backend/requirements.txt` with bounded version ranges for FastAPI, Uvicorn, pytest, HTTPX, pytest-cov, and python-dotenv. The Dockerfile installs these with `uv pip install --system` after installing `uv`.
- **Container build:** Docker uses a Node 24 build stage for the static frontend and a Python 3.12 runtime stage for FastAPI. The runtime runs as non-root `appuser` and exposes port 8000.
- **Configuration:** `.env` supplies `OPENROUTER_API_KEY` and may override `OPENROUTER_MODEL`; the code default is `openai/gpt-oss-120b`. `.env` is passed into the container by the start scripts.

## 5. Normal application run

Run the platform script from the repository root:

- Windows: `scripts/start-windows.ps1`
- macOS: `scripts/start-mac.sh`
- Linux: `scripts/start-linux.sh`

Each script builds image `pm-app`, replaces any existing `pm-app` container, mounts the named volume `pm-data` at `/app/backend/data`, passes `.env`, and publishes `http://localhost:8000`. Stop with the matching `stop-*` script. The SQLite database is therefore persistent in the Docker volume.

For frontend-only development, run `npm run dev` from `frontend/`; this is useful for UI work but does not represent the production serving path. Backend tests can be run from `backend/` with `python -m pytest`.

## 6. Test organization and execution

- **Backend unit/API tests:** `backend/tests/test_main.py`, `test_board_api.py`, `test_chat_api.py`, `test_chat_structured_api.py`, `test_ai_actions.py`, and `test_schema.py`. Run from `backend/` with `python -m pytest`; use `-k` or a file path to narrow the run.
- **Backend live integration test:** `backend/tests/test_integration.py` targets `PM_BASE_URL` (normally a detached Docker container at `http://127.0.0.1:8000`).
- **Frontend unit tests:** colocated `src/**/*.test.tsx`/`src/**/*.test.ts`, run by Vitest via `npm run test:unit`. `vitest.config.ts` uses jsdom, Testing Library setup, and optional V8 coverage.
- **Frontend E2E tests:** `frontend/tests/kanban.spec.ts`, run with `npm run test:e2e`. Playwright starts or reuses the platform Docker script and tests the backend-served static build, not `next dev`.
- **Combined frontend suite:** `npm run test:all` runs unit tests followed by Playwright.

## 7. Git status and branch

At inspection time:

```text
## main...origin/main
?? docs/how-to-use-it.md
```

The current branch is `main`, tracking `origin/main`. There are no tracked modifications; `docs/how-to-use-it.md` is an existing untracked file and was left untouched. This report is a new documentation file created at `docs/ARCHITECTURE_REPORT.md`.

## What to understand before changing the project

1. Keep the production request path in mind: static Next.js output is served by FastAPI, so changes that work under `next dev` still need a static build and backend serving check.
2. Preserve user scoping and ordering invariants in `database.py`; board queries and card/column position resequencing are shared by REST and AI mutations.
3. Treat the frontend/backend board JSON shape and ID prefix conversion as an API contract.
4. Understand the authentication boundary: the login is browser-only, while the backend trusts `X-User`; this is intentionally an MVP limitation, not a complete auth system.
5. Keep OpenRouter structured-output requirements aligned with `models.py` and `docs/ai-structured-output.json`, and remember that `OPENROUTER_MODEL` can override the documented default.
6. Run the relevant test layer after changes, and use the Docker-backed integration/E2E path for anything involving static serving, persistence, or the full chat flow.
7. Review `docs/PLAN.md` before starting work because it is the project’s stated implementation and acceptance checklist.
