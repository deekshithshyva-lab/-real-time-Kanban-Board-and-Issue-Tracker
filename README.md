# Realtime Kanban & Issue Tracker

FastAPI + SQLAlchemy (async) + PostgreSQL full-text search + Redis pub/sub WebSockets. React frontend in `frontend/` (next step).

```
kanban/
├── docker-compose.yml          # Postgres 16 + Redis 7
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py             # app + lifespan (create tables, start Redis listener)
│       ├── config.py           # settings
│       ├── database.py         # async engine / session
│       ├── models.py           # User, Board, BoardMember, Task, Comment
│       ├── schemas.py          # pydantic models
│       ├── security.py         # bcrypt + JWT
│       ├── deps.py             # auth + membership helpers
│       ├── realtime/manager.py # WebSocket rooms + Redis pub/sub
│       ├── services/positions.py  # fractional ordering for drag & drop
│       └── routers/            # auth, boards, tasks (CRUD/move/search), comments, ws
└── frontend/                   # React + @hello-pangea/dnd (coming next)
```

## Run the backend (Python 3.11+)

```bash
docker compose up -d                      # Postgres + Redis
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for interactive API docs. Use a single uvicorn process in dev
(multiple workers would race on `create_all`; Redis pub/sub itself supports many workers).

## Quick smoke test

```bash
# register two users
curl -s localhost:8000/api/auth/register -H 'content-type: application/json' \
  -d '{"email":"a@x.com","display_name":"Ana","password":"password123"}'
# -> copy access_token as $T, then:
curl -s localhost:8000/api/boards -H "authorization: Bearer $T" -H 'content-type: application/json' -d '{"name":"Sprint 1"}'
curl -s localhost:8000/api/boards/1/tasks -H "authorization: Bearer $T" -H 'content-type: application/json' \
  -d '{"title":"Fix authentication bug","priority":"high"}'
curl -s "localhost:8000/api/boards/1/tasks/search?q=auth" -H "authorization: Bearer $T"
# watch live events in another terminal (npx wscat -c "ws://localhost:8000/ws/boards/1?token=$T")
```

## REST API (prefix `/api`)

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | returns `{access_token, user}` |
| GET | `/auth/me` | |
| POST / GET | `/boards` | create / list my boards |
| GET / DELETE | `/boards/{id}` | snapshot (members + tasks) / delete (owner) |
| POST | `/boards/{id}/members` | add by email (owner) |
| POST | `/boards/{id}/tasks` | create issue |
| GET | `/boards/{id}/tasks/search?q=` | prefix full-text search, ranked |
| GET / PATCH / DELETE | `/tasks/{id}` | read / partial update / delete |
| POST | `/tasks/{id}/move` | `{status, index}` drag & drop |
| GET / POST | `/tasks/{id}/comments` | |
| DELETE | `/comments/{id}` | author only |

Send header `X-Client-ID: <uuid per browser window>` on mutations; it's echoed as `origin` in events.

## WebSocket contract

`ws://localhost:8000/ws/boards/{board_id}?token=<JWT>` (send `"ping"` every ~25s, server replies `"pong"`).
Close 4401 = bad token, 4403 = not a member.

```json
{"type": "task.moved", "board_id": 1, "origin": "client-uuid", "data": { /* TaskOut */ }}
```

| type | data |
|---|---|
| `task.created` / `task.updated` / `task.moved` | full task object (clients upsert by `id`, sort by `position`) |
| `task.deleted` | `{id, board_id}` |
| `comment.created` / `comment.deleted` | comment / `{id, task_id}` |
| `member.added` | `{user, role}` |
| `board.refresh` | `{}`: refetch `GET /boards/{id}` (column rebalanced or Redis reconnected) |

## Design notes

- **Real-time path**: REST mutation -> commit -> `PUBLISH board:<id>` -> every server process's `PSUBSCRIBE board:*` listener -> local sockets. Works across many workers/machines.
- **Search speed**: a generated `tsvector` column + GIN index; query is index-only on `board_id`/vector, no table scans. Verify your latency with `EXPLAIN ANALYZE` and the browser Network tab; local Postgres typically answers in single-digit ms, but I haven't benchmarked your dataset.
- **Ordering**: fractional `position` floats, so a drag updates one row; columns auto-rebalance if gaps get tiny.
- **Not included yet**: Alembic migrations, tests, presence indicators, rate limiting.
