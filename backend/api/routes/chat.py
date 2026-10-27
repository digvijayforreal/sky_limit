from fastapi import APIRouter, HTTPException

from ...api.schemas import ChatRequest
from ...services.chat import ChatServiceError, send_message

router = APIRouter(prefix='/api')


@router.post('/chat')
async def talk(payload: ChatRequest):
    try:
        return await send_message(payload.chat_id, payload.message, payload.model)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ChatServiceError as exc:
        raise HTTPException(503, str(exc)) from exc
