import json

QUERY_FIELDS = {"cleaned_query", "intent", "entities_json", "confidence", "status"}
MAX_COMMENT = 500


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def add_audit(conn, entity, entity_id, action, actor="system", details=None):
    if details is not None and not isinstance(details, str):
        details = json.dumps(details)
    conn.execute(
        "INSERT INTO audit_log (entity, entity_id, action, actor, details) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity, entity_id, action, actor, details))
    conn.commit()


def learner_exists(conn, learner_id) -> bool:
    return conn.execute(
        "SELECT 1 FROM learners WHERE learner_id = ? AND status = 'active'",
        (learner_id,)).fetchone() is not None


def create_query(conn, learner_id, raw_query) -> int:
    cur = conn.execute(
        "INSERT INTO search_queries (learner_id, raw_query, status) "
        "VALUES (?, ?, 'received')", (learner_id, raw_query))
    conn.commit()
    return cur.lastrowid


def update_query(conn, query_id, **fields) -> None:
    bad = set(fields) - QUERY_FIELDS
    if bad:
        raise ValueError(f"Cannot update fields: {sorted(bad)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)   # names are whitelisted
    conn.execute(
        f"UPDATE search_queries SET {assignments}, updated_at = datetime('now') "
        "WHERE query_id = ?", (*fields.values(), query_id))
    conn.commit()


def save_results(conn, query_id, courses, lessons, source) -> None:
    for rank, course in enumerate(courses, 1):
        conn.execute(
            "INSERT INTO search_results (query_id, course_id, lesson_id, score, rank, source) "
            "VALUES (?, ?, NULL, ?, ?, ?)",
            (query_id, course["course_id"], course.get("score", 0), rank, source))
    for rank, lesson in enumerate(lessons, 1):
        conn.execute(
            "INSERT INTO search_results (query_id, course_id, lesson_id, score, rank, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (query_id, lesson["course_id"], lesson["lesson_id"],
             lesson.get("score", 0), rank, source))
    conn.commit()


def save_llm_call(conn, query_id, call, status, error_message=None) -> None:
    conn.execute(
        "INSERT INTO llm_calls (query_id, provider, model, prompt_version, request_json, "
        "response_json, input_tokens, output_tokens, latency_ms, status, error_message) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (query_id, call.provider, call.model, call.prompt_version,
         json.dumps(call.request_payload), call.raw_text, call.input_tokens,
         call.output_tokens, call.latency_ms, status, error_message))
    conn.commit()


def save_feedback(conn, query_id, rating, result_id=None, comment=None) -> int:
    if rating not in (-1, 1):
        raise ValueError("Rating must be 1 (helpful) or -1 (not helpful).")
    if conn.execute("SELECT 1 FROM search_queries WHERE query_id = ?",
                    (query_id,)).fetchone() is None:
        raise ValueError("Query not found.")
    if result_id is not None and conn.execute(
            "SELECT 1 FROM search_results WHERE result_id = ? AND query_id = ?",
            (result_id, query_id)).fetchone() is None:
        raise ValueError("Result does not belong to this query.")
    comment = (comment or "").strip()[:MAX_COMMENT] or None
    cur = conn.execute(
        "INSERT INTO feedback (query_id, result_id, rating, comment) VALUES (?, ?, ?, ?)",
        (query_id, result_id, rating, comment))
    conn.commit()
    add_audit(conn, "search_query", query_id, "feedback_saved", actor="learner",
              details={"rating": rating})
    return cur.lastrowid


def get_history(conn, limit=20):
    return _rows(
        conn,
        "SELECT query_id, learner_id, raw_query, intent, confidence, status, created_at "
        "FROM search_queries ORDER BY query_id DESC LIMIT ?", (limit,))


def get_review_queue(conn):
    return _rows(
        conn,
        "SELECT query_id, raw_query, intent, confidence, created_at "
        "FROM search_queries WHERE status = 'needs_review' ORDER BY query_id")


def resolve_review(conn, query_id, reviewer, note="") -> None:
    """A human closes a review item. Nothing else is changed automatically."""
    row = conn.execute("SELECT status FROM search_queries WHERE query_id = ?",
                       (query_id,)).fetchone()
    if row is None:
        raise ValueError("Query not found.")
    if row["status"] != "needs_review":
        raise ValueError("Query is not waiting for review.")
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ValueError("Reviewer name is required.")
    update_query(conn, query_id, status="completed")
    add_audit(conn, "search_query", query_id, "review_resolved",
              actor=reviewer[:50], details=(note or "")[:300])


def get_query_trace(conn, query_id) -> dict:
    """Everything stored for one query: NLP result, results, API call, audit."""
    query = _rows(conn, "SELECT * FROM search_queries WHERE query_id = ?", (query_id,))
    if not query:
        raise ValueError("Query not found.")
    return {
        "query": query[0],
        "results": _rows(
            conn,
            "SELECT sr.result_id, sr.source, sr.rank, sr.score, sr.course_id, "
            "c.title AS course_title, sr.lesson_id, l.title AS lesson_title "
            "FROM search_results sr JOIN courses c ON c.course_id = sr.course_id "
            "LEFT JOIN lessons l ON l.lesson_id = sr.lesson_id "
            "WHERE sr.query_id = ? ORDER BY sr.source, sr.rank", (query_id,)),
        "llm_calls": _rows(
            conn,
            "SELECT call_id, provider, model, prompt_version, status, latency_ms, "
            "input_tokens, output_tokens, error_message, created_at "
            "FROM llm_calls WHERE query_id = ?", (query_id,)),
        "audit": _rows(
            conn,
            "SELECT action, actor, details, created_at FROM audit_log "
            "WHERE entity = 'search_query' AND entity_id = ? ORDER BY audit_id",
            (query_id,)),
        "feedback": _rows(conn, "SELECT * FROM feedback WHERE query_id = ?", (query_id,)),
    }


def list_learners(conn):
    return _rows(
        conn,
        "SELECT learner_id, alias, level FROM learners "
        "WHERE status = 'active' ORDER BY learner_id")


def get_stats(conn) -> dict:
    by_status = {
        r["status"]: r["n"]
        for r in _rows(conn, "SELECT status, COUNT(*) AS n FROM search_queries GROUP BY status")
    }
    avg = conn.execute(
        "SELECT AVG(latency_ms) FROM llm_calls WHERE status = 'success'").fetchone()[0]
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "avg_llm_latency_ms": round(avg) if avg else None,
    }