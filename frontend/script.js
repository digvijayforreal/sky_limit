'use strict';
const $=id=>document.getElementById(id);
let currentChat=null,selectedModel='',busy=false,models=[];
async function api(url,options={}){
  let res;
  try {res=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}})}
  catch {throw new Error('Cannot reach FastAPI. Make sure the server is running.')}
  let data;try{data=await res.json()}catch{data={}}
  if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:`HTTP ${res.status}`);
  return data;
}
function toast(message){const el=$('toast');el.textContent=message;el.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.add('hidden'),5000)}
function setBusy(on){busy=on;$('sendBtn').disabled=on;$('messageInput').disabled=on;$('sendBtn').textContent=on?'…':'↑'}
function renderMessage(role,content,meta){
  $('emptyState')?.remove();const item=document.createElement('div');item.className=`message ${role}`;
  const avatar=document.createElement('div');avatar.className='avatar';avatar.textContent=role==='user'?'U':'O';
  const body=document.createElement('div');body.className='message-body';
  const header=document.createElement('div');header.className='message-header';header.textContent=role==='user'?'YOU / MESSAGE':'OMNIAGENT / RESPONSE';
  const txt=document.createElement('div');txt.className='message-text';txt.textContent=content;
  body.append(header,txt);
  if(meta){const m=document.createElement('div');m.className='meta';m.textContent=`ENGINE: ${meta.model}  ·  VIA: ${meta.used_key}  ·  ROUTE: ${meta.attempts.map(a=>a.key+' ['+a.result+']').join(' → ')}`;body.append(m)}
  item.append(avatar,body);$('messages').append(item);$('chatPanel').scrollTop=$('chatPanel').scrollHeight;
  return item;
}
function renderEmailConfirmation(email){
  const card=document.createElement('div');card.className='email-preview';
  const title=document.createElement('strong');title.textContent='EMAIL PREVIEW — REVIEW BEFORE SENDING';
  const recipient=document.createElement('div');recipient.textContent=`TO: ${email.to}`;
  const subject=document.createElement('div');subject.textContent=`SUBJECT: ${email.subject}`;
  const body=document.createElement('pre');body.textContent=email.body;
  const actions=document.createElement('div');actions.className='email-preview-actions';
  const approve=document.createElement('button');approve.textContent='APPROVE & SEND';
  const cancel=document.createElement('button');cancel.textContent='CANCEL';
  approve.onclick=async()=>{approve.disabled=true;cancel.disabled=true;approve.textContent='SENDING…';try{const result=await api('/api/email/confirm',{method:'POST',body:JSON.stringify({confirmation_id:email.id})});card.textContent=result.message;toast('Email sent.')}catch(e){card.textContent='Email send failed or could not be confirmed. This preview cannot be retried. '+e.message;toast(e.message)}};
  cancel.onclick=async()=>{approve.disabled=true;cancel.disabled=true;try{await api('/api/email/cancel',{method:'POST',body:JSON.stringify({confirmation_id:email.id})});card.textContent='Email cancelled; nothing was sent.'}catch(e){toast(e.message);approve.disabled=false;cancel.disabled=false}};
  actions.append(approve,cancel);card.append(title,recipient,subject,body,actions);$('messages').append(card);$('chatPanel').scrollTop=$('chatPanel').scrollHeight;
}
function renderEmpty(){ $('messages').innerHTML=`<div id="emptyState" class="empty-state"><div class="eyebrow">↗ INTRODUCING YOUR PERSONAL INTELLIGENCE</div><h1>THINK BEYOND<br><em>THE ORDINARY.</em></h1><p>One mind. Multiple engines. Memory that stays with you.</p><div class="divider-line"></div><div class="quick-actions"><button data-prompt="Explain how large language models work.">EXPLORE INTELLIGENCE ↗</button><button data-prompt="Write a Python program that sorts a list.">START CODING ↗</button></div></div>` }
async function getChats(){let data=await api('/api/chats');$('chatCount').textContent=String(data.chats.length).padStart(2,'0');const list=$('chatList');list.replaceChildren();for(const c of data.chats){const btn=document.createElement('div');btn.setAttribute('role','button');btn.tabIndex=0;btn.className='chat-item'+(c.id===currentChat?' active':'');const name=document.createElement('span');name.textContent=c.title;const del=document.createElement('button');del.className='del';del.textContent='×';del.title='Delete conversation';del.onclick=async ev=>{ev.stopPropagation();if(!confirm('Delete this conversation permanently?'))return;try{await api('/api/chats/'+encodeURIComponent(c.id),{method:'DELETE'});if(currentChat===c.id){currentChat=null;await newChat()}else await getChats()}catch(e){toast(e.message)}};btn.append('⌁',name,del);btn.onclick=()=>openChat(c.id);btn.onkeydown=e=>{if(e.key==='Enter')openChat(c.id)};list.append(btn)}}
async function openChat(id){if(busy)return;try{const data=await api('/api/chats/'+encodeURIComponent(id));currentChat=id;$('chatTitle').textContent=data.chat.title.toUpperCase();$('messages').replaceChildren();if(!data.messages.length)renderEmpty();else for(const m of data.messages)renderMessage(m.role,m.content);await getChats();$('sidebar').classList.remove('open')}catch(e){toast(e.message)}}
async function newChat(){if(busy)return;try{const chat=await api('/api/chats',{method:'POST'});await openChat(chat.id)}catch(e){toast(e.message)}}
async function loadModels(){try{const data=await api('/api/models');models=data.models;const select=$('modelSelect');const former=select.value||selectedModel;select.replaceChildren();if(!models.length){select.add(new Option('ADD API KEY TO BEGIN',''));selectedModel='';}else{for(const m of models)select.add(new Option(`${m.id} (${m.key_count} key${m.key_count===1?'':'s'})`,m.id));select.value=models.some(m=>m.id===former)?former:(models.find(m=>m.id==='llama-3.3-70b-versatile')?.id||models.find(m=>m.id==='openai/gpt-oss-120b')?.id||models[0].id);selectedModel=select.value}const keys=(await api('/api/keys')).keys;$('apiStatus').textContent=keys.length?`${keys.filter(k=>k.status==='ready').length}/${keys.length} APIs READY`:'NO API CONNECTED';renderKeys(keys)}catch(e){toast(e.message)}}
function renderKeys(keys){const list=$('keyList');list.replaceChildren();if(!keys.length){const txt=document.createElement('p');txt.className='fine-print';txt.textContent='No keys configured. Add your first Groq API key above.';list.append(txt);return}for(const k of keys){const card=document.createElement('div');card.className='key-card';const detail=document.createElement('div');const title=document.createElement('strong');title.textContent=k.name;const status=document.createElement('small');status.textContent=`${k.masked}  ·  ${k.status.toUpperCase()}  ·  ${k.models.length} MODELS${k.last_error?'  ·  '+k.last_error:''}`;detail.append(title,status);const del=document.createElement('button');del.textContent='REMOVE';del.onclick=async()=>{try{await api('/api/keys/'+encodeURIComponent(k.id),{method:'DELETE'});await loadModels();toast('API key removed.')}catch(e){toast(e.message)}};card.append(detail,del);list.append(card)}}
async function sendMessage(){if(busy)return;let message=$('messageInput').value.trim();if(!message)return;if(!selectedModel){toast('Add a Groq API key first.');showSettings();return}if(!currentChat)await newChat();if(!currentChat)return;setBusy(true);$('messageInput').value='';const prompt=renderMessage('user',message);const pending=renderMessage('assistant','THINKING…');try{const out=await api('/api/chat',{method:'POST',body:JSON.stringify({chat_id:currentChat,message,model:selectedModel})});pending.remove();renderMessage('assistant',out.answer,out.meta);if(out.email_confirmation)renderEmailConfirmation(out.email_confirmation);await getChats();const chat=await api('/api/chats/'+encodeURIComponent(currentChat));$('chatTitle').textContent=chat.chat.title.toUpperCase();await loadModels()}catch(e){pending.remove();prompt.remove();$('messageInput').value=message;toast('Request failed: '+e.message)}finally{setBusy(false);$('messageInput').focus()}}
function showSettings(){$('settingsOverlay').classList.remove('hidden');$('apiKey').value='';loadEmailSettings()}
$('settingsBtn').onclick=()=>{showSettings();loadMemories()};$('closeSettings').onclick=()=>$('settingsOverlay').classList.add('hidden');$('settingsOverlay').addEventListener('click',e=>{if(e.target===$('settingsOverlay'))$('settingsOverlay').classList.add('hidden')});$('menuBtn').onclick=()=>$('sidebar').classList.toggle('open');$('newChat').onclick=newChat;$('chatForm').onsubmit=e=>{e.preventDefault();sendMessage()};$('messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}});$('modelSelect').onchange=e=>{selectedModel=e.target.value};document.addEventListener('click',e=>{const quick=e.target.closest('[data-prompt]');if(quick){$('messageInput').value=quick.dataset.prompt;$('messageInput').focus()}});
$('keyForm').onsubmit=async e=>{e.preventDefault();const btn=$('addKeyBtn');btn.disabled=true;btn.textContent='VALIDATING…';try{const key=$('apiKey').value;await api('/api/keys',{method:'POST',body:JSON.stringify({name:$('keyName').value,api_key:key,remember:$('rememberKey').checked})});$('apiKey').value='';$('keyName').value='';await loadModels();toast('Groq key validated and connected.')}catch(err){toast(err.message)}finally{btn.disabled=false;btn.textContent='+ CONNECT API'}};
$('refreshModels').onclick=async()=>{try{toast('Refreshing models…');await api('/api/keys/refresh',{method:'POST'});await loadModels();toast('Model discovery refreshed.')}catch(e){toast(e.message)}};
$('testFailover').onclick=async()=>{if(!selectedModel){toast('Add an API key and select a model first.');return}const btn=$('testFailover');btn.disabled=true;const result=$('testResults');result.classList.remove('hidden');result.textContent='RUNNING SIMULATED FAILURE TEST…';try{const data=await api('/api/test-failover',{method:'POST',body:JSON.stringify({model:selectedModel})});result.textContent=`${data.note}\n\n${data.meta.attempts.map(a=>a.key+' → '+a.result).join('\n')}\n\nMODEL: ${data.meta.model}\nRESPONSE: ${data.answer}`;await loadModels()}catch(e){result.textContent='TEST FAILED: '+e.message}finally{btn.disabled=false}};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='n'){e.preventDefault();newChat()}if(e.key==='Escape')$('settingsOverlay').classList.add('hidden')});
(async()=>{try{const data=await api('/api/chats');if(data.chats.length)await openChat(data.chats[0].id);else await newChat();await loadModels();if(new URLSearchParams(location.search).has('settings'))showSettings();await loadMemories()}catch(e){toast(e.message)}})();

$('addMemory').onclick=async()=>{const content=$('memoryText').value.trim();if(!content){toast('Enter something to remember');return}try{await api('/api/memories',{method:'POST',body:JSON.stringify({content,ttl_hours:$('memoryTtl').value?Number($('memoryTtl').value):null})});$('memoryText').value='';await loadMemories();toast('Memory saved for all conversations.')}catch(e){toast(e.message)}};

async function loadEmailSettings(){
  try{
    const config=await api('/api/email/settings');
    $('emailConfigStatus').textContent=config.configured?'CONFIGURED':'NOT CONFIGURED';
    $('smtpHost').value=config.host||'';
    $('smtpPort').value=config.port||587;
    $('smtpUsername').value=config.username||'';
    $('smtpFrom').value=config.from_email||'';
    $('smtpSecurity').value=config.security||'starttls';
    $('smtpPassword').value='';
    $('smtpPassword').placeholder=config.has_password?'Saved password kept unless replaced':'SMTP password';
  }catch(e){toast(e.message)}
}
$('emailSettingsForm').onsubmit=async e=>{
  e.preventDefault();
  const btn=$('saveEmailSettings');btn.disabled=true;btn.textContent='SAVING…';
  try{
    const config=await api('/api/email/settings',{method:'PUT',body:JSON.stringify({
      host:$('smtpHost').value,port:Number($('smtpPort').value),username:$('smtpUsername').value,
      password:$('smtpPassword').value,from_email:$('smtpFrom').value,security:$('smtpSecurity').value
    })});
    $('emailConfigStatus').textContent=config.configured?'CONFIGURED':'NOT CONFIGURED';
    $('smtpPassword').value='';
    $('smtpPassword').placeholder=config.has_password?'Saved password kept unless replaced':'SMTP password';
    toast('SMTP settings saved. Email previews require your approval before sending.');
  }catch(e){toast(e.message)}
  finally{btn.disabled=false;btn.textContent='SAVE SMTP SETTINGS'}
};
$('clearEmailSettings').onclick=async()=>{
  if(!confirm('Remove the saved SMTP configuration?'))return;
  try{await api('/api/email/settings',{method:'DELETE'});await loadEmailSettings();toast('SMTP configuration removed.')}
  catch(e){toast(e.message)}
};
