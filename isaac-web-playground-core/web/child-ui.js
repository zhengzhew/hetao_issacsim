// Presentation and guided interaction only; simulation operations remain in app.js.
import { voiceGuides } from './voice-guides.js'
export const sceneNames = {warehouse:'小小仓库','warehouse-multi':'货架迷宫','simple-room':'温馨小屋',grid:'自由练习场'}
export const sceneNotes = {warehouse:'穿过通道，看看仓库里的世界。','warehouse-multi':'好多条路，试着慢慢探索吧。','simple-room':'换个角度，发现房间的小细节。',grid:'宽宽的空地，适合第一次出发。'}
export function sceneLabel(scene) { return sceneNames[scene?.id] || scene?.name || '我的世界' }

export function picture(kind, id) {
  const palette = {warehouse:['#fff1ca','#efb74c'],'warehouse-multi':['#eee4fc','#b997dd'],'simple-room':['#e0f1fa','#7fbace'],grid:['#e6f3e9','#80b995']}
  const [bg,ink] = palette[id] || ['#e3f0ed','#72a88d']
  let art
  if (kind === 'scene') {
    if (id === 'simple-room') art='<path d="M45 82V46L100 18l55 28v64H45Z" fill="#fff"/><path d="m45 46 55 29 55-29M100 75v35" fill="none" stroke="#d3e2e2" stroke-width="3"/><rect x="58" y="50" width="25" height="27" rx="4" fill="#9ed2e4"/><path d="m103 84 28-14 22 12-28 15Z" fill="#e9b56d"/><path d="M108 88v20m38-23v21" stroke="#b0834c" stroke-width="5"/>'
    else if(id === 'grid') art='<ellipse cx="100" cy="81" rx="75" ry="32" fill="#bddbc6"/><path d="m38 70 104 39M55 59l104 38M77 51l98 34M34 87l92-37M50 100l102-40M76 111l94-40" stroke="#f4fcf5" stroke-width="2"/><path d="M120 42v42" stroke="#487963" stroke-width="4"/><path d="M122 42h26l-7 10 7 10h-26Z" fill="#efbe50"/><circle cx="72" cy="80" r="13" fill="#fff"/><circle cx="72" cy="80" r="6" fill="#61a278"/>'
    else art='<path d="m25 86 78-38 76 35-78 39Z" fill="#ffffff99"/>'+[0,1,2].map((v)=>`<g transform="translate(${42+v*44} ${36+v*5})"><path d="M0 0v57M32 0v57M0 27h32M0 53h32" stroke="${ink}" stroke-width="5"/><rect x="3" y="6" width="12" height="18" rx="2" fill="#dfae71"/><rect x="18" y="10" width="11" height="14" rx="2" fill="#f1ce9d"/><rect x="4" y="32" width="24" height="17" rx="2" fill="#a4c5b9"/></g>`).join('')
  } else {
    const colors = {jetbot:'#91c7a3','carter-v1':'#ebc35b','nova-carter':'#84b8d2',kaya:'#ba9bd9'}
    const c=colors[id] || '#91c7a3'
    art=`<ellipse cx="100" cy="109" rx="52" ry="9" fill="#c2d9d0"/><rect x="51" y="78" width="20" height="30" rx="9" fill="#344b4c"/><rect x="129" y="78" width="20" height="30" rx="9" fill="#344b4c"/><path d="M64 63q36-17 72 0v34q-36 20-72 0Z" fill="${c}"/><rect x="71" y="32" width="58" height="46" rx="17" fill="#fff"/><rect x="79" y="43" width="42" height="24" rx="10" fill="#355451"/><circle cx="91" cy="54" r="4" fill="#c1edc9"/><circle cx="110" cy="54" r="4" fill="#c1edc9"/><path d="M100 32V22" stroke="#52766a" stroke-width="3"/><circle cx="100" cy="19" r="5" fill="#efc453"/><rect x="91" y="86" width="19" height="6" rx="3" fill="#ffffffaa"/>`
  }
  return `<svg viewBox="0 0 200 140" aria-hidden="true"><rect x="4" y="4" width="192" height="132" rx="28" fill="${bg}"/>${art}</svg>`
}

const mascot = `<svg viewBox="0 0 130 130" aria-hidden="true"><ellipse cx="66" cy="119" rx="38" ry="6" fill="#bbdbca"/><g class="buddy-body"><path d="M33 88 19 81M100 84l14-16" stroke="#61a780" stroke-width="12" stroke-linecap="round"/><rect x="41" y="75" width="49" height="38" rx="18" fill="#62ad81"/><path d="M49 110v8m34-8v8" stroke="#376e55" stroke-width="12" stroke-linecap="round"/><rect x="24" y="26" width="81" height="61" rx="25" fill="#83c59b"/><path d="M65 28V16" stroke="#518a65" stroke-width="4"/><circle cx="65" cy="12" r="7" fill="#f0c84e"/><rect x="33" y="36" width="63" height="39" rx="17" fill="#f7fff9"/><g class="buddy-eyes" fill="#2c5145"><ellipse cx="50" cy="52" rx="5" ry="7"/><ellipse cx="79" cy="52" rx="5" ry="7"/></g><path class="buddy-smile" d="M57 64q8 7 16 0" fill="none" stroke="#2c5145" stroke-width="3" stroke-linecap="round"/><circle cx="42" cy="64" r="4" fill="#f4c9ac"/><circle cx="88" cy="64" r="4" fill="#f4c9ac"/><path d="m65 89 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z" fill="#ffde79"/></g></svg>`

export function initChildUI(api) {
  const $ = id => document.getElementById(id)
  document.body.classList.add('child-ui')
  const launcher=$('launcher'), panel=launcher.querySelector('.launcher-panel')
  let step=1, muted=false, audioContext, message='你好！我是小芽。先选一个想去的地方吧。', parentUntil=0, answer=0, gateAction=null, lastFocus=null
  const voicePlayer = document.createElement('audio')
  voicePlayer.id='guideAudio';voicePlayer.preload='none';document.body.append(voicePlayer)
  try { muted=localStorage.getItem('isaac-child-muted')==='true' } catch {}
  function speak(text) {
    voicePlayer.pause()
    if(muted) return
    if(voiceGuides[text]) {
      window.speechSynthesis?.cancel()
      voicePlayer.src=voiceGuides[text]
      voicePlayer.play().catch(()=>{})
      return
    }
    if(!('speechSynthesis' in window))return
    speechSynthesis.cancel()
    const utterance=new SpeechSynthesisUtterance(text)
    utterance.lang='zh-CN'; utterance.rate=.92; utterance.pitch=1.08
    const voices=speechSynthesis.getVoices()
    utterance.voice=voices.find(v=>v.lang.startsWith('zh')) || null
    utterance.onerror=event=>{if(!['interrupted','canceled'].includes(event.error))document.querySelectorAll('.speak-guide').forEach(button=>button.title='这台设备暂时无法播放语音，可以阅读小芽的文字提示。')}
    speechSynthesis.speak(utterance)
  }
  function tone(good=true) {
    if(muted) return
    try {
      audioContext ||= new (window.AudioContext || window.webkitAudioContext)()
      audioContext.resume().catch(()=>{})
      const t=audioContext.currentTime
      ;(good?[523.25,659.25]:[392,440]).forEach((frequency,i)=>{
        const o=audioContext.createOscillator(), g=audioContext.createGain()
        o.type='sine';o.frequency.value=frequency;g.gain.setValueAtTime(0,t+i*.075);g.gain.linearRampToValueAtTime(.055,t+i*.075+.012);g.gain.exponentialRampToValueAtTime(.001,t+i*.075+.16)
        o.connect(g);g.connect(audioContext.destination);o.start(t+i*.075);o.stop(t+i*.075+.18)
      })
    } catch {}
  }
  function guide(text,mood='happy',voice=true) {
    message=text
    document.querySelectorAll('.buddy-message').forEach(el=>el.textContent=text)
    document.querySelectorAll('.buddy').forEach(el=>{el.dataset.mood=mood;el.classList.remove('celebrate');void el.offsetWidth;el.classList.add('celebrate')})
    if(voice)speak(text)
  }
  const buddyMarkup=`<div class="buddy" data-mood="happy">${mascot}</div><div><span class="buddy-name">小芽 · 你的机器人伙伴</span><p class="buddy-message" aria-live="polite">${message}</p></div><button type="button" class="speak-guide" aria-label="再听一次引导">♬<span>听一听</span></button>`
  const banner=document.createElement('section');banner.className='buddy-banner';banner.innerHTML=buddyMarkup
  document.querySelector('.control-panel').prepend(banner)
  const libraryBuddy=document.createElement('section');libraryBuddy.className='buddy-banner library-buddy';libraryBuddy.innerHTML=buddyMarkup
  panel.querySelector('.launcher-head').after(libraryBuddy)
  const toolbar=document.createElement('nav');toolbar.className='child-toolbar';toolbar.setAttribute('aria-label','常用功能')
  toolbar.innerHTML='<button id="childHome" aria-label="回到选择世界">⌂<span>选世界</span></button><button id="childSound" aria-pressed="true">♫<span>声音开</span></button><button id="parentEntry">⚙<span>家长 / 老师</span></button>'
  document.querySelector('.topbar').append(toolbar)
  const rail=document.createElement('div');rail.className='step-rail';rail.innerHTML='<span data-step="1"><b>1</b>选世界</span><i></i><span data-step="2"><b>2</b>选伙伴</span><i></i><span data-step="3"><b>3</b>出发探索</span>'
  panel.querySelector('.launcher-head').after(rail)
  const blocks=panel.querySelectorAll('.library-block')
  blocks[0].id='childWorldStep';blocks[1].id='childRobotStep'
  const previous=document.createElement('button');previous.id='previousStep';previous.className='secondary';previous.textContent='← 上一步'
  const next=document.createElement('button');next.id='nextStep';next.className='primary';next.textContent='选好啦，找伙伴 →'
  panel.querySelector('.launcher-footer').prepend(previous)
  panel.querySelector('.launcher-footer').append(next)

  const adult=document.createElement('dialog');adult.id='adultPanel';adult.className='adult-dialog'
  adult.innerHTML='<header><div><span class="eyebrow">NVIDIA · Isaac Sim</span><h2>家长与老师工作台</h2></div><button class="close-adult" aria-label="关闭工作台">×</button></header><p>这里可以调整参数、上传资产和查看服务状态。关闭后会重新锁定。</p><div id="adultContent"></div>'
  document.body.append(adult)
  const adultContent=$('adultContent')
  for(const element of [blocks[2],$('assistantPanel'),document.querySelector('#robotControls .settings'),$('teleopPanel'),document.querySelector('.diagnostics')]) if(element)adultContent.append(element)
  const diagnostics=adult.querySelector('.diagnostics');diagnostics.open=true
  const connection=document.createElement('section');connection.className='adult-connection';connection.innerHTML='<h3>画面连接</h3>'
  for(const id of ['streamSwitch','connectStream','disconnectStream','useCompatStream','connectionExplanation'])connection.append($(id))
  adultContent.append(connection)
  const gate=document.createElement('dialog');gate.id='parentGate';gate.className='gate-dialog'
  gate.innerHTML='<form id="gateForm"><div class="gate-icon">♧</div><h2>请让家长或老师来帮忙</h2><p>大人完成验证后，就能打开工作台。</p><label for="gateAnswer" id="gateQuestion"></label><input id="gateAnswer" inputmode="numeric" autocomplete="off" required aria-describedby="gateError"/><p id="gateError" role="alert"></p><div class="gate-actions"><button type="button" id="gateCancel" class="secondary">返回探索</button><button type="submit" class="primary">确认答案 →</button></div></form>'
  document.body.append(gate)
  function requestAdult(action=()=>adult.showModal()) {
    api.clearKeys(true);lastFocus=document.activeElement
    if(Date.now()<parentUntil && adult.open) {action();return}
    const a=12+Math.floor(Math.random()*14),b=3+Math.floor(Math.random()*5),c=6+Math.floor(Math.random()*13)
    answer=a*b+c;gateAction=action;$('gateQuestion').textContent=`请计算：${a} × ${b} + ${c} = ?`;$('gateAnswer').value='';$('gateError').textContent=''
    gate.showModal();$('gateAnswer').focus()
  }
  $('parentEntry').onclick=()=>requestAdult()
  $('gateCancel').onclick=()=>gate.close()
  gate.addEventListener('close',()=>lastFocus?.focus())
  $('gateForm').onsubmit=event=>{event.preventDefault();if($('gateAnswer').value.trim()!==String(answer)){$('gateError').textContent='答案还不对，请让大人再算一次。';tone(false);return}parentUntil=Date.now()+180000;gate.close();gateAction?.();tone()}
  adult.querySelector('.close-adult').onclick=()=>adult.close()
  adult.addEventListener('close',()=>{parentUntil=0;lastFocus?.focus()})
  document.addEventListener('visibilitychange',()=>{if(document.hidden){parentUntil=0;if(adult.open)adult.close();if(gate.open)gate.close()}})
  document.addEventListener('click',event=>{
    const anchor=event.target.closest('a[href]')
    if(!anchor)return
    const url=new URL(anchor.href,location.href)
    if(url.origin!==location.origin){event.preventDefault();requestAdult(()=>window.open(url.href,'_blank','noopener,noreferrer'))}
  },true)
  document.addEventListener('pointerdown',event=>{
    const button=event.target.closest('button,.library-card')
    if(!button||button.disabled)return
    tone();button.classList.remove('tap-feedback');void button.offsetWidth;button.classList.add('tap-feedback')
  },true)
  document.querySelectorAll('.speak-guide').forEach(button=>button.onclick=()=>speak(message))
  function soundLabel(){ $('childSound').innerHTML=muted?'♩<span>声音关</span>':'♫<span>声音开</span>';$('childSound').setAttribute('aria-pressed',String(!muted)) }
  soundLabel()
  $('childSound').onclick=()=>{muted=!muted;try{localStorage.setItem('isaac-child-muted',String(muted))}catch{}soundLabel();if(muted){voicePlayer.pause();window.speechSynthesis?.cancel()}else{tone();speak(message)}}
  $('childHome').onclick=()=>{api.openLauncher();showStep(1)}
  function showStep(value){
    step=value;blocks[0].hidden=step!==1;blocks[1].hidden=step!==2
    $('launchSession').classList.toggle('child-step-hidden',step!==2)
    previous.hidden=step===1;next.hidden=step!==1
    rail.querySelectorAll('[data-step]').forEach(el=>el.classList.toggle('active',Number(el.dataset.step)===step))
    panel.querySelector('h1').textContent=step===1?'今天，去哪里探索？':'选一位机器人伙伴吧！'
    panel.querySelector('.launcher-head p').textContent=step===1?'点一张卡片，选一个你喜欢的世界。':'每个伙伴都有自己的本领。'
    guide(step===1?'你好！我是小芽。先选一个想去的地方吧。':'世界选好啦！现在选一位机器人伙伴。')
  }
  next.onclick=()=>{showStep(2);previous.focus()};previous.onclick=()=>showStep(1)
  $('sceneLibrary').addEventListener('click',event=>{const card=event.target.closest('[data-scene-id]');if(card)guide(`选中了${sceneNames[card.dataset.sceneId]||'这个世界'}！点绿色按钮，去找机器人伙伴。`)})
  $('robotLibrary').addEventListener('click',event=>{const card=event.target.closest('[data-robot-id]');if(card)guide(`选中了${card.querySelector('strong').textContent}！准备好就一起出发。`)})
  new MutationObserver(()=>{if(!launcher.hidden){showStep(1);document.querySelector('.workspace').inert=true}else{document.querySelector('.workspace').inert=false;guide('准备好啦！按住方向按钮移动，松开就停。');api.setMode('robot')}}).observe(launcher,{attributes:true,attributeFilter:['hidden']})
  $('stop').addEventListener('click',()=>guide('停一停，观察一下周围吧。','calm'))
  document.querySelectorAll('.mode').forEach(button=>button.addEventListener('click',()=>guide(button.dataset.mode==='robot'?'按住方向按钮移动，松开就停。':'按住箭头转一转、拉近看看。')))
  const waiting=document.createElement('div');waiting.id='childWaiting';waiting.innerHTML=`${mascot}<h2>实验室正在准备中</h2><p>等画面出现，就能和机器人一起探索啦。</p><span>NVIDIA Isaac Sim · 真实机器人仿真</span>`;$('viewerShell').append(waiting)
  let previousReady=false
  setInterval(()=>{
    const state=api.getState(), ready=state.robotReady && (state.compatHealthy || state.streamLive || state.bridgeMock)
    $('closeLauncher').hidden=!state.session
    if(adult.open && Date.now()>=parentUntil)adult.close()
    waiting.hidden=Boolean(state.compatHealthy||state.streamLive||state.bridgeMock)
    $('launchSession').disabled=state.launching||!state.bridgeConnected||!state.selectedSceneId||!state.selectedRobotId
    if(!state.launching)$('launchSession').textContent=state.bridgeConnected?'▶ 一起出发':'◷ 等待实验室连接'
    if(ready&&!previousReady)guide('实验室准备好啦！选好伙伴就能出发。')
    previousReady=ready
  },1000)
  showStep(1)
  return {guide,requestAdult}
}
