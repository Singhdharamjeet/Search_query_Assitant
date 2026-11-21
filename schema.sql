PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS learners (
    learner_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    alias        TEXT NOT NULL,
    level        TEXT NOT NULL DEFAULT 'beginner'
                 CHECK (level IN ('beginner','intermediate','advanced')),
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','inactive')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS courses (
    course_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    category     TEXT NOT NULL,
    level        TEXT NOT NULL
                 CHECK (level IN ('beginner','intermediate','advanced')),
    description  TEXT NOT NULL,
    tags         TEXT,
    status       TEXT NOT NULL DEFAULT 'published'
                 CHECK (status IN ('published','draft','archived')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lessons (
    lesson_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id    INTEGER NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    duration_min INTEGER NOT NULL DEFAULT 10,
    position     INTEGER NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'published'
                 CHECK (status IN ('published','draft','archived')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synonyms (
    synonym_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    term           TEXT NOT NULL UNIQUE,
    canonical_term TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_queries (
    query_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id    INTEGER,
    raw_query     TEXT NOT NULL,
    cleaned_query TEXT,
    intent        TEXT,
    entities_json TEXT,
    confidence    REAL,
    status        TEXT NOT NULL DEFAULT 'received'
                  CHECK (status IN ('received','parsed','searched','llm_done',
                                    'llm_failed','completed','needs_review',
                                    'rejected')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (learner_id) REFERENCES learners(learner_id)
);

CREATE TABLE IF NOT EXISTS search_results (
    result_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id   INTEGER NOT NULL,
    course_id  INTEGER NOT NULL,
    lesson_id  INTEGER,
    score      REAL NOT NULL DEFAULT 0,
    rank       INTEGER NOT NULL,
    source     TEXT NOT NULL DEFAULT 'tfidf'
               CHECK (source IN ('tfidf','llm','fallback')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (query_id)  REFERENCES search_queries(query_id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    FOREIGN KEY (lesson_id) REFERENCES lessons(lesson_id)
);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id       INTEGER NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    request_json   TEXT,
    response_json  TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    latency_ms     INTEGER,
    status         TEXT NOT NULL
                   CHECK (status IN ('success','timeout','error','invalid_response')),
    error_message  TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (query_id) REFERENCES search_queries(query_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id    INTEGER NOT NULL,
    result_id   INTEGER,
    rating      INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    comment     TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (query_id)  REFERENCES search_queries(query_id) ON DELETE CASCADE,
    FOREIGN KEY (result_id) REFERENCES search_results(result_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    action     TEXT NOT NULL,
    actor      TEXT NOT NULL DEFAULT 'system',
    details    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lessons_course   ON lessons(course_id);
CREATE INDEX IF NOT EXISTS idx_queries_created  ON search_queries(created_at);
CREATE INDEX IF NOT EXISTS idx_results_query    ON search_results(query_id);
CREATE INDEX IF NOT EXISTS idx_llm_query        ON llm_calls(query_id);