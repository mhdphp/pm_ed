# Project review (2026-10-06)

A snapshot of what has been built and where the documentation and code disagree. Sources reviewed: docs/PLAN.md, AGENTS.md, backend/AGENTS.md, frontend/AGENTS.md, README.md, docs/DB_MODEL.md, docs/kanban-schema.json, docs/ai-structured-output.json, CLAUDE.md.

## Status

All 10 parts of docs/PLAN.md are complete. The MVP is functionally done.

| Part | Delivered |
|---|---|
| 1. Plan | Detailed plan and frontend/AGENTS.md |
| 2. Scaffolding | Python 3.12 Docker image using uv, non-root `appuser`, HEALTHCHECK. Start/stop scripts for Mac, Linux, Windows (only Mac verified; user approved skipping the others). Backend unit coverage 98%. |
| 3. Frontend serving | Next.js static export served by FastAPI at `/` |
| 4. Fake sign-in | Client-side check of `user`/`password`, logout control |
| 5. Database design | users, boards, columns, cards; JSON schema in docs/kanban-schema.json, rationale in docs/DB_MODEL.md |
| 6. Backend API | Board/column/card CRUD on SQLite, every query scoped to the user from the `X-User` header |
| 7. Frontend + backend | Board loaded from and saved to the API, optimistic UI updates, `col-`/`card-` id prefixing for drag-and-drop, Playwright runs against the backend-served build |
| 8. AI connectivity | `/api/chat` calls OpenRouter with `openai/gpt-oss-120b`; live "2+2" integration test (skipped without API key) |
| 9. AI board updates | Structured `{reply, actions}` output (create/update/move/delete card), validated and applied to the DB; invalid targets skipped. Schema in docs/ai-structured-output.json. |
| 10. Chat sidebar | Chat UI inside the board; AI changes replace board state immediately |

## Documentation and code gaps

### 1. frontend/AGENTS.md is out of date

It still describes the original in-memory demo: `KanbanBoard` owning state from `initialData`, and only the board components and `lib/kanban.ts`. Since Part 7:

- `src/app/page.tsx` is the stateful container (login, board state, chat state, all API-calling handlers).
- `KanbanBoard` receives `board` and `onBoardChange` as props and calls the page's handlers.
- Missing from the doc: `ChatSidebar.tsx`, `lib/api.ts` (API client, `toBoardData()`), the login screen, and the id prefix helpers.

CLAUDE.md describes the current architecture correctly.

### 2. Demo-only code paths remain in the frontend

- `KanbanBoard.tsx` `handleAddCard` falls back to `createId("card")` and a local state update when `onAddCard` is not passed. The app (`page.tsx`) always passes `onAddCard`, so this path only runs in `KanbanBoard.test.tsx`.
- `initialData` in `lib/kanban.ts` is only used by `KanbanBoard.test.tsx`.

Removing these would require updating that unit test to supply its own fixture and handler.

### 3. Migration approach in DB_MODEL.md is not implemented

DB_MODEL.md describes versioned, forward-only migrations tracked in `PRAGMA user_version`. Nothing in the code uses `user_version`; `init_db()` only runs `CREATE TABLE` statements on startup. Any future schema change needs either this mechanism built or the doc updated.

### 4. `archived` column is filtered but never set

All card queries in `database.py`, `routes/board.py`, and `ai.py` filter on `archived = 0`, but no code sets `archived = 1`; deleting a card removes the row. This matches the doc's "soft-delete flag for future use", but it is dead state today.

### 5. Conflicting backend test instructions

- docs/PLAN.md (testing notes after Part 8): set `PYTHONPATH` to the repo root and run `pytest backend`.
- CLAUDE.md: run `python -m pytest` from `backend/`.

Tests import `app.*`, which resolves from `backend/`, so the CLAUDE.md version is the correct one. The PLAN.md note should be updated.

### 6. Minor

- backend/AGENTS.md lists `GET /api/hello`, a scaffolding example endpoint from Part 2 that is still present.
- Windows and Linux start/stop scripts have never been verified.
