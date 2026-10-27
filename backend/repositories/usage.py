import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock

PATH = Path(__file__).resolve().parents[2] / 'data' / 'usage.db'
LOCK = RLock()


def connect():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def connection():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with LOCK, connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            key_id TEXT NOT NULL,
            key_label TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            response_ms INTEGER NOT NULL,
            rate_limits_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        )''')
        db.execute(
            'CREATE INDEX IF NOT EXISTS idx_usage_key_time '
            'ON usage_events(provider, key_id, occurred_at)'
        )


def record(provider, key_id, key_label, model, input_tokens, output_tokens, response_ms, rate_limits):
    occurred_at = datetime.now(timezone.utc).isoformat()
    with LOCK, connection() as db:
        db.execute(
            '''INSERT INTO usage_events(
                provider, key_id, key_label, model, input_tokens, output_tokens,
                response_ms, rate_limits_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                provider,
                key_id,
                key_label,
                model,
                input_tokens,
                output_tokens,
                response_ms,
                json.dumps(rate_limits),
                occurred_at,
            ),
        )
    return occurred_at


def summary(period):
    now = datetime.now(timezone.utc)
    durations = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30)}
    cutoff = (now - durations[period]).isoformat() if period in durations else None
    condition = 'WHERE occurred_at >= ?' if cutoff else ''

    with LOCK, connection() as db:
        totals = db.execute(
            f'''SELECT provider, key_id, key_label, COUNT(*) AS requests,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COUNT(input_tokens) AS input_token_reports,
                    COUNT(output_tokens) AS output_token_reports,
                    MAX(occurred_at) AS last_used
                FROM usage_events {condition}
                GROUP BY provider, key_id, key_label
                ORDER BY provider, key_label''',
            (cutoff,) if cutoff else (),
        ).fetchall()
        latest = db.execute(
            '''SELECT event.provider, event.key_id, event.key_label,
                    event.model, event.response_ms, event.rate_limits_json,
                    event.occurred_at
                FROM usage_events AS event
                JOIN (
                    SELECT provider, key_id, MAX(id) AS latest_id
                    FROM usage_events
                    GROUP BY provider, key_id
                ) AS recent ON recent.latest_id = event.id'''
        ).fetchall()

    latest_by_key = {
        (row['provider'], row['key_id']): {
            'key_label': row['key_label'],
            'model': row['model'],
            'response_ms': row['response_ms'],
            'rate_limits': json.loads(row['rate_limits_json']),
            'observed_at': row['occurred_at'],
        }
        for row in latest
    }
    totals_by_key = {}
    for row in totals:
        key = (row['provider'], row['key_id'])
        totals_by_key[key] = {
            'provider': row['provider'],
            'key_id': row['key_id'],
            'key_label': row['key_label'],
            'requests': row['requests'],
            'input_tokens': row['input_tokens'],
            'output_tokens': row['output_tokens'],
            'input_token_reports': row['input_token_reports'],
            'output_token_reports': row['output_token_reports'],
            'last_used': row['last_used'],
            'latest': latest_by_key.get(key),
        }
    for key, latest_snapshot in latest_by_key.items():
        totals_by_key.setdefault(key, {
            'provider': key[0],
            'key_id': key[1],
            'key_label': latest_snapshot['key_label'],
            'requests': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'input_token_reports': 0,
            'output_token_reports': 0,
            'last_used': None,
            'latest': latest_snapshot,
        })
        totals_by_key[key]['latest'] = latest_snapshot
    keys = sorted(
        totals_by_key.values(),
        key=lambda item: (item['provider'], item['key_label'].lower()),
    )

    return {
        'period': period,
        'totals': {
            'requests': sum(key['requests'] for key in keys),
            'input_tokens': sum(key['input_tokens'] for key in keys),
            'output_tokens': sum(key['output_tokens'] for key in keys),
            'input_token_reports': sum(key['input_token_reports'] for key in keys),
            'output_token_reports': sum(key['output_token_reports'] for key in keys),
        },
        'keys': keys,
    }
