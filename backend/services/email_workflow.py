import time
from threading import RLock

pending_confirmations = {}
_lock = RLock()


def clear_pending_confirmations():
    with _lock:
        pending_confirmations.clear()


def remember_confirmation(confirmation_id, chat_id, to, subject, body):
    with _lock:
        now = time.monotonic()
        for key, value in list(pending_confirmations.items()):
            if value['expires_at'] <= now:
                pending_confirmations.pop(key, None)
        pending_confirmations[confirmation_id] = {
            'chat_id': chat_id,
            'to': to,
            'subject': subject,
            'body': body,
            'expires_at': now + 600,
        }


def take_confirmation(confirmation_id):
    with _lock:
        pending = pending_confirmations.pop(confirmation_id, None)
    if not pending or pending['expires_at'] <= time.monotonic():
        return None
    return pending
