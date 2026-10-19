'use strict';

const $ = (id) => document.getElementById(id);
const state = { user: null, units: [], unitId: null, roomId: null, rooms: [], catalog: [], sources: [], sensors: [], summary: null };
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const money = (v) => Number(v).toLocaleString('pt-BR', {style:'currency',currency:'BRL'});
const fmt = (v, n=2) => Number(v).toLocaleString('pt-BR',{minimumFractionDigits:n,maximumFractionDigits:n});
const formObject = (form) => Object.fromEntries(new FormData(form).entries());
function flash(message, error=false) { $('flash').textContent=message; $('flash').className=error?'error':''; window.scrollTo({top:0,behavior:'smooth'}); }
async function api(url, method='GET', body=undefined, extraHeaders={}) {
  const options = {method,credentials:'same-origin',headers:{...extraHeaders}};
  if (body !== undefined) { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(body); }
  const response = await fetch(url, options);
  const payload = await response.json().catch(()=>({}));
  if (!response.ok) throw new Error(payload.erro || `Erro HTTP ${response.status}`);
  return payload;
}
async function attempt(fn) { try { await fn(); } catch(e) { console.error(e); flash(e.message,true); } }
function showAuth() {
  $('dashboardView').classList.add('hidden'); $('authView').classList.remove('hidden');
  $('logoutBtn').classList.add('hidden'); $('headerUser').textContent='';
}
function showDashboard() {
  $('authView').classList.add('hidden'); $('dashboardView').classList.remove('hidden');
  $('headerUser').textContent=state.user.nome; $('logoutBtn').classList.remove('hidden');
}
function changeAuthTab(signup) {
  $('loginForm').classList.toggle('hidden',signup); $('signupForm').classList.toggle('hidden',!signup);
  $('signupTab').classList.toggle('active',signup); $('loginTab').classList.toggle('active',!signup);
  $('flash').textContent='';
}
$('loginTab').addEventListener('click',()=>changeAuthTab(false));
$('signupTab').addEventListener('click',()=>changeAuthTab(true));
$('loginForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  const p=await api('/api/auth/login','POST',formObject(e.target)); state.user=p;
  showDashboard(); await loadUnits(); flash('Acesso realizado com sucesso.');
});});
$('signupForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  const p=await api('/api/auth/cadastro','POST',formObject(e.target)); state.user=p;
  showDashboard(); await loadUnits(); flash('Conta criada! Cadastre sua primeira unidade.');
});});
$('logoutBtn').addEventListener('click',()=>attempt(async()=>{
  await api('/api/auth/sair','POST',{}); Object.assign(state,{user:null,units:[],unitId:null,roomId:null});
  showAuth(); flash('Você saiu da conta.');
}));
async function loadStates() {
  const states=await api('/api/estados');
  $('stateSelect').innerHTML=states.map(s=>`<option value="${s.id}" ${s.sigla==='SP'?'selected':''}>${esc(s.nome)} (${esc(s.sigla)})</option>`).join('');
}
function toggleUnitForm(show) {$('unitForm').classList.toggle('hidden',!show);}
$('newUnitBtn').addEventListener('click',()=>toggleUnitForm(true));
$('cancelUnitBtn').addEventListener('click',()=>toggleUnitForm(false));
$('unitForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  const p=await api('/api/unidades','POST',formObject(e.target));
  e.target.reset(); toggleUnitForm(false); state.unitId=p.id; state.roomId=null;
  await loadUnits(); flash('Unidade cadastrada com sucesso.');
});});
$('unitSelect').addEventListener('change',e=>attempt(async()=>{
  state.unitId=Number(e.target.value)||null; state.roomId=null; await loadUnitData();
}));
async function loadUnits() {
  state.units=await api('/api/unidades');
  $('unitSelect').innerHTML=state.units.map(u=>`<option value="${u.id}">${esc(u.nome)}</option>`).join('');
  if(!state.units.length) {
    state.unitId=null; $('unitContent').classList.add('hidden'); toggleUnitForm(true);
    $('unitSelect').disabled=true; return;
  }
  $('unitSelect').disabled=false;
  if (!state.units.some(u=>u.id===state.unitId)) state.unitId=state.units[0].id;
  $('unitSelect').value=String(state.unitId);
  await loadUnitData();
}
async function loadUnitData() {
  if (!state.unitId) return;
  const id=state.unitId;
  const [rooms,summary,sources,sensors,catalog]=await Promise.all([
    api(`/api/unidades/${id}/comodos`),api(`/api/unidades/${id}/resumo`),
    api(`/api/unidades/${id}/renovaveis`),api(`/api/unidades/${id}/sensores`),api('/api/catalogo')
  ]);
  if (state.unitId!==id) return;
  Object.assign(state,{rooms,summary,sources,sensors,catalog});
  if(!rooms.some(r=>r.id===state.roomId)) state.roomId=rooms[0]?.id??null;
  $('unitContent').classList.remove('hidden'); renderMetrics(); renderGoal(); renderRooms();
  renderSources(); renderSensors(); renderAlerts(); renderChart();
  await renderRoomDetails();
}
function renderMetrics() {
  const s=state.summary;
  const cards=[['⚡','Consumo bruto',`${fmt(s.totalKwh,3)} kWh`,'Neste mês'],
    ['☀','Geração renovável',`${fmt(s.renovavelKwh,3)} kWh`,'Neste mês'],
    ['💰','Custo líquido estimado',money(s.custoEstimado),`Tarifa ${money(s.tarifa)}/kWh`],
    ['📈','Projeção mensal',`${fmt(s.previsaoMesKwh)} kWh`,'Extrapolação simples']];
  $('metricCards').innerHTML=cards.map(x=>`<div class="metric"><div class="icon">${x[0]}</div><p>${x[1]}</p><strong>${x[2]}</strong><small>${esc(x[3])}</small></div>`).join('');
}
function renderGoal() {
  const s=state.summary;
  $('goalInfo').textContent=s.meta?`Meta: ${fmt(s.meta.limite)} kWh · Aviso a partir de ${fmt(s.meta.aviso)} kWh · Atual: ${fmt(s.totalKwh)} kWh`:'Nenhuma meta definida para este mês.';
  $('goalForm').elements.limite.value=s.meta?.limite??'';
}
$('goalForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  await api(`/api/unidades/${state.unitId}/meta`,'POST',formObject(e.target));
  await loadUnitData(); flash('Meta salva. O alerta será emitido aos 80% do limite.');
});});
function renderRooms() {
  $('roomTabs').innerHTML=state.rooms.length?state.rooms.map(r=>`<button type="button" role="tab" aria-selected="${r.id===state.roomId}" class="room-tab ${r.id===state.roomId?'active':''}" data-id="${r.id}">${esc(r.nome)}</button>`).join(''):'<p class="empty">Cadastre seu primeiro cômodo para adicionar aparelhos.</p>';
}
$('roomTabs').addEventListener('click',e=>{
  const b=e.target.closest('button[data-id]'); if(!b)return;
  state.roomId=Number(b.dataset.id);renderRooms();attempt(renderRoomDetails);
});
$('roomForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  const p=await api(`/api/unidades/${state.unitId}/comodos`,'POST',formObject(e.target));
  e.target.reset();state.roomId=p.id;await loadUnitData();flash('Cômodo criado.');
});});
async function renderRoomDetails() {
  const id=state.roomId;
  if(!id){$('roomPanel').innerHTML='<p class="empty">Sem cômodo selecionado.</p>';return;}
  const room=state.rooms.find(r=>r.id===id);if(!room)return;
  const devices=await api(`/api/comodos/${id}/aparelhos`);
  if(state.roomId!==id)return;
  const stats=state.summary.comodos.find(r=>r.id===id);
  const options=state.catalog.map(d=>`<option value="${d.id}" data-power="${d.potencia}">${esc(d.nome)} (${d.potencia} W)</option>`).join('');
  $('roomPanel').innerHTML=`<div class="room-head"><div><h3>${esc(room.nome)}</h3><span class="muted small">${fmt(stats?.kwh??0,3)} kWh • ${money(stats?.custo??0)} • <span class="pill">${stats?.origem==='IOT'?'Leituras IoT':'Simulação'}</span></span></div><button type="button" class="btn danger" data-delete-room="${id}">Excluir cômodo</button></div>
  <form id="applianceForm" class="appliance-form"><select id="applianceType" name="tipoId" required>${options}</select><input id="appliancePower" name="potencia" type="number" min="1" max="30000" placeholder="Potência W" required><input name="nome" placeholder="Nome personalizado (opcional)" maxlength="100"><button class="btn outline">+ Adicionar aparelho</button></form>
  <div>${devices.length?devices.map(d=>`<div class="device"><div><strong>${esc(d.nome)}</strong><small>${esc(d.tipo)} · ${d.potencia} W</small></div><div class="device-actions"><input type="number" min="1" max="43200" value="60" aria-label="Minutos simulados" data-minutes="${d.id}"><button type="button" class="btn outline" data-simulate="${d.id}">Simular uso</button><button type="button" class="btn danger" aria-label="Excluir ${esc(d.nome)}" data-delete-device="${d.id}">×</button></div></div>`).join(''):'<p class="empty">Nenhum aparelho cadastrado neste cômodo.</p>'}</div>`;
  setReferencePower();
}
function setReferencePower(){const s=$('applianceType');if(s&&s.selectedOptions.length)$('appliancePower').value=s.selectedOptions[0].dataset.power;}
$('roomPanel').addEventListener('change',e=>{if(e.target.id==='applianceType')setReferencePower();});
$('roomPanel').addEventListener('submit',e=>{if(e.target.id!=='applianceForm')return;e.preventDefault();attempt(async()=>{
  await api(`/api/comodos/${state.roomId}/aparelhos`,'POST',formObject(e.target));
  await loadUnitData();flash('Aparelho adicionado.');
});});
$('roomPanel').addEventListener('click',e=>attempt(async()=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.simulate) {
    const id=Number(b.dataset.simulate), mins=$('roomPanel').querySelector(`[data-minutes="${id}"]`).value;
    const p=await api(`/api/aparelhos/${id}/simular`,'POST',{minutos:mins});
    await loadUnitData();flash(`Uso registrado: ${fmt(p.energiaKwh,3)} kWh simulados.`);
  } else if(b.dataset.deleteDevice) {
    if(!confirm('Excluir o aparelho e TODO o seu histórico?'))return;
    await api(`/api/aparelhos/${b.dataset.deleteDevice}`,'DELETE');await loadUnitData();flash('Aparelho excluído.');
  } else if(b.dataset.deleteRoom) {
    if(!confirm('Excluir o cômodo, aparelhos, sensores e TODO o histórico correspondente?'))return;
    await api(`/api/comodos/${b.dataset.deleteRoom}`,'DELETE');state.roomId=null;
    await loadUnitData();flash('Cômodo excluído.');
  }
}));
function renderAlerts() {
  $('alertsList').innerHTML=state.summary.alertas.length?state.summary.alertas.map(a=>`<div class="alert"><strong>${esc(a.tipo.replaceAll('_',' '))}</strong><div>${esc(a.mensagem)}</div><small>${esc(a.data.slice(0,16).replace('T',' '))}</small></div>`).join(''):'<p class="empty">Tudo tranquilo! Nenhum alerta registrado.</p>';
}
function renderChart() {
  const serie=state.summary.serie;
  if(!serie.length){$('usageChart').innerHTML='<p class="empty">Registre o uso de um aparelho ou envie leituras IoT para visualizar o gráfico.</p>';return;}
  const max=Math.max(...serie.map(d=>Number(d.kwh)),0.001);
  $('usageChart').innerHTML=serie.map(d=>`<div class="chart-col" title="${esc(d.dia)}: ${fmt(d.kwh,3)} kWh"><small>${fmt(d.kwh,1)}</small><div class="chart-bar" style="height:${Math.max(3,Math.round(Number(d.kwh)/max*160))}px"></div><span>${esc(d.dia.slice(8))}</span></div>`).join('');
}
$('forecastBtn').addEventListener('click',()=>attempt(async()=>{
  const p=await api(`/api/unidades/${state.unitId}/previsoes`,'POST',{});
  flash(`Previsão de ${fmt(p.previsaoMesKwh)} kWh registrada no banco para ${p.dataPrevisao}.`);
}));
function renderSources() {
  $('sourceList').innerHTML=state.sources.length?state.sources.map(s=>`<div class="source"><strong>☀ ${esc(s.nome)}</strong><small class="muted">${esc(s.tipo)} · registre a geração em kWh</small><form data-source="${s.id}"><input name="energiaKwh" type="number" min="0.001" max="1000000" step="0.001" placeholder="kWh gerados" required><button class="btn outline">Registrar</button></form></div>`).join(''):'<p class="empty">Ainda não há fontes cadastradas.</p>';
}
$('sourceForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  await api(`/api/unidades/${state.unitId}/renovaveis`,'POST',formObject(e.target));
  e.target.reset();await loadUnitData();flash('Fonte renovável cadastrada.');
});});
$('sourceList').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  const sourceId=e.target.dataset.source;
  await api(`/api/renovaveis/${sourceId}/geracao`,'POST',formObject(e.target));
  await loadUnitData();flash('Geração registrada com sucesso.');
});});
function renderSensors() {
  $('sensorRoom').innerHTML=state.rooms.map(r=>`<option value="${r.id}">${esc(r.nome)}</option>`).join('');
  $('sensorList').innerHTML=state.sensors.length?state.sensors.map(s=>`<div class="sensor-line">📡 Sensor #${s.id} · ${esc(s.nome)} (${esc(s.comodo)})</div>`).join(''):'<p class="empty">Nenhum sensor cadastrado. Use a simulação dos aparelhos sem hardware.</p>';
}
$('sensorForm').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{
  const secret=await api(`/api/unidades/${state.unitId}/sensores`,'POST',formObject(e.target));
  e.target.reset();await loadUnitData();
  $('sensorSecret').classList.remove('hidden');
  $('sensorSecret').innerHTML=`<strong>Chave do sensor #${secret.id} (visível apenas agora):</strong> <code>${esc(secret.chave)}</code><p class="small">Guarde essa chave e envie no cabeçalho X-Sensor-Key para POST /api/iot/leituras. Consulte o guia de instalação.</p>`;
  flash('Sensor criado. Copie a chave exibida na seção IoT.');
});});
// Atualiza o painel quando chegarem novas leituras IoT (a cada 30 segundos).
setInterval(async()=>{
  if(!state.unitId || !state.user || document.visibilityState!=='visible')return;
  try {
    const id=state.unitId; const fresh=await api(`/api/unidades/${id}/resumo`);
    if(state.unitId!==id)return; state.summary=fresh;
    renderMetrics(); renderAlerts(); renderChart();
  } catch(err) {console.warn('Atualização automática indisponível:',err.message);}
},30000);

(async function init() {
  await attempt(async()=>{
    await loadStates();
    try {state.user=await api('/api/auth/eu');showDashboard();await loadUnits();}
    catch(e) { if (e.message==='Faça login para continuar.')showAuth();else throw e; }
  });
})();
