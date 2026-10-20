import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import {once} from 'node:events'
import {WebSocket} from 'ws'
import {AccessStore,AccessError,allowed} from '../server/platform/access.js'
import {createGateway,validateConfig} from '../server/platform/gateway.js'
const root=path.resolve(import.meta.dirname,'..')
function temporary(){return fs.mkdtempSync(path.join(os.tmpdir(),'isaac-platform-test-'))}
function cleanup(directory){assert.ok(directory.startsWith(path.join(os.tmpdir(),'isaac-platform-test-')));fs.rmSync(directory,{recursive:true,force:true})}
const station=(id,webPort)=>({id,name:id,webPort,bridgePort:21000+Number(id.slice(-1))*3,signalPort:21001+Number(id.slice(-1))*3,mediaPort:21002+Number(id.slice(-1))*3})
test('one-time pairing, expiry, roles and duplicate browser ownership',()=>{
  const directory=temporary();let now=1000
  try{
    const store=new AccessStore(directory,[station('room1',22001)],()=>now)
    const code=store.pairCode('room1','operator'),result=store.redeem(code,{},'peer')
    assert.equal(store.lookup(result.token).stationId,'room1')
    assert.throws(()=>store.redeem(code,{},'peer'),AccessError)
    assert.throws(()=>store.redeem(store.pairCode('room1','operator'),{},'peer'),/已有浏览器/)
    assert.equal(allowed(result.principal,'POST','/api/assets'),false)
    assert.equal(allowed(result.principal,'POST','/api/challenges/start'),true)
    now+=13*3600000;assert.throws(()=>store.lookup(result.token),/过期/)
  }finally{cleanup(directory)}
})
test('station port collisions rejected',()=>{
  const first=station('room1',22001),second=station('room2',22001)
  assert.throws(()=>validateConfig({port:8080,stations:[first,second]}),/duplicate port/)
})
test('gateway isolates stations, protects management and expires/revokes credentials',async()=>{
  const directory=temporary(),workers=[],calls=[];let gateway
  try{
    for(let i=1;i<=2;i++){
      const worker=http.createServer(async(req,res)=>{
        let raw='';for await(const chunk of req)raw+=chunk
        calls.push({room:i,path:req.url,body:raw?JSON.parse(raw):{},key:req.headers['x-isaac-worker-key']})
        res.setHeader('Content-Type','application/json');res.end(JSON.stringify({ok:true,room:i}))
      }).listen(0,'127.0.0.1');await once(worker,'listening');workers.push(worker)
    }
    const stations=workers.map((worker,i)=>station('room'+(i+1),worker.address().port))
    gateway=createGateway({root,directory,config:{port:0,stations}});gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening')
    const base=`http://127.0.0.1:${gateway.server.address().port}`
    const operator=gateway.access.issue('operator','room1'),device=gateway.access.issue('device','room2',{clientId:'client-test'})
    assert.equal((await fetch(base+'/api/config')).status,401)
    assert.equal((await fetch(base+'/platform/diagnostics',{headers:{Authorization:'Bearer '+operator.token}})).status,403)
    assert.equal((await fetch(base+'/api/assets',{method:'POST',headers:{Authorization:'Bearer '+operator.token},body:'{}'})).status,403)
    const response=await fetch(base+'/api/challenges/start',{method:'POST',headers:{Authorization:'Bearer '+operator.token,'Content-Type':'application/json','X-Isaac-Worker-Key':'forged'},body:JSON.stringify({id:'arm-dice',stationId:'room2'})})
    assert.equal((await response.json()).room,1);assert.equal(calls.at(-1).key,gateway.access.data.workerKey)
    assert.equal((await (await fetch(base+'/api/config',{headers:{Authorization:'Bearer '+device.token}})).json()).room,2)
    assert.equal((await fetch(base+'/api/config',{headers:{Authorization:'Bearer '+operator.token,Origin:'https://evil.invalid'}})).status,403)
    gateway.access.revoke(operator.principal.id)
    assert.equal((await fetch(base+'/api/config',{headers:{Authorization:'Bearer '+operator.token}})).status,401)
    assert.equal(calls.length,2)
  }finally{if(gateway){gateway.close();await new Promise(r=>gateway.server.close(r))}for(const worker of workers)await new Promise(r=>worker.close(r));cleanup(directory)}
})
test('WebSocket coalesces poses, rejects old samples, and releases ownership',async()=>{
  const directory=temporary();let gateway,ws;const applied=[];let released=0
  const worker=http.createServer(async(req,res)=>{
    let raw='';for await(const chunk of req)raw+=chunk;const input=raw?JSON.parse(raw):{}
    let result={ok:true}
    if(req.url==='/api/status')result={bridge:{result:{session:{serverId:'boot',status:'ready',robotId:'so101',launchId:1,robot:{joint_limits:{Jaw:[0,1]}}}}}}
    if(req.url==='/api/teleop/engage')result={ok:true,teleop:{token:'private'}}
    if(req.url==='/api/teleop/disengage')released++
    if(req.url==='/api/teleop'){await new Promise(r=>setTimeout(r,45));applied.push(input.seq);result={ok:true,applied:true,rate_hz:20}}
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result))
  }).listen(0,'127.0.0.1');await once(worker,'listening')
  try{
    gateway=createGateway({root,directory,config:{port:0,stations:[station('room1',worker.address().port)]}})
    gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening')
    const credential=gateway.access.issue('device','room1',{clientId:'client-test'})
    ws=new WebSocket(`ws://127.0.0.1:${gateway.server.address().port}/platform/teleop`,{headers:{Authorization:'Bearer '+credential.token}})
    await once(ws,'open')
    const ready=new Promise(resolve=>ws.on('message',raw=>{const m=JSON.parse(raw);if(m.type==='ready')resolve(m)}))
    ws.send(JSON.stringify({type:'hello',driver:'desheng-se-v401',armId:'arm-test',calibrationHash:'f'.repeat(64)}))
    const info=await ready
    const sample=seq=>({type:'sample',seq,launchId:info.launchId,capturedAt:Date.now(),positions:{Jaw:.5}})
    ws.send(JSON.stringify({...sample(1),capturedAt:Date.now()-5000}))
    for(let i=2;i<=15;i++)ws.send(JSON.stringify(sample(i)))
    await new Promise(r=>setTimeout(r,300))
    assert.ok(!applied.includes(1));assert.ok(applied.length<14);assert.equal(applied.at(-1),15)
    gateway.access.revoke(credential.principal.id)
    ws.send(JSON.stringify(sample(16)));await once(ws,'close')
    await new Promise(r=>setTimeout(r,60));assert.equal(released,1)
  }finally{ws?.terminate();if(gateway){gateway.close();await new Promise(r=>gateway.server.close(r))}await new Promise(r=>worker.close(r));cleanup(directory)}
})

 test('arm identity persists across computers and profile changes need teacher approval',()=>{
  const directory=temporary()
  try {
    let store=new AccessStore(directory,[station('room1',22001)])
    const profile={armId:'school-arm-01',driver:'desheng-se-v401',calibrationHash:'a'.repeat(64)}
    store.bindArm(profile)
    store=new AccessStore(directory,[station('room1',22001)])
    store.bindArm({...profile,clientId:'different-computer',port:'COM99'})
    const changed={...profile,calibrationHash:'b'.repeat(64)}
    assert.throws(()=>store.bindArm(changed),/发生变化/)
    assert.equal(store.arms()[0].calibrationHash,profile.calibrationHash)
    assert.throws(()=>store.approveArm(profile.armId,'c'.repeat(64)),/已变化/)
    store.approveArm(profile.armId,changed.calibrationHash);store.bindArm(changed)
    assert.equal(store.arms()[0].calibrationHash,changed.calibrationHash)
    assert.throws(()=>store.bindArm({...profile,armId:'new-arm',driver:'unknown'}),/无效/)
  } finally {cleanup(directory)}
})
