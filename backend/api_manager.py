"""In-memory, local-only credentials; never persisted or returned to browser."""
import time
import uuid
from dataclasses import dataclass, field
from threading import RLock
import httpx

BASE='https://api.groq.com/openai/v1'
lock=RLock()
_keys=[]

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

    def public(self):
        return {'id':self.id,'name':self.name,'masked':'••••' + self.secret[-4:], 'models':self.models,
                'status': 'invalid' if self.disabled else ('cooldown' if self.cooldown_until>time.time() else 'ready'),
                'last_error':self.last_error}

def _get_models(secret):
    try:
        with httpx.Client(timeout=15) as client:
            response=client.get(BASE+'/models',headers={'Authorization':f'Bearer {secret}'})
            response.raise_for_status()
            models=response.json().get('data',[])
            return sorted({m['id'] for m in models if isinstance(m,dict) and m.get('id') and m.get('active',True) is not False})
    except httpx.HTTPStatusError as exc:
        raise RouterError(f'Groq rejected key/model request (HTTP {exc.response.status_code}).') from None
    except (httpx.HTTPError,ValueError,KeyError) as exc:
        raise RouterError('Could not connect to Groq or read its model list.') from exc

def add_key(name,secret,key_id=None):
    secret=secret.strip()
    if not secret.startswith('gsk_') or len(secret)<15:
        raise RouterError('This does not look like a Groq API key.')
    models=_get_models(secret)
    with lock:
        if any(k.secret==secret for k in _keys):
            raise RouterError('This API key is already configured.')
        k=ProviderKey(key_id or str(uuid.uuid4()),name.strip() or f'Groq Key {len(_keys)+1}',secret,models)
        _keys.append(k)
        return k.public()

def list_keys():
    with lock:
        return [k.public() for k in _keys]

def remove_key(key_id):
    with lock:
        count=len(_keys)
        _keys[:]=[k for k in _keys if k.id!=key_id]
        return count!=len(_keys)

def refresh_keys():
    with lock:
        keys=list(_keys)
    for k in keys:
        try:
            models=_get_models(k.secret)
            with lock:
                k.models=models
                k.disabled=False
                k.last_error=''
                k.cooldown_until=0
        except RouterError as exc:
            with lock:
                k.last_error=str(exc)
    return list_keys()

def all_models():
    with lock:
        models={}
        for k in _keys:
            if k.disabled: continue
            for model in k.models:
                models.setdefault(model,[]).append(k.id)
        return [{'id':m,'key_count':len(ids)} for m,ids in sorted(models.items())]

def _err_detail(response):
    try:
        obj=response.json()
        return str(obj.get('error',{}).get('message',''))[:180]
    except Exception:
        return f'HTTP {response.status_code}'

def completion(model,messages,simulate_primary_failure=False,tools=None,return_message=False):
    """Attempts provider keys and returns a text or provider message with metadata."""
    with lock:
        candidates=[k for k in _keys if not k.disabled and model in k.models]
    if not candidates:
        raise RouterError('No configured Groq API key advertises this model.')
    attempts=[]
    for index,k in enumerate(candidates):
        with lock:
            if k.cooldown_until>time.time():
                attempts.append({'key':k.name,'result':'cooldown'})
                continue
        if simulate_primary_failure and index==0:
            attempts.append({'key':k.name,'result':'simulated failure'})
            continue
        try:
            with httpx.Client(timeout=65) as client:
                response=client.post(BASE+'/chat/completions',headers={'Authorization':f'Bearer {k.secret}'},
                    json={**{'model':model,'messages':messages,'temperature':0.4,'max_tokens':1024},
                          **({'tools':tools,'tool_choice':'auto'} if tools else {})})
            if response.is_success:
                data=response.json()
                message=data['choices'][0]['message']
                if return_message:
                    with lock:
                        k.last_error=''
                    attempts.append({'key':k.name,'result':'success'})
                    return message,{'used_key':k.name,'model':model,'attempts':attempts}
                content=message.get('content')
                if not isinstance(content,str) or not content.strip():
                    raise RouterError('Provider returned an empty text response.')
                with lock:
                    k.last_error=''
                attempts.append({'key':k.name,'result':'success'})
                return content,{'used_key':k.name,'model':model,'attempts':attempts}
            detail=_err_detail(response)
            if response.status_code in (401,403):
                with lock:
                    k.disabled=True
                    k.last_error=f'HTTP {response.status_code}: {detail}'
            elif response.status_code in (429,500,502,503,504,498):
                retry=response.headers.get('retry-after','')
                try: seconds=min(max(float(retry),5),180) if retry else 30
                except ValueError: seconds=30
                with lock:
                    k.cooldown_until=time.time()+seconds
                    k.last_error=f'HTTP {response.status_code}: {detail}'
            else:
                # Bad request/model errors generally affect all credentials, so stop.
                raise RouterError(f'Model request failed (HTTP {response.status_code}): {detail}')
            attempts.append({'key':k.name,'result':f'HTTP {response.status_code}'})
        except (httpx.TimeoutException,httpx.TransportError):
            with lock:
                k.cooldown_until=time.time()+15
                k.last_error='Connection failure or timeout'
            attempts.append({'key':k.name,'result':'network/timeout'})
    raise RouterError('All eligible API keys failed or are cooling down. Attempts: '+', '.join(f"{a['key']}: {a['result']}" for a in attempts))


def clear_keys():
    with lock:_keys.clear()
