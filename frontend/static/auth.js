const API_URL = '';

function showMessage(message, error = false) {
  let box = document.getElementById('authMessage');
  if (!box) {
    box = document.createElement('div');
    box.id = 'authMessage';
    box.style.cssText = 'margin:12px 0;padding:12px;border-radius:10px;background:rgba(124,92,252,.12);color:#d8daea;font-size:14px';
    document.querySelector('.auth-form')?.prepend(box);
  }
  box.style.border = error ? '1px solid rgba(255,90,90,.35)' : '1px solid rgba(40,220,130,.35)';
  box.textContent = message;
}

async function request(path, options = {}) {
  const res = await fetch(API_URL + path, options);
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    let detail = data?.detail || `HTTP ${res.status}`;
    if (Array.isArray(detail)) detail = detail.map(x => x.msg).join('; ');
    throw new Error(detail);
  }
  return data;
}

if (localStorage.getItem('token') && (location.pathname === '/login' || location.pathname === '/register')) {
  request('/users/me', {headers:{Authorization:`Bearer ${localStorage.getItem('token')}`}})
    .then(() => location.href = '/')
    .catch(() => { localStorage.removeItem('token'); localStorage.removeItem('user'); });
}

document.getElementById('registerForm')?.addEventListener('submit', async e => {
  e.preventDefault();
  const button = e.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    await request('/users/register', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        username: document.getElementById('regUsername').value.trim(),
        email: document.getElementById('regEmail').value.trim(),
        password: document.getElementById('regPassword').value,
        full_name: document.getElementById('regFullName').value.trim() || null,
        phone: document.getElementById('regPhone').value.trim() || null,
      })
    });
    showMessage('Регистрация успешна. Сейчас можно войти.');
    setTimeout(() => location.href = '/login', 700);
  } catch (err) { showMessage(err.message, true); }
  finally { button.disabled = false; }
});

document.getElementById('loginForm')?.addEventListener('submit', async e => {
  e.preventDefault();
  const button = e.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    const data = await request('/users/login', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        username: document.getElementById('loginUsername').value.trim(),
        password: document.getElementById('loginPassword').value,
      })
    });
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('user', JSON.stringify(data.user));
    location.href = '/';
  } catch (err) { showMessage(err.message, true); }
  finally { button.disabled = false; }
});


async function loadResetConfig(){
  const channel=document.getElementById('resetChannel');
  if(!channel) return;
  try{
    const cfg=await request('/verification/public-config');
    const emailOption=channel.querySelector('option[value="email"]');
    const phoneOption=channel.querySelector('option[value="phone"]');
    const enabled=new Set(cfg.password_reset_channels||[]);
    if(emailOption) emailOption.disabled=!enabled.has('email')||!cfg.email_delivery_configured;
    if(phoneOption) phoneOption.disabled=!enabled.has('phone')||!cfg.sms_delivery_configured;
    if(channel.selectedOptions[0]?.disabled){
      const first=[...channel.options].find(x=>!x.disabled); if(first) channel.value=first.value;
    }
    const notice=document.getElementById('resetConfigNotice');
    if(notice){
      const parts=[];
      if(enabled.has('email')&&cfg.email_delivery_configured) parts.push('email');
      if(enabled.has('phone')&&cfg.sms_delivery_configured) parts.push('SMS');
      notice.textContent=parts.length?`Код можно получить через ${parts.join(' или ')}.`:'Восстановление пароля временно недоступно.';
    }
    updateResetChannel();
  }catch(_){ updateResetChannel(); }
}
function updateResetChannel(){
  const channel=document.getElementById('resetChannel');
  const input=document.getElementById('resetIdentifier');
  const label=document.getElementById('resetIdentifierLabel');
  if(!channel||!input||!label)return;
  if(channel.value==='phone'){
    label.textContent='Телефон'; input.placeholder='+79991234567'; input.type='tel'; input.autocomplete='tel';
  }else{
    label.textContent='Email'; input.placeholder='name@example.com'; input.type='email'; input.autocomplete='email';
  }
}
document.getElementById('resetChannel')?.addEventListener('change',updateResetChannel);

document.getElementById('resetRequestForm')?.addEventListener('submit', async e => {
  e.preventDefault();
  const button=e.currentTarget.querySelector('button'); button.disabled=true;
  try {
    const identifier=document.getElementById('resetIdentifier').value.trim();
    const channel=document.getElementById('resetChannel').value;
    const data=await request('/users/password-reset/request',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identifier,channel})});
    showMessage(channel==='email'?'Если аккаунт существует, код отправлен на указанную почту.':'Если аккаунт существует, код отправлен SMS на указанный телефон.');
    const dev=document.getElementById('resetDevCode'); if(dev) dev.textContent=data.dev_code?`DEV-код: ${data.dev_code}`:'';
    let left=Number(data.resend_after_seconds||60),label=button.textContent;
    const timer=setInterval(()=>{left--;button.textContent=left>0?`Повторно через ${left}с`:label;if(left<=0){clearInterval(timer);button.disabled=false;}},1000);
  } catch(err){ showMessage(err.message,true); button.disabled=false; }
});

document.getElementById('resetConfirmForm')?.addEventListener('submit', async e => {
  e.preventDefault(); const button=e.currentTarget.querySelector('button'); button.disabled=true;
  try {
    await request('/users/password-reset/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      identifier:document.getElementById('resetIdentifier').value.trim(),
      channel:document.getElementById('resetChannel').value,
      code:document.getElementById('resetCode').value.trim(),
      new_password:document.getElementById('resetNewPassword').value
    })});
    showMessage('Пароль изменён. Все старые сессии отозваны.'); setTimeout(()=>location.href='/login',900);
  } catch(err){ showMessage(err.message,true); } finally { button.disabled=false; }
});

loadResetConfig();
