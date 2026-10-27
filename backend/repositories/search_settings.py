import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

PATH = Path(__file__).resolve().parents[2] / 'data' / 'search_settings.db'
LOCK = RLock()


def connect():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS search_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        tavily_api_key TEXT NOT NULL
    )''')
    return db


@contextmanager
def connection():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with LOCK, connection():
        pass


def get_tavily_api_key():
    with LOCK, connection() as db:
        row = db.execute(
            'SELECT tavily_api_key FROM search_settings WHERE id = 1'
        ).fetchone()
    return row['tavily_api_key'] if row else ''


def save_tavily_api_key(api_key):
    with LOCK, connection() as db:
        db.execute(
            'INSERT OR REPLACE INTO search_settings(id, tavily_api_key) VALUES (1, ?)',
            (api_key.strip(),),
        )


def clear_tavily_api_key():
    with LOCK, connection() as db:
        db.execute('DELETE FROM search_settings WHERE id = 1')
