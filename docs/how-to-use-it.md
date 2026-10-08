# How to Use It

A Kanban board with an AI assistant. Sign in, manage cards, and ask the AI to update the board for you.

## 1. Start the app

Requirements: Docker and an OpenRouter API key (only needed for AI chat).

Create `.env` in the repo root:

```
OPENROUTER_API_KEY=your-key-here
OPENROUTER_MODEL=openai/gpt-oss-120b
```

`OPENROUTER_MODEL` is optional. Default is `openai/gpt-oss-120b`. Restart after changing `.env`.

Run:

- Mac: `scripts/start-mac.sh`
- Linux: `scripts/start-linux.sh`
- Windows: `scripts/start-windows.ps1`

Open http://localhost:8000 and sign in with `user` / `password`.

Stop:

- Mac: `scripts/stop-mac.sh`
- Linux: `scripts/stop-linux.sh`
- Windows: `scripts/stop-windows.ps1`

## 2. Use the board

- Columns: default board has Backlog, Discovery, In Progress, Review, Done. Click a column title to rename it (Enter or blur to save).
- Add a card: click "Add a card" in a column, enter title (required) and details (optional).
- Edit a card: click Edit on the card, change title/details, save.
- Remove a card: click Remove on the card.
- Move a card: drag it within a column or to another column.
- Reloading the page returns you to login, but board data is saved on the server.

## 3. Use the AI chat

Open the sidebar panel and type a message. Enter sends, Shift+Enter adds a newline.

Example prompts:

- `Add a card called Write tests to Review`
- `Move the QA card to Done`
- `Rename card X to Y`
- `Delete the card called Z`
- `Summarize what is in each column`

The assistant replies and the board updates automatically. Chat history is kept in browser memory only and clears on logout or reload.

If chat fails: without `OPENROUTER_API_KEY` the server returns 500; bad model output or network errors return 502 and the sidebar shows "Unable to reach the assistant right now." Free `:free` models are limited to about 20 requests per minute and 50 per day.

## 4. Data and reset

Board data is stored in the `pm-data` Docker volume and survives restarts. To reset to the default board:

```
docker rm -f pm-app
docker volume rm pm-data
```

Then start again.

## 5. Troubleshooting

- Port busy: stop anything on port 8000 or stop the existing `pm-app` container.
- Changed `.env`: rebuild/restart via the start script.
- Login fails: credentials are `user` / `password`, checked in the browser.
- Board error banner: an optimistic change failed; the app re-fetches the board to restore it.

MVP limits: one board per user, local Docker only, no real authentication. See `docs/APP_OVERVIEW.md` for architecture details.
