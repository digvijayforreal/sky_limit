"""In-memory, local-only provider routing for model APIs."""
import json
import time
import uuid
from dataclasses import dataclass, field
from threading import RLock
from urllib.parse import quote

import httpx

PROVIDERS = {
    'groq': {
        'name': 'Groq',
        'base': 'https://api.groq.com/openai/v1',
        'models_url': 'https://api.groq.com/openai/v1/models',
        'prefix': 'gsk_',
    },
    'google': {
        'name': 'Google AI Studio',
        'base': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'models_url': 'https://generativelanguage.googleapis.com/v1beta/models',
    },
}
NON_CHAT_MODEL_TERMS = (
    'embedding', 'embed-', 'whisper', 'transcribe', 'speech', 'tts', 'orpheus', 'playai',
    'image', 'nano-banana', 'veo', 'robotics', 'computer-use',
    'guard', 'safeguard', 'moderation',
)
lock = RLock()
_keys = []


class RouterError(Exception):
    pass


@dataclass
class ProviderKey:
    id: str
    name: str
    secret: str = field(repr=False)
    models: list[str] = field(default_factory=list)
    disabled: bool = False
    cooldown_until: float = 0
    last_error: str = ''
    provider: str = 'groq'

    def public(self):
        return {
            'id': self.id,
            'name': self.name,
            'masked': '••••' + self.secret[-4:],
            'models': self.models,
            'provider': self.provider,
            'status': 'invalid' if self.disabled else ('cooldown' if self.cooldown_until > time.time() else 'ready'),
            'last_error': self.last_error,
        }


def _provider(provider):
    if provider not in PROVIDERS:
        raise RouterError('Choose Groq or Google AI Studio.')
    return PROVIDERS[provider]

def _is_chat_model(model_id):
    lowered = model_id.lower()
    return not any(term in lowered for term in NON_CHAT_MODEL_TERMS)

def _get_models(secret, provider='groq'):
    config = _provider(provider)
    try:
        with httpx.Client(timeout=15) as client:
            if provider == 'google':
                models = []
                page_token = None
                while True:
                    params = {'pageSize': 1000}
                    if page_token:
                        params['pageToken'] = page_token
                    response = client.get(
                        config['models_url'],
                        headers={'x-goog-api-key': secret},
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                    models.extend(
                        model.get('baseModelId') or model.get('name', '').split('/')[-1]
                        for model in data.get('models', [])
                        if isinstance(model, dict)
                        and isinstance(model.get('supportedGenerationMethods'), list)
                        and 'generateContent' in model['supportedGenerationMethods']
                        and _is_chat_model(model.get('baseModelId') or model.get('name', '').split('/')[-1])
                    )
                    page_token = data.get('nextPageToken')
                    if not page_token:
                        break
            else:
                response = client.get(
                    config['models_url'],
                    headers={'Authorization': f'Bearer {secret}'},
                )
                response.raise_for_status()
                models = [
                    model['id'] for model in response.json().get('data', [])
                    if isinstance(model, dict) and model.get('id') and model.get('active', True) is not False
                    and _is_chat_model(model['id'])
                ]
            return sorted(set(models))
    except httpx.HTTPStatusError as exc:
        raise RouterError(f"{config['name']} rejected key/model request (HTTP {exc.response.status_code}).") from None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise RouterError(f"Could not connect to {config['name']} or read its model list.") from exc


def add_key(name, secret, key_id=None, provider='groq'):
    config = _provider(provider)
    secret = secret.strip()
    valid_format = (
        secret.startswith(config['prefix']) and len(secret) >= 15
        if provider == 'groq'
        else len(secret) >= 20
    )
    if not valid_format:
        raise RouterError(f"This does not look like a {config['name']} API key.")
    models = _get_models(secret, provider)
    with lock:
        if any(key.secret == secret for key in _keys):
            raise RouterError('This API key is already configured.')
        key = ProviderKey(
            key_id or str(uuid.uuid4()),
            name.strip() or f"{config['name']} Key {len(_keys) + 1}",
            secret,
            models,
            provider=provider,
        )
        _keys.append(key)
        return key.public()


def list_keys():
    with lock:
        return [key.public() for key in _keys]


def remove_key(key_id):
    with lock:
        count = len(_keys)
        _keys[:] = [key for key in _keys if key.id != key_id]
        return count != len(_keys)


def refresh_keys():
    with lock:
        keys = list(_keys)
    for key in keys:
        try:
            models = _get_models(key.secret, key.provider)
            with lock:
                key.models = models
                key.disabled = False
                key.last_error = ''
                key.cooldown_until = 0
        except RouterError as exc:
            with lock:
                key.last_error = str(exc)
    return list_keys()


def all_models():
    with lock:
        models = {}
        for key in _keys:
            if key.disabled:
                continue
            for model in key.models:
                models.setdefault((key.provider, model), []).append(key.id)
        return [
            {'id': model, 'provider': provider, 'key_count': len(ids)}
            for (provider, model), ids in sorted(models.items())
        ]

def model_key_count(model_selector):
    provider, model = _split_model_selector(model_selector)
    with lock:
        return sum(
            not key.disabled and (provider is None or key.provider == provider) and model in key.models
            for key in _keys
        )

def _split_model_selector(model_selector):
    if '::' in model_selector:
        provider, model = model_selector.split('::', 1)
        _provider(provider)
        return provider, model
    return None, model_selector


def _err_detail(response):
    try:
        obj = response.json()
        error = obj.get('error')
        if isinstance(error, dict):
            detail = error.get('message')
        elif isinstance(error, str):
            detail = error
        else:
            detail = obj.get('message')
        if detail:
            return str(detail)[:180]
    except (AttributeError, TypeError, ValueError):
        pass
    body = getattr(response, 'text', '')
    return body.strip()[:180] if body.strip() else f'HTTP {response.status_code}'


def _google_compatible_schema(value):
    if isinstance(value, dict):
        return {
            key: _google_compatible_schema(item)
            for key, item in value.items()
            if key != 'additionalProperties'
        }
    if isinstance(value, list):
        return [_google_compatible_schema(item) for item in value]
    return value


def _google_generate_content(client, secret, model_id, messages, tools):
    contents = []
    system_parts = []
    for item in messages:
        role = item.get('role')
        content = item.get('content')
        if not isinstance(content, str):
            raise RouterError('Google chat fallback requires text messages.')
        if role == 'system':
            system_parts.append(content)
        elif role in ('user', 'assistant'):
            contents.append({
                'role': 'model' if role == 'assistant' else 'user',
                'parts': [{'text': content}],
            })
        else:
            raise RouterError(f'Google chat fallback does not support the "{role}" message role.')

    request = {'contents': contents}
    if system_parts:
        request['systemInstruction'] = {'parts': [{'text': '\n'.join(system_parts)}]}
    if tools:
        declarations = [
            {
                'name': tool['function']['name'],
                'description': tool['function'].get('description', ''),
                'parameters': _google_compatible_schema(tool['function']['parameters']),
            }
            for tool in tools
            if tool.get('type') == 'function' and isinstance(tool.get('function'), dict)
        ]
        if declarations:
            request['tools'] = [{'functionDeclarations': declarations}]

    url = (
        PROVIDERS['google']['models_url'].rsplit('/models', 1)[0]
        + '/models/' + quote(model_id, safe='') + ':generateContent'
    )
    response = client.post(url, headers={'x-goog-api-key': secret}, json=request)
    if not response.is_success:
        detail = _err_detail(response)
        if response.status_code == 404:
            raise RouterError(
                f'The selected Google model "{model_id}" is unavailable for chat (HTTP 404): {detail}. '
                'Choose another Gemini model and try again.'
            )
        raise RouterError(f'Google model request failed (HTTP {response.status_code}): {detail}')

    try:
        data = response.json()
    except ValueError as exc:
        raise RouterError('Google returned an invalid JSON response.') from exc
    if not isinstance(data, dict):
        raise RouterError('Google returned an invalid response format.')
    candidates = data.get('candidates', [])
    if not candidates or not isinstance(candidates[0], dict):
        raise RouterError('Google returned no response candidate.')
    content = candidates[0].get('content')
    parts = content.get('parts') if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise RouterError('Google returned an invalid response candidate.')
    text = ''.join(part.get('text', '') for part in parts if isinstance(part, dict))
    tool_calls = []
    for part in parts:
        call = part.get('functionCall') if isinstance(part, dict) else None
        if isinstance(call, dict) and isinstance(call.get('name'), str):
            tool_calls.append({
                'id': str(uuid.uuid4()),
                'type': 'function',
                'function': {
                    'name': call['name'],
                    'arguments': json.dumps(call.get('args', {})),
                },
            })
    return {'role': 'assistant', 'content': text or None, 'tool_calls': tool_calls}


def completion(model, messages, simulate_primary_failure=False, tools=None, return_message=False):
    """Attempts eligible provider keys and returns a text or provider message with metadata."""
    provider, model_id = _split_model_selector(model)
    with lock:
        candidates = [
            key for key in _keys
            if not key.disabled and model_id in key.models and (provider is None or key.provider == provider)
        ]
    if not candidates:
        raise RouterError('No configured provider API key advertises this model.')
    attempts = []
    for index, key in enumerate(candidates):
        with lock:
            if key.cooldown_until > time.time():
                attempts.append({'key': key.name, 'result': 'cooldown'})
                continue
        if simulate_primary_failure and index == 0:
            attempts.append({'key': key.name, 'result': 'simulated failure'})
            continue
        config = _provider(key.provider)
        try:
            request = {
                'model': model_id,
                'messages': messages,
                'max_tokens': 4096 if key.provider == 'google' else 1024,
                **({'temperature': 0.4} if key.provider == 'groq' else {}),
                **({
                    'tools': _google_compatible_schema(tools) if key.provider == 'google' else tools,
                    'tool_choice': 'auto',
                } if tools else {}),
            }
            with httpx.Client(timeout=65) as client:
                response = client.post(
                    config['base'] + '/chat/completions',
                    headers={'Authorization': f'Bearer {key.secret}'},
                    json=request,
                )
            native_google_response = (
                response.status_code == 404 and key.provider == 'google'
            )
            if native_google_response:
                with httpx.Client(timeout=65) as client:
                    message = _google_generate_content(
                        client, key.secret, model_id, messages, tools
                    )
            if native_google_response or response.is_success:
                if not native_google_response:
                    message = response.json()['choices'][0]['message']
                if return_message:
                    with lock:
                        key.last_error = ''
                    attempts.append({'key': key.name, 'result': 'success'})
                    return message, {'used_key': key.name, 'provider': key.provider, 'model': model_id, 'attempts': attempts}
                content = message.get('content')
                if not isinstance(content, str) or not content.strip():
                    raise RouterError('Provider returned an empty text response.')
                with lock:
                    key.last_error = ''
                attempts.append({'key': key.name, 'result': 'success'})
                return content, {'used_key': key.name, 'provider': key.provider, 'model': model_id, 'attempts': attempts}
            detail = _err_detail(response)
            if response.status_code in (401, 403):
                with lock:
                    key.disabled = True
                    key.last_error = f'HTTP {response.status_code}: {detail}'
            elif response.status_code in (429, 500, 502, 503, 504, 498):
                retry = response.headers.get('retry-after', '')
                try:
                    seconds = min(max(float(retry), 5), 180) if retry else 30
                except ValueError:
                    seconds = 30
                with lock:
                    key.cooldown_until = time.time() + seconds
                    key.last_error = f'HTTP {response.status_code}: {detail}'
            else:
                raise RouterError(f'Model request failed (HTTP {response.status_code}): {detail}')
            attempts.append({'key': key.name, 'result': f'HTTP {response.status_code}'})
        except (httpx.TimeoutException, httpx.TransportError):
            with lock:
                key.cooldown_until = time.time() + 15
                key.last_error = 'Connection failure or timeout'
            attempts.append({'key': key.name, 'result': 'network/timeout'})
    raise RouterError(
        'All eligible API keys failed or are cooling down. Attempts: '
        + ', '.join(f"{attempt['key']}: {attempt['result']}" for attempt in attempts)
    )


def clear_keys():
    with lock:
        _keys.clear()
