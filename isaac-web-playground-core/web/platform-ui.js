const $=id=>document.getElementById(id)
let latest=null,refreshing=false
async function api(path,data) {
  const response=await fetch('/platform/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(10000)})
  const result=await response.json()
  if(!response.ok)throw Error(result.error||'连接失败')
  return result
}
function notice(text=''){$('notice').textContent=text}
async function run(action){try{notice();await action()}catch(error){notice(error.message)}}
$('teacherForm').onsubmit=event=>{event.preventDefault();run(async()=>{await api('login',{password:$('password').value});$('password').value='';await boot()})}
$('pairForm').onsubmit=event=>{event.preventDefault();run(async()=>{await api('pair',{code:$('code').value});location.href='/'})}
for(const [id,role] of [['browserCode','operator'],['deviceCode','device']])$(id).onclick=()=>run(async()=>{
  const result=await api('codes',{stationId:$('stations').value,role})
  $('pairResult').replaceChildren(document.createTextNode(`${role==='device'?'采集器':'浏览器'}配对码（5 分钟内使用一次）：`))
  const code=document.createElement('code');code.textContent=result.code;$('pairResult').append(code)
})
$('openGame').onclick=()=>run(async()=>{await api('select',{stationId:$('stations').value});location.href='/'})
$('logout').onclick=()=>run(async()=>{await api('logout',{});location.href='/login'})
$('refresh').onclick=()=>run(refresh)
$('export').onclick=()=>run(async()=>{
  await refresh();const url=URL.createObjectURL(new Blob([JSON.stringify(latest,null,2)],{type:'application/json'}))
  const a=document.createElement('a');a.href=url;a.download='isaac-diagnostics-'+Date.now()+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
})
function metric(parent,label,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;parent.append(dt,dd)}
async function refresh(){
  if(refreshing)return;refreshing=true
  try {
    latest=await api('diagnostics');$('diagnostics').replaceChildren();$('clients').replaceChildren();$('arms').replaceChildren()
    for(const station of latest.stations){
      const card=document.createElement('article'),title=document.createElement('h3'),list=document.createElement('dl');title.textContent=station.name+' · '+station.id;card.append(title,list)
      metric(list,'仿真',station.status.bridge?.result?.session?.status||(station.status.error?'连接失败，请查看实例日志':'未就绪'))
      const device=station.device
      metric(list,'机械臂采集',device?`${device.metadata?.armId||'识别中'} · ${device.metadata?.driver||''} · 最近数据 ${device.lastSampleAgeMs??'尚无'} ms 前`:'未连接')
      metric(list,'控制传输',device?`确认耗时 ${device.ackMs} ms · 已应用 ${device.samples} · 丢弃旧数据 ${device.dropped}`:'未开始')
      metric(list,'跟随',station.teleop.teleop?.engaged?`${station.teleop.teleop.rate_hz} Hz${station.teleop.teleop.holding?' · 等待新数据':''}`:'未接管')
      const reports=latest.reports.filter(r=>r.stationId===station.id)
      metric(list,'浏览器视频',reports.length?reports.map(r=>`${r.clientId.slice(0,8)}：${r.width||0}×${r.height||0} · ${r.fps??'—'} FPS · ${r.mbps??'—'} Mbps${r.stale?' · 数据已过期':''}${r.lastPresentedAgeMs>3000&&r.visible?' · 画面停止更新':''}${r.visible?'':' · 页面在后台'}`).join('\n'):'暂无客户端上报')
      const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='实例与队列详情';pre.textContent=JSON.stringify(station,null,2);details.append(summary,pre);card.append(details);$('diagnostics').append(card)
    }
    for(const arm of latest.arms||[]){
      const row=document.createElement('article'),title=document.createElement('h4'),detail=document.createElement('pre');title.textContent=arm.armId+' · '+arm.driver;detail.textContent='当前校准 SHA-256：'+arm.calibrationHash;row.append(title,detail)
      if(arm.pending){const pending=document.createElement('pre');pending.textContent='待确认校准 SHA-256：'+arm.pending.calibrationHash;row.append(pending)
        const approve=document.createElement('button');approve.textContent='已核对设备与文件，使用新校准';approve.onclick=()=>run(async()=>{await api('arms/approve',{armId:arm.armId,calibrationHash:arm.pending.calibrationHash});await refresh()});row.append(approve)}
      $('arms').append(row)
    }
    for(const client of latest.clients.filter(c=>c.role!=='teacher')){
      const row=document.createElement('p');row.textContent=`${client.stationId} · ${client.role==='device'?'采集器':'体验浏览器'} · ${client.label||client.id.slice(0,8)} `
      const button=document.createElement('button');button.className='secondary';button.textContent='解除配对';button.onclick=()=>run(async()=>{await api('revoke',{id:client.id});await refresh()});row.append(button);$('clients').append(row)
    }
  } finally{refreshing=false}
}
async function boot(){
  try {
    const me=await api('me')
    if(me.principal.role!=='teacher'){location.href='/';return}
    $('login').hidden=true;$('manage').hidden=false;$('stations').replaceChildren()
    for(const station of me.stations){const option=document.createElement('option');option.value=station.id;option.textContent=station.name;$('stations').append(option)}
    await refresh()
  }catch{$('login').hidden=false;$('manage').hidden=true}
}
setInterval(()=>{if(!$('manage').hidden&&!document.hidden)run(refresh)},5000)
boot()

api('config').then(config=>{
  $('connectorHelp').textContent=config.localConnectorEnabled
    ? '机械臂插在另一台电脑时，在那台电脑打开连接工具，选择该臂的配置文件并点击连接。同一 WLAN 子网内免采集器配对码；体验浏览器仍单独配对。'
    : '机械臂插在另一台电脑时，在那台电脑运行连接工具，选择该臂的配置文件，并输入单独的采集器配对码。'
  if(config.localConnectorEnabled)$('deviceCode').textContent='生成采集器配对码（其他网络）'
}).catch(()=>{})
