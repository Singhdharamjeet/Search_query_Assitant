import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "lms.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> None:
    """Create the SQLite database and all tables from schema.sql."""
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    print(f"Database ready at {db_path}")


if __name__ == "__main__":
    init_db()