const API_URL = '';
const orderId = Number((location.pathname.match(/\/order\/(\d+)/) || [])[1] || 0);
const state = { user:null, room:null, ws:null, messages:[], events:[], reviewRating:5, typingTimer:null, reconnectTimer:null, counterpartOnline:false };

function token(){ return localStorage.getItem('token') || ''; }
function esc(v=''){ return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
function money(v){ return Number(v||0).toLocaleString('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2})+' ₽'; }
function dt(v){ return v ? new Date(v).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '—'; }
function time(v){ return v ? new Date(v).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}) : ''; }
function toast(message,type='success'){ const wrap=document.getElementById('toastWrap'); const el=document.createElement('div'); el.className=`toast ${type}`; el.textContent=message; wrap.appendChild(el); setTimeout(()=>el.remove(),3600); }
function json(method,body){ return {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}; }
async function api(path,opt={}){ const h=new Headers(opt.headers||{}); if(token()) h.set('Authorization',`Bearer ${token()}`); const r=await fetch(API_URL+path,{...opt,headers:h}); let d=null; try{ d=await r.json(); }catch(_){ } if(!r.ok){ let x=d?.detail||`HTTP ${r.status}`; if(Array.isArray(x)) x=x.map(i=>i.msg).join('; '); throw new Error(x); } return d; }

const STATUS = {
  pending:['Ожидает оплаты','pending'],
  paid:['Продавец выполняет заказ','paid'],
  delivered:['Товар передан — проверьте','delivered'],
  completed:['Сделка завершена','completed'],
  disputed:['Открыт спор','disputed'],
  cancelled:['Заказ отменён','cancelled'],
};
function statusText(s){ return STATUS[s]?.[0] || s; }
function initials(user){ const s=(user?.username||'?').trim(); return esc(s.slice(0,2).toUpperCase()); }
function relativeLastActive(v){ if(!v) return 'давно не был'; const sec=(Date.now()-new Date(v).getTime())/1000; if(sec<60) return 'был только что'; if(sec<3600) return `был ${Math.max(1,Math.floor(sec/60))} мин назад`; if(sec<86400) return `был ${Math.floor(sec/3600)} ч назад`; return `был ${Math.floor(sec/86400)} дн назад`; }

async function boot(){
  if(!orderId){ showError('Некорректный ID заказа'); return; }
  if(!token()){ location.href=`/login?next=${encodeURIComponent(location.pathname)}`; return; }
  try{
    state.user=await api('/users/me');
    await loadRoom(true);
    connectWs();
  }catch(e){
    if(/401|token|inactive|revoked/i.test(e.message)) location.href='/login';
    else showError(e.message);
  }
}

function showError(msg){ document.getElementById('orderRoomLoading').style.display='none'; const e=document.getElementById('orderRoomError'); e.style.display='grid'; e.textContent=msg; }

async function loadRoom(first=false){
  const data=await api(`/order-room/${orderId}`);
  state.room=data;
  state.messages=data.messages||[];
  state.events=data.events||[];
  renderRoom(first);
  if(first){ document.getElementById('orderRoomLoading').style.display='none'; document.getElementById('orderRoomApp').style.display='block'; }
  try{ await api(`/order-room/${orderId}/read`,{method:'POST'}); }catch(_){ }
}

function renderRoom(first=false){
  const r=state.room,o=r.order,s=r.seller,b=r.buyer,stats=r.seller_stats||{};
  document.title=`Заказ #${o.id} — GameMarket`;
  document.getElementById('dealKicker').textContent=`${r.role==='buyer'?'Покупка':r.role==='seller'?'Продажа':'Сделка'} · заказ #${o.id}`;
  document.getElementById('dealTitle').textContent=o.product_title;
  document.getElementById('dealMeta').textContent=`${o.product_category||'Без категории'} · ${o.quantity} шт. · создан ${dt(o.created_at)}`;
  document.getElementById('dealPrice').textContent=money(o.total_price);
  const st=document.getElementById('dealStatus'); st.textContent=statusText(o.status); st.className=`deal-status ${o.status}`;

  const counterpart=r.role==='buyer'?s:b;
  document.getElementById('chatAvatar').innerHTML=initials(counterpart);
  document.getElementById('chatPerson').textContent=counterpart.username;
  updatePresence(counterpart.id,false,counterpart.last_active);

  document.getElementById('sideTotal').textContent=money(o.total_price);
  document.getElementById('sideCommission').textContent=money(o.commission);
  document.getElementById('sellerEarningsRow').style.display=r.role==='seller'?'flex':'none';
  document.getElementById('sideEarnings').textContent=money(o.seller_earnings);
  const protectedStatus=['paid','delivered','disputed'].includes(o.status);
  document.getElementById('escrowText').innerHTML=protectedStatus
    ? `🔒 <strong>${money(o.total_price)}</strong> удерживается площадкой до завершения сделки или решения спора.`
    : o.status==='completed' ? '✅ Сделка завершена. Средства уже распределены.'
    : o.status==='pending' ? 'Оплата ещё не произведена. После оплаты сумма будет защищена площадкой.'
    : 'Заказ больше не находится в активной защите сделки.';

  document.getElementById('sideOrderId').textContent=`#${o.id}`;
  document.getElementById('sideProduct').textContent=o.product_title;
  document.getElementById('sideCategory').textContent=o.product_category||'—';
  document.getElementById('sideQuantity').textContent=o.quantity;
  document.getElementById('sideFulfillment').textContent=o.fulfillment_type==='automatic'?'Автоматическая':'Ручная';
  document.getElementById('sideCreated').textContent=dt(o.created_at);

  document.getElementById('sellerAvatar').innerHTML=initials(s);
  document.getElementById('sellerName').textContent=s.username;
  document.getElementById('sellerTitle').textContent=r.role==='seller'?'Ваш профиль продавца':'Продавец';
  document.getElementById('sellerVerified').textContent=s.is_verified?'✓':'';
  document.getElementById('sellerVerified').className=s.is_verified?'mini-verify-badge verified':'mini-verify-badge';
  document.getElementById('sellerOnlineText').textContent=state.counterpartOnline && r.role==='buyer'?'● онлайн':relativeLastActive(s.last_active);
  document.getElementById('sellerProfileLink').href=`/seller/${s.id}`;
  document.getElementById('sellerRating').textContent=`${'★'.repeat(Math.max(0,Math.min(5,Math.round(Number(s.rating||0)))))}${'☆'.repeat(5-Math.max(0,Math.min(5,Math.round(Number(s.rating||0)))))}  ${Number(s.rating||0).toFixed(2)}`;
  document.getElementById('statSales').textContent=s.total_sales ?? 0;
  document.getElementById('statSuccess').textContent=stats.success_rate==null?'—':`${stats.success_rate}%`;
  document.getElementById('statDisputes').textContent=stats.dispute_rate==null?'—':`${stats.dispute_rate}%`;
  document.getElementById('statResponse').textContent=stats.avg_response_minutes==null?'—':stats.avg_response_minutes<60?`~${Math.max(1,Math.round(stats.avg_response_minutes))} мин`:`~${(stats.avg_response_minutes/60).toFixed(1)} ч`;

  const delivery=document.getElementById('deliveryCard');
  if(o.delivery_content && ['delivered','completed','disputed'].includes(o.status)){ delivery.style.display='block'; document.getElementById('deliveryContent').textContent=o.delivery_content; }
  else delivery.style.display='none';

  const supportUrl=`/support?new=1&order_id=${o.id}`;
  document.getElementById('supportFromOrder').href=supportUrl;
  document.getElementById('orderSupportTop').href=supportUrl;

  renderActions(); renderChat(first); renderTimeline(); renderAutoComplete();
  const compose=document.getElementById('orderCompose'); compose.classList.toggle('disabled',!r.permissions.can_message);
  document.getElementById('orderMessage').placeholder=r.permissions.can_message?'Напишите сообщение по заказу…':'Чат доступен только для активной сделки';
}

function updatePresence(userId,online,lastActive=null){
  const r=state.room; if(!r) return;
  const counterpart=r.role==='buyer'?r.seller:r.buyer;
  if(userId!==counterpart.id) return;
  state.counterpartOnline=online;
  const el=document.getElementById('chatPresence');
  el.innerHTML=online?'<i class="presence-dot online"></i> онлайн':`<i class="presence-dot"></i> ${esc(relativeLastActive(lastActive||counterpart.last_active))}`;
  if(r.role==='buyer') document.getElementById('sellerOnlineText').textContent=online?'● онлайн':relativeLastActive(lastActive||r.seller.last_active);
}

function renderActions(){
  const p=state.room.permissions,o=state.room.order,box=document.getElementById('dealActions'); const a=[];
  if(p.can_pay) a.push('<button class="deal-action-primary" data-deal-action="pay">💳 Оплатить заказ</button>');
  if(p.can_cancel) a.push('<button class="deal-action-muted" data-deal-action="cancel">Отменить заказ</button>');
  if(p.can_deliver) a.push('<button class="deal-action-primary" data-deal-action="deliver">📦 Передать товар</button>');
  if(p.can_confirm) a.push('<button class="deal-action-success" data-deal-action="confirm">✅ Всё работает — завершить сделку</button>');
  if(p.can_dispute) a.push('<button class="deal-action-danger" data-deal-action="dispute">⚖️ Открыть спор</button>');
  if(p.can_review) a.push('<button class="deal-action-primary" data-deal-action="review">⭐ Оставить отзыв</button>');
  if(o.status==='disputed') a.push('<div class="deal-action-muted" style="cursor:default">⚖️ Средства заморожены до решения поддержки</div>');
  if(state.room.role==='admin'&&state.room.open_dispute){a.push('<button class="deal-action-success" data-deal-action="resolve-buyer">↩ Вернуть покупателю</button>','<button class="deal-action-primary" data-deal-action="resolve-seller">💰 Выплатить продавцу</button>','<button class="deal-action-muted" data-deal-action="resolve-split">½ Разделить сумму</button>');}
  if(o.status==='completed' && !p.can_review) a.push('<div class="deal-action-success" style="cursor:default">✓ Сделка завершена</div>');
  box.innerHTML=a.join('')||'<div class="deal-action-muted" style="cursor:default">Активных действий нет</div>';
}

function combinedFeed(){
  const rows=[];
  for(const m of state.messages) rows.push({kind:'message',at:new Date(m.created_at).getTime(),id:m.id,data:m});
  for(const e of state.events) rows.push({kind:'event',at:new Date(e.created_at).getTime(),id:e.id,data:e});
  return rows.sort((a,b)=>a.at-b.at || (a.kind==='event'?-1:1));
}

function renderChat(first=false){
  const feed=document.getElementById('orderChatFeed');
  const nearBottom=feed.scrollHeight-feed.scrollTop-feed.clientHeight<120;
  feed.innerHTML=combinedFeed().map(row=>{
    if(row.kind==='event'){
      const e=row.data; return `<div class="order-system"><strong>GameMarket</strong> · ${esc(e.text)} <span>${time(e.created_at)}</span></div>`;
    }
    const m=row.data,mine=m.sender_id===state.user.id;
    const image=m.attachment_url?`<div class="order-attachment"><img data-private-src="${esc(m.attachment_url)}" alt="Вложение"></div><div class="order-attachment-name">📎 ${esc(m.attachment_name||'изображение')}</div>`:'';
    const text=m.message?`<div class="order-bubble">${image}${esc(m.message)}</div>`:`<div class="order-bubble">${image}</div>`;
    const receipt=mine?`<span class="order-msg-read">${m.is_read?'✓✓':'✓'}</span>`:'';
    return `<div class="order-message ${mine?'mine':''}" data-message-id="${m.id}">${text}<div class="order-msg-meta"><span>${time(m.created_at)}</span>${receipt}</div></div>`;
  }).join('') || '<div class="empty-state small">Переписка по заказу пока пуста</div>';
  hydratePrivateImages(feed);
  if(first||nearBottom) feed.scrollTop=feed.scrollHeight;
}

async function hydratePrivateImages(root){
  for(const img of root.querySelectorAll('img[data-private-src]')){
    const path=img.dataset.privateSrc; if(!path||img.dataset.loaded)return; img.dataset.loaded='1';
    try{ const r=await fetch(path,{headers:{Authorization:`Bearer ${token()}`}}); if(!r.ok)throw new Error('image'); const blob=await r.blob(); img.src=URL.createObjectURL(blob); img.style.cursor='zoom-in'; }catch(_){ img.alt='Не удалось загрузить вложение'; }
  }
}

function renderTimeline(){
  const box=document.getElementById('dealTimeline');
  box.innerHTML=(state.events||[]).map(e=>`<div class="timeline-row"><div class="timeline-time">${dt(e.created_at)}</div><div class="timeline-axis"><span class="timeline-dot"></span></div><div class="timeline-content"><strong>${esc(e.text)}</strong><span>${eventLabel(e.event_type)}</span></div></div>`).join('')||'<div class="empty-state small">История появится после действий с заказом</div>';
}
function eventLabel(t){ return ({created:'Создание заказа',paid:'Оплата',awaiting_delivery:'Выполнение',delivered:'Передача товара',confirmed:'Подтверждение',auto_completed:'Автозавершение',disputed:'Спор',dispute_resolved:'Решение поддержки',review:'Отзыв',cancelled:'Отмена'})[t]||t; }
function renderAutoComplete(){ const o=state.room.order,el=document.getElementById('autoCompleteText'); if(!o.auto_complete_at||o.status!=='delivered'){el.textContent='';return;} const update=()=>{const ms=new Date(o.auto_complete_at)-Date.now(); if(ms<=0){el.textContent='Ожидается автозавершение';return;} const h=Math.floor(ms/3600000),m=Math.floor((ms%3600000)/60000); el.textContent=`Автозавершение через ${h} ч ${m} мин`;}; update(); clearInterval(window.__orderTimer); window.__orderTimer=setInterval(update,30000); }

async function connectWs(){
  clearTimeout(state.reconnectTimer);
  try{
    const {token:wsToken}=await api(`/order-room/${orderId}/ws-token`,{method:'POST'});
    const proto=location.protocol==='https:'?'wss':'ws';
    const ws=new WebSocket(`${proto}://${location.host}/ws/orders/${orderId}?token=${encodeURIComponent(wsToken)}`); state.ws=ws;
    ws.onopen=()=>{ ws.send(JSON.stringify({type:'read'})); };
    ws.onmessage=async ev=>{ let data; try{data=JSON.parse(ev.data);}catch(_){return;} if(data.type==='message'){ if(!state.messages.some(x=>x.id===data.message.id)) state.messages.push(data.message); renderChat(false); if(data.message.sender_id!==state.user.id) ws.send(JSON.stringify({type:'read'})); } if(data.type==='typing'&&data.user_id!==state.user.id){ document.getElementById('typingIndicator').textContent=data.typing?'печатает…':''; } if(data.type==='read'){ const ids=new Set(data.message_ids||[]); state.messages.forEach(m=>{if(ids.has(m.id))m.is_read=true;}); renderChat(false); } if(data.type==='presence') updatePresence(data.user_id,data.online); if(data.type==='order_updated'){ try{await loadRoom(false);}catch(e){toast(e.message,'error');} } if(data.type==='error')toast(data.detail||'Ошибка чата','error'); };
    ws.onclose=()=>{ if(state.ws===ws){ state.ws=null; state.reconnectTimer=setTimeout(connectWs,2500); } };
  }catch(e){ state.reconnectTimer=setTimeout(connectWs,4000); }
}

async function sendMessage(){ const input=document.getElementById('orderMessage'),text=input.value.trim(); if(!text||!state.room.permissions.can_message)return; if(state.ws&&state.ws.readyState===WebSocket.OPEN){state.ws.send(JSON.stringify({type:'message',message:text}));input.value='';resizeMessage();stopTyping();return;} try{const m=await api(`/order-room/${orderId}/messages`,json('POST',{message:text}));if(!state.messages.some(x=>x.id===m.id))state.messages.push(m);input.value='';resizeMessage();renderChat(false);}catch(e){toast(e.message,'error');} }
function resizeMessage(){ const el=document.getElementById('orderMessage'); el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,130)+'px'; }
function typing(){ if(!state.ws||state.ws.readyState!==WebSocket.OPEN)return; state.ws.send(JSON.stringify({type:'typing',typing:true})); clearTimeout(state.typingTimer); state.typingTimer=setTimeout(stopTyping,900); }
function stopTyping(){ clearTimeout(state.typingTimer); if(state.ws&&state.ws.readyState===WebSocket.OPEN)state.ws.send(JSON.stringify({type:'typing',typing:false})); }

async function uploadAttachment(file){
  if(!file)return; const fd=new FormData(); fd.append('file',file); const h=new Headers(); h.set('Authorization',`Bearer ${token()}`);
  try{ const r=await fetch(`/order-room/${orderId}/attachments`,{method:'POST',headers:h,body:fd}); let d=null;try{d=await r.json();}catch(_){} if(!r.ok)throw new Error(d?.detail||`HTTP ${r.status}`); toast('Изображение отправлено'); if(!state.ws||state.ws.readyState!==WebSocket.OPEN){state.messages.push(d);renderChat(false);} }catch(e){toast(e.message,'error');}
  document.getElementById('orderAttachment').value='';
}

async function doAction(action){
  try{
    if(action==='pay'){ await api(`/orders/${orderId}/pay`,{method:'POST'}); toast('Заказ оплачен'); await loadRoom(false); }
    if(action==='cancel'){ if(!confirm('Отменить неоплаченный заказ?'))return; await api(`/orders/${orderId}`,{method:'DELETE'}); toast('Заказ отменён'); await loadRoom(false); }
    if(action==='deliver') openModal('deliveryModal');
    if(action==='confirm'){ if(!confirm('Вы действительно получили и проверили товар? После подтверждения средства будут перечислены продавцу.'))return; await api(`/orders/${orderId}/confirm`,{method:'PUT'}); toast('Сделка завершена'); await loadRoom(false); setTimeout(()=>openModal('reviewModal'),350); }
    if(action==='dispute') openModal('disputeModal');
    if(action==='review') openModal('reviewModal');
    if(action.startsWith('resolve-')){const resolution=action.replace('resolve-','');if(!state.room.open_dispute)return;if(!confirm('Разрешить спор этим способом? Действие изменит распределение денег.'))return;await api(`/disputes/${state.room.open_dispute.id}/resolve`,json('PUT',{resolution}));toast('Спор разрешён');await loadRoom(false);}
  }catch(e){toast(e.message,'error');}
}

function openModal(id){ document.getElementById(id).style.display='flex'; }
function closeModal(el){ el.closest('.modal').style.display='none'; }

async function submitDelivery(){ const value=document.getElementById('deliveryInput').value.trim(); if(!value)return toast('Введите данные товара','error'); try{ await api(`/orders/${orderId}/deliver`,json('PUT',{delivery_info:value})); document.getElementById('deliveryModal').style.display='none'; document.getElementById('deliveryInput').value=''; toast('Товар передан покупателю'); await loadRoom(false); }catch(e){toast(e.message,'error');} }
async function submitDispute(){ const reason=document.getElementById('disputeReason').value,description=document.getElementById('disputeDescription').value.trim()||null; try{ await api('/disputes/',json('POST',{order_id:orderId,reason,description})); document.getElementById('disputeModal').style.display='none'; toast('Спор открыт. Средства остаются в резерве.'); await loadRoom(false); }catch(e){toast(e.message,'error');} }
async function submitReview(){ try{ await api('/profile/reviews',json('POST',{order_id:orderId,rating:state.reviewRating,comment:document.getElementById('reviewComment').value.trim()||null})); document.getElementById('reviewModal').style.display='none'; toast('Спасибо за отзыв'); await loadRoom(false); }catch(e){toast(e.message,'error');} }

function bind(){
  document.getElementById('dealActions').onclick=e=>{ const b=e.target.closest('[data-deal-action]'); if(b)doAction(b.dataset.dealAction); };
  document.getElementById('orderSend').onclick=sendMessage;
  document.getElementById('orderMessage').addEventListener('input',()=>{resizeMessage();typing();});
  document.getElementById('orderMessage').addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();} });
  document.getElementById('orderAttachment').onchange=e=>uploadAttachment(e.target.files?.[0]);
  document.getElementById('orderChatFeed').onclick=e=>{const img=e.target.closest('.order-attachment img');if(img?.src)window.open(img.src,'_blank','noopener');};
  document.getElementById('copyDelivery').onclick=async()=>{try{await navigator.clipboard.writeText(document.getElementById('deliveryContent').textContent);toast('Скопировано');}catch(_){toast('Не удалось скопировать','error');}};
  document.querySelectorAll('.modal .close').forEach(x=>x.onclick=()=>closeModal(x));
  window.addEventListener('click',e=>{if(e.target.classList.contains('modal'))e.target.style.display='none';});
  document.getElementById('submitDelivery').onclick=submitDelivery;
  document.getElementById('submitDispute').onclick=submitDispute;
  document.getElementById('submitReview').onclick=submitReview;
  document.getElementById('reviewStars').onclick=e=>{const b=e.target.closest('[data-rating]');if(!b)return;state.reviewRating=Number(b.dataset.rating);document.querySelectorAll('#reviewStars button').forEach(x=>x.classList.toggle('active',Number(x.dataset.rating)<=state.reviewRating));};
  document.querySelectorAll('#reviewStars button').forEach(x=>x.classList.toggle('active',Number(x.dataset.rating)<=state.reviewRating));
  window.addEventListener('beforeunload',()=>{if(state.ws)state.ws.close();});
}

bind();boot();
