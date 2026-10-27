from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ...api.schemas import AddKey
from ...repositories import saved_keys
from ...services import model_router

router = APIRouter(prefix='/api')


@router.get('/keys')
def list_keys():
    return {'keys': model_router.list_keys()}


@router.post('/keys')
async def add_key(payload: AddKey):
    try:
        result = await run_in_threadpool(
            model_router.add_key,
            payload.name,
            payload.api_key,
            None,
            payload.provider,
        )
        if payload.remember:
            saved_keys.save(
                result['id'], payload.name, payload.api_key, payload.provider
            )
        return result
    except model_router.RouterError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete('/keys/{key_id}')
def delete_key(key_id: str):
    if not model_router.remove_key(key_id):
        raise HTTPException(404, 'Key not found')
    saved_keys.delete(key_id)
    return {'ok': True}


@router.post('/keys/refresh')
async def refresh_keys():
    return {'keys': await run_in_threadpool(model_router.refresh_keys)}


@router.get('/models')
def get_models():
    return {'models': model_router.all_models()}
