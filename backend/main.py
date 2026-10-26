import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from . import saved_keys
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from . import database as db, api_manager as router, email_tool

ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT/'frontend'
SYSTEM_PROMPT='You are OmniAgent, a helpful, precise AI assistant. Respect conversation context and answer clearly. Use saved personal memories if provided. Do not claim access to tools or the internet that have not been provided.'
MAX_CONTEXT_CHARS=65000 # History stays in SQLite; only a bounded recent portion fits into model requests.
EMAIL_TOOLS=[{'type':'function','function':{'name':'send_email','description':'Prepare an email to send. The user must explicitly approve the preview before anything is sent.','parameters':{'type':'object','properties':{'to':{'type':'string','description':'One or more recipient email addresses.'},'subject':{'type':'string'},'body':{'type':'string'}},'required':['to','subject','body'],'additionalProperties':False}}}]
pending_email_confirmations={}
pending_email_lock=RLock()

def clear_pending_email_confirmations():
    with pending_email_lock:
        pending_email_confirmations.clear()

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    db.init_memories()
    saved_keys.init_db()
    # Restore configured API credentials automatically on each server start.
    for kid, label, secret in saved_keys.load():
        try:
            await run_in_threadpool(router.add_key, label, secret, kid)
        except router.RouterError:
            # Keep saved credential so it can be refreshed later.
            pass
    yield

app=FastAPI(title='OmniAgent AI — Local MVP',lifespan=lifespan)
app.mount('/assets',StaticFiles(directory=FRONT/'assets'),name='assets')

@app.middleware('http')
async def local_only(request:Request,call_next):
    from fastapi.responses import JSONResponse
    # This MVP has no login; do not allow remote access, even if accidentally bound to 0.0.0.0.
    if not request.client or request.client.host not in ('127.0.0.1','::1','localhost','testclient'):
        return JSONResponse({'detail':'Local-only server. Use 127.0.0.1.'},status_code=403)
    return await call_next(request)

@app.get('/')
def homepage(): return FileResponse(FRONT/'landing.html')

@app.get('/workspace')
def workspace(): return FileResponse(FRONT/'index.html')

@app.get('/style.css')
def css(): return FileResponse(FRONT/'style.css',media_type='text/css')

@app.get('/script.js')
def js(): return FileResponse(FRONT/'script.js',media_type='text/javascript')

class AddKey(BaseModel):
    name:str=Field(default='Groq Key',max_length=70)
    api_key:str=Field(min_length=15,max_length=300)
    remember:bool=True

class ChatRequest(BaseModel):
    chat_id:str
    message:str=Field(min_length=1,max_length=16000)
    model:str=Field(min_length=1,max_length=150)

class RenameRequest(BaseModel):
    title:str=Field(min_length=1,max_length=100)

@app.get('/api/keys')
def keys():return {'keys':router.list_keys()}

@app.post('/api/keys')
async def add_key(payload:AddKey):
    try:
        result=await run_in_threadpool(router.add_key,payload.name,payload.api_key)
        if payload.remember:
            saved_keys.save(result['id'],payload.name,payload.api_key)
        return result
    except router.RouterError as exc: raise HTTPException(400,str(exc))

@app.delete('/api/keys/{key_id}')
def delete_key(key_id:str):
    if not router.remove_key(key_id):raise HTTPException(404,'Key not found')
    saved_keys.delete(key_id)
    return {'ok':True}

@app.post('/api/keys/refresh')
async def refresh_keys():return {'keys':await run_in_threadpool(router.refresh_keys)}

@app.get('/api/models')
def get_models():return {'models':router.all_models()}

@app.get('/api/chats')
def chats():return {'chats':db.list_chats()}

@app.post('/api/chats')
def create_chat():return db.new_chat(str(uuid.uuid4()))

@app.get('/api/chats/{chat_id}')
def get_chat(chat_id:str):
    chat=db.get_chat(chat_id)
    if not chat:raise HTTPException(404,'Chat not found')
    return {'chat':chat,'messages':db.get_messages(chat_id)}

@app.patch('/api/chats/{chat_id}')
def rename_chat(chat_id:str,payload:RenameRequest):
    if not db.rename_chat(chat_id,payload.title.strip()):raise HTTPException(404,'Chat not found')
    return {'ok':True}

@app.delete('/api/chats/{chat_id}')
def remove_chat(chat_id:str):
    if not db.delete_chat(chat_id):raise HTTPException(404,'Chat not found')
    return {'ok':True}

def build_context(previous,new_message):
    remaining=MAX_CONTEXT_CHARS-len(new_message)
    selected=[]
    for item in reversed(previous):
        if len(item['content'])>remaining:break
        selected.append({'role':item['role'],'content':item['content']})
        remaining-=len(item['content'])
    selected.reverse()
    memories=db.list_memories()[:40]
    memory_text='\n'.join('- '+m['content'][:500] for m in memories)[:8500]
    system=SYSTEM_PROMPT+('\nSaved user memories (from prior chats; user can edit/delete):\n'+memory_text if memory_text else '')
    return [{'role':'system','content':system}]+selected+[{'role':'user','content':new_message}]

@app.post('/api/chat')
async def talk(payload:ChatRequest):
    if not db.get_chat(payload.chat_id):raise HTTPException(404,'Chat not found')
    history=db.get_messages(payload.chat_id)
    messages=build_context(history,payload.message.strip())
    tools=EMAIL_TOOLS if email_tool.get_settings()['configured'] else None
    if tools:
        messages[0]['content'] += '\nAn SMTP email tool is available. Use it only when the user asks you to send an email. The tool only prepares a preview; never claim an email was sent until the user approves it.'
    try:
        if tools:
            response,meta=await run_in_threadpool(router.completion,payload.model,messages,False,tools,True)
            calls=response.get('tool_calls') or []
            if calls:
                function=calls[0].get('function') if isinstance(calls,list) and calls and isinstance(calls[0],dict) else None
                if len(calls)!=1 or not isinstance(function,dict) or function.get('name')!='send_email':
                    raise router.RouterError('The model requested an unsupported email action.')
                try:
                    arguments=json.loads(function['arguments'])
                    to=arguments['to']
                    subject=arguments['subject']
                    body=arguments['body']
                    confirmation_id=email_tool.create_confirmation(to,subject,body)
                except (ValueError,KeyError,TypeError,email_tool.EmailToolError) as exc:
                    raise router.RouterError(f'The model returned an invalid email draft: {exc}') from exc
                with pending_email_lock:
                    now=time.monotonic()
                    for key,value in list(pending_email_confirmations.items()):
                        if value['expires_at']<=now:
                            pending_email_confirmations.pop(key,None)
                    pending_email_confirmations[confirmation_id]={'chat_id':payload.chat_id,'to':to,'subject':subject,'body':body,'expires_at':now+600}
                answer=response.get('content') or 'Email draft prepared. Review the preview and approve it to send.'
                db.save_exchange(payload.chat_id,payload.message.strip(),answer)
                return {'answer':answer,'meta':meta,'email_confirmation':{'id':confirmation_id,'to':to,'subject':subject,'body':body}}
            answer=response.get('content')
            if not isinstance(answer,str) or not answer.strip():
                raise router.RouterError('Provider returned an empty response.')
        else:
            answer,meta=await run_in_threadpool(router.completion,payload.model,messages)
    except router.RouterError as exc:raise HTTPException(503,str(exc))
    # Only persist a successful exchange; failed prompts stay in browser draft.
    db.save_exchange(payload.chat_id,payload.message.strip(),answer)
    return {'answer':answer,'meta':meta}

class EmailSettingsInput(BaseModel):
    host:str=Field(min_length=1,max_length=253)
    port:int=Field(ge=1,le=65535)
    username:str=Field(default='',max_length=320)
    password:str=Field(default='',max_length=1000)
    from_email:str=Field(min_length=3,max_length=320)
    security:str=Field(default='starttls',pattern='^(starttls|ssl)$')

class EmailConfirmation(BaseModel):
    confirmation_id:str

@app.get('/api/email/settings')
def get_email_settings():return email_tool.get_settings()

@app.put('/api/email/settings')
def update_email_settings(payload:EmailSettingsInput):
    try:
        email_tool.save_settings(payload.host,payload.port,payload.username,payload.password,payload.from_email,payload.security)
        clear_pending_email_confirmations()
        return email_tool.get_settings()
    except email_tool.EmailToolError as exc:raise HTTPException(400,str(exc))

@app.delete('/api/email/settings')
def delete_email_settings():
    email_tool.clear_settings()
    clear_pending_email_confirmations()
    return {'ok':True}

@app.post('/api/email/confirm')
async def confirm_email(payload:EmailConfirmation):
    with pending_email_lock:
        pending=pending_email_confirmations.pop(payload.confirmation_id,None)
    if not pending or pending['expires_at']<=time.monotonic():raise HTTPException(404,'Email preview expired or was already handled.')
    if not db.get_chat(pending['chat_id']):raise HTTPException(404,'Chat not found.')
    try:
        await run_in_threadpool(email_tool.send_email,pending['to'],pending['subject'],pending['body'])
    except email_tool.EmailToolError as exc:raise HTTPException(502,str(exc))
    result=f"Email sent to {pending['to']} with subject: {pending['subject']}"
    db.save_assistant_message(pending['chat_id'],result)
    return {'ok':True,'message':result}

@app.post('/api/email/cancel')
def cancel_email(payload:EmailConfirmation):
    with pending_email_lock:
        pending=pending_email_confirmations.pop(payload.confirmation_id,None)
    if not pending or pending['expires_at']<=time.monotonic():
        raise HTTPException(404,'Email preview expired or was already handled.')
    if not db.get_chat(pending['chat_id']):raise HTTPException(404,'Chat not found.')
    db.save_assistant_message(pending['chat_id'],'Email draft canceled; nothing was sent.')
    return {'ok':True}

class FailoverTest(BaseModel):
    model:str

@app.post('/api/test-failover')
async def test_failover(payload:FailoverTest):
    if sum(payload.model in k['models'] for k in router.list_keys() if k['status']!='invalid')<2:
        raise HTTPException(400,'At least two valid keys must advertise the selected model.')
    try:
        answer,meta=await run_in_threadpool(router.completion,payload.model,[{'role':'user','content':'Reply with only: Backup connection successful.'}],True)
    except router.RouterError as exc:raise HTTPException(503,str(exc))
    return {'answer':answer,'meta':meta,'note':'First eligible key was artificially skipped; backup key made a real Groq request.'}


class MemoryInput(BaseModel):
    content:str=Field(min_length=1,max_length=1000)
    ttl_hours:int|None=Field(default=None,ge=1,le=8760)

@app.get('/api/memories')
def get_memories():return {'memories':db.list_memories()}

@app.post('/api/memories')
def add_memory(payload:MemoryInput):
    expiry=(datetime.now(timezone.utc)+timedelta(hours=payload.ttl_hours)).isoformat() if payload.ttl_hours else None
    memory_id=str(uuid.uuid4())
    db.save_memory(memory_id,payload.content.strip(),expiry)
    return {'id':memory_id,'content':payload.content.strip(),'expires_at':expiry}

@app.delete('/api/memories/{memory_id}')
def remove_memory(memory_id:str):
    if not db.delete_memory(memory_id):raise HTTPException(404,'Memory not found')
    return {'ok':True}
