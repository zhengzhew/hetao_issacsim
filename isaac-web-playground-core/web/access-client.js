// The existing child interface stays intact; credentials are server-owned cookies.
export function initAccessClient(onExpired) {
  let managed=false,busy=false
  async function check(){
    if(busy)return;busy=true
    try{
      if(!managed){const config=await fetch('/platform/config',{signal:AbortSignal.timeout(5000)});if(!config.ok)return;managed=(await config.json()).managed===true}
      if(!managed)return
      const response=await fetch('/platform/me',{signal:AbortSignal.timeout(5000)})
      if(response.status===401){await onExpired();location.replace('/login');return}
      if(!response.ok)return
      const data=await response.json()
      if(data.principal.role==='teacher'&&!document.getElementById('managePlatform')){
        const a=document.createElement('a');a.id='managePlatform';a.textContent='老师管理 · 配对设备与诊断';a.href='/manage';a.target='_blank';a.rel='noopener'
        document.getElementById('adultContent')?.prepend(a)
      }
      if(data.principal.role==='operator')document.querySelectorAll('#registerForm input,#registerForm button').forEach(el=>el.disabled=true)
    }catch{}finally{busy=false}
  }
  check();setInterval(check,10000)
}
