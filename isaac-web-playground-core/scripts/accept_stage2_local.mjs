import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const child = spawn(process.execPath, [path.join(ROOT, 'scripts/local_demo.mjs')], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] })
let output = ''
let base = null
child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8')
child.stdout.on('data', (chunk) => { output += chunk; process.stdout.write(chunk); const m = chunk.match(/local playground (http:\/\/127\.0\.0\.1:\d+)/); if (m) base = m[1] })
child.stderr.on('data', (chunk) => { output += chunk; process.stderr.write(chunk) })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function waitForBase() { for (let i=0;i<100;i++){ if(base) return base; if(child.exitCode!==null) throw new Error(`demo exited early\n${output}`); await sleep(50) } throw new Error('timed out waiting for local playground URL') }
async function jf(baseUrl, p, init) { const res=await fetch(baseUrl+p, init); const data=await res.json(); if(!res.ok) throw new Error(`${p} HTTP ${res.status}: ${JSON.stringify(data)}`); return data }
const post=(baseUrl,p,body)=>jf(baseUrl,p,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)})
const pos=(payload)=>payload?.pose?.position?.map(Number) || payload?.position?.map(Number) || null
let failures=0
const pass=(s)=>console.log(`[PASS] ${s}`); const fail=(s)=>{failures++;console.error(`[FAIL] ${s}`)}; const info=(s)=>console.log(`[INFO] ${s}`)

try {
  const b=await waitForBase(); await sleep(250)
  console.log(`\nStage 2 local acceptance: ${b}`)
  const cfg=await jf(b,'/api/config'); cfg.version==='2.0.0-stage2'?pass('Stage 2 server version'):fail(`unexpected version ${cfg.version}`)
  const catalog=await jf(b,'/api/catalog')
  catalog.scenes?.length===4?pass('4-scene library loaded'):fail(`scene count=${catalog.scenes?.length}`)
  catalog.robots?.length===4?pass('4-robot library loaded'):fail(`robot count=${catalog.robots?.length}`)

  let comboCount=0
  for (const scene of catalog.scenes) {
    for (const robot of catalog.robots) {
      const launch=await post(b,'/api/session/launch',{sceneId:scene.id,robotId:robot.id})
      if (launch.session?.status==='ready' && launch.session?.sceneId===scene.id && launch.session?.robotId===robot.id) comboCount++
      else fail(`launch ${scene.id}+${robot.id}: ${JSON.stringify(launch.session)}`)
    }
  }
  comboCount===16?pass('all 16 Scene x Robot combinations switch successfully'):fail(`only ${comboCount}/16 combinations switched`)

  await post(b,'/api/session/launch',{sceneId:'warehouse',robotId:'jetbot'})
  const diff=await post(b,'/api/control',{type:'motion',linear:0,lateral:0.3,angular:0})
  diff.result?.accepted===false && diff.result?.unsupported_axis==='lateral'?pass('differential adapter rejects lateral motion'):fail('differential adapter did not reject lateral motion')

  await post(b,'/api/session/launch',{sceneId:'grid',robotId:'kaya'})
  const kayaBefore=pos((await jf(b,'/api/robot')).pose)
  for(let i=0;i<10;i++){await post(b,'/api/control',{type:'motion',linear:0,lateral:0.35,angular:0});await sleep(80)}
  await post(b,'/api/control',{type:'motion',linear:0,lateral:0,angular:0}); await sleep(120)
  const kayaAfter=pos((await jf(b,'/api/robot')).pose)
  const kayaMove=kayaBefore&&kayaAfter?Math.hypot(kayaAfter[0]-kayaBefore[0],kayaAfter[1]-kayaBefore[1]):0
  kayaMove>.05?pass(`holonomic Kaya lateral motion works (${kayaMove.toFixed(3)} m)`):fail(`Kaya lateral motion too small (${kayaMove.toFixed(3)} m)`)

  await post(b,'/api/session/launch',{sceneId:'simple-room',robotId:'carter-v1'})
  const carterBefore=pos((await jf(b,'/api/robot')).pose)
  for(let i=0;i<8;i++){await post(b,'/api/control',{type:'motion',linear:0.35,lateral:0,angular:0});await sleep(80)}
  await post(b,'/api/control',{type:'motion',linear:0,lateral:0,angular:0}); await sleep(100)
  const carterAfter=pos((await jf(b,'/api/robot')).pose)
  const carterMove=carterBefore&&carterAfter?Math.hypot(carterAfter[0]-carterBefore[0],carterAfter[1]-carterBefore[1]):0
  carterMove>.04?pass(`differential Carter forward motion works (${carterMove.toFixed(3)} m)`):fail(`Carter motion too small (${carterMove.toFixed(3)} m)`)

  await post(b,'/api/control',{type:'motion',linear:0.4,lateral:0,angular:0}); await sleep(650)
  const mock=await jf(b,'/api/mock/state')
  mock.state?.watchdogStop && Number(mock.state?.linear)===0?pass('watchdog stops stale motion'):fail('watchdog did not stop stale motion')

  const reset=await post(b,'/api/robot/reset',{})
  reset.result?.reset?pass('robot reset survives session switching'):fail('robot reset failed')
  const current=await jf(b,'/api/session')
  current.session?.sceneId==='simple-room'&&current.session?.robotId==='carter-v1'?pass('active session query is consistent'):fail('active session query inconsistent')
  info('UI still needs a human browser check for cards, Camera/Robot input isolation and canvas rendering.')
} catch(err){fail(err.stack||err.message)} finally {
  child.kill('SIGTERM'); await sleep(100)
}

if(failures){console.error(`\nSTAGE 2 LOCAL ACCEPTANCE FAILED (${failures})`);process.exit(1)}
console.log('\nSTAGE 2 LOCAL ACCEPTANCE PASS')
