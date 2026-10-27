from fastapi import APIRouter
from fastapi import HTTPException

from ...api.schemas import SearchSettingsInput
from ...repositories import search_settings

router = APIRouter(prefix='/api/search')


@router.get('/settings')
def get_search_settings():
    key = search_settings.get_tavily_api_key()
    return {
        'tavily_configured': bool(key),
        'tavily_key_hint': key[-4:] if key else '',
    }


@router.put('/settings')
def save_search_settings(payload: SearchSettingsInput):
    key = payload.tavily_api_key.strip()
    if not key:
        raise HTTPException(400, 'Enter a Tavily API key.')
    search_settings.save_tavily_api_key(key)
    return get_search_settings()


@router.delete('/settings')
def delete_search_settings():
    search_settings.clear_tavily_api_key()
    return {'tavily_configured': False, 'tavily_key_hint': ''}
