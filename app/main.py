import logging
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import repository as repo
from app.db import get_connection
from app.pipeline import SearchAssistant

logger = logging.getLogger("lms_search")
BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "public" / "index.html"

app = FastAPI(
    title="LMS Search Query Understanding Assistant",
    description="Understands learner intent and returns only records from the LMS dataset.",
    version="1.0.0",
)

# ------------------------------------------------------------------ helpers
_assistant = None
_assistant_lock = threading.Lock()


def get_assistant() -> SearchAssistant:
    """Create the assistant once, on first use."""
    global _assistant
    with _assistant_lock:
        if _assistant is None:
            try:
                _assistant = SearchAssistant()
            except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
                raise HTTPException(503, f"Service not ready: {exc}")
        return _assistant


def open_db():
    try:
        return get_connection()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))


RATE_LIMIT = 20          # searches allowed per IP
RATE_WINDOW = 60         # seconds
_hits = defaultdict(deque)
_hits_lock = threading.Lock()


def check_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _hits_lock:
        queue = _hits[ip]
        while queue and now - queue[0] > RATE_WINDOW:
            queue.popleft()
        if len(queue) >= RATE_LIMIT:
            raise HTTPException(429, "Too many searches. Please wait a minute and try again.")
        queue.append(now)

def require_reviewer(x_review_passcode: str | None = Header(default=None)):
    """If REVIEW_PASSCODE is set, review endpoints need it in a header."""
    expected = os.getenv("REVIEW_PASSCODE")
    if not expected:
        return
    given = (x_review_passcode or "").encode()
    if not secrets.compare_digest(given, expected.encode()):
        raise HTTPException(401, "Reviewer passcode required.")

# ------------------------------------------------------------------ models
class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=1000)
    learner_id: int | None = None


class FeedbackRequest(BaseModel):
    query_id: int
    rating: int
    result_id: int | None = None
    comment: str | None = Field(default=None, max_length=500)


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=50)
    note: str = Field(default="", max_length=300)


# ------------------------------------------------------------------ routes
@app.get("/", include_in_schema=False)
def home():
    if not INDEX_FILE.exists():
        raise HTTPException(404, "public/index.html not found.")
    return FileResponse(INDEX_FILE)


@app.get("/api/health")
def health():
    assistant = get_assistant()
    provider = assistant.provider
    return {
        "status": "ok",
        "llm_provider": provider.name if provider else None,
        "llm_model": provider.model if provider else None,
        "llm_available": provider is not None,
        "llm_note": assistant.provider_error,
    }


@app.post("/api/search")
def search(body: SearchRequest, request: Request):
    check_rate_limit(request)
    assistant = get_assistant()
    try:
        return assistant.run(body.query, body.learner_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Search failed")
        raise HTTPException(500, "Something went wrong while searching. Please try again.")


@app.post("/api/feedback")
def feedback(body: FeedbackRequest):
    conn = open_db()
    try:
        feedback_id = repo.save_feedback(
            conn, body.query_id, body.rating, body.result_id, body.comment)
        return {"feedback_id": feedback_id, "saved": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    finally:
        conn.close()


@app.get("/api/history")
def history(limit: int = Query(20, ge=1, le=100)):
    conn = open_db()
    try:
        return repo.get_history(conn, limit)
    finally:
        conn.close()


@app.get("/api/stats")
def stats():
    conn = open_db()
    try:
        return repo.get_stats(conn)
    finally:
        conn.close()


@app.get("/api/learners")
def learners():
    conn = open_db()
    try:
        return repo.list_learners(conn)
    finally:
        conn.close()


@app.get("/api/review-queue", dependencies=[Depends(require_reviewer)])
def review_queue():
    conn = open_db()
    try:
        return repo.get_review_queue(conn)
    finally:
        conn.close()


@app.post("/api/review-queue/{query_id}/resolve", dependencies=[Depends(require_reviewer)])
def resolve(query_id: int, body: ReviewRequest):
    conn = open_db()
    try:
        repo.resolve_review(conn, query_id, body.reviewer, body.note)
        return {"query_id": query_id, "status": "completed"}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    finally:
        conn.close()


@app.get("/api/trace/{query_id}")
def trace(query_id: int):
    conn = open_db()
    try:
        return repo.get_query_trace(conn, query_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    finally:
        conn.close()