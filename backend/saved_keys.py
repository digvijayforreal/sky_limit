"""Local-only key persistence, without a vault/password. Secrets are stored in SQLite plaintext.
Protect the data directory with filesystem permissions; never commit or share it.
"""
import sqlite3
from pathlib import Path
from threading import RLock

PATH = Path(__file__).resolve().parents[1] / "data" / "api_keys.db"
LOCK = RLock()

def connect():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(PATH, timeout=15)
    db.execute("CREATE TABLE IF NOT EXISTS saved_keys (id TEXT PRIMARY KEY, label TEXT NOT NULL, secret TEXT NOT NULL)")
    return db

def init_db():
    with LOCK, connect():
        pass

def save(key_id, label, secret):
    with LOCK, connect() as db:
        db.execute("INSERT OR REPLACE INTO saved_keys(id,label,secret) VALUES (?,?,?)", (key_id,label,secret.strip()))

def load():
    with LOCK, connect() as db:
        return db.execute("SELECT id,label,secret FROM saved_keys ORDER BY rowid").fetchall()

def delete(key_id):
    with LOCK, connect() as db:
        db.execute("DELETE FROM saved_keys WHERE id=?", (key_id,))
