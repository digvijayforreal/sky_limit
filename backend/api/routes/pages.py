from fastapi import APIRouter
from fastapi.responses import FileResponse

from ...core.config import FRONTEND_DIR

router = APIRouter()


@router.get('/')
def homepage():
    return FileResponse(FRONTEND_DIR / 'landing.html')


@router.get('/workspace')
def workspace():
    return FileResponse(FRONTEND_DIR / 'index.html')


@router.get('/style.css')
def css():
    return FileResponse(FRONTEND_DIR / 'style.css', media_type='text/css')


@router.get('/script.js')
def javascript():
    return FileResponse(FRONTEND_DIR / 'script.js', media_type='text/javascript')
