from contextlib import asynccontextmanager

from starlette.concurrency import run_in_threadpool

from ..repositories import database, saved_keys, search_settings, usage
from ..services import model_router
from ..services.email_workflow import clear_pending_confirmations


@asynccontextmanager
async def lifespan(app):
    database.init_db()
    database.init_memories()
    saved_keys.init_db()
    search_settings.init_db()
    usage.init_db()
    clear_pending_confirmations()

    for key_id, label, secret, provider in saved_keys.load():
        try:
            await run_in_threadpool(
                model_router.add_key, label, secret, key_id, provider
            )
        except model_router.RouterError:
            # Keep saved credentials available for a later refresh.
            continue

    yield
