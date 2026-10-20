import test from 'node:test'
import assert from 'node:assert/strict'
import net from 'node:net'
import {once} from 'node:events'
import {BridgeChannel} from '../server/bridge-channel.js'
test('connect time consumes sample lifetime; expired sample is never written',async()=>{
  const channel=new BridgeChannel('127.0.0.1',1);let writes=0
  channel.connect=async()=>{await new Promise(r=>setTimeout(r,40));channel.socket={write:()=>writes++}}
  await assert.rejects(channel.send('teleop_sample',{},10),/expired while connecting/)
  assert.equal(writes,0)
})
test('an old TCP socket closing cannot destroy a newer connection',async()=>{
  const peers=new Set(),server=net.createServer(socket=>{peers.add(socket);socket.on('close',()=>peers.delete(socket))}).listen(0,'127.0.0.1')
  await once(server,'listening');const channel=new BridgeChannel('127.0.0.1',server.address().port)
  try {
    const old=await channel.connect();channel.teardown(Error('test reconnect'))
    const current=await channel.connect();old.emit('close')
    assert.equal(channel.socket,current);assert.equal(current.destroyed,false)
  } finally {channel.teardown(Error('done'));for(const socket of peers)socket.destroy();await new Promise(r=>server.close(r))}
})
