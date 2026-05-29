# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dev server (localhost:5001)
python app.py
```

No build step, no test suite, no linter configured.

## Architecture

ReelBrain is a two-file app: a Flask backend (`app.py`) and a single-page frontend (`templates/index.html`). There is no database — all video data and chat history live in the browser's `localStorage`.

### Backend (`app.py`)

Four routes:

| Route | Method | Behaviour |
|---|---|---|
| `/` | GET | Renders `index.html` |
| `/api/chat` | POST | Streaming SSE — handles both `video_chat` and `library_chat` modes |
| `/api/process` | POST | Non-streaming — extracts structured metadata from a transcript using Claude |
| `/api/digest` | POST | Streaming SSE — generates a weekly digest across a list of videos |

The Anthropic API key is **sent by the client on every request** (`data.get('api_key')`). The server holds no credentials. A fresh `anthropic.Anthropic(api_key=...)` client is instantiated per request.

Context is injected into the Claude conversation as a fake user/assistant exchange at the top of `messages`:
```python
full_messages = [
    {'role': 'user', 'content': f'<context>\n{context_json}\n</context>'},
    {'role': 'assistant', 'content': 'Got it.'},
    *messages
]
```

`SYSTEM_PROMPT` at the top of `app.py` controls ReelBrain's entire personality and the three operating modes (`video_chat`, `library_chat`, `weekly_digest`). Editing it is the primary lever for changing AI behaviour.

### Frontend (`templates/index.html`)

Vanilla JS, no framework. Three views toggled with `show(viewId)`:
- `v-setup` — API key entry (first launch only)
- `v-library` — video grid with search bar
- `v-video-chat` — per-video chat interface

Two modals sit on top: `modal-library-chat` (cross-library AI search) and `modal-digest` (weekly digest).

SSE streaming is handled by `streamSSE(response, onChunk)` — it reads the response body as a stream and calls `onChunk` for each `data:` line until `[DONE]`.

The `state` object is the single source of truth at runtime; `loadState()` / `saveVideos()` / `saveVideoMessages()` sync it to `localStorage`.

### Deployment

`Procfile` targets Railway. The server binds to `0.0.0.0` and reads `PORT` from the environment (falls back to `5001` locally).
