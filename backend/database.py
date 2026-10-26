import sqlite3
from pathlib import Path
from threading import RLock
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'chats.db'
LOCK = RLock()

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def init_db():
    with LOCK, connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE, role TEXT NOT NULL CHECK(role IN (\'user\',\'assistant\')), content TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id,id)')

def list_chats():
    with LOCK, connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM chats ORDER BY updated_at DESC')]

def new_chat(chat_id):
    t=now()
    with LOCK, connect() as db:
        db.execute('INSERT INTO chats VALUES (?, ?, ?, ?)', (chat_id,'New conversation',t,t))
    return {'id':chat_id,'title':'New conversation','created_at':t,'updated_at':t}

def get_chat(chat_id):
    with LOCK, connect() as db:
        row=db.execute('SELECT * FROM chats WHERE id=?',(chat_id,)).fetchone()
        return dict(row) if row else None

def get_messages(chat_id):
    with LOCK, connect() as db:
        return [dict(r) for r in db.execute('SELECT id,role,content,created_at FROM messages WHERE chat_id=? ORDER BY id',(chat_id,))]

def save_exchange(chat_id, user_text, assistant_text):
    with LOCK, connect() as db:
        row=db.execute('SELECT title FROM chats WHERE id=?',(chat_id,)).fetchone()
        if not row:
            raise KeyError('Chat not found')
        t=now()
        db.execute('INSERT INTO messages(chat_id,role,content,created_at) VALUES (?,?,?,?)',(chat_id,'user',user_text,t))
        db.execute('INSERT INTO messages(chat_id,role,content,created_at) VALUES (?,?,?,?)',(chat_id,'assistant',assistant_text,t))
        title = user_text.strip().replace('\n',' ')[:54] if row['title']=='New conversation' else row['title']
        db.execute('UPDATE chats SET title=?,updated_at=? WHERE id=?',(title,t,chat_id))

def save_assistant_message(chat_id, content):
    with LOCK, connect() as db:
        t=now()
        db.execute('INSERT INTO messages(chat_id,role,content,created_at) VALUES (?,?,?,?)',(chat_id,'assistant',content,t))
        db.execute('UPDATE chats SET updated_at=? WHERE id=?',(t,chat_id))

def rename_chat(chat_id, title):
    with LOCK, connect() as db:
        result=db.execute('UPDATE chats SET title=?,updated_at=? WHERE id=?',(title,now(),chat_id))
        return result.rowcount > 0

def delete_chat(chat_id):
    with LOCK, connect() as db:
        result=db.execute('DELETE FROM chats WHERE id=?',(chat_id,))
        return result.rowcount > 0

# Cross-conversation memory; explicit user-authored facts with optional expiry.
def init_memories():
    with LOCK,connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS memories (
          id TEXT PRIMARY KEY, content TEXT NOT NULL, expires_at TEXT, created_at TEXT NOT NULL)''')

def save_memory(memory_id,content,expires_at=None):
    with LOCK,connect() as db:
        db.execute('INSERT INTO memories VALUES (?,?,?,?)',(memory_id,content,expires_at,now()))

def list_memories():
    with LOCK,connect() as db:
        db.execute('DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?',(now(),))
        return [dict(r) for r in db.execute('SELECT * FROM memories ORDER BY created_at DESC')]

def delete_memory(memory_id):
    with LOCK,connect() as db:
        return db.execute('DELETE FROM memories WHERE id=?',(memory_id,)).rowcount>0
