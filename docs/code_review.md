# Code review (2026-10-06)

Scope: the whole repository at commit `dc78685` - backend (`backend/app`, tests), frontend (`frontend/src`, configs, Playwright spec), Dockerfile, scripts and docs. Documentation drift is already covered in `docs/PROJECT_REVIEW.md` and is only summarised here (section 5).

## Remediation status (2026-10-06)

All High and Medium items (1.1-2.7) are fixed; Low items (section 3 and 4) are not yet addressed.

| # | Fix | Verified by |
|---|---|---|
| 1.1 | `routes/static.py` resolves the path and rejects anything outside the static dir; `api/*` misses return 404 | Unit tests `test_static_fallback_blocks_path_traversal`, `test_static_fallback_404_for_unknown_api_path`; live container returns 404 for `/..%2F..%2Fbackend%2Fdata%2Fpm.db` and `/..%2F..%2F..%2Fetc%2Fpasswd` |
| 1.2 | Start scripts, CLAUDE.md and README use the `pm-data` volume | Card created, container removed and re-run, card still present |
| 1.3 | Loading view only shown before the first board load | Unit test: chat draft survives adding a card |
| 2.1 | Column title saved on blur/Enter; empty title reverts | Unit tests (one call on blur, none for empty); E2E rename persists after reload |
| 2.2 | Non-numeric ids skipped; `ValidationError` and non-JSON bodies return 502 | Unit tests for each case in the table in 2.2 |
| 2.3 | Edit button on each card with inline title/details form | Unit test; E2E edit persists after reload |
| 2.4 | `handleDragEnd` computes the move from props and calls `onMoveCard` outside the updater | E2E drag test |
| 2.5 | `response_format` with the `StructuredChatOutput` JSON schema (`strict: false`) | Unit test asserts the payload; live check blocked (see above) |
| 2.6 | Shared helpers in `database.py` used by both `routes/board.py` and `apply_actions()` | Full backend suite |
| 2.7 | `node:24-slim`, `@types/node` ^24 | Docker build |

Additional bugs found and fixed while remediating:
- Moving a card to a later position within the same column landed one slot short (first of four moved to index 3 ended at index 2). Fixed in the shared `move_card` helper; covered by `test_reorder_card_within_column`.
- The board error banner never appeared: `refreshBoard()` cleared `boardError` immediately after each handler set it. Errors now stay visible until the next action.
- At the default 1280px viewport the card action button rendered outside the 154px-wide column (the old "Remove" button was already clipped). Actions now sit below the card text and long words wrap.
- While a card is being edited, dnd-kit's `aria-disabled` on the card element made the form inputs read as disabled to assistive tech. Drag attributes are now omitted during editing.

Test results after remediation: backend 34 passed (live OpenRouter test fails with 402 from OpenRouter, unrelated to code), coverage 95%; frontend unit 16 passed; Playwright 5 passed against the rebuilt container, including a second run on persisted data; lint clean.

## How findings were verified

- Backend unit tests: 20 passed, 3 skipped (live tests need `PM_BASE_URL`). Coverage 89%.
- Frontend unit tests: 12 passed. Coverage 73% statements. `npm run lint` clean.
- `npx tsc --noEmit`: 38 errors, all in test files (see 4.4).
- Playwright E2E was not run (needs the Docker image built and running).
- Every bug marked "Confirmed" below was reproduced with a TestClient probe or by tracing the code path; the probe output is quoted where relevant.

## Summary

| # | Severity | Area | Finding |
|---|---|---|---|
| 1.1 | High | Backend | Path traversal in the static catch-all route serves any readable file, including `.env` |
| 1.2 | High | Docker | The database lives inside the container and is wiped on every start |
| 1.3 | High | Frontend | Every card add/move/delete unmounts the board and shows the loading screen |
| 2.1 | Medium | Frontend | Column rename sends a PATCH per keystroke; clearing the title reverts it |
| 2.2 | Medium | Backend/AI | Malformed AI output returns 500 instead of being skipped or returning 502 |
| 2.3 | Medium | Frontend | Cards cannot be edited from the UI (business requirement) |
| 2.4 | Medium | Frontend | API call fired from inside a React state updater |
| 2.5 | Medium | Backend/AI | JSON output is not enforced at the model level |
| 2.6 | Medium | Backend | Board mutation logic is duplicated between `routes/board.py` and `ai.py` |
| 2.7 | Medium | Docker | Frontend build stage uses Node 20, which is end-of-life |
| 3.1 | Low | Backend | Deleting every column reseeds the demo board |
| 3.2 | Low | Frontend | "Assistant" label in chat bubbles is white on white |
| 3.3 | Low | Frontend | Drag-and-drop ids are double-prefixed (`card-card-5`) |
| 3.4 | Low | Frontend | Failed-chat placeholder text is sent back to the model as history |
| 3.5 | Low | Frontend | Drag-and-drop is pointer-only (no keyboard sensor) |
| 3.6 | Low | Backend/AI | Prompt sends the board twice; message and history are unbounded |
| 3.7 | Low | Both | Dead and scaffolding code |
| 4.x | Low | Tests/tooling | Coverage gaps, type-check failures, committed test artefact, runtime test deps |

---

## 1. High

### 1.1 Path traversal in the static catch-all (Confirmed)

`backend/app/routes/static.py:47` builds `STATIC_DIR / full_path` from the URL with no containment check. Starlette percent-decodes the path, so `%2F`-encoded `..` segments reach the filesystem.

Probe (static dir `tmp/out`, file `tmp/secret.txt`):

```
GET /..%2Fsecret.txt  ->  200 SECRET
```

Impact:
- Running locally (`uvicorn` from `backend/`), the static dir resolves to `frontend/out`, so `/..%2F..%2F.env` returns the repo-root `.env` with `OPENROUTER_API_KEY`.
- In the container, it exposes `/app/backend/data/pm.db` and any other file readable by `appuser`.

The same route also returns `index.html` with status 200 for unknown API paths (`GET /api/nonexistent -> 200 INDEX`), which hides client mistakes.

Actions
- [ ] (Not taken; the containment check below was used instead, keeping the existing route and tests.) Replace the hand-written catch-all with `app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))` registered after `api_router`. Starlette's `StaticFiles` rejects traversal and serves the exported `404.html` for misses. This also removes most of `routes/static.py` and the separate `/_next` and `/static` mounts in `main.py`.
- [x] If the catch-all is kept instead, resolve the path and require `requested_path.resolve().is_relative_to(STATIC_DIR.resolve())`, and return 404 for paths under `api/`.
- [x] Add a unit test asserting `GET /..%2F<file>` does not return the file.

### 1.2 Database is wiped on every start (Confirmed by code)

`Dockerfile:31` creates `/app/backend/data` inside the image, and every start script (`scripts/start-*.sh:11-13`, `start-windows.ps1:9-11`) runs `docker rm -f` followed by `docker run` with no volume. Each start therefore begins with an empty database and the seed board. Data only survives page reloads within one container's lifetime, which undercuts the Part 7 goal "Kanban data persists across reloads".

Actions
- [x] Add `-v pm-data:/app/backend/data` to the `docker run` line in all three start scripts and in the detached-run command in `CLAUDE.md`. A named volume is initialised from the image directory, so `appuser` ownership carries over.
- [x] Mention the volume (and how to reset it: `docker volume rm pm-data`) in README.

### 1.3 Board unmounts on every mutation (Confirmed by code)

`frontend/src/app/page.tsx:37-49`: `refreshBoard()` sets `isLoading = true`. `page.tsx:290` renders the full-page "Loading your board" view whenever `isLoading` is true. `handleAddCard`, `handleDeleteCard` and `handleMoveCard` all call `refreshBoard()` after a successful request.

Result: after every add, delete or drag, the optimistic update is shown for a moment, then the whole `KanbanBoard` (including the chat sidebar) unmounts, the loading screen flashes, and the board remounts. Any unsent text in the chat textarea and the scroll position are lost.

Actions
- [x] Only show the loading view on the initial load: change the condition to `if (!board)`, or keep `isLoading` for the first fetch and do silent refreshes afterwards.
- [x] Add a unit test that drafts a chat message, adds a card, and asserts the draft is still in the textarea.

---

## 2. Medium

### 2.1 Column rename: one PATCH per keystroke, empty title reverts (Confirmed by code)

`frontend/src/components/KanbanColumn.tsx:50` calls `onRename` on every `onChange`, and `page.tsx:94-107` sends a PATCH for each call. Typing a 12-character title sends 12 requests that can complete out of order. Clearing the field sends `title: ""`, which fails `ColumnUpdate`'s `min_length=1` (422); the error handler then calls `refreshBoard()`, which (because of 1.3) unmounts the board and restores the old title mid-edit.

Actions
- [x] Keep the local optimistic update on change, but persist on blur and on Enter only.
- [x] Skip the request when the trimmed title is empty or unchanged; restore the previous title on blur if empty.

### 2.2 Malformed AI output causes HTTP 500 (Confirmed)

CLAUDE.md states "Invalid action targets are silently skipped", but probe results with a mocked OpenRouter response were:

| Model output | Result |
|---|---|
| `create_card` with `columnId: "Backlog"` (title instead of id) | 500 |
| `delete_card` with `cardId: "card-1"` | 500 |
| an unknown action type | 500 |
| JSON missing `reply` | 500 |

Causes:
- `backend/app/ai.py:137,144,171,195,202,249`: `int(action.columnId)` / `int(action.cardId)` raise `ValueError` for non-numeric ids.
- `ai.py:41`: `StructuredChatOutput.model_validate()` raises `ValidationError`, which is not an `HTTPException`, so FastAPI returns 500.
- `ai.py:72`: `response.json()` on a non-JSON body also escapes as 500.

Because the connection is closed without commit, no partial changes are persisted, which is good. But the user only sees "Something went wrong" and the model's reply is lost.

Actions
- [x] Parse ids with a small helper that returns `None` for non-digit strings, and `continue` on `None`, so bad targets are skipped as documented.
- [x] Catch `ValidationError` in `parse_structured_output` and raise `HTTPException(502, "OpenRouter returned an invalid response")`. Do the same for `response.json()` decoding.
- [x] Add unit tests for each row in the table above.

### 2.3 Cards cannot be edited in the UI (requirement gap)

`AGENTS.md` business requirements: "The cards on the Kanban board can be moved with drag and drop, and edited". `KanbanCard.tsx` only offers "Remove". `PATCH /api/cards/{id}` and `api.updateCard` already support `title` and `details`, so only the UI is missing. Today only the AI can edit cards.

Actions
- [x] Add inline editing to `KanbanCard` (for example, click title/details to edit, save on blur/Enter) wired through a new `onEditCard` handler in `page.tsx` that calls `updateCard`.
- [x] Unit test plus one Playwright test for editing a card.

### 2.4 Side effect inside a state updater

`frontend/src/components/KanbanBoard.tsx:107-114` calls `onMoveCard(...)` (which sends a PATCH) from inside the `setBoard` updater function. Updaters must be pure; React StrictMode (on by default in the App Router) invokes them twice in development, so each drag sends two PATCH requests under `npm run dev`.

Actions
- [x] Compute `nextColumns = moveCard(board.columns, activeId, overId)` from the current `board` prop, call `setBoard({...board, columns: nextColumns})`, then call `onMoveCard` outside the updater.

### 2.5 JSON output is not enforced at the model level

`ai.py:49-53` relies on the system prompt alone to get JSON, plus a brace-extraction fallback (`ai.py:28-40`). OpenRouter supports `response_format` with a JSON schema for models/providers that accept it, which removes most of the failure cases in 2.2 at the source.

Actions
- [x] Send `response_format: {"type": "json_schema", "json_schema": {...}}` built from `StructuredChatOutput.model_json_schema()` (or the existing `docs/ai-structured-output.json`). Keep the fallback parser for providers that ignore it.
- [ ] Verify with the live integration test that `openai/gpt-oss-120b` on OpenRouter honours it. Blocked: the OpenRouter account returns 402 "Insufficient credits" for every request.

### 2.6 Duplicated board mutation logic

The same logic is written out several times:
- insert-position clamping: `routes/board.py:42-46`, `:150-154`, `:227-231`, `ai.py:148-152`, `:224-228`
- move card between columns: `routes/board.py:212-240` and `ai.py:187-238`
- delete card + resequence: `routes/board.py:267-273` and `ai.py:252-258`
- "card belongs to this board" query: 5 copies across both files

The two move implementations are already identical by copy, so a future fix to one will silently miss the other.

Actions
- [x] Move these into `database.py` as plain functions (`get_owned_card`, `insert_card`, `move_card`, `delete_card`, `clamp_position`), each following the existing `resequence_positions()` pattern.
- [x] Have both `routes/board.py` and `apply_actions()` call them. Existing tests should pass unchanged.

### 2.7 Node 20 is end-of-life

`Dockerfile:1` uses `node:20-slim`. Node 20 reached end-of-life in April 2026, and `@types/node` is pinned to `^20` in `frontend/package.json`.

Actions
- [x] Switch to `node:24-slim` (current LTS) and bump `@types/node` to match. Rebuild and run `npm run test:all`.

---

## 3. Low

### 3.1 Deleting every column reseeds the demo board (Confirmed)

`database.py:107-114` seeds whenever a board has zero columns, and `fetch_board()` calls it on every read. Probe: delete all 5 columns via the API, then `GET /api/board` returns 5 seeded columns again. The UI cannot delete columns today, so this is only reachable through the API or a future feature.

- [ ] Seed only when the board row is first created (inside `get_or_create_board`'s insert branch) instead of when the column count is zero.

### 3.2 Assistant label invisible in chat

`frontend/src/components/ChatSidebar.tsx:64` gives the "You"/"Assistant" label `text-white/70` for both roles, but the assistant bubble has a white background.

- [ ] Use `text-[var(--gray-text)]` for the assistant label.

### 3.3 Double-prefixed drag-and-drop ids

Card ids are already `card-<n>` after `toBoardData()`, but `KanbanCard.tsx:15,35` and `KanbanColumn.tsx:59` prefix again (`card-card-5`), and `KanbanColumn.tsx:25,38` produces `column-col-3`. It works because all three sites agree, but it is confusing and the Playwright selectors depend on it.

- [ ] Use `card.id` and `column.id` directly as the sortable/droppable ids and test ids; update `tests/kanban.spec.ts` selectors.

### 3.4 Error placeholder becomes model history

`page.tsx:208-211` appends "Something went wrong. Please try again." as an `assistant` message, and the next `handleSendChat` sends it to the model as real history.

- [ ] Show the failure only via `chatError` (already rendered), or exclude failed turns from `history`.

### 3.5 Drag-and-drop is pointer-only

`KanbanBoard.tsx:46-50` registers only `PointerSensor`; `useSortable` gives cards `role="button"` and focus, but they cannot be moved with the keyboard.

- [ ] Add `useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })`.

### 3.6 Prompt size

`ai.py:85-119` sends both a text summary and the full indented board JSON, plus unbounded `history`. `ChatRequest.message` (`models.py:74`) has no length limit.

- [ ] Drop the text summary or the `indent=2`; cap history (for example, last 20 turns) and add `max_length` to `message`.

### 3.7 Dead and scaffolding code

- `database.py:78-83` `get_db()` duplicates `dependencies.py:10-15` and is unused (shows as uncovered).
- `main.py:39-41` `/api/hello` and `routes/static.py:12-30` fallback HTML are Part 2 scaffolding.
- `lib/kanban.ts` `initialData` and `createId`, and the local fallback in `KanbanBoard.tsx:147-160`, are only exercised by `KanbanBoard.test.tsx` (also noted in PROJECT_REVIEW.md).
- `KanbanBoard.tsx:52` `useMemo(() => board.cards, ...)` adds nothing.
- `config.py:10-11` makes the OpenRouter base URL and model env-overridable, while PLAN.md Part 8 says hardcoded. Either is fine; pick one and make the docs match.

- [ ] Remove the duplicate `get_db`, `/api/hello`, the fallback HTML (if 1.1 switches to `StaticFiles`), and the demo-only frontend paths, updating the tests that use them.

---

## 4. Tests and tooling

### 4.1 Backend coverage gaps

89% overall, but the uncovered lines are the error paths most likely to break:
- `ai.py:28-40` (JSON fallback parser), `66-78` (OpenRouter network/HTTP/shape errors), and every `continue` branch in `apply_actions` (invalid targets).
- `routes/board.py` 404 branches and column reordering (`84-93`).

- [ ] Add tests for these alongside the fixes in 1.1, 2.2 and 3.1.

### 4.2 Frontend coverage gaps

73% statements; `page.tsx` is at 62%. Untested: rename/add/delete/move error handling, chat failure path. Playwright covers load, add card and move card only; there is no E2E for rename, delete, logout or chat (a mocked chat route via `page.route()` would keep it offline).

- [ ] Add unit tests for `page.tsx` error handlers and E2E tests for rename, delete, logout and a mocked chat round-trip.

### 4.3 Test dependencies ship in the runtime image

`backend/requirements.txt` includes `pytest` and `pytest-cov`, which are installed into the production image. `pytest-cov<5` is several majors old. The test run also emits `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`.

- [ ] Split into `requirements.txt` (runtime) and `requirements-dev.txt` (tests), and refresh the upper bounds.

### 4.4 Type check fails on test files

`npx tsc --noEmit` reports 38 errors, all in `*.test.tsx`/`*.test.ts` (`describe`/`it`/`expect` unknown) and `tests/kanban.spec.ts` (implicit `any` for `page`). `next build` does not fail because it only checks app code, so the errors are invisible day to day.

- [ ] Add `"types": ["vitest/globals", "@testing-library/jest-dom"]` to `tsconfig.json` (or import from `vitest` explicitly), type the Playwright helpers with `Page`, and add `tsc --noEmit` to `npm run lint` or `test:all`.

### 4.5 Committed test artefact

`frontend/test-results/.last-run.json` is tracked in git although `.dockerignore` already excludes the folder.

- [ ] `git rm --cached frontend/test-results/.last-run.json` and add `test-results/` to `frontend/.gitignore`.

---

## 5. Documentation

`docs/PROJECT_REVIEW.md` already lists the drift (outdated `frontend/AGENTS.md`, unimplemented `PRAGMA user_version` migrations, unused `archived` flag, conflicting backend test instructions in PLAN.md). Additional items:

- [ ] `CLAUDE.md`: "Invalid action targets are silently skipped" is only true for numeric ids (see 2.2); update after the fix.
- [ ] `scripts/AGENTS.md` still says the folder "will contain" scripts.
- [ ] After 1.2, document the data volume in README and CLAUDE.md.

## 6. Accepted MVP risks (no action now)

- Authentication is client-side only and the backend trusts the `X-User` header, so any caller can act as any user. Acceptable for a local single-user MVP; must change before any shared deployment.
- Card titles and details are sent to the model, and the model can delete cards. Content in a card could instruct the model to do so (prompt injection). Low risk for a single user editing their own board.

## Suggested order

1. 1.1 path traversal (with test).
2. 1.2 data volume.
3. 1.3 loading flash, then 2.1 rename on blur.
4. 2.2 AI error handling and 2.6 shared mutation helpers together (both touch `apply_actions`), then 2.5 `response_format`.
5. 2.3 card editing.
6. Remaining Medium items, then Low items and tooling.
