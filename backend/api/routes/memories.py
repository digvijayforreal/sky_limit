import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from ...api.schemas import MemoryInput
from ...repositories import database

router = APIRouter(prefix='/api/memories')


@router.get('')
def list_memories():
    return {'memories': database.list_memories()}


@router.post('')
def add_memory(payload: MemoryInput):
    expiry = (
        datetime.now(timezone.utc) + timedelta(hours=payload.ttl_hours)
    ).isoformat() if payload.ttl_hours else None
    memory_id = str(uuid.uuid4())
    content = payload.content.strip()
    database.save_memory(memory_id, content, expiry)
    return {'id': memory_id, 'content': content, 'expires_at': expiry}


@router.delete('/{memory_id}')
def delete_memory(memory_id: str):
    if not database.delete_memory(memory_id):
        raise HTTPException(404, 'Memory not found')
    return {'ok': True}
