import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import crypto from 'node:crypto'
import {once} from 'node:events'
import {execFile} from 'node:child_process'
import {promisify} from 'node:util'
import {createGateway} from '../server/platform/gateway.js'

const root=path.resolve(import.meta.dirname,'..')
const python=process.env.PYTHON||(process.platform==='win32'?'python':'python3')

test('default connector delivers 50 Hz through the real gateway without waiting for acknowledgements', {timeout:15000}, async()=>{
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'isaac-rate-test-'))
  const times=[],sequences=[],errors=[]
  const limits=Object.fromEntries(['Rotation','Pitch','Elbow','Wrist_Pitch','Wrist_Roll','Jaw'].map(name=>[name,[-1,1]]))
  const worker=http.createServer(async(req,res)=>{
    let raw='';for await(const part of req)raw+=part
    const input=raw?JSON.parse(raw):{}
    let result={ok:true}
    if(req.url==='/api/status')result={bridge:{result:{session:{serverId:'rate-test',status:'ready',robotId:'so101',launchId:1,robot:{joint_limits:limits}}}}}
    if(req.url==='/api/teleop/engage')result={ok:true,teleop:{token:'test-lease'}}
    if(req.url==='/api/teleop'){
      times.push(performance.now());sequences.push(input.seq)
      if(!Object.keys(limits).every(name=>Number.isFinite(input.positions[name])))errors.push('invalid pose')
      // A small acknowledgement delay catches a client that waits a whole sample
      // period after each reply before it looks for the next USB sample.
      await new Promise(resolve=>setTimeout(resolve,7))
      result={ok:true,applied:true,rate_hz:times.length>1?(times.length-1)*1000/(times.at(-1)-times[0]):0}
    }
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify(result))
  }).listen(0,'127.0.0.1')
  await once(worker,'listening')
  let gateway
  try {
    gateway=createGateway({root,directory:path.join(directory,'gateway'),config:{port:0,stations:[{id:'rate-test',name:'rate test',webPort:worker.address().port,bridgePort:21992,signalPort:21993,mediaPort:21994}]}})
    gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening')
    const server=`http://127.0.0.1:${gateway.server.address().port}`
    const state=path.join(directory,'client');fs.mkdirSync(state)
    const credential=gateway.access.issue('device','rate-test',{clientId:'rate-test-client'})
    fs.writeFileSync(path.join(state,crypto.createHash('sha256').update(server).digest('hex').slice(0,16)+'.json'),JSON.stringify(credential))
    const stop=path.join(directory,'stop')
    const script=`
import sys,time,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,sys.argv.pop(1))
import leader_client
class Reader:
    port=SimpleNamespace(baudrate=1000000)
    def open(self):pass
    def close(self):pass
    def positions(self):time.sleep(.002);return [2048]*6
stop=Path(sys.argv[sys.argv.index('--stop-file')+1])
timer=threading.Timer(3.2,stop.touch);timer.start()
try:
    with patch.object(leader_client,'make_reader',return_value=Reader()):leader_client.main()
finally:timer.cancel()
`
    const {stdout}=await promisify(execFile)(python,['-B','-c',script,path.join(root,'tools'),'--port','TEST','--server',server,'--arm-id','rate-test-arm','--driver','feetech-so101','--calibration',path.join(root,'scripts/fixtures/leader_arm_isaac_calibration.json'),'--state-dir',state,'--stop-file',stop],{timeout:10000,env:{...process.env,PYTHONIOENCODING:'utf-8'}})
    const hz=(times.length-1)*1000/(times.at(-1)-times[0])
    console.log(JSON.stringify({input:'synthetic USB, real Python client and gateway, simulated worker',frames:times.length,measuredHz:Number(hz.toFixed(2))}))
    assert.ok(times.length>=125,`only ${times.length} poses applied in 3.2 seconds`)
    assert.ok(hz>=45&&hz<=55,`expected approximately 50 Hz, got ${hz.toFixed(2)}`)
    assert.ok(sequences.every((seq,index)=>index===0||seq>sequences[index-1]),'old sample was replayed')
    assert.deepEqual(errors,[])
    const events=stdout.trim().split(/\r?\n/).map(line=>JSON.parse(line))
    assert.ok(events.some(event=>event.event==='following'))
    assert.ok(events.some(event=>event.event==='closed'))
    assert.ok(!events.some(event=>event.event==='error'))
  } finally {
    if(gateway){gateway.close();await new Promise(resolve=>gateway.server.close(resolve))}
    await new Promise(resolve=>worker.close(resolve))
    assert.equal(path.dirname(directory),path.resolve(os.tmpdir()))
    assert.ok(path.basename(directory).startsWith('isaac-rate-test-'))
    fs.rmSync(directory,{recursive:true,force:true})
  }
})
