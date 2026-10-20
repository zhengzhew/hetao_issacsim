export function initChallengesUI(api) {
  const card=document.createElement('section');card.className='challenge-card';card.hidden=true
  card.innerHTML='<div class="eyebrow">我的挑战</div><h2 id="challengeName"></h2><p id="challengeGuide"></p><div class="challenge-goal" id="challengeGoal"></div><p id="challengeProgress" role="status" aria-live="polite"></p><div id="challengeActions" class="challenge-actions"></div><div class="challenge-actions"><button id="retryChallenge" class="secondary">↺ 重新挑战</button><button id="chooseChallenge" class="secondary">⌂ 选择关卡</button></div>'
  const copy=document.createElement('div');copy.className='challenge-copy'
  for(const selector of ['.eyebrow','#challengeName','#challengeGuide'])copy.append(card.querySelector(selector))
  const status=document.createElement('div');status.className='challenge-status'
  for(const selector of ['#challengeGoal','#challengeProgress'])status.append(card.querySelector(selector))
  const buttons=document.createElement('div');buttons.className='challenge-buttons'
  card.querySelectorAll('.challenge-actions').forEach(element=>buttons.append(element))
  card.replaceChildren(copy,status,buttons)
  document.querySelector('.workspace-footer').prepend(card)
  const $=id=>document.getElementById(id);let shownId=null,complete=false,busy=false,polling=false,epoch=0
  $('retryChallenge').onclick=async()=>{if(busy)return;epoch++;api.clearKeys(true);busy=true;try{await api.launch();complete=false;shownId=null}finally{busy=false}}
  $('chooseChallenge').onclick=()=>{epoch++;api.clearKeys(true);api.openLauncher()}
  async function action(name){
    if(busy)return
    busy=true;card.querySelectorAll('button').forEach(b=>b.disabled=true)
    try {const r=await fetch('/api/challenges/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:name})}).then(r=>r.json());if(!r.ok)throw Error(r.error);api.guide(({sit:'等小鸭子坐稳，再点站起来。',stand:'正在站起来，等它站稳。',roll:'观察小鸭子能不能翻过一周，摔倒了也没关系。',kick:'正在踢球，看看足球滚向哪里！'})[name])}
    catch(e){$('challengeProgress').textContent=e.message;api.guide('这个动作暂时没有完成，请再试一次。','calm')}
    finally {busy=false;card.querySelectorAll('button').forEach(b=>b.disabled=false)}
  }
  function render(c){
    card.hidden=!c?.level;if(!c?.level)return
    if(shownId!==c.level.id){
      shownId=c.level.id;complete=false
      $('challengeName').textContent=c.level.name;$('challengeGuide').textContent=c.level.instruction;$('challengeGoal').textContent='目标：'+c.level.goal
      $('challengeActions').replaceChildren()
      const actions=c.level.kind==='posture'?[['sit','↓ 坐下'],['stand','↑ 站起来']]:c.level.kind==='roll'?[['roll','↻ 前滚翻']]:c.level.kind==='kick'?[['kick','⚽ 右脚踢球']]:[]
      for(const [name,label] of actions){const b=document.createElement('button');b.className='primary';b.textContent=label;b.onclick=()=>action(name);$('challengeActions').append(b)}
    }
    $('challengeProgress').textContent=c.message;card.classList.toggle('completed',c.complete)
    if(c.complete&&!complete)api.guide('挑战成功！你做到了！再选一个关卡吧。')
    complete=c.complete
  }
  setInterval(async()=>{
    const state=api.getState();render(state.challenge)
    if(document.getElementById('launcher').hidden===false||state.launching||busy||polling)return
    polling=true;const generation=epoch,previous=state.challenge
    try {const r=await fetch('/api/challenges',{cache:'no-store'}).then(r=>r.json());if(generation!==epoch||state.launching||state.challenge!==previous)return;if(r.ok){state.challenge=r.challenge;render(r.challenge)}else{$('challengeProgress').textContent='暂时连接不上关卡，请稍等'}}
    catch {$('challengeProgress').textContent='连接中断，正在重试'}finally{polling=false}
  },700)
}
