"""Local-only key persistence, without a vault/password. Secrets are stored in SQLite plaintext.
Protect the data directory with filesystem permissions; never commit or share it.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

PATH = Path(__file__).resolve().parents[1] / "data" / "api_keys.db"
LOCK = RLock()

def connect():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(PATH, timeout=15)
    db.execute("CREATE TABLE IF NOT EXISTS saved_keys (id TEXT PRIMARY KEY, label TEXT NOT NULL, secret TEXT NOT NULL, provider TEXT NOT NULL DEFAULT 'groq')")
    columns = {row[1] for row in db.execute("PRAGMA table_info(saved_keys)")}
    if "provider" not in columns:
        db.execute("ALTER TABLE saved_keys ADD COLUMN provider TEXT NOT NULL DEFAULT 'groq'")
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

def save(key_id, label, secret, provider="groq"):
    with LOCK, connection() as db:
        db.execute("INSERT OR REPLACE INTO saved_keys(id,label,secret,provider) VALUES (?,?,?,?)",
                   (key_id,label,secret.strip(),provider))

def load():
    with LOCK, connection() as db:
        return db.execute("SELECT id,label,secret,provider FROM saved_keys ORDER BY rowid").fetchall()

def delete(key_id):
    with LOCK, connection() as db:
        db.execute("DELETE FROM saved_keys WHERE id=?", (key_id,))
