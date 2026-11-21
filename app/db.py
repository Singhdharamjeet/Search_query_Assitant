import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def get_db_path() -> Path:
    path = Path(os.getenv("DB_PATH", "data/lms.db"))
    return path if path.is_absolute() else BASE_DIR / path


def get_connection() -> sqlite3.Connection:
    """Open the SQLite database with foreign keys on and dict-like rows."""
    path = get_db_path()
    if not path.exists():
        raise FileNotFoundError(f"Database not found at {path}. Run: python init_db.py")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn