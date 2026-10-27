import uuid

from fastapi import APIRouter, HTTPException

from ...api.schemas import RenameRequest
from ...repositories import database

router = APIRouter(prefix='/api/chats')


@router.get('')
def list_chats():
    return {'chats': database.list_chats()}


@router.post('')
def create_chat():
    return database.new_chat(str(uuid.uuid4()))


@router.get('/{chat_id}')
def get_chat(chat_id: str):
    chat = database.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, 'Chat not found')
    return {'chat': chat, 'messages': database.get_messages(chat_id)}


@router.patch('/{chat_id}')
def rename_chat(chat_id: str, payload: RenameRequest):
    if not database.rename_chat(chat_id, payload.title.strip()):
        raise HTTPException(404, 'Chat not found')
    return {'ok': True}


@router.delete('/{chat_id}')
def delete_chat(chat_id: str):
    if not database.delete_chat(chat_id):
        raise HTTPException(404, 'Chat not found')
    return {'ok': True}
