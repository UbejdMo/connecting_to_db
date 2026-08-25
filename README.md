# Task API

A small REST API for tracking tasks, built with FastAPI as the Week 2 assignment. Tasks are kept in a plain Python list in memory, so the data resets every time the server restarts — that is deliberate, and the point of the exercise.

Everything lives in one file, [`main.py`](main.py). No database, no ORM, no file persistence.

## Requirements

- Python 3.10 or newer (built and tested on 3.14)
- `fastapi` — the only dependency

## Install

```bash
git clone https://github.com/<your-username>/task-api.git
cd task-api

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install "fastapi[standard]"
```

## Run

```bash
uvicorn main:app --reload
```

The API is then at <http://localhost:8000> and the interactive docs at <http://localhost:8000/docs>.

## Endpoints

| Method | Path | Description | Success | Errors |
|---|---|---|---|---|
| `GET` | `/` | Service name, version, and where to go next | `200` | — |
| `GET` | `/health` | Liveness probe for monitors and load balancers | `200` | — |
| `GET` | `/tasks` | Every task, oldest first | `200` | — |
| `GET` | `/tasks/{id}` | One task by id | `200` | `400` non-integer id, `404` unknown id |
| `POST` | `/tasks` | Create a task from `{"title": "..."}` | `201` | `400` missing/empty/non-string title |
| `PUT` | `/tasks/{id}` | Update `title`, `done`, or both | `200` | `400` empty body or bad field, `404` unknown id |
| `DELETE` | `/tasks/{id}` | Remove a task; response body is empty | `204` | `404` unknown id |

### The task object

```json
{ "id": 1, "title": "Buy milk", "done": false }
```

### The error shape

Every failure — all of them, no exceptions — comes back as a single-key object:

```json
{ "error": "Task 99 not found" }
```

### Rules the server enforces

1. A new task's `id` is the highest current `id` plus one.
2. A new task is always created with `done: false`. If the client sends `done: true` on create, it is ignored.
3. A `title` that is missing, empty, whitespace-only, or not a string is rejected with `400`. Titles are stored trimmed.
4. `PUT` accepts `title`, `done`, or both. Whatever you leave out keeps its current value. An empty body `{}` is a `400`.
5. `DELETE` returns `204` with a genuinely empty body — no `null`, no `content-length`.

## It works — real output

Captured from a live server; only the `date:` headers are stripped.

```console
$ curl -i http://localhost:8000/tasks
HTTP/1.1 200 OK
server: uvicorn
content-length: 153
content-type: application/json

[{"id":1,"title":"Buy milk","done":false},{"id":2,"title":"Read a chapter of the FastAPI docs","done":true},{"id":3,"title":"Walk the dog","done":false}]

$ curl -i -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d '{"title":"Write the README"}'
HTTP/1.1 201 Created
server: uvicorn
content-length: 48
content-type: application/json

{"id":4,"title":"Write the README","done":false}

$ curl -i -X POST http://localhost:8000/tasks -H "Content-Type: application/json" -d '{}'
HTTP/1.1 400 Bad Request
server: uvicorn
content-length: 60
content-type: application/json

{"error":"title is required and must be a non-empty string"}

$ curl -i -X PUT http://localhost:8000/tasks/4 -H "Content-Type: application/json" -d '{"done":true}'
HTTP/1.1 200 OK
server: uvicorn
content-length: 47
content-type: application/json

{"id":4,"title":"Write the README","done":true}

$ curl -i -X DELETE http://localhost:8000/tasks/4
HTTP/1.1 204 No Content
server: uvicorn

$ curl -i http://localhost:8000/tasks/4
HTTP/1.1 404 Not Found
server: uvicorn
content-length: 28
content-type: application/json

{"error":"Task 4 not found"}
```

## Interactive docs

FastAPI generates an OpenAPI document at `/openapi.json` and serves Swagger UI at `/docs`, where every endpoint can be run from the browser.

![Swagger UI showing a successful POST /tasks](docs/swagger.png)

![Swagger UI showing the 404 error shape](docs/swagger-404.png)

## Notes / what I learned

**Getting `{"error": ...}` instead of `{"detail": ...}`.** FastAPI's `HTTPException` produces a `detail` key. Rather than returning a hand-built `JSONResponse` from every route, one `@app.exception_handler(HTTPException)` rewrites the body in a single place — so route code stays as a readable `raise HTTPException(404, ...)` and no future endpoint can leak the wrong shape.

**Getting `400` instead of `422`.** Some bad requests never reach a route at all: malformed JSON, a missing body, or `/tasks/abc`. FastAPI rejects those itself with `RequestValidationError` and a `422`. A second handler catches it and translates to `400`. The title rules are checked by hand inside the route instead, because the spec demands one exact error message and Pydantic would have supplied its own wording.

**A `204` must not have a body.** Returning a dict from a `204` route makes FastAPI serialize it anyway, producing a response that contradicts its own status line. Returning a bare `Response(status_code=204)` is the fix.

**The docs can lie.** FastAPI automatically documents a `422` on every route with a parameter, even though this API converts all of those to `400`. I override `app.openapi()` to strip those entries, so `/docs` describes what actually happens.

**PUT vs PATCH.** With both fields optional and omitted fields preserved, what I built is really PATCH behaviour served under the PUT verb. A strict PUT would replace the whole resource and reset anything left out.

**`max(id) + 1`, not `len(tasks) + 1`.** Length-based ids collide as soon as anything is deleted from the middle: with tasks 1, 2, 3, delete task 2 and `len + 1` hands out `3` — an id that already exists. One consequence of the `max + 1` rule is that deleting the *highest* task frees its id for reuse; that follows from the spec as written.

### The mortality experiment

I created two tasks (ids 4 and 5, five tasks in total), stopped the server, started it again, and called `GET /tasks` — the two new tasks were gone and only the three seed tasks came back, with ids 4 and 5 free to be handed out again.

The list only ever existed in the process's memory, so killing the process destroyed it; nothing was ever written anywhere else. Persistence is not something a web framework gives you for free — it is a separate decision to write state to a database or a file, which is what Week 3 is about.
