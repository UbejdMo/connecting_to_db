"""Task API - Week 2 assignment.

A tiny CRUD API over an in-memory list, documented at /docs.
Every error answers {"error": "..."}, validation failures are 400 (never
FastAPI's default 422), and DELETE returns a bare 204.

Run it with:  uvicorn main:app --reload
"""

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Task API",
    description=(
        "A minimal task tracker built for Week 2.\n\n"
        "Tasks live in a plain Python list in memory, so **everything is lost "
        "when the server restarts** - that is intentional, not a bug.\n\n"
        "Errors always come back as a JSON object with a single *error* key, "
        "and invalid input is 400, never 422."
    ),
    version="1.0",
)

# The whole database. It lives in RAM and dies with the process - on purpose.
tasks = [
    {"id": 1, "title": "Buy milk", "done": False},
    {"id": 2, "title": "Read a chapter of the FastAPI docs", "done": True},
    {"id": 3, "title": "Walk the dog", "done": False},
]

TITLE_ERROR = "title is required and must be a non-empty string"
DONE_ERROR = "done must be true or false"
EMPTY_UPDATE_ERROR = "send at least one of title or done"


class Task(BaseModel):
    """One task, exactly as it appears in every successful response."""

    id: int
    title: str
    done: bool


class Error(BaseModel):
    """The one and only error shape this API produces."""

    error: str


# Reusable OpenAPI blocks so each route documents its failures without repeating
# the schema. These describe responses; they do not enforce anything.
NOT_FOUND = {"model": Error, "description": "No task with that id"}
BAD_REQUEST = {"model": Error, "description": "The request body failed validation"}


@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    """Rewrite every HTTPException into the graded error shape.

    Raising HTTPException(404, "Task 99 not found") would normally produce
    {"detail": "Task 99 not found"}. This handler intercepts it and emits
    {"error": "Task 99 not found"} instead, so route code stays readable.
    """
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc: RequestValidationError):
    """Catch what FastAPI itself rejects before a route ever runs.

    Unparseable JSON, a missing body, or /tasks/abc never reach my code -
    FastAPI raises RequestValidationError and answers 422 with a list under
    "detail". The contract says 400 and {"error": ...}, so translate here.
    """
    first = exc.errors()[0]
    # loc looks like ("path", "task_id") or ("body", 0); keep only the named
    # parts so the client sees "task_id: ...", never a character offset.
    named = [part for part in first["loc"] if isinstance(part, str)]
    field = ".".join(part for part in named if part not in ("body", "query", "path"))
    message = f"{field}: {first['msg']}" if field else f"invalid request body: {first['msg']}"
    return JSONResponse(status_code=400, content={"error": message})


def find_task(task_id: int):
    """Return the task dict with this id, or None."""
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


def clean_title(payload: dict) -> str:
    """Validate the client's title and hand back a trimmed one.

    The server never trusts the client: the key may be absent, be null, be a
    number, or be nothing but spaces. Every one of those is a 400.
    """
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(status_code=400, detail=TITLE_ERROR)
    return title.strip()


def next_id() -> int:
    """Highest id currently in the list plus one."""
    return max((task["id"] for task in tasks), default=0) + 1


@app.get(
    "/",
    tags=["meta"],
    summary="Service information",
    description="Name, version, and where to find the interesting endpoints.",
)
def read_root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get(
    "/health",
    tags=["meta"],
    summary="Liveness probe",
    description="Returns 200 as long as the process is up. Cheap on purpose - "
    "monitors and load balancers hit this every few seconds.",
)
def health():
    return {"status": "ok"}


@app.get(
    "/tasks",
    response_model=list[Task],
    tags=["tasks"],
    summary="List every task",
    description="Returns all tasks, oldest first. The list is never paginated.",
)
def list_tasks():
    return tasks


@app.get(
    "/tasks/{task_id}",
    response_model=Task,
    responses={404: NOT_FOUND, 400: BAD_REQUEST},
    tags=["tasks"],
    summary="Get one task",
    description="Looks a task up by id. A non-integer id is a 400; an unknown "
    "integer id is a 404.",
)
def get_task(task_id: int):
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post(
    "/tasks",
    status_code=201,
    response_model=Task,
    responses={400: BAD_REQUEST},
    tags=["tasks"],
    summary="Create a task",
    description="Send a title. The server assigns the id and always starts the "
    "task at done=false - a done sent by the client is ignored.",
)
def create_task(payload: dict = Body(..., examples=[{"title": "Buy milk"}])):
    task = {"id": next_id(), "title": clean_title(payload), "done": False}
    tasks.append(task)
    return task


@app.put(
    "/tasks/{task_id}",
    response_model=Task,
    responses={404: NOT_FOUND, 400: BAD_REQUEST},
    tags=["tasks"],
    summary="Update a task",
    description="Send title, done, or both. Whatever you leave out keeps its "
    "current value, so this is really a partial update. An empty object is a 400.",
)
def update_task(
    task_id: int,
    payload: dict = Body(..., examples=[{"title": "Buy oat milk", "done": True}]),
):
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Both fields are optional, but an empty body means the client asked for
    # nothing - that is a mistake worth reporting, not a silent no-op.
    if "title" not in payload and "done" not in payload:
        raise HTTPException(status_code=400, detail=EMPTY_UPDATE_ERROR)

    if "title" in payload:
        task["title"] = clean_title(payload)
    if "done" in payload:
        if not isinstance(payload["done"], bool):
            raise HTTPException(status_code=400, detail=DONE_ERROR)
        task["done"] = payload["done"]

    return task


@app.delete(
    "/tasks/{task_id}",
    status_code=204,
    response_class=Response,
    responses={204: {"description": "Deleted. The body is empty."}, 404: NOT_FOUND},
    tags=["tasks"],
    summary="Delete a task",
    description="Removes the task and returns 204 with no body at all.",
)
def delete_task(task_id: int):
    task = find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    tasks.remove(task)
    # 204 means "done, and there is deliberately nothing to send back".
    # Returning a dict here would make FastAPI write a body that contradicts
    # the status line, so hand back a bodyless Response instead.
    return Response(status_code=204)


def custom_openapi():
    """Generate the OpenAPI document, minus the 422s this API never sends.

    FastAPI adds a 422 response to every route that takes a parameter, because
    that is what it would normally return for bad input. The validation handler
    above turns those into 400s, so leaving 422 in the document would document
    a status code that can never actually arrive.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    for operations in schema["paths"].values():
        for operation in operations.values():
            operation["responses"].pop("422", None)
    for unused in ("HTTPValidationError", "ValidationError"):
        schema["components"]["schemas"].pop(unused, None)

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
