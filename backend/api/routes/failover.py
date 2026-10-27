from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from ...api.schemas import FailoverTest
from ...services import model_router

router = APIRouter(prefix='/api')


@router.post('/test-failover')
async def test_failover(payload: FailoverTest):
    if model_router.model_key_count(payload.model) < 2:
        raise HTTPException(
            400, 'At least two valid keys must advertise the selected model.'
        )
    try:
        answer, metadata = await run_in_threadpool(
            model_router.completion,
            payload.model,
            [{'role': 'user', 'content': 'Reply with only: Backup connection successful.'}],
            True,
        )
    except model_router.RouterError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {
        'answer': answer,
        'meta': metadata,
        'note': 'First eligible key was artificially skipped; the next eligible provider key made a real request.',
    }
