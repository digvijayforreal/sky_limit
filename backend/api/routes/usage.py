from typing import Literal

from fastapi import APIRouter

from ...repositories import usage as usage_repository
from ...services import model_router

router = APIRouter(prefix='/api')


@router.get('/usage')
def get_usage(period: Literal['24h', '7d', '30d', 'all'] = '7d'):
    summary = usage_repository.summary(period)
    keys_by_id = {
        (key['provider'], key['key_id']): key
        for key in summary['keys']
    }

    for configured in model_router.list_keys():
        identity = (configured['provider'], configured['id'])
        if identity not in keys_by_id:
            keys_by_id[identity] = {
                'provider': configured['provider'],
                'key_id': configured['id'],
                'key_label': configured['name'],
                'requests': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'input_token_reports': 0,
                'output_token_reports': 0,
                'last_used': None,
                'latest': None,
            }

    summary['keys'] = sorted(
        keys_by_id.values(),
        key=lambda item: (item['provider'], item['key_label'].lower()),
    )
    return summary
