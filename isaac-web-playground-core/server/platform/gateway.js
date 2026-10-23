import http from 'node:http'
import https from 'node:https'
import {workerOrigin, validateOrigin, validHost} from './runtime.js'
import fs from 'node:fs'
import path from 'node:path'
import {WebSocketServer, WebSocket} from 'ws'
import {AccessStore,AccessError,requestToken,checkOrigin,allowed} from './access.js'
import {assertLocalConnector,checkLanCredential,localConnectorEnabled} from './local-connector.js'
import {createStreamProxy} from './stream-proxy.js'
const json=(res,status,value,headers={})=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',...headers});res.end(JSON.stringify(value))}
async function body(req) {
  let data='',size=0
  for await (const chunk of req) {size+=chunk.length;if(size>65536) throw new AccessError('请求过大',413);data+=chunk}
  try {return JSON.parse(data||'{}')} catch {throw new AccessError('JSON 无效',400)}
}
export function validateConfig(config) {
  if (!Array.isArray(config.stations)||!config.stations.length) throw Error('At least one station is required')
  const ids=new Set(),ports=new Set([`127.0.0.1:${config.port}`])
  for (const s of config.stations) {
    if (!/^[a-z0-9-]{1,48}$/.test(s.id)||ids.has(s.id)) throw Error('Invalid or duplicate station id')
    ids.add(s.id)
    const origin=validateOrigin(workerOrigin(s),'workerOrigin')
    const workerHost=new URL(origin).hostname
    for(const field of ['streamHost','publicIp','webHost','bridgeHost','signalHost'])
      if(s[field]!==undefined&&!validHost(s[field]))throw Error(`Invalid ${field} for ${s.id}`)
    for(const [key,minimum,maximum] of [['gpu',0,32],['width',320,3840],['height',240,2160],['fps',1,60]]) {
      if(s[key]!==undefined&&(!Number.isInteger(s[key])||s[key]<minimum||s[key]>maximum))throw Error(`Invalid ${key} for ${s.id}`)
    }
    for (const key of ['webPort','bridgePort','signalPort','mediaPort']) {
      const endpoint=`${workerHost}:${key==='webPort'?(new URL(origin).port||({ 'http:':80, 'https:':443 }[new URL(origin).protocol])):s[key]}`
      if (!Number.isInteger(s[key])||s[key]<1024||s[key]>65535||ports.has(endpoint)) throw Error(`Invalid or duplicate port: ${s.id}/${key}`)
      ports.add(endpoint)
    }
  }
  if (config.localConnector?.enabled && (!Array.isArray(config.localConnector.interfaces) || !config.localConnector.interfaces.length || config.localConnector.interfaces.some(name=>typeof name!=='string'||!name.trim()))) throw Error('Local connector requires explicit network interface names')
  if (config.publicOrigin) validateOrigin(config.publicOrigin,'publicOrigin')
  if (config.publicOrigin?.startsWith('https:')&&!config.secureCookies) throw Error('HTTPS requires secureCookies')
  if (config.proxyStreaming && !config.publicOrigin?.startsWith('https:')) throw Error('Proxied streaming requires an HTTPS publicOrigin')
  return config
}
export function createGateway({config,root,directory,store:givenStore,workerKey}) {
  validateConfig(config)
  const access=givenStore||new AccessStore(directory,config.stations)
  const serviceKey=workerKey||access.data.workerKey
  const streamProxy=createStreamProxy({config,access})
  const live=new Map(),reports=new Map(),readAgent=new http.Agent({keepAlive:true,maxSockets:16}),secureAgent=new https.Agent({keepAlive:true,maxSockets:16})
  const cookie=token=>`isaac_access=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200${config.secureCookies?'; Secure':''}`
  const workerUrl=(station,pathname)=>`${workerOrigin(station)}${pathname}`
  async function call(station,pathname,data,timeout=1500) {
    const response=await fetch(workerUrl(station,pathname),{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Isaac-Worker-Key':serviceKey},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(timeout)})
    const result=await response.json()
    if (!response.ok || result.ok===false) throw new AccessError(result.error||'仿真实例暂不可用',response.status===200?503:response.status)
    return result
  }
  function endDevice(stationId,reason) {live.get(stationId)?.ws.close(1000,reason)}
  async function diagnostics() {
    const stations=await Promise.all(config.stations.map(async station=>{
      const read=await Promise.allSettled([call(station,'/api/status'),call(station,'/api/teleop/status')])
      const control=live.get(station.id)
      return {...station, status:read[0].status==='fulfilled'?read[0].value:{error:String(read[0].reason)},teleop:read[1].status==='fulfilled'?read[1].value:{error:String(read[1].reason)},device:control?{principalId:control.principal.id, metadata:control.metadata, samples:control.samples, dropped:control.dropped, lastSampleAgeMs:control.lastAt?Date.now()-control.lastAt:null, ackMs:control.ackMs}:null}
    }))
    return {at:Date.now(),stations,clients:access.list(),arms:access.arms(),reports:[...reports.values()].map(r=>({...r,stale:Date.now()-r.at>15000})),audit:access.data.audit.slice(-100)}
  }
  const server=http.createServer(async(req,res)=>{
    try {
      const url=new URL(req.url,'http://gateway'),pathname=url.pathname
      checkOrigin(req,config.publicOrigin)
      if(pathname==='/health')return json(res,200,{ok:true,service:'isaac-platform'})
      if(pathname==='/platform/config')return json(res,200,{managed:true,localConnectorEnabled:localConnectorEnabled(config)})
      if(pathname==='/login'||pathname==='/manage'||pathname==='/platform-ui.js') {
        const file=pathname==='/platform-ui.js'?'platform-ui.js':'platform.html'
        res.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript; charset=utf-8':'text/html; charset=utf-8','Cache-Control':'no-store'})
        return fs.createReadStream(path.join(root,'web',file)).pipe(res)
      }
      if(pathname==='/downloads/so101-leader-windows.zip') {
        const file=path.join(root,'web',pathname.slice(1));if(!fs.existsSync(file))throw new AccessError('连接工具尚未构建',404)
        res.writeHead(200,{'Content-Type':'application/zip'});return fs.createReadStream(file).pipe(res)
      }
      if(pathname==='/platform/login'&&req.method==='POST') {
        const input=await body(req),result=access.login(input.password,req.socket.remoteAddress)
        return json(res,200,{ok:true,principal:result.principal},{'Set-Cookie':cookie(result.token)})
      }
      if(pathname==='/platform/pair'&&req.method==='POST') {
        const input=await body(req),result=access.redeem(input.code,input,req.socket.remoteAddress)
        return json(res,200,{ok:true,...(result.principal.role==='device'?{token:result.token}:{}),principal:result.principal},{'Set-Cookie':cookie(result.token)})
      }
      if(pathname==='/platform/connector/connect'&&req.method==='POST') {
        const peer=assertLocalConnector(req,config)
        access.rateLimit('lan:'+peer)
        const input=await body(req)
        if(!/^[a-zA-Z0-9_-]{8,80}$/.test(input.clientId||''))throw new AccessError('采集器编号无效',400)
        const choices=config.stations.map(({id,name})=>({id,name}))
        let stationId=input.stationId
        if(stationId!==undefined&&typeof stationId!=='string')throw new AccessError('体验台编号无效',400)
        if(!stationId&&choices.length===1)stationId=choices[0].id
        if(!choices.some(s=>s.id===stationId))return json(res,200,{ok:false,chooseStation:true,stations:choices})
        if(live.has(stationId))throw new AccessError('体验台正在被另一连接工具使用，请先停止原工具',409)
        const previous=requestToken(req)
        if(previous) {
          try {
            const principal=access.lookup(previous)
            checkLanCredential(req,principal,config)
            if(principal.role==='device'&&principal.accessMode==='lan'&&principal.clientId===input.clientId&&principal.stationId===stationId)
              return json(res,200,{ok:true,token:previous,principal,stations:choices})
          } catch {}
        }
        // A native LAN grant can only control its selected station; never issue browser/teacher roles.
        const result=access.issue('device',stationId,{clientId:input.clientId,label:String(input.label||'主臂连接器').slice(0,80),accessMode:'lan',peer})
        access.record('lan-connector',{principalId:result.principal.id,stationId,peer})
        return json(res,200,{ok:true,...result,stations:choices})
      }
      let principal
      try {principal=access.lookup(requestToken(req))}catch(error){
        if(req.method==='GET'&&pathname==='/'){res.writeHead(302,{Location:'/login'});return res.end()}
        throw error
      }
      checkLanCredential(req,principal,config)
      if(pathname==='/platform/me')return json(res,200,{principal,stations:principal.role==='teacher'?config.stations.map(({id,name,storeId})=>({id,name,storeId})):[]})
      if(pathname==='/platform/logout'&&req.method==='POST') {access.revoke(principal.id);if(principal.role==='device')endDevice(principal.stationId,'退出');return json(res,200,{ok:true},{'Set-Cookie':'isaac_access=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict'})}
      if(pathname.startsWith('/platform/')) {
        if(principal.role!=='teacher')throw new AccessError('需要老师权限')
        if(pathname==='/platform/diagnostics'&&req.method==='GET')return json(res,200,await diagnostics())
        const input=await body(req)
        if(pathname==='/platform/codes'&&req.method==='POST')return json(res,200,{code:access.pairCode(input.stationId,input.role),expiresInSeconds:300})
        if(pathname==='/platform/select'&&req.method==='POST') {access.station(input.stationId);principal.stationId=input.stationId;access.save();return json(res,200,{ok:true})}
        if(pathname==='/platform/arms/approve'&&req.method==='POST') {access.approveArm(input.armId,input.calibrationHash);return json(res,200,{ok:true})}
        if(pathname==='/platform/revoke'&&req.method==='POST') {
          if(input.id===principal.id)throw new AccessError('请使用退出登录',400)
          access.revoke(input.id);for(const row of live.values())if(row.principal.id===input.id)row.ws.close(1000,'老师已解除配对')
          return json(res,200,{ok:true})
        }
        throw new AccessError('接口不存在',404)
      }
      if(!principal.stationId){res.writeHead(302,{Location:'/manage'});return res.end()}
      const station=access.station(principal.stationId)
      if(pathname.startsWith('/api/')&&!allowed(principal,req.method,pathname))throw new AccessError('此角色不能执行这个操作')
      if(pathname==='/api/config'&&req.method==='GET'&&config.proxyStreaming) {
        const result=await call(station,'/api/config'),origin=new URL(config.publicOrigin)
        return json(res,200,{...result,stream:{...result.stream,
          signalHost:origin.hostname,signalPort:Number(origin.port||443),
          signalPath:`/platform/stream/${station.id}`,forceWSS:true}})
      }
      if(pathname==='/api/stream/client-report'&&req.method==='POST') {
        const input=await body(req),report={at:Date.now(),clientId:principal.id,stationId:station.id,surface:String(input.surface||'').slice(0,24),visible:input.visible===true}
        for(const key of ['width','height','frames','time','fps','mbps','dropped','rttMs','jitterMs','decodeMs','presentedFrames','lastPresentedAgeMs'])if(Number.isFinite(input[key])&&input[key]>=0)report[key]=input[key]
        reports.set(principal.id,report)
        for(const [key,row] of reports)if(Date.now()-row.at>3600000)reports.delete(key)
        return json(res,200,{ok:true})
      }
      if(pathname==='/api/teleop/disengage'&&req.method==='POST')endDevice(station.id,'操作者停止了同步')
      // Never relay caller-selected host, authorization or internal worker headers.
      const headers={'X-Isaac-Worker-Key':serviceKey}
      for(const name of ['content-type','content-length','accept','range'])if(req.headers[name])headers[name]=req.headers[name]
      const secure=workerOrigin(station).startsWith('https:')
      const upstream=(secure?https:http).request(workerUrl(station,url.pathname+url.search),{method:req.method,headers,agent:secure?secureAgent:readAgent},reply=>{
        res.writeHead(reply.statusCode,Object.fromEntries(Object.entries(reply.headers).filter(([name])=>!['set-cookie','connection','transfer-encoding'].includes(name))))
        reply.pipe(res)
      })
      upstream.setTimeout(300000,()=>upstream.destroy(Error('实例响应超时')))
      upstream.on('error',()=>{if(!res.headersSent)json(res,502,{ok:false,error:'仿真实例连接失败'});else res.destroy()})
      req.on('aborted',()=>upstream.destroy());res.on('close',()=>{if(!res.writableEnded)upstream.destroy()});req.pipe(upstream)
    }catch(error){if(!res.headersSent)json(res,error.status||500,{ok:false,error:error.status?error.message:'服务暂不可用'});else res.destroy()}
  })
  const wss=new WebSocketServer({noServer:true,maxPayload:16384,perMessageDeflate:false})
  server.on('upgrade',(req,socket,head)=>{
    try {
      checkOrigin(req,config.publicOrigin)
      if(new URL(req.url,'http://gateway').pathname.startsWith('/platform/stream/')) {
        const principal=access.lookup(requestToken(req))
        checkLanCredential(req,principal,config)
        return streamProxy.upgrade(req,socket,head,principal)
      }
      if(new URL(req.url,'http://gateway').pathname!=='/platform/teleop')throw new AccessError('Not found',404)
      const principal=access.lookup(requestToken(req)),station=access.station(principal.stationId)
      checkLanCredential(req,principal,config)
      if(principal.role!=='device'||live.has(station.id))throw new AccessError('体验台已有采集器连接',409)
      wss.handleUpgrade(req,socket,head,ws=>connectDevice(ws,principal,station,requestToken(req),req))
    }catch(e){socket.end(`HTTP/1.1 ${e.status||403} Rejected\r\nConnection: close\r\n\r\n`)}
  })
  function connectDevice(ws,principal,station,credential,request) {
    const row={connectedAt:Date.now(),ws,principal,metadata:null,token:null,launchId:null,latest:null,busy:false,engaging:false,samples:0,dropped:0,lastAt:0,lastRetry:0,ackMs:0,windowAt:Date.now(),windowCount:0}
    live.set(station.id,row)
    const send=value=>{if(ws.readyState===WebSocket.OPEN){if(ws.bufferedAmount>65536)ws.close(1013,'客户端接收过慢');else ws.send(JSON.stringify(value))}}
    let nextNetworkCheck=0
    const valid=()=>{try{if(Date.now()>=nextNetworkCheck){checkLanCredential(request,principal,config);nextNetworkCheck=Date.now()+1000}return access.lookup(credential).id===principal.id}catch{return false}}
    const release=async token=>{if(token)try{await call(station,'/api/teleop/disengage',{token})}catch{}}
    async function engage() {
      if(row.engaging||!row.metadata||ws.readyState!==WebSocket.OPEN||Date.now()-row.lastRetry<1000)return
      row.engaging=true;row.lastRetry=Date.now()
      try {
        const status=await call(station,'/api/status'),session=status.bridge?.result?.session
        if(session?.status!=='ready'||session.robotId!=='so101')throw Error('请先选择机械臂关卡')
        const generation=`${session.serverId || "legacy"}:${session.launchId}`
        const input={source:principal.id,requestId:`${principal.id.slice(0,16)}:${generation}`}
        const result=await call(station,'/api/teleop/engage',input)
        if(ws.readyState!==WebSocket.OPEN||!valid()){await release(result.teleop.token);return}
        row.token=result.teleop.token;row.launchId=generation;row.latest=null
        send({type:'ready',token:row.token,launchId:row.launchId,limits:session.robot.joint_limits,serverTime:Date.now()})
      }catch(error){send({type:'waiting',message:error.message})}finally{row.engaging=false}
    }
    async function pump() {
      if(row.busy||!row.latest||!row.token||ws.readyState!==WebSocket.OPEN)return
      const sample=row.latest;row.latest=null
      if(Date.now()-sample.receivedAt>200){row.dropped++;return}
      row.busy=true
      try {
        const started=performance.now()
        const result=await call(station,'/api/teleop',{positions:sample.positions,seq:sample.seq,token:row.token,expiresAt:sample.expiresAt},600)
        row.ackMs=Math.round(performance.now()-started)
        if(result.applied){row.samples++;send({type:'applied',seq:sample.seq,rate_hz:result.rate_hz,bridgeMs:result.bridge_ms,ackMs:row.ackMs})}
        else if(result.reengage||/not engaged/.test(result.reason||'')){row.token=null;await engage()}
      }catch(error){row.dropped++;send({type:'sample-error',message:error.message})}
      finally{row.busy=false;if(row.latest)setImmediate(pump)}
    }
    ws.on('message',raw=>{
      try {
        if(!valid())return ws.close(1008,'凭证已失效')
        if(Date.now()-row.windowAt>1000){row.windowAt=Date.now();row.windowCount=0}
        if(++row.windowCount>120)return ws.close(1008,'采样发送过快')
        const data=JSON.parse(raw)
        if(data.type==='clock')return send({type:'clock',echo:data.echo,serverTime:Date.now()})
        if(data.type==='hello') {
          if(row.metadata)throw Error('already identified')
          access.bindArm({armId:data.armId,driver:data.driver,calibrationHash:data.calibrationHash})
          if([...live.values()].some(other=>other!==row&&other.metadata?.armId===data.armId))throw Error('这台机械臂已绑定其他体验台')
          row.metadata={clientId:principal.clientId,armId:String(data.armId).slice(0,80),driver:data.driver,calibrationHash:String(data.calibrationHash).slice(0,64),port:String(data.port||'').slice(0,32)}
          access.record('device-connected',{stationId:station.id,principalId:principal.id,...row.metadata});engage();return
        }
        if(data.type!=='sample'||!Number.isSafeInteger(data.seq)||data.seq<=0)throw Error('invalid sample')
        if(!Number.isFinite(data.capturedAt)||Date.now()-data.capturedAt>250||data.capturedAt-Date.now()>100){row.dropped++;return}
        if(data.launchId!==row.launchId||!row.token){row.dropped++;engage();return}
        if(row.latest)row.dropped++
        row.latest={positions:data.positions,seq:data.seq,receivedAt:Date.now(),expiresAt:data.capturedAt+250};row.lastAt=Date.now();pump()
      }catch(error){send({type:'error',message:error.message,fatal:!row.metadata});if(!row.metadata)ws.close(1008,'设备配置无效')}
    })
    const timer=setInterval(()=>{if(!valid())ws.close(1008,'凭证过期');else if(!row.metadata&&Date.now()-row.connectedAt>5000)ws.close(1008,'设备未完成识别');else if(!row.token)engage();else if(row.lastAt&&Date.now()-row.lastAt>5000)ws.close(1000,'采集数据已停止')},1000)
    ws.on('error',()=>{})
    ws.on('close',()=>{clearInterval(timer);row.latest=null;if(live.get(station.id)===row)live.delete(station.id);release(row.token)})
  }
  const close=()=>{streamProxy.close();for(const row of live.values())row.ws.terminate();wss.close();readAgent.destroy();secureAgent.destroy()}
  server.on('close',close)
  return {server,access,diagnostics,close}
}
