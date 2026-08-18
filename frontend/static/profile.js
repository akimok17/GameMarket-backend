const API_URL='';
let currentProfile=null;
let verificationStatus=null;
let financeConfig=null;
let balanceState=null;
let sbpBanks=[];

function tok(){return localStorage.getItem('token')||'';}
function esc(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function rub(v){return new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(Number(v||0));}
function toast(m,t='success'){const w=document.getElementById('toastWrap'),e=document.createElement('div');e.className=`toast ${t}`;e.textContent=m;w.appendChild(e);setTimeout(()=>e.remove(),4500);}
async function api(path,opt={}){const h=new Headers(opt.headers||{});h.set('Authorization',`Bearer ${tok()}`);const r=await fetch(API_URL+path,{...opt,headers:h});let d=null;try{d=await r.json();}catch(_){}if(!r.ok){if(r.status===401){localStorage.removeItem('token');localStorage.removeItem('user');location.href='/login';}let x=d?.detail||`HTTP ${r.status}`;if(Array.isArray(x))x=x.map(i=>i.msg).join('; ');throw new Error(x);}return d;}
function json(method,body){return{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}}
function setStatus(id,ok,text){const e=document.getElementById(id);e.textContent=text;e.className=`status-pill ${ok?'ok':'warn'}`;}
function uuid(){return (crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(16).slice(2)}`).replace(/[^A-Za-z0-9_.:-]/g,'');}
function paymentStatus(s){return({pending:'Ожидает оплаты',succeeded:'Зачислено',canceled:'Отменено'})[s]||s;}
function withdrawalStatus(s){return({pending:'На проверке',processing:'Выполняется',succeeded:'Выплачено',canceled:'Отменено',rejected:'Отклонено',approved:'Выплачено'})[s]||s;}
function historyType(s){return({deposit:'Пополнение',dev_deposit:'Тестовое пополнение',payment:'Покупка',earning:'Доход от продажи',refund:'Возврат',withdrawal:'Вывод',withdrawal_hold:'Резерв на вывод',withdrawal_release:'Снятие резерва'})[s]||s;}

function renderVerification(v){
  verificationStatus=v;
  setStatus('emailStatus',v.email_verified,v.email_verified?'✓ Подтверждён':'Не подтверждён');
  setStatus('phoneStatus',v.phone_verified,v.phone_verified?'✓ Подтверждён':'Не подтверждён');
  document.getElementById('emailDestination').textContent=v.email||'Email не указан';
  document.getElementById('phoneDestination').textContent=v.phone||'Добавь телефон во вкладке «Информация».';

  const emailBtn=document.getElementById('requestEmailCode');
  const phoneBtn=document.getElementById('requestPhoneCode');
  emailBtn.disabled=v.email_verified||!v.email||!v.email_delivery_configured;
  phoneBtn.disabled=v.phone_verified||!v.phone||!v.sms_delivery_configured;
  emailBtn.title=!v.email_delivery_configured?'Отправка email временно не настроена':'';
  phoneBtn.title=!v.sms_delivery_configured?'SMS-провайдер временно не настроен':'';

  const accountOk=v.email_verified||v.phone_verified;
  document.getElementById('overallVerification').innerHTML=`<span class="status-pill ${accountOk?'ok':'warn'}">${accountOk?'✓ Контакты подтверждены':'Требуется подтверждение'}</span>`;
  document.getElementById('profileVerifyBadge').innerHTML=`<span class="status-pill ${accountOk?'ok':'warn'}">${accountOk?'✓ Подтверждён':'! Не подтверждён'}</span>`;

  const sellerText=v.seller_ready?'<span class="status-pill ok">✓ Можно продавать</span>':`<span class="status-pill warn">${esc(v.seller_requirement||'Нужно подтвердить контакты')}</span>`;
  const withdrawalText=v.withdrawal_ready?'<span class="status-pill ok">✓ Аккаунт готов к выводу</span>':`<span class="status-pill warn">${esc(v.withdrawal_requirement||'Нужно подтвердить контакты')}</span>`;
  document.getElementById('securitySummary').innerHTML=`<div class="status-wrap">${sellerText}${withdrawalText}</div>`;
  document.getElementById('verificationPolicyText').textContent=`Для продажи: ${v.seller_requirement}. Для вывода: ${v.withdrawal_requirement}.`;

  document.getElementById('emailDevCode').textContent=!v.email_delivery_configured?'Email-провайдер пока не настроен администратором.':'';
  document.getElementById('phoneDevCode').textContent=!v.sms_delivery_configured?'Чтобы получать реальные SMS, администратор должен настроить SMS.RU/Twilio или другой SMS-провайдер.':'';
}

function renderFinanceConfig(c){
  financeConfig=c;
  const dep=document.getElementById('openDeposit'),wd=document.getElementById('openWithdraw'),note=document.getElementById('paymentProviderNote');
  if(c.payment_configured){dep.disabled=false;dep.textContent='＋ Пополнить';note.textContent='Пополнение через ЮKassa';}
  else if(c.dev_deposit_available){dep.disabled=false;dep.textContent='＋ Пополнить (dev)';note.textContent='Реальный платёжный провайдер не настроен — доступен dev-режим';}
  else{dep.disabled=true;dep.textContent='Пополнение недоступно';note.textContent='Платёжный провайдер не настроен';}
  wd.disabled=!c.payout_configured||!c.withdrawal_methods?.length;
  if(c.payout_provider==='yookassa')wd.textContent='− Вывести по СБП';
}

function renderMoney(b){
  balanceState=b;
  document.getElementById('profileBalance').textContent=rub(b.balance);
  document.getElementById('profileFrozen').textContent=rub(b.frozen);
  document.getElementById('profileWithdrawable').textContent=rub(b.withdrawable_available);
}

function renderDeposits(items){
  const el=document.getElementById('depositsList');
  if(!items.length){el.innerHTML='<div class="empty-state">Пополнений пока нет</div>';return;}
  el.innerHTML=items.map(x=>`<div class="history-item"><span>#${x.id} · ${esc(paymentStatus(x.status))}${x.provider?' · '+esc(x.provider):''}</span><strong>${rub(x.amount)}</strong></div>`).join('');
}
function renderWithdrawals(items){
  const el=document.getElementById('withdrawalsList');
  if(!items.length){el.innerHTML='<div class="empty-state">Заявок на вывод нет</div>';return;}
  el.innerHTML=items.map(x=>`<div class="history-item withdrawal-row"><span>#${x.id} · ${esc(withdrawalStatus(x.status))}<small>${esc(x.wallet_type)} · ${esc(x.wallet_address||'')}</small></span><div class="history-trailing"><strong>${rub(x.amount)}</strong>${x.status==='processing'?`<button class="mini-action" data-sync-withdrawal="${x.id}">Обновить</button>`:''}</div></div>`).join('');
  el.querySelectorAll('[data-sync-withdrawal]').forEach(b=>b.onclick=async()=>{try{await api(`/balance/withdrawals/${b.dataset.syncWithdrawal}/sync`,{method:'POST'});await load();}catch(e){toast(e.message,'error');}});
}

async function load(){
  try{
    const[p,b,h,w,v,c,d]=await Promise.all([
      api('/profile/me'),api('/balance/me'),api('/balance/history'),api('/balance/withdrawals'),api('/verification/status'),api('/balance/config'),api('/balance/deposits')
    ]);
    currentProfile=p;
    document.getElementById('profileUsername').textContent=p.username;
    document.getElementById('profileBadge').textContent=p.is_seller?'Продавец':'Покупатель';
    document.getElementById('statRating').textContent=Number(p.rating||0).toFixed(1);
    document.getElementById('statSales').textContent=p.total_sales||0;
    document.getElementById('statOrders').textContent=p.total_orders||0;
    document.getElementById('editFullName').value=p.full_name||'';
    document.getElementById('editEmail').value=p.email||'';
    document.getElementById('editPhone').value=p.phone||'';
    renderMoney(b);renderVerification(v);renderFinanceConfig(c);renderDeposits(d);renderWithdrawals(w);
    const reviews=await api(`/profile/${p.id}/reviews`);
    document.getElementById('reviewsList').innerHTML=reviews.length?reviews.map(x=>`<div class="review-item"><div class="review-rating">${'⭐'.repeat(x.rating)}</div><div class="review-comment">${esc(x.comment||'Без комментария')}</div><div class="review-date">Заказ #${x.order_id}</div></div>`).join(''):'<div class="empty-state">Отзывов пока нет</div>';
    document.getElementById('historyList').innerHTML=h.length?h.map(x=>`<div class="history-item ${Number(x.amount)>=0?'positive':'negative'}"><span>${esc(x.description||historyType(x.type))}<small>${esc(historyType(x.type))}</small></span><strong>${rub(x.amount)}</strong></div>`).join(''):'<div class="empty-state">История пуста</div>';
  }catch(e){toast(e.message,'error');}
}

async function requestCode(channel){
  const btn=document.getElementById(channel==='email'?'requestEmailCode':'requestPhoneCode');
  const original=channel==='email'?'Получить код':'Получить SMS-код';
  try{
    btn.disabled=true;
    const d=await api('/verification/request',json('POST',{channel}));
    if(d.verified){toast(channel==='email'?'Email уже подтверждён':'Телефон уже подтверждён');await load();return;}
    toast(`Код отправлен: ${d.destination}`);
    const box=document.getElementById(channel==='email'?'emailDevCode':'phoneDevCode');
    box.textContent=d.dev_code?`DEV-код: ${d.dev_code}`:`Код отправлен. Проверь ${channel==='email'?'почту':'SMS'}.`;
    let left=Number(d.resend_after_seconds||60);
    btn.textContent=`Повторно через ${left}с`;
    const timer=setInterval(()=>{left--;btn.textContent=left>0?`Повторно через ${left}с`:original;if(left<=0){clearInterval(timer);btn.disabled=false;}},1000);
  }catch(e){btn.disabled=false;btn.textContent=original;toast(e.message,'error');}
}
async function confirmCode(channel){
  const input=document.getElementById(channel==='email'?'emailCode':'phoneCode'),code=input.value.trim();
  if(!/^\d{6}$/.test(code)){toast('Введи 6 цифр','error');return;}
  try{await api('/verification/confirm',json('POST',{channel,code}));toast(channel==='email'?'Email подтверждён':'Телефон подтверждён');input.value='';await load();}catch(e){toast(e.message,'error');}
}

async function openDeposit(){
  if(!financeConfig)return;
  const note=document.getElementById('depositNote'),submit=document.getElementById('depositSubmit'),amount=document.getElementById('depositAmount');
  amount.min=financeConfig.deposit_min||1;amount.max=financeConfig.deposit_max||150000;
  if(financeConfig.payment_configured){note.textContent=`Оплата проходит на защищённой странице ЮKassa. После подтверждения провайдером баланс пополнится автоматически. Сумма: ${financeConfig.deposit_min}–${financeConfig.deposit_max} ₽.`;submit.textContent='Перейти к оплате';}
  else if(financeConfig.dev_deposit_available){note.textContent='Тестовое пополнение для локальной разработки. Реальные деньги не списываются.';submit.textContent='Пополнить (dev)';}
  else{toast('Пополнение сейчас недоступно','error');return;}
  document.getElementById('depositModal').style.display='flex';
}

async function openWithdraw(){
  if(!financeConfig?.payout_configured){toast('Вывод пока не настроен','error');return;}
  const amount=document.getElementById('withdrawAmount');amount.min=financeConfig.withdrawal_min||1;amount.max=financeConfig.withdrawal_max||100000;
  document.getElementById('sbpFields').style.display='none';document.getElementById('manualFields').style.display='none';
  if(financeConfig.payout_provider==='yookassa'){
    if(!verificationStatus?.phone_verified||!currentProfile?.phone){toast('Сначала добавь и подтверди номер телефона во вкладке «Безопасность»','error');document.querySelector('[data-tab="security"]')?.click();return;}
    document.getElementById('sbpFields').style.display='block';document.getElementById('withdrawPhone').value=currentProfile.phone;
    document.getElementById('withdrawNote').textContent=`Автоматический вывод через СБП на подтверждённый номер. Доступно к выводу: ${rub(balanceState?.withdrawable_available)}.`;
    try{
      if(!sbpBanks.length)sbpBanks=await api('/balance/sbp-banks');
      const sel=document.getElementById('withdrawBank');sel.innerHTML='<option value="">Выберите банк</option>'+sbpBanks.map(x=>`<option value="${esc(x.bank_id)}">${esc(x.name)}</option>`).join('');
    }catch(e){toast(e.message,'error');return;}
  }else{
    document.getElementById('manualFields').style.display='block';
    document.getElementById('withdrawNote').textContent=`Заявка будет проверена администратором. Доступно к выводу: ${rub(balanceState?.withdrawable_available)}.`;
  }
  document.getElementById('withdrawModal').style.display='flex';
}

async function handlePaymentReturn(){
  const params=new URLSearchParams(location.search);
  const depositId=params.get('deposit_id')||sessionStorage.getItem('lastDepositId');
  if(params.get('payment_return')!=='1'&&!depositId)return;
  if(depositId){
    try{const d=await api(`/balance/deposits/${encodeURIComponent(depositId)}/sync`,{method:'POST'});toast(d.status==='succeeded'?'Оплата подтверждена, баланс пополнен':d.status==='canceled'?'Платёж отменён':'Платёж ещё обрабатывается',d.status==='canceled'?'error':'success');}catch(e){toast(e.message,'error');}
  }
  sessionStorage.removeItem('lastDepositId');
  history.replaceState({},'',location.pathname+location.hash);
  await load();
}

document.getElementById('logoutProfile').onclick=()=>{localStorage.removeItem('token');localStorage.removeItem('user');location.href='/';};
document.querySelectorAll('.tab-btn').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab-btn').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.tab-content').forEach(x=>x.classList.toggle('active',x.id===`tab-${b.dataset.tab}`));b.scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'});});
document.getElementById('profileForm').onsubmit=async e=>{e.preventDefault();try{await api('/profile/me',json('PUT',{full_name:document.getElementById('editFullName').value.trim()||null,email:document.getElementById('editEmail').value.trim(),phone:document.getElementById('editPhone').value.trim()||null}));toast('Профиль сохранён. Изменённый контакт нужно подтвердить заново.');await load();}catch(x){toast(x.message,'error');}};
document.getElementById('requestEmailCode').onclick=()=>requestCode('email');document.getElementById('requestPhoneCode').onclick=()=>requestCode('phone');document.getElementById('confirmEmailCode').onclick=()=>confirmCode('email');document.getElementById('confirmPhoneCode').onclick=()=>confirmCode('phone');
document.getElementById('passwordForm').onsubmit=async e=>{e.preventDefault();try{await api('/users/me/password',json('PUT',{current_password:document.getElementById('currentPassword').value,new_password:document.getElementById('newPassword').value}));e.currentTarget.reset();toast('Пароль изменён. Войди заново.');localStorage.removeItem('token');localStorage.removeItem('user');setTimeout(()=>location.href='/login',900);}catch(x){toast(x.message,'error');}};
document.getElementById('openDeposit').onclick=openDeposit;document.getElementById('openWithdraw').onclick=openWithdraw;document.querySelectorAll('.modal .close').forEach(x=>x.onclick=()=>x.closest('.modal').style.display='none');window.onclick=e=>{if(e.target.classList.contains('modal'))e.target.style.display='none';};

document.getElementById('depositForm').onsubmit=async e=>{e.preventDefault();const amount=document.getElementById('depositAmount').value;const submit=document.getElementById('depositSubmit');try{submit.disabled=true;if(financeConfig.payment_configured){const d=await api('/balance/deposit',json('POST',{amount,idempotency_key:uuid()}));if(!d.confirmation_url)throw new Error('Провайдер не вернул ссылку на оплату');sessionStorage.setItem('lastDepositId',String(d.id));location.href=d.confirmation_url;return;}await api(`/balance/dev-deposit?amount=${encodeURIComponent(amount)}`,{method:'POST'});document.getElementById('depositModal').style.display='none';toast('Тестовый баланс пополнен');await load();}catch(x){toast(x.message,'error');}finally{submit.disabled=false;}};

document.getElementById('withdrawForm').onsubmit=async e=>{e.preventDefault();const submit=document.getElementById('withdrawSubmit');try{submit.disabled=true;let body={amount:document.getElementById('withdrawAmount').value};if(financeConfig.payout_provider==='yookassa'){const bank=document.getElementById('withdrawBank').value;if(!bank)throw new Error('Выберите банк СБП');body={...body,wallet_type:'sbp',wallet_address:currentProfile.phone,bank_id:bank};}else{body={...body,wallet_type:document.getElementById('walletType').value,wallet_address:document.getElementById('walletAddress').value.trim()};if(!body.wallet_address)throw new Error('Укажите реквизиты');}await api('/balance/withdraw',json('POST',body));document.getElementById('withdrawModal').style.display='none';toast('Заявка на вывод создана');await load();}catch(x){toast(x.message,'error');}finally{submit.disabled=false;}};

if(location.hash==='#security'){document.querySelector('[data-tab="security"]')?.click();}
if(!tok())location.href='/login';else load().then(handlePaymentReturn);
