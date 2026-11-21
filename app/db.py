import os
import shutil
import sqlite3
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SEED_DB = BASE_DIR / "data" / "lms.db"
ON_VERCEL = bool(os.getenv("VERCEL"))
_copy_lock = threading.Lock()


def get_db_path() -> Path:
    if ON_VERCEL:
        
        tmp_db = Path("/tmp/lms.db")
        with _copy_lock:
            if not tmp_db.exists():
                if not SEED_DB.exists():
                    raise FileNotFoundError(f"Seed database missing at {SEED_DB}")
                part = Path("/tmp/lms.db.part")
                shutil.copyfile(SEED_DB, part)
                os.replace(part, tmp_db)     # atomic, so no half-copied file
        return tmp_db

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