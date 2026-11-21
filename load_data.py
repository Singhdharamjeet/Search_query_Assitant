import sqlite3
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lms.db"

REQUIRED_COLUMNS = {
    "learners": ["alias", "level"],
    "courses": ["title", "category", "level", "description", "tags"],
    "lessons": ["course_id", "title", "summary", "duration_min", "position"],
    "synonyms": ["term", "canonical_term"],
}
LOAD_ORDER = ["learners", "courses", "lessons", "synonyms"]


RESET_ORDER = [
    "feedback", "llm_calls", "search_results", "search_queries",
    "lessons", "courses", "learners", "synonyms", "audit_log",
]


def read_csv(table: str) -> pd.DataFrame:
    """Read one CSV and validate columns and empty values."""
    path = DATA_DIR / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing data file: {path}")

    df = pd.read_csv(path, dtype=str).dropna(how="all")
    required = REQUIRED_COLUMNS[table]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{table}.csv is missing columns: {missing}")

    df = df[required].apply(lambda col: col.str.strip())
    if df.isnull().any().any():
        raise ValueError(f"{table}.csv has empty values in required columns")

    for col in ("course_id", "duration_min", "position"):
        if col in df.columns:
            df[col] = df[col].astype(int)
    return df


def table_has_rows(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None


def reset_tables(conn: sqlite3.Connection) -> None:
    for table in RESET_ORDER:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")  # restart ids from 1


def load_all(reset: bool = False) -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError("Database not found. Run: python init_db.py")

    frames = {table: read_csv(table) for table in LOAD_ORDER}  # validate first

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")

        if reset:
            reset_tables(conn)
        elif any(table_has_rows(conn, t) for t in LOAD_ORDER):
            print("Data already loaded. Use --reset to reload from scratch.")
            return

        for table in LOAD_ORDER:
            frames[table].to_sql(table, conn, if_exists="append", index=False)
            print(f"Loaded {len(frames[table]):>3} rows into {table}")

        conn.execute(
            "INSERT INTO audit_log (entity, action, actor, details) "
            "VALUES ('database', 'seed_data_loaded', 'load_data.py', ?)",
            (f"reset={reset}",),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        load_all(reset="--reset" in sys.argv)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        sys.exit(1)