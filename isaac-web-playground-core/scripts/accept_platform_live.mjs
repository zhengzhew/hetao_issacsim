// Opt-in real Kit transport check. Reapplies the current virtual pose; never opens a USB device.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import {once} from 'node:events'
import {WebSocket} from 'ws'
import {createGateway} from '../server/platform/gateway.js'
const root=path.resolve(import.meta.dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(root,'configs/platform.json'),'utf8'))
const station=config.stations[0],directory=fs.mkdtempSync(path.join(os.tmpdir(),'isaac-live-test-'))
const key=JSON.parse(fs.readFileSync(path.join(root,'run/platform/access.json'),'utf8')).workerKey
const gateway=createGateway({root,directory,config:{port:0,stations:[station]}})
gateway.access.data.workerKey=key
let ws
async function worker(route){const r=await fetch(`http://127.0.0.1:${station.webPort}${route}`,{headers:{'X-Isaac-Worker-Key':key},signal:AbortSignal.timeout(5000)});assert.ok(r.ok);return r.json()}
try {
  const before=await worker('/api/teleop/status');assert.equal(before.teleop.engaged,false,'A real leader owns this station; stop the test')
  const status=await worker('/api/status');assert.equal(status.bridge.result.mock,false);assert.equal(status.bridge.result.session.status,'ready')
  const robot=await worker('/api/robot'),positions=robot.info.joint_targets;assert.equal(Object.keys(positions).length,6)
  gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening')
  const credential=gateway.access.redeem(gateway.access.pairCode(station.id,'device'),{clientId:'synthetic-live-test'},'local-test')
  ws=new WebSocket(`ws://127.0.0.1:${gateway.server.address().port}/platform/teleop`,{headers:{Authorization:'Bearer '+credential.token}})
  await once(ws,'open');const messages=[],sent=new Map(),elapsed=[]
  const ready=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('ready timed out')),10000);ws.on('message',raw=>{const m=JSON.parse(raw);messages.push(m);if(m.type==='ready'){clearTimeout(timer);resolve(m)}if(m.type==='applied'&&sent.has(m.seq))elapsed.push(performance.now()-sent.get(m.seq))})})
  ws.send(JSON.stringify({type:'hello',armId:'synthetic-virtual-test',driver:'desheng-se-v401',calibrationHash:'0'.repeat(64)}));const info=await ready
  for(let seq=1;seq<=40;seq++){sent.set(seq,performance.now());ws.send(JSON.stringify({type:'sample',seq,positions,capturedAt:Date.now(),launchId:info.launchId}));await new Promise(r=>setTimeout(r,50))}
  await new Promise(r=>setTimeout(r,400));const following=await worker('/api/teleop/status')
  assert.ok(elapsed.length>=30,`Too few applied poses: ${elapsed.length}/40`);assert.equal(following.teleop.seq,40)
  const appliedBefore=following.teleop.applied
  ws.send(JSON.stringify({type:'sample',seq:41,positions,capturedAt:Date.now()-1000,launchId:info.launchId}))
  await new Promise(r=>setTimeout(r,150));assert.equal((await worker('/api/teleop/status')).teleop.applied,appliedBefore)
  // Reload the virtual level while the paired connection stays open.
  const launched=await fetch(`http://127.0.0.1:${station.webPort}/api/challenges/start`,{method:'POST',headers:{'Content-Type':'application/json','X-Isaac-Worker-Key':key},body:JSON.stringify({id:'arm-dice'}),signal:AbortSignal.timeout(120000)})
  assert.ok(launched.ok);assert.equal((await launched.json()).ok,true)
  const newReady=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('scene reconnect timed out')),10000);ws.on('message',raw=>{const m=JSON.parse(raw);if(m.type==='ready'&&m.launchId!==info.launchId){clearTimeout(timer);resolve(m)}})})
  ws.send(JSON.stringify({type:'sample',seq:42,positions,capturedAt:Date.now(),launchId:info.launchId}));const next=await newReady
  ws.send(JSON.stringify({type:'sample',seq:43,positions,capturedAt:Date.now(),launchId:next.launchId}))
  await new Promise(r=>setTimeout(r,250));assert.equal((await worker('/api/teleop/status')).teleop.seq,43)
  const end=once(ws,'close');ws.close();await end;await new Promise(r=>setTimeout(r,200));assert.equal((await worker('/api/teleop/status')).teleop.engaged,false)
  elapsed.sort((a,b)=>a-b)
  const result={at:new Date().toISOString(),simulation:'real Isaac Sim',input:'synthetic current-pose samples; no USB',sent:40,applied:elapsed.length,rate_hz:following.teleop.rate_hz,localRoundTripMs:{median:elapsed[Math.floor(elapsed.length*.5)],p95:elapsed[Math.floor(elapsed.length*.95)],max:elapsed.at(-1)},staleRejected:true,sceneReconnected:true,released:true,errors:messages.filter(m=>m.type.includes('error'))}
  fs.writeFileSync(path.join(root,'run/platform-live-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result))
} finally {ws?.terminate();gateway.close();await new Promise(r=>gateway.server.close(r));assert.ok(directory.startsWith(path.join(os.tmpdir(),'isaac-live-test-')));fs.rmSync(directory,{recursive:true,force:true})}
