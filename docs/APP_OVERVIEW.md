# Project Management MVP - Application Overview

This document describes what the app does, how it is built, and how the pieces work together at runtime. It reflects the code as of this writing; when in doubt, the source in `backend/app/` and `frontend/src/` is authoritative.

## 1. What the app is

A single-page project management tool built around a Kanban board, with an AI assistant in a side panel.

A user can:

- Sign in with the demo credentials (`user` / `password`) and sign out.
- View one personal board with five default columns: Backlog, Discovery, In Progress, Review, Done.
- Rename columns inline.
- Add, edit, and remove cards (each card has a title and details).
- Drag cards within a column or between columns.
- Chat with an AI assistant that can answer questions about the board and create, edit, move, or delete cards on the user's behalf.

All board data is persisted in SQLite, so it survives page reloads and container restarts (when the data volume is mounted).

MVP constraints:

- Login is hardcoded and checked only in the browser.
- One board per user.
- Runs locally in a single Docker container.
- The database schema already supports multiple users and boards for future growth.

## 2. Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (static export), React 19, TypeScript, Tailwind CSS v4, @dnd-kit (core, sortable, utilities), clsx |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic, httpx, python-dotenv |
| Database | SQLite (file `backend/data/pm.db`) via Python's built-in `sqlite3` |
| AI | OpenRouter chat completions API, model `openai/gpt-oss-120b` |
| Packaging | Single multi-stage Docker image; `uv` installs Python dependencies |
| Testing | Vitest + Testing Library (frontend unit), Playwright (E2E), pytest (backend unit and integration) |

## 3. High-level architecture

```
                       Browser (http://localhost:8000)
   +--------------------------------------------------------------+
   |  Next.js static app (React)                                  |
   |   page.tsx  -> login, board state, chat state, API handlers  |
   |   KanbanBoard / KanbanColumn / KanbanCard / NewCardForm      |
   |   ChatSidebar                                                |
   |   lib/api.ts (fetch + X-User header)   lib/kanban.ts         |
   +------------------------------|-------------------------------+
                                  | HTTP (same origin, JSON)
   +------------------------------v-------------------------------+
   |  Docker container "pm-app"  (uvicorn, port 8000)             |
   |                                                              |
   |  FastAPI app (backend/app/main.py)                           |
   |   /health, /api/hello                                        |
   |   api_router:  /api/board, /api/columns, /api/cards,         |
   |                /api/chat                                     |
   |   static:      /_next, /static mounts + catch-all route      |
   |                serving /app/frontend/out                     |
   |                                                              |
   |  database.py ----> SQLite  /app/backend/data/pm.db           |
   |                    (Docker volume "pm-data")                 |
   |  ai.py ----------> OpenRouter (HTTPS)                        |
   +--------------------------------------------------------------+
```

The frontend and backend are served from the same origin, so there is no CORS configuration. In development, `NEXT_PUBLIC_API_BASE` can point the frontend at a different backend URL.

## 4. Repository layout

```
pm/
  Dockerfile                 Multi-stage build (Node build -> Python runtime)
  .env                       OPENROUTER_API_KEY (not committed)
  scripts/                   start/stop scripts for Mac, Linux, Windows
  docs/                      Plan, DB model, schemas, reviews, this overview
  backend/
    requirements.txt
    app/
      main.py                FastAPI app, lifespan, static mounts, router registration
      config.py              Env config, paths, seed board data
      database.py            Schema, board fetch/seed, shared card helpers
      dependencies.py        get_db (per-request connection), get_username (X-User)
      models.py              Pydantic request/response models, ChatAction union
      ai.py                  OpenRouter call, prompt building, output parsing, apply_actions
      routes/
        __init__.py          api_router (board + chat), static_router
        board.py             Board, column, and card endpoints
        chat.py              /api/chat
        static.py            "/" and catch-all static file serving
    tests/                   pytest suites (unit + live integration)
  frontend/
    next.config.ts           output: "export", trailingSlash, unoptimized images
    src/app/page.tsx         Stateful container (auth, board, chat, handlers)
    src/app/layout.tsx       Root layout, fonts, globals.css
    src/components/          KanbanBoard, KanbanColumn, KanbanCard,
                             KanbanCardPreview, NewCardForm, ChatSidebar
    src/lib/api.ts           API client and payload conversion
    src/lib/kanban.ts        Types, id prefix helpers, moveCard, findCardLocation
    tests/kanban.spec.ts     Playwright E2E tests
```

## 5. Build and deployment

### Docker image

The `Dockerfile` has two stages:

1. `node:24-slim` (frontend-build): runs `npm ci` and `npm run build`. Because `next.config.ts` sets `output: "export"`, the build produces a fully static site in `frontend/out`.
2. `python:3.12-slim` (runtime):
   - Installs `curl` (for the health check) and `uv`, then installs `backend/requirements.txt` with `uv pip install --system`.
   - Copies `backend/` to `/app/backend` and the static build to `/app/frontend/out`.
   - Sets `PM_STATIC_DIR=/app/frontend/out`.
   - Runs as non-root user `appuser` (uid 1000) and creates `/app/backend/data`.
   - Exposes port 8000, declares a `HEALTHCHECK` against `/health`, and starts `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

### Start and stop scripts

`scripts/start-*.sh` / `start-windows.ps1` build the image, remove any existing `pm-app` container, and run a new one in the foreground:

```
docker run --name pm-app --env-file .env -v pm-data:/app/backend/data -p 8000:8000 pm-app
```

- `--env-file .env` passes `OPENROUTER_API_KEY` into the container.
- `-v pm-data:/app/backend/data` keeps the SQLite database in a named volume so data survives container rebuilds.

`scripts/stop-*` remove the container. The app is available at http://localhost:8000.

### Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | none | Required for `/api/chat`; missing key returns HTTP 500 |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter endpoint |
| `OPENROUTER_MODEL` | `openai/gpt-oss-120b` | Model id |
| `OPENROUTER_TEMPERATURE` | `0` | Sampling temperature |
| `PM_DB_PATH` | `backend/data/pm.db` | SQLite file location (tests point this at a temp file) |
| `PM_STATIC_DIR` | `frontend/out`, then `/app/frontend/out` | Location of the static frontend build |
| `NEXT_PUBLIC_API_BASE` | `""` (same origin) | Frontend build-time API base URL |

`config.py` loads the repo-root `.env` with `python-dotenv` when running outside Docker.

## 6. Backend

### 6.1 Application startup (`main.py`)

- A FastAPI `lifespan` handler calls `init_db()`, which creates tables and indexes if they do not exist.
- If a static directory is found, `/_next` and `/static` are mounted as `StaticFiles`.
- `GET /health` returns `{"status": "ok"}`; `GET /api/hello` is a simple connectivity endpoint.
- `api_router` (board + chat routes) is registered before `static_router`. This order matters: the static router contains a catch-all `/{full_path:path}` route, so any new API route must be added to `api_router` to avoid being swallowed by the catch-all.

### 6.2 Static file serving (`routes/static.py`)

- `GET /` returns `index.html` from the static build, or a small fallback HTML page if no build exists.
- `GET /{full_path}`:
  - Returns 404 for paths starting with `api/` (unknown API routes do not fall through to the SPA).
  - Resolves the path inside the static directory and rejects anything that escapes it (path traversal protection).
  - Serves a directory's `index.html`, an exact file, or falls back to the root `index.html` (SPA behavior).

### 6.3 Request dependencies (`dependencies.py`)

- `get_db()` opens a new SQLite connection per request (`row_factory = sqlite3.Row`) and closes it afterwards.
- `get_username()` reads the `X-User` request header and defaults to `user`. There is no server-side authentication; the header is trusted as-is.

### 6.4 Data model (`database.py`)

```
users (id, username UNIQUE, password_hash, created_at, updated_at)
  1 ── 1
boards (id, user_id UNIQUE -> users.id, title, created_at, updated_at)
  1 ── n
columns (id, board_id -> boards.id, title, position, created_at, updated_at)
  1 ── n
cards (id, column_id -> columns.id, title, details, position, archived, created_at, updated_at)
```

- Indexes on `boards.user_id`, `columns.board_id`, `cards.column_id`.
- `boards.user_id` is UNIQUE, enforcing one board per user.
- `cards.archived` exists for future soft-delete; current queries only return `archived = 0` cards, and deletes are hard deletes.
- `password_hash` is unused in the MVP.
- Full rationale is in `docs/DB_MODEL.md` and `docs/kanban-schema.json`.

Lazy creation and seeding:

- `get_or_create_user()` inserts the user row on first request for a username.
- `get_or_create_board()` inserts the board on first access.
- `fetch_board()` calls `ensure_seed_data()`, which populates the five default columns and eight sample cards (from `config.INITIAL_COLUMNS`) if the board has no columns.

Board payload returned by `fetch_board()` (and `GET /api/board`):

```json
{
  "board":   { "id": "1", "title": "My Board" },
  "columns": [ { "id": "1", "title": "Backlog", "position": 0, "cardIds": ["1", "2"] } ],
  "cards":   { "1": { "id": "1", "title": "Align roadmap themes", "details": "..." } }
}
```

Ids are numeric in the database and returned as strings.

### 6.5 Ordering model

Columns and cards each have an integer `position`. Instead of computing gaps or fractional positions, every mutation:

1. Loads the current ordered id list (for a board's columns or a column's cards).
2. Modifies the list in Python (insert, remove, move).
3. Calls `resequence_positions()`, which rewrites positions as `0..n-1` in list order.

`clamp_position()` keeps requested positions inside `[0, len]`; `None` means "append to the end". `resequence_positions()` only accepts the `cards` and `columns` table names, since the table name is interpolated into SQL.

### 6.6 Shared card helpers

Both the REST endpoints and the AI action applier use the same helpers, so manual edits and AI edits behave identically:

| Helper | Behavior |
|---|---|
| `get_owned_column(conn, column_id, board_id)` | Returns the column only if it belongs to the board |
| `get_owned_card(conn, card_id, board_id)` | Returns the card (with its `column_id`) only if its column belongs to the board |
| `insert_card(...)` | Inserts at a clamped position and resequences the column |
| `update_card_fields(...)` | Updates title and/or details (only fields that are not `None`) |
| `move_card(...)` | Removes the card from the source list, inserts into the target list, updates `column_id`, resequences both columns |
| `delete_card(...)` | Deletes the card and resequences its column |

Helpers do not commit; the caller commits once at the end of the request.

### 6.7 REST API (`routes/board.py`)

All endpoints resolve the user from `X-User`, then get or create that user's board. Every query is scoped to that board by joining through `columns.board_id`, so a user cannot touch another user's data even by guessing ids (the result is a 404).

| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/api/board` | - | Full board payload (seeds on first access) |
| POST | `/api/columns` | `{title, position?}` | `{"id": "<id>"}` |
| PATCH | `/api/columns/{id}` | `{title?, position?}` | `{"status": "ok"}`; reorders if `position` is set |
| DELETE | `/api/columns/{id}` | - | Deletes the column and its cards, resequences columns |
| POST | `/api/cards` | `{column_id, title, details?, position?}` | `{"id": "<id>"}` |
| PATCH | `/api/cards/{id}` | `{title?, details?, column_id?, position?}` | Updates fields and/or moves the card |
| DELETE | `/api/cards/{id}` | - | Deletes the card, resequences its column |

Validation (Pydantic, `models.py`): column titles 1-200 characters, card titles 1-500, card details up to 5000. Invalid bodies return 422; ids not on the user's board return 404.

The frontend currently uses column rename only; column create/delete/reorder exist in the API but have no UI.

### 6.8 AI chat (`routes/chat.py`, `ai.py`)

`POST /api/chat` body:

```json
{ "message": "Move the QA card to Done", "history": [{"role": "user", "content": "..."}], "apply_updates": true }
```

Processing steps:

1. Resolve the user and load the current board with `fetch_board()`.
2. `build_structured_messages()` builds the prompt:
   - A system message that instructs the model to reply only with JSON `{"reply": string, "actions": [...]}`, lists the four action shapes, keeps replies short, and forbids inventing columns or cards.
   - The system message also includes a one-line column list, a one-line summary of card titles per column, and the full board JSON (with numeric ids the model must reference).
   - The prior conversation (`history`) and the new user message follow.
3. `call_openrouter()` POSTs to `{OPENROUTER_BASE_URL}/chat/completions` with `model`, `messages`, `temperature`, and a `response_format` of type `json_schema` generated from the `StructuredChatOutput` Pydantic model (non-strict). Timeout is 20 seconds.
4. `parse_structured_output()` parses the returned content as JSON. If that fails it extracts the outermost `{...}` and tries again. The result is validated against `StructuredChatOutput`.
5. If `apply_updates` is true and there are actions, `apply_actions()` applies them and the board is re-fetched.
6. The response is returned:

```json
{ "response": "Moved it to Done.", "actions": [ {"type": "move_card", "cardId": "6", "columnId": "5", "position": null} ], "board": { ... }, "model": "openai/gpt-oss-120b" }
```

Action types (discriminated union `ChatAction` on the `type` field):

| type | Fields |
|---|---|
| `create_card` | `columnId`, `title`, `details` (default ""), `position` (optional) |
| `update_card` | `cardId`, `title` (optional), `details` (optional) |
| `move_card` | `cardId`, `columnId`, `position` (optional) |
| `delete_card` | `cardId` |

`apply_actions()` processes actions in order. Ids that are non-numeric or do not belong to the user's board are silently skipped, so a model hallucination cannot affect other data or fail the whole request. All applied actions are committed together at the end.

The JSON schema for the model output is documented in `docs/ai-structured-output.json`.

Error mapping:

| Condition | HTTP status |
|---|---|
| `OPENROUTER_API_KEY` missing | 500 |
| Network error, OpenRouter 4xx/5xx, non-JSON response, missing choices/content | 502 |
| Model content is not JSON, or fails schema validation | 502 |

## 7. Frontend

### 7.1 Build mode

The frontend is a client-rendered single page. `next build` produces static HTML/JS in `frontend/out` (`output: "export"`, `trailingSlash: true`, unoptimized images), which the FastAPI backend serves. There is no Next.js server at runtime.

### 7.2 State container (`src/app/page.tsx`)

`Home` is the only stateful component for application data. It holds:

| State | Purpose |
|---|---|
| `isAuthenticated`, `username`, `error` | Login state |
| `board` (`BoardData` or null) | Current board shown in the UI |
| `boardError` | Banner message for failed board operations |
| `chatMessages`, `chatError`, `isChatSending` | Chat state |

Screens:

1. Not authenticated: login form. Credentials are compared in the browser against `user` / `password`.
2. Authenticated, board not yet loaded: "Loading your board" (or the load error).
3. Authenticated with board: `KanbanBoard` with `ChatSidebar` passed in its `sidebar` slot.

Logout resets authentication, board, and chat state. Login state is held in memory only, so a page reload returns to the login screen (the board data itself is persisted on the server).

### 7.3 API client (`src/lib/api.ts`)

- `apiFetch()` wraps `fetch`: sets `Content-Type: application/json`, adds `X-User: <username>`, applies a 30-second timeout via `AbortController`, and throws on non-2xx responses.
- Functions: `fetchBoard`, `updateColumn`, `createCard`, `updateCard`, `deleteCard`, `sendChat`.
- `toBoardData()` converts the backend payload to the frontend `BoardData` shape and adds id prefixes.

### 7.4 Board model and id prefixing (`src/lib/kanban.ts`)

```ts
type Card = { id: string; title: string; details: string };
type Column = { id: string; title: string; cardIds: string[] };
type BoardData = { columns: Column[]; cards: Record<string, Card> };
```

The backend uses numeric ids (for example `"7"`). The frontend stores them prefixed as `col-7` and `card-7` (`toColumnId`, `toCardId`) so column and card ids never collide inside dnd-kit, and strips the prefix (`fromColumnId`, `fromCardId`) before calling the API.

`moveCard(columns, activeId, overId)` is a pure function that returns new columns after a drag: reorder within a column, move to the end of another column when dropped on the column, or insert before a card when dropped on a card. `findCardLocation()` returns a card's column and index, which the page uses to compute the target `column_id` and `position` for the API.

### 7.5 Components

| Component | Responsibility |
|---|---|
| `KanbanBoard` | Page header, column chips, `DndContext` setup (pointer sensor with a 6px activation distance, custom collision detection: pointer, then rect intersection, then closest corners), drag overlay, and the optional sidebar layout. Applies optimistic updates through `onBoardChange` and then calls the page's handlers. |
| `KanbanColumn` | Droppable column with an inline editable title (commits on blur/Enter, reverts if empty), card count, `SortableContext` for its cards, empty-state drop zone, and `NewCardForm`. |
| `KanbanCard` | Sortable card with view and edit modes; dragging is disabled while editing. Edit and Remove buttons. |
| `KanbanCardPreview` | Static card rendering used inside the drag overlay. |
| `NewCardForm` | Collapsible "Add a card" form (title required, details optional). |
| `ChatSidebar` | Presentational chat panel: message list, error text, textarea (Enter sends, Shift+Enter adds a newline), Send button disabled while sending. |

### 7.6 How user actions flow

Each handler in `page.tsx` clears `boardError`, converts prefixed ids to numbers, calls the API, and on failure shows an error banner and re-fetches the board to undo any optimistic change.

| Action | Optimistic update in UI | API call | After success |
|---|---|---|---|
| Rename column | Yes | `PATCH /api/columns/{id}` `{title}` | Nothing further |
| Add card | No | `POST /api/cards` (empty details become "No details yet.") | Re-fetch board (to get the new id) |
| Edit card | Yes | `PATCH /api/cards/{id}` `{title, details}` | Nothing further |
| Remove card | Yes | `DELETE /api/cards/{id}` | Re-fetch board |
| Drag card | Yes (`moveCard`) | `PATCH /api/cards/{id}` `{column_id, position}` | Re-fetch board |
| Send chat | User message appended immediately | `POST /api/chat` with prior history and `apply_updates: true` | Assistant reply appended; `board` replaced with the board returned by the server |

If a chat request fails, the sidebar shows "Unable to reach the assistant right now." and an assistant message "Something went wrong. Please try again."

### 7.7 Styling

Tailwind CSS v4 with CSS variables defined in `globals.css`. The color scheme:

| Token | Color | Usage |
|---|---|---|
| Accent Yellow | `#ecad0a` | Accent lines, drop-target ring |
| Blue Primary | `#209dd7` | Links, focus borders, user chat bubbles |
| Purple Secondary | `#753991` | Submit buttons, error text |
| Dark Navy | `#032147` | Headings and main text |
| Gray Text | `#888888` | Labels and supporting text |

## 8. End-to-end walkthroughs

### 8.1 First visit

1. Browser loads `/`; FastAPI returns `frontend/out/index.html`, and JS/CSS load from `/_next`.
2. The user signs in with `user` / `password` (checked in the browser).
3. The page calls `GET /api/board` with `X-User: user`.
4. The backend creates the user and board rows if missing, seeds default columns and cards, and returns the board.
5. The frontend converts ids to `col-*` / `card-*` and renders the board.

### 8.2 Dragging a card

1. The user drags a card from Backlog to In Progress.
2. `KanbanBoard.handleDragEnd` resolves the drop target from dnd-kit metadata, computes new columns with `moveCard()`, and updates state immediately.
3. `page.handleMoveCard` finds the card's new column and index and sends `PATCH /api/cards/{id}` with `{column_id, position}`.
4. The backend verifies ownership, calls `move_card()`, resequences both columns, and commits.
5. The frontend re-fetches the board so it matches the server.

### 8.3 Asking the AI to change the board

1. The user types "Add a card called Write tests to Review".
2. The frontend appends the user message and sends `POST /api/chat` with the message and previous history.
3. The backend builds a prompt containing the current board JSON and sends it to OpenRouter.
4. The model returns `{"reply": "Added it to Review.", "actions": [{"type": "create_card", "columnId": "4", "title": "Write tests", "details": "", "position": null}]}`.
5. The backend validates the output, checks column 4 belongs to the user's board, inserts the card, commits, and re-fetches the board.
6. The frontend shows the reply and replaces its board state with the returned board, so the new card appears immediately.

## 9. Testing

### Backend (`backend/tests/`, run with `python -m pytest` from `backend/`)

| File | Covers |
|---|---|
| `test_main.py` | Health and hello endpoints, static serving, SPA fallback, path traversal block, 404 for unknown API paths |
| `test_board_api.py` | Seeded board, column create/rename/delete, card create/move/reorder/edit/delete, 404s |
| `test_chat_api.py` | Missing API key returns 500 |
| `test_chat_structured_api.py` | Actions applied via `/api/chat`, 502 on invalid model output, `json_schema` response format sent (OpenRouter mocked) |
| `test_ai_actions.py` | `parse_structured_output()` (including wrapped JSON and invalid output) and `apply_actions()`, including skipped invalid targets |
| `test_schema.py` | Validates the schema JSON structure in `docs/` |
| `test_integration.py` | Live tests against a running container (`PM_BASE_URL`): health, root, and a live OpenRouter chat (skipped when not configured) |

Unit tests isolate the database by setting `PM_DB_PATH` to a temporary file and calling `init_db()` before creating a `TestClient`.

### Frontend (from `frontend/`)

- `npm run test:unit`: Vitest + Testing Library tests for `page.tsx`, `KanbanBoard`, `KanbanCardPreview`, `ChatSidebar`, and `lib/kanban.ts`.
- `npm run test:e2e`: Playwright tests in `tests/kanban.spec.ts` (load board, add card, move card between columns, edit card and rename column with persistence across reload). The Playwright `webServer` runs the platform start script (or reuses a server already on port 8000), so E2E tests run against the backend-served static build, the same as production.

## 10. Security notes and known limitations

- Authentication is cosmetic: credentials are hardcoded in the frontend, and the backend trusts the `X-User` header. Anyone who can reach the server can act as any user. This is acceptable only for the local MVP.
- No CSRF protection or rate limiting.
- All SQL uses parameterized queries; the only interpolated identifier (table name in `resequence_positions`) is checked against an allowlist.
- Static file serving guards against path traversal.
- The OpenRouter API key stays on the server and is never sent to the browser.
- AI actions are restricted to the requesting user's board; invalid ids are skipped rather than applied.
- Chat history lives only in browser memory and is cleared on logout or reload.
- Column create, delete, and reorder exist in the API but are not exposed in the UI.

## 11. Related documents

- `docs/PLAN.md` - delivery plan and checklist for each part of the MVP
- `docs/DB_MODEL.md` - database design rationale and migration approach
- `docs/kanban-schema.json` - schema proposal as JSON
- `docs/ai-structured-output.json` - JSON schema for AI chat output
- `docs/PROJECT_REVIEW.md`, `docs/code_review.md` - review notes
- `AGENTS.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`, `scripts/AGENTS.md` - per-area notes
