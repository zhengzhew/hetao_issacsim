const args=process.argv.slice(2)
const getArg=(name,fallback)=>{const i=args.indexOf(name);return i>=0&&i+1<args.length?args[i+1]:fallback}
const base=getArg('--base','http://127.0.0.1:8080').replace(/\/$/,'')
const sleep=(ms)=>new Promise((r)=>setTimeout(r,ms))
async function jf(p,init,timeout=240000){const res=await fetch(base+p,{...init,signal:AbortSignal.timeout(timeout)});const data=await res.json();if(!res.ok)throw new Error(`${p} HTTP ${res.status}: ${JSON.stringify(data)}`);return data}
const post=(p,body,timeout)=>jf(p,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)},timeout)
const pos=(p)=>Array.isArray(p?.position)?p.position.map(Number):null
let failures=0
const pass=(s)=>console.log(`[PASS] ${s}`);const fail=(s)=>{failures++;console.error(`[FAIL] ${s}`)};const info=(s)=>console.log(`[INFO] ${s}`)

console.log(`Stage 2 real-server acceptance: ${base}`)
console.log('----------------------------------------')
try{
  const cfg=await jf('/api/config');cfg.version==='2.0.0-stage2'?pass('Stage 2 web API online'):fail(`unexpected version ${cfg.version}`);cfg.renderer==='native'?pass('native renderer selected'):fail(`renderer=${cfg.renderer}`);cfg.nativeBundleAvailable?pass('NVIDIA WebRTC bundle exists'):fail('native WebRTC bundle missing')
  const catalog=await jf('/api/catalog');catalog.scenes?.length>=4?pass(`${catalog.scenes.length} scenes exposed`):fail('scene library incomplete');catalog.robots?.length>=4?pass(`${catalog.robots.length} robots exposed`):fail('robot library incomplete')
  const status=await jf('/api/status');status.signaling?.connected?pass('WebRTC signaling reachable'):fail(`signaling offline: ${status.signaling?.error||'unknown'}`);status.bridge?.connected?pass('Isaac bridge online'):fail(`bridge offline: ${status.bridge?.error||'unknown'}`)

  const profiles=[['warehouse','jetbot'],['simple-room','carter-v1'],['warehouse-multi','nova-carter'],['grid','kaya']]
  for(const [sceneId,robotId] of profiles){
    info(`launching ${sceneId} + ${robotId}`)
    const launched=await post('/api/session/launch',{sceneId,robotId},360000)
    if(launched.session?.status==='ready'&&launched.session?.robot?.ready)pass(`${sceneId} + ${robotId} loaded with ${launched.session.robot.adapter}`)
    else fail(`${sceneId}+${robotId} failed: ${launched.session?.error||'not ready'}`)
  }

  // Differential real motion.
  await post('/api/session/launch',{sceneId:'warehouse',robotId:'jetbot'},360000)
  let r=await jf('/api/robot');const before=pos(r.pose)
  if(before){for(let i=0;i<12;i++){await post('/api/control',{type:'motion',linear:.12,lateral:0,angular:0});await sleep(100)}await post('/api/control',{type:'motion',linear:0,lateral:0,angular:0});await sleep(300);r=await jf('/api/robot');const after=pos(r.pose);const d=after?Math.hypot(after[0]-before[0],after[1]-before[1]):0;d>.02?pass(`Jetbot moves through universal API (${d.toFixed(3)} m)`):fail(`Jetbot motion too small (${d.toFixed(3)} m)`)}else fail('Jetbot pose unavailable')
  const lateralReject=await post('/api/control',{type:'motion',linear:0,lateral:.2,angular:0});lateralReject.result?.accepted===false?pass('Jetbot differential adapter rejects lateral axis'):fail('Jetbot accepted unsupported lateral axis')

  // Holonomic real motion.
  await post('/api/session/launch',{sceneId:'grid',robotId:'kaya'},360000)
  r=await jf('/api/robot');const kb=pos(r.pose)
  if(kb){for(let i=0;i<12;i++){await post('/api/control',{type:'motion',linear:0,lateral:.18,angular:0});await sleep(100)}await post('/api/control',{type:'motion',linear:0,lateral:0,angular:0});await sleep(300);r=await jf('/api/robot');const ka=pos(r.pose);const d=ka?Math.hypot(ka[0]-kb[0],ka[1]-kb[1]):0;d>.02?pass(`Kaya lateral motion through same API (${d.toFixed(3)} m)`):fail(`Kaya lateral motion too small (${d.toFixed(3)} m)`)}else fail('Kaya pose unavailable')
} catch(err){fail(err.stack||err.message)}
console.log('----------------------------------------')
if(failures){console.error(`STAGE 2 REAL ACCEPTANCE FAILED (${failures})`);process.exit(1)}
console.log('STAGE 2 REAL ACCEPTANCE PASS')
console.log('Human check: switch all four library cards in Chrome, confirm live video persists, and verify Q/E appears only for Kaya.')
