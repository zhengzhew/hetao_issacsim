import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import {once} from 'node:events'
import {WebSocket} from 'ws'
import {assertLocalConnector,checkLanCredential} from '../server/platform/local-connector.js'
import {createGateway} from '../server/platform/gateway.js'
const policy={localConnector:{enabled:true,interfaces:['WLAN']}}
const networks={WLAN:[{address:'192.168.8.57',netmask:'255.255.255.0',family:'IPv4',internal:false}],VPN:[{address:'10.0.0.1',netmask:'255.0.0.0',family:'IPv4',internal:false}]}
const request=(address,headers={})=>({socket:{remoteAddress:address},headers})
test('local connection admits only loopback or configured WLAN subnet',()=>{
  for(const address of ['192.168.8.46','::ffff:192.168.8.46','127.0.0.1','::1'])assert.ok(assertLocalConnector(request(address),policy,networks))
  for(const address of ['192.168.9.46','10.1.2.3','8.8.8.8','fe80::1','192.168.8.0','192.168.8.255'])assert.throws(()=>assertLocalConnector(request(address),policy,networks))
  assert.throws(()=>assertLocalConnector(request('192.168.8.46'),policy,{}))
})
test('LAN enrollment rejects browser, proxy and public deployment requests',()=>{
  for(const headers of [{origin:'http://localhost:8080'},{'sec-fetch-mode':'cors'},{'x-forwarded-for':'192.168.8.46'},{forwarded:'for=192.168.8.46'},{'x-real-ip':'192.168.8.46'}])assert.throws(()=>assertLocalConnector(request('127.0.0.1',headers),policy,networks))
  assert.throws(()=>assertLocalConnector(request('127.0.0.1'),{...policy,publicOrigin:'https://example.invalid'},networks))
  assert.throws(()=>assertLocalConnector(request('127.0.0.1'),{localConnector:{enabled:false}},networks))
})
test('LAN credentials stay bound to the connecting address without changing browser credentials',()=>{
  checkLanCredential(request('127.0.0.1'),{accessMode:'lan',peer:'127.0.0.1'},policy)
  assert.throws(()=>checkLanCredential(request('127.0.0.1'),{accessMode:'lan',peer:'192.168.8.46'},policy))
  checkLanCredential(request('8.8.8.8',{origin:'http://example.invalid'}),{role:'operator'},policy)
})
function native(base,route,data,token,extra={}) {
  return new Promise((resolve,reject)=>{
    const req=http.request(base+route,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...extra}},res=>{
      let raw='';res.on('data',part=>raw+=part);res.on('end',()=>resolve({status:res.statusCode,data:JSON.parse(raw)}))
    })
    req.on('error',reject);req.end(data===undefined?undefined:JSON.stringify(data))
  })
}
async function fixture(count,run) {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'isaac-connector-test-'))
  const stations=Array.from({length:count},(_,i)=>({id:'room'+(i+1),name:'体验台 '+(i+1),webPort:24000+i*4,bridgePort:24001+i*4,signalPort:24002+i*4,mediaPort:24003+i*4}))
  const gateway=createGateway({root:path.resolve(import.meta.dirname,'..'),directory,config:{port:0,...policy,stations}})
  gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening')
  try {await run(gateway,'http://127.0.0.1:'+gateway.server.address().port)}
  finally {gateway.close();await new Promise(r=>gateway.server.close(r));fs.rmSync(directory,{recursive:true,force:true})}
}
test('single station enrolls native devices, reuses credentials and never grants teacher access',async()=>{
  await fixture(1,async(gateway,base)=>{
    const input={clientId:'connector-test',role:'teacher'}
    const first=await native(base,'/platform/connector/connect',input)
    assert.equal(first.status,200);assert.equal(first.data.principal.role,'device');assert.equal(first.data.principal.stationId,'room1')
    assert.equal((await native(base,'/platform/me',undefined,first.data.token)).status,200)
    assert.equal((await native(base,'/platform/diagnostics',undefined,first.data.token)).status,403)
    assert.equal((await native(base,'/api/challenges/start',{id:'arm-block'},first.data.token)).status,403)
    const second=await native(base,'/platform/connector/connect',input,first.data.token)
    assert.equal(second.data.token,first.data.token)
    // Browser fetch includes Sec-Fetch-Mode; it cannot obtain a native device grant.
    assert.equal((await fetch(base+'/platform/connector/connect',{method:'POST',body:JSON.stringify(input)})).status,403)
    assert.equal((await native(base,'/platform/connector/connect',input,undefined,{Origin:base})).status,403)
    assert.equal((await native(base,'/platform/diagnostics')).status,401)
    gateway.access.revoke(first.data.principal.id)
    const renewed=await native(base,'/platform/connector/connect',input,first.data.token)
    assert.notEqual(renewed.data.token,first.data.token);assert.equal(renewed.data.principal.role,'device')
  })
})
test('multiple stations require a choice and never silently switch a missing saved station',async()=>{
  await fixture(2,async(gateway,base)=>{
    const input={clientId:'connector-test'}
    for(const data of [input,{...input,stationId:'removed-room'}]) {
      const choice=await native(base,'/platform/connector/connect',data)
      assert.equal(choice.data.chooseStation,true);assert.equal(choice.data.stations.length,2);assert.equal(choice.data.token,undefined)
    }
    const selected=await native(base,'/platform/connector/connect',{...input,stationId:'room2'})
    assert.equal(selected.data.principal.stationId,'room2')
    const operator=gateway.access.issue('operator','room1')
    assert.equal((await native(base,'/platform/me',undefined,operator.token)).data.principal.stationId,'room1')
    assert.equal((await native(base,'/platform/select',{stationId:'room2'},operator.token)).status,403)
    assert.equal((await native(base,'/platform/connector/connect',{...input,stationId:'room1'},operator.token,{Origin:base})).status,403)
  })
})
test('automatic enrollment cannot take over an active station',async()=>{
  await fixture(1,async(gateway,base)=>{
    const first=await native(base,'/platform/connector/connect',{clientId:'connector-one'})
    const ws=new WebSocket(base.replace('http:','ws:')+'/platform/teleop',{headers:{Authorization:'Bearer '+first.data.token}})
    await once(ws,'open')
    try {assert.equal((await native(base,'/platform/connector/connect',{clientId:'connector-two'})).status,409)}
    finally {ws.close();await once(ws,'close')}
  })
})
