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
function escapeHtml(value){
  return value.replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function markdownHtml(content){
  if(!window.marked||!window.DOMPurify)return null;
  const renderer=new marked.Renderer();
  renderer.code=({text,lang})=>{
    const language=(lang||'').trim().split(/\s+/)[0].toLowerCase();
    const safeLanguage=/^[a-z0-9_+#.-]+$/.test(language)?language:'';
    let highlighted=escapeHtml(text);
    if(window.hljs){
      if(safeLanguage&&hljs.getLanguage(safeLanguage)){
        highlighted=hljs.highlight(text,{language:safeLanguage,ignoreIllegals:true}).value;
      }else if(!safeLanguage){
        highlighted=hljs.highlightAuto(text).value;
      }
    }
    const label=safeLanguage?safeLanguage.toUpperCase():'CODE';
    return `<section class="code-widget"><header class="code-widget-header"><span>${escapeHtml(label)}</span><button type="button" class="copy-code-btn" data-copy-code>Copy code</button></header><pre><code class="hljs${safeLanguage?` language-${escapeHtml(safeLanguage)}`:''}">${highlighted}</code></pre></section>`;
  };
  const html=marked.parse(content,{gfm:true,breaks:false,renderer});
  return DOMPurify.sanitize(html,{
    USE_PROFILES:{html:true},
    ADD_ATTR:['data-copy-code'],
    FORBID_TAGS:['img','style'],
  });
}
async function copyText(text){
  if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);return}
  const field=document.createElement('textarea');
  field.value=text;field.setAttribute('readonly','');field.style.position='fixed';field.style.opacity='0';
  document.body.append(field);field.select();
  const copied=document.execCommand('copy');field.remove();
  if(!copied)throw new Error('Clipboard access is unavailable in this browser.');
}
function renderMessage(role,content,meta){
  $('emptyState')?.remove();const item=document.createElement('div');item.className=`message ${role}`;
  content=typeof content==='string'?content:'';
  const avatar=document.createElement('div');avatar.className='avatar';avatar.textContent=role==='user'?'U':'A';
  const body=document.createElement('div');body.className='message-body';
  const header=document.createElement('div');header.className='message-header';header.textContent=role==='user'?'YOU / MESSAGE':'ASSISTANT / RESPONSE';
  const txt=document.createElement('div');txt.className='message-text';
  if(role==='assistant'){
    txt.classList.add('markdown-body');txt._rawMarkdown=content;
    try{
      const html=markdownHtml(content);
      if(html===null){txt.textContent=content||'No response text.'}
      else if(content.trim()){txt.innerHTML=html}
      else{txt.textContent='No response text.'}
    }catch(error){
      console.error('Could not render assistant Markdown.',error);
      txt.textContent=content||'No response text.';
      toast('Could not format the response; showing plain text instead.');
    }
    txt.querySelectorAll('a[href]').forEach(link=>{link.target='_blank';link.rel='noopener noreferrer'});
    item._rawResponse=content;
  }else{txt.textContent=content}
  body.append(header,txt);
  if(role==='assistant'&&!content.startsWith('THINKING WITH ')){
    const actions=document.createElement('div');actions.className='message-actions';
    const copy=document.createElement('button');copy.type='button';copy.className='copy-response-btn';copy.dataset.copyResponse='';copy.textContent='Copy response';copy.setAttribute('aria-label','Copy assistant response');
    actions.append(copy);body.append(actions);
  }
  if(meta){
    const m=document.createElement('div');m.className='meta';
    const details=[`ENGINE: ${meta.model}`,`PROVIDER: ${(meta.provider||'groq').toUpperCase()}`,`VIA: ${meta.used_key}`,`ROUTE: ${(meta.attempts||[]).map(a=>a.key+' ['+a.result+']').join(' → ')}`];
    if(meta.response_ms!==undefined)details.push(`TIME: ${(meta.response_ms/1000).toFixed(2)}s`);
    if(meta.usage){
      const input=meta.usage.input_tokens,output=meta.usage.output_tokens;
      details.push(input===null||input===undefined||output===null||output===undefined
        ?'TOKENS: NOT REPORTED'
        :`TOKENS: ${input.toLocaleString()} IN / ${output.toLocaleString()} OUT`);
    }
    if(meta.rate_limits?.requests_remaining!==undefined)details.push(`REQUESTS REMAINING: ${meta.rate_limits.requests_remaining}`);
    if(meta.rate_limits?.tokens_remaining!==undefined)details.push(`TOKENS REMAINING: ${meta.rate_limits.tokens_remaining}`);
    m.textContent=details.join('  ·  ');body.append(m);
  }
  item.append(avatar,body);$('messages').append(item);$('chatPanel').scrollTop=$('chatPanel').scrollHeight;
  return item;
}
document.addEventListener('click',async event=>{
  const codeButton=event.target.closest('[data-copy-code]');
  const responseButton=event.target.closest('[data-copy-response]');
  const button=codeButton||responseButton;
  if(!button)return;
  const original=button.textContent;
  button.disabled=true;
  try{
    const text=codeButton
      ?button.closest('.code-widget').querySelector('pre code').textContent
      :button.closest('.message')._rawResponse;
    await copyText(text);
    button.textContent='Copied!';
    setTimeout(()=>{button.textContent=original;button.disabled=false},1500);
  }catch(error){
    button.disabled=false;
    toast(`Could not copy ${codeButton?'code':'response'}: ${error.message}`);
  }
});
function renderEmailConfirmation(email){
  const card=document.createElement('div');card.className='email-preview';
  const title=document.createElement('strong');title.textContent='EMAIL PREVIEW — REVIEW BEFORE SENDING';
  const form=document.createElement('form');form.className='email-preview-form';
  const recipient=document.createElement('input');recipient.type='text';recipient.required=true;recipient.value=email.to;
  const subject=document.createElement('input');subject.type='text';subject.required=true;subject.maxLength=250;subject.value=email.subject;
  const body=document.createElement('textarea');body.required=true;body.maxLength=20000;body.rows=8;body.value=email.body;
  for(const [text,input] of [['TO',recipient],['SUBJECT',subject],['BODY',body]]){
    const label=document.createElement('label');label.append(document.createTextNode(text),input);form.append(label);
  }
  const actions=document.createElement('div');actions.className='email-preview-actions';
  const approve=document.createElement('button');approve.type='submit';approve.textContent='SEND EMAIL';
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='CANCEL';
  form.onsubmit=async event=>{event.preventDefault();approve.disabled=true;cancel.disabled=true;approve.textContent='SENDING…';try{const result=await api('/api/email/confirm',{method:'POST',body:JSON.stringify({confirmation_id:email.id,to:recipient.value,subject:subject.value,body:body.value})});card.textContent=result.message;toast('Email sent.')}catch(e){card.textContent='Email send failed or could not be confirmed. This preview cannot be retried. '+e.message;toast(e.message)}};
  cancel.onclick=async()=>{approve.disabled=true;cancel.disabled=true;try{await api('/api/email/cancel',{method:'POST',body:JSON.stringify({confirmation_id:email.id})});card.textContent='Email cancelled; nothing was sent.'}catch(e){toast(e.message);approve.disabled=false;cancel.disabled=false}};
  actions.append(approve,cancel);form.append(actions);card.append(title,form);$('messages').append(card);$('chatPanel').scrollTop=$('chatPanel').scrollHeight;
}
function renderEmpty(){ $('messages').innerHTML=`<div id="emptyState" class="empty-state"><div class="eyebrow">TESTING WORKSPACE</div><h1>TEST INTERFACE</h1><p>Use the controls below to test chat, model, memory, and email features.</p><div class="divider-line"></div><div class="quick-actions"><button data-prompt="Explain how large language models work.">TEST A CHAT RESPONSE</button><button data-prompt="Write a Python program that sorts a list.">TEST CODE GENERATION</button></div></div>` }
async function getChats(){let data=await api('/api/chats');$('chatCount').textContent=String(data.chats.length).padStart(2,'0');const list=$('chatList');list.replaceChildren();for(const c of data.chats){const btn=document.createElement('div');btn.setAttribute('role','button');btn.tabIndex=0;btn.className='chat-item'+(c.id===currentChat?' active':'');const name=document.createElement('span');name.textContent=c.title;const del=document.createElement('button');del.className='del';del.textContent='×';del.title='Delete conversation';del.onclick=async ev=>{ev.stopPropagation();if(!confirm('Delete this conversation permanently?'))return;try{await api('/api/chats/'+encodeURIComponent(c.id),{method:'DELETE'});if(currentChat===c.id){currentChat=null;await newChat()}else await getChats()}catch(e){toast(e.message)}};btn.append('⌁',name,del);btn.onclick=()=>openChat(c.id);btn.onkeydown=e=>{if(e.key==='Enter')openChat(c.id)};list.append(btn)}}
async function openChat(id){if(busy)return;try{const data=await api('/api/chats/'+encodeURIComponent(id));currentChat=id;$('chatTitle').textContent=data.chat.title.toUpperCase();$('messages').replaceChildren();if(!data.messages.length)renderEmpty();else for(const m of data.messages)renderMessage(m.role,m.content);await getChats();$('sidebar').classList.remove('open')}catch(e){toast(e.message)}}
async function newChat(){if(busy)return;try{const chat=await api('/api/chats',{method:'POST'});await openChat(chat.id)}catch(e){toast(e.message)}}
function modelValue(model){return `${model.provider}::${model.id}`}
function renderModelOptions(){
  const select=$('modelSelect'),query=$('modelSearch').value.trim().toLowerCase();
  if(!models.length){select.replaceChildren(new Option('ADD API KEY TO BEGIN',''));return}
  const selected=models.find(model=>modelValue(model)===selectedModel);
  let visible=models.filter(model=>`${model.provider} ${model.id}`.toLowerCase().includes(query));
  if(selected&&!visible.includes(selected))visible=[selected,...visible];
  select.replaceChildren();
  if(!visible.length){select.add(new Option('NO MODELS MATCH SEARCH',''));return}
  for(const model of visible){
    const provider=model.provider==='google'?'GEMINI':'GROQ';
    const pinned=modelValue(model)===selectedModel&&!`${model.provider} ${model.id}`.toLowerCase().includes(query);
    const label=`${provider} · ${model.id} (${model.key_count} key${model.key_count===1?'':'s'})${pinned?' · SELECTED':''}`;
    select.add(new Option(label,modelValue(model)));
  }
  select.value=selectedModel;
}
async function loadModels(){
  try{
    const data=await api('/api/models');models=data.models;
    if(!models.some(model=>modelValue(model)===selectedModel)){
      selectedModel=modelValue(models.find(model=>model.provider==='google'&&model.id.includes('gemini-2.5-flash'))
        ||models.find(model=>model.provider==='groq'&&model.id==='llama-3.3-70b-versatile')
        ||models.find(model=>model.provider==='groq'&&model.id.includes('llama'))
        ||models.find(model=>model.provider==='google'&&model.id.includes('gemini'))
        ||models[0]||{provider:'',id:''});
      if(!models.length)selectedModel='';
    }
    renderModelOptions();
    const keys=(await api('/api/keys')).keys;
    $('apiStatus').textContent=keys.length?`${keys.filter(k=>k.status==='ready').length}/${keys.length} APIs READY`:'NO API CONNECTED';
    renderKeys(keys);
    await loadUsage();
  }catch(e){toast(e.message)}
}
function renderKeys(keys){const list=$('keyList');list.replaceChildren();if(!keys.length){const txt=document.createElement('p');txt.className='fine-print';txt.textContent='No keys configured. Add a Groq or Google AI Studio API key above.';list.append(txt);return}for(const k of keys){const card=document.createElement('div');card.className='key-card';const detail=document.createElement('div');const title=document.createElement('strong');title.textContent=`${k.name} · ${k.provider==='google'?'GOOGLE AI STUDIO':'GROQ'}`;const status=document.createElement('small');status.textContent=`${k.masked}  ·  ${k.status.toUpperCase()}  ·  ${k.models.length} MODELS${k.last_error?'  ·  '+k.last_error:''}`;detail.append(title,status);const del=document.createElement('button');del.textContent='REMOVE';del.onclick=async()=>{try{await api('/api/keys/'+encodeURIComponent(k.id),{method:'DELETE'});await loadModels();toast('API key removed.')}catch(e){toast(e.message)}};card.append(detail,del);list.append(card)}}
function usageValue(value){return Number(value||0).toLocaleString()}
function renderUsage(summary){
  const totals=$('usageTotals'),keys=$('usageKeys');totals.replaceChildren();keys.replaceChildren();
  const inputLabel=summary.totals.requests
    ?`INPUT TOKENS (${usageValue(summary.totals.input_token_reports)}/${usageValue(summary.totals.requests)} REPORTED)`
    :'INPUT TOKENS REPORTED';
  const outputLabel=summary.totals.requests
    ?`OUTPUT TOKENS (${usageValue(summary.totals.output_token_reports)}/${usageValue(summary.totals.requests)} REPORTED)`
    :'OUTPUT TOKENS REPORTED';
  const inputTotal=summary.totals.requests&&!summary.totals.input_token_reports?'—':usageValue(summary.totals.input_tokens);
  const outputTotal=summary.totals.requests&&!summary.totals.output_token_reports?'—':usageValue(summary.totals.output_tokens);
  for(const [label,value] of [['SUCCESSFUL REQUESTS',usageValue(summary.totals.requests)],[inputLabel,inputTotal],[outputLabel,outputTotal]]){
    const card=document.createElement('div');card.className='usage-total';
    const number=document.createElement('strong');number.textContent=usageValue(value);
    const caption=document.createElement('span');caption.textContent=label;
    card.append(number,caption);totals.append(card);
  }
  if(!summary.keys.length){const empty=document.createElement('p');empty.className='fine-print';empty.textContent='No API keys are currently configured.';keys.append(empty);return}
  for(const item of summary.keys){
    const card=document.createElement('article');card.className='usage-key';
    const heading=document.createElement('strong');heading.textContent=`${item.key_label} · ${item.provider==='google'?'GEMINI':'GROQ'}`;
    const inputTokens=item.requests
      ?`${item.input_token_reports?usageValue(item.input_tokens):'not reported'} input tokens (${usageValue(item.input_token_reports)}/${usageValue(item.requests)} reported)`
      :'input tokens not reported';
    const outputTokens=item.requests
      ?`${item.output_token_reports?usageValue(item.output_tokens):'not reported'} output tokens (${usageValue(item.output_token_reports)}/${usageValue(item.requests)} reported)`
      :'output tokens not reported';
    const totals=document.createElement('p');totals.textContent=`${usageValue(item.requests)} successful requests · ${inputTokens} · ${outputTokens}`;
    card.append(heading,totals);
    if(item.latest?.response_ms!==undefined){
      const responseTime=document.createElement('p');responseTime.textContent=`Last response: ${(item.latest.response_ms/1000).toFixed(2)}s${item.latest.model?` · ${item.latest.model}`:''}`;
      card.append(responseTime);
    }
    const limits=item.latest?.rate_limits||{};
    if(item.provider==='google'){
      if(limits.requests_remaining!==undefined||limits.tokens_remaining!==undefined){
        const parts=[];
        if(limits.requests_remaining!==undefined)parts.push(`Requests remaining: ${limits.requests_remaining}${limits.requests_limit!==undefined?` / ${limits.requests_limit}`:''}`);
        if(limits.tokens_remaining!==undefined)parts.push(`Tokens remaining: ${limits.tokens_remaining}${limits.tokens_limit!==undefined?` / ${limits.tokens_limit}`:''}`);
        if(limits.requests_reset)parts.push(`Request reset: ${limits.requests_reset}`);
        if(limits.tokens_reset)parts.push(`Token reset: ${limits.tokens_reset}`);
        const providerLimits=document.createElement('p');providerLimits.className='usage-note';providerLimits.textContent=`Latest provider-reported window: ${parts.join(' · ')}`;card.append(providerLimits);
      }
      const note=document.createElement('p');note.className='usage-note';note.textContent='Remaining Gemini quota is not provided by this API response.';
      const link=document.createElement('a');link.href='https://aistudio.google.com/';link.target='_blank';link.rel='noopener noreferrer';link.textContent='Check Google AI Studio';
      note.append(document.createTextNode(' '),link);card.append(note);
    }else if(limits.requests_remaining!==undefined||limits.tokens_remaining!==undefined){
      const note=document.createElement('p');note.className='usage-note';const parts=[];
      if(limits.requests_remaining!==undefined)parts.push(`Requests remaining: ${limits.requests_remaining}${limits.requests_limit!==undefined?` / ${limits.requests_limit}`:''}`);
      if(limits.tokens_remaining!==undefined)parts.push(`Tokens remaining: ${limits.tokens_remaining}${limits.tokens_limit!==undefined?` / ${limits.tokens_limit}`:''}`);
      if(limits.requests_reset)parts.push(`Request reset: ${limits.requests_reset}`);
      if(limits.tokens_reset)parts.push(`Token reset: ${limits.tokens_reset}`);
      note.textContent=`Latest provider-reported window: ${parts.join(' · ')}`;card.append(note);
    }else{
      const note=document.createElement('p');note.className='usage-note';note.textContent='Provider-reported remaining limits are unavailable.';card.append(note);
    }
    if(item.latest?.observed_at){const observed=document.createElement('small');observed.textContent=`Limit snapshot: ${new Date(item.latest.observed_at).toLocaleString()}`;card.append(observed)}
    keys.append(card);
  }
}
async function loadUsage(){
  try{
    const summary=await api('/api/usage?period='+encodeURIComponent($('usagePeriod').value));
    renderUsage(summary);
  }catch(e){$('usageTotals').textContent='Could not load usage: '+e.message}
}
async function changeUsagePeriod(){await loadUsage()}
async function sendMessage(){
  if(busy)return;
  const message=$('messageInput').value.trim();
  if(!message)return;
  if(!selectedModel){toast('Add a Groq or Google AI Studio API key first.');showSettings();return}
  if(!currentChat)await newChat();
  if(!currentChat)return;
  setBusy(true);$('messageInput').value='';
  const prompt=renderMessage('user',message);
  const model=models.find(item=>modelValue(item)===selectedModel);
  const pending=renderMessage('assistant',`THINKING WITH ${model?.provider==='google'?'GEMINI':'GROQ'}…`);
  const controller=new AbortController();
  const slowTimer=setTimeout(()=>{pending.querySelector('.message-text').textContent='Still waiting for the selected model…'},10000);
  const timeout=setTimeout(()=>controller.abort(),75000);
  try{
    const out=await api('/api/chat',{method:'POST',body:JSON.stringify({chat_id:currentChat,message,model:selectedModel}),signal:controller.signal});
    clearTimeout(slowTimer);clearTimeout(timeout);
    pending.remove();renderMessage('assistant',out.answer,out.meta);
    if(out.email_confirmation)renderEmailConfirmation(out.email_confirmation);
    try{
      await getChats();
      const chat=await api('/api/chats/'+encodeURIComponent(currentChat));
      $('chatTitle').textContent=chat.chat.title.toUpperCase();
      await loadModels();
    }catch(e){toast('Reply received, but chat refresh failed: '+e.message)}
  }catch(e){
    prompt.remove();$('messageInput').value=message;
    pending.classList.add('request-error');
    pending.querySelector('.message-text').textContent=(e.name==='AbortError'?'Request timed out after 75 seconds.':`Request failed: ${e.message}`)+' Check the selected provider/model and API key, then retry.';
    toast(pending.querySelector('.message-text').textContent);
  }finally{
    clearTimeout(slowTimer);clearTimeout(timeout);setBusy(false);$('messageInput').focus();
  }
}
function showSettings(){$('settingsOverlay').classList.remove('hidden');$('apiKey').value='';loadEmailSettings();loadUsage()}
$('settingsBtn').onclick=()=>{showSettings();loadMemories()};$('closeSettings').onclick=()=>$('settingsOverlay').classList.add('hidden');$('settingsOverlay').addEventListener('click',e=>{if(e.target===$('settingsOverlay'))$('settingsOverlay').classList.add('hidden')});$('menuBtn').onclick=()=>$('sidebar').classList.toggle('open');$('newChat').onclick=newChat;$('chatForm').onsubmit=e=>{e.preventDefault();sendMessage()};$('messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}});$('modelSelect').onchange=e=>{selectedModel=e.target.value};$('modelSearch').oninput=renderModelOptions;document.addEventListener('click',e=>{const quick=e.target.closest('[data-prompt]');if(quick){$('messageInput').value=quick.dataset.prompt;$('messageInput').focus()}});
$('apiProvider').onchange=()=>{const google=$('apiProvider').value==='google';$('apiKeyLabel').firstChild.textContent=google?'GOOGLE AI STUDIO API KEY':'GROQ API KEY';$('apiKey').placeholder=google?'AIza••••••••••••••••':'gsk_••••••••••••••'};
$('keyForm').onsubmit=async e=>{e.preventDefault();const btn=$('addKeyBtn');btn.disabled=true;btn.textContent='VALIDATING…';const provider=$('apiProvider').value;try{const key=$('apiKey').value;await api('/api/keys',{method:'POST',body:JSON.stringify({name:$('keyName').value,api_key:key,provider,remember:$('rememberKey').checked})});$('apiKey').value='';$('keyName').value='';await loadModels();toast(`${provider==='google'?'Google AI Studio':'Groq'} key validated and connected.`)}catch(err){toast(err.message)}finally{btn.disabled=false;btn.textContent='+ CONNECT API'}};
$('refreshModels').onclick=async()=>{try{toast('Refreshing models…');await api('/api/keys/refresh',{method:'POST'});await loadModels();toast('Model discovery refreshed.')}catch(e){toast(e.message)}};
$('testFailover').onclick=async()=>{if(!selectedModel){toast('Add an API key and select a model first.');return}const btn=$('testFailover');btn.disabled=true;const result=$('testResults');result.classList.remove('hidden');result.textContent='RUNNING SIMULATED FAILURE TEST…';try{const data=await api('/api/test-failover',{method:'POST',body:JSON.stringify({model:selectedModel})});result.textContent=`${data.note}\n\n${data.meta.attempts.map(a=>a.key+' → '+a.result).join('\n')}\n\nPROVIDER: ${(data.meta.provider||'groq').toUpperCase()}\nMODEL: ${data.meta.model}\nRESPONSE: ${data.answer}`;await loadModels()}catch(e){result.textContent='TEST FAILED: '+e.message}finally{btn.disabled=false}};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='n'){e.preventDefault();newChat()}if(e.key==='Escape')$('settingsOverlay').classList.add('hidden')});
$('usagePeriod').onchange=changeUsagePeriod;$('refreshUsage').onclick=loadUsage;
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
