from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import ASSETS_DIR
from ..core.lifecycle import lifespan
from .routes import chat, chats, design, email, failover, keys, memories, pages, usage


def create_app():
    application = FastAPI(
        title='OmniAgent AI — Local MVP',
        lifespan=lifespan,
    )
    application.mount(
        '/assets', StaticFiles(directory=ASSETS_DIR), name='assets'
    )

    @application.middleware('http')
    async def local_only(request: Request, call_next):
        if (
            not request.client
            or request.client.host not in ('127.0.0.1', '::1', 'localhost', 'testclient')
        ):
            return JSONResponse(
                {'detail': 'Local-only server. Use 127.0.0.1.'},
                status_code=403,
            )
        return await call_next(request)

    application.include_router(pages.router)
    for api_router in (
        keys.router,
        chats.router,
        chat.router,
        email.router,
        design.router,
        failover.router,
        memories.router,
        usage.router,
    ):
        application.include_router(api_router)
    return application


app = create_app()
