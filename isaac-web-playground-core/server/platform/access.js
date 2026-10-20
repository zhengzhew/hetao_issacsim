import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
export const randomToken = () => crypto.randomBytes(32).toString('base64url')
export const digest = value => crypto.createHash('sha256').update(String(value)).digest('hex')
export class AccessError extends Error { constructor(message, status = 403) { super(message); this.status = status } }
export class AccessStore {
  constructor(directory, stations, clock = Date.now) {
    this.directory = directory; this.stations = stations; this.clock = clock
    fs.mkdirSync(directory, {recursive:true})
    this.file = path.join(directory, 'access.json')
    if (fs.existsSync(this.file)) this.data = JSON.parse(fs.readFileSync(this.file, 'utf8'))
    else {
      const password = randomToken(), salt = crypto.randomBytes(16).toString('hex')
      this.data = {salt, passwordHash: crypto.scryptSync(password, salt, 32).toString('hex'), workerKey:randomToken(), credentials:{}, codes:{}, audit:[]}
      fs.writeFileSync(path.join(directory, 'teacher-password.txt'), password + '\n', {mode:0o600})
      this.save()
    }
    this.data.arms ||= {}
    this.failures = new Map()
    this.cleanup()
  }
  save() {
    fs.writeFileSync(this.file + '.tmp', JSON.stringify(this.data, null, 2), {mode:0o600})
    fs.renameSync(this.file + '.tmp', this.file)
  }
  cleanup() {
    for (const group of ['credentials','codes']) for (const [key,value] of Object.entries(this.data[group])) if (value.expires <= this.clock()) delete this.data[group][key]
  }
  record(action, details={}) {
    this.data.audit.push({at:this.clock(), action, ...details})
    this.data.audit = this.data.audit.slice(-1000); this.save()
  }
  rateLimit(peer) {
    let row = this.failures.get(peer)
    if (!row || this.clock()-row.at>60000) row={at:this.clock(), count:0}
    this.failures.set(peer,row)
    if (++row.count > 15) throw new AccessError('尝试过于频繁，请一分钟后再试',429)
    if (this.failures.size>1000) for (const [key,value] of this.failures) if (this.clock()-value.at>60000) this.failures.delete(key)
  }
  issue(role, stationId=null, metadata={}) {
    this.cleanup()
    if (Object.keys(this.data.credentials).length>500) throw new AccessError('连接数量已达上限',429)
    const token=randomToken()
    const principal={id:crypto.randomUUID(), role, stationId, expires:this.clock()+12*3600000, ...metadata}
    this.data.credentials[digest(token)]=principal; this.save()
    return {token, principal}
  }
  login(password, peer) {
    this.rateLimit(peer)
    const test=crypto.scryptSync(String(password).slice(0,256),this.data.salt,32)
    if (!crypto.timingSafeEqual(test,Buffer.from(this.data.passwordHash,'hex'))) throw new AccessError('老师密码不正确',401)
    return this.issue('teacher')
  }
  lookup(token) {
    const p=this.data.credentials[digest(token || '')]
    if (!p || p.expires <= this.clock()) throw new AccessError('连接已过期，请重新配对',401)
    return p
  }
  station(id) {
    const station=this.stations.find(s=>s.id===id)
    if (!station) throw new AccessError('体验台不存在',404)
    return station
  }
  pairCode(stationId, role) {
    this.station(stationId)
    if (!['operator','device'].includes(role)) throw new AccessError('配对角色无效',400)
    this.cleanup()
    if (Object.keys(this.data.codes).length>=100) throw new AccessError('配对码过多',429)
    const code=crypto.randomBytes(6).toString('hex').toUpperCase()
    this.data.codes[digest(code)]={stationId,role,expires:this.clock()+300000}; this.save()
    return code
  }
  redeem(code, metadata, peer) {
    this.rateLimit(peer)
    const key=digest(String(code).trim().toUpperCase()), grant=this.data.codes[key]
    if (!grant || grant.expires<=this.clock()) throw new AccessError('配对码无效或已过期',401)
    if (grant.role==='device' && !/^[a-zA-Z0-9_-]{8,80}$/.test(metadata.clientId || '')) throw new AccessError('采集器编号无效',400)
    if (grant.role==='operator' && Object.values(this.data.credentials).some(p=>p.role==='operator'&&p.stationId===grant.stationId&&p.expires>this.clock())) throw new AccessError('体验台已有浏览器，请老师先解除旧配对',409)
    delete this.data.codes[key]
    const result=this.issue(grant.role, grant.stationId, {clientId:String(metadata.clientId||'').slice(0,80), label:String(metadata.label||'').slice(0,80)})
    this.record('paired',{principalId:result.principal.id, stationId:grant.stationId, role:grant.role})
    return result
  }
  bindArm(metadata) {
    const {armId,driver,calibrationHash}=metadata
    if (typeof armId!=='string'||!armId.trim()||armId!==armId.trim()||armId.length>80||/[\x00-\x1f]/.test(armId)) throw new AccessError('机械臂编号无效',400)
    if (driver!=='desheng-se-v401'||! /^[a-f0-9]{64}$/.test(calibrationHash||'')) throw new AccessError('驱动或校准文件指纹无效',400)
    const key=digest(armId),current=this.data.arms[key],profile={armId,driver,calibrationHash}
    if (!current) {
      if (Object.keys(this.data.arms).length>=500) throw new AccessError('机械臂登记数量已达上限',429)
      this.data.arms[key]={...profile,registeredAt:this.clock()};this.record('arm-registered',profile);return
    }
    if (current.driver===driver&&current.calibrationHash===calibrationHash) return
    current.pending={...profile,at:this.clock()};this.record('arm-profile-change-requested',profile)
    throw new AccessError('该机械臂的驱动或校准文件发生变化，请老师在管理页核对后确认，再重新连接',409)
  }
  approveArm(armId, calibrationHash) {
    const current=this.data.arms[digest(armId)],pending=current?.pending
    if (!pending||pending.calibrationHash!==calibrationHash) throw new AccessError('待确认的校准文件已变化，请刷新后核对',409)
    Object.assign(current,pending,{updatedAt:this.clock()});delete current.pending
    this.record('arm-profile-approved',{armId,calibrationHash})
  }
  arms() { return Object.values(this.data.arms).map(p=>({...p})) }
  revoke(id) {
    for (const [key,p] of Object.entries(this.data.credentials)) if (p.id===id) delete this.data.credentials[key]
    this.record('revoked',{principalId:id})
  }
  list() { this.cleanup(); return Object.values(this.data.credentials).map(p=>({...p})) }
}
export function requestToken(req) {
  const bearer=/^Bearer ([A-Za-z0-9_-]{40,100})$/.exec(req.headers.authorization||'')
  if (bearer) return bearer[1]
  return /(?:^|;\s*)isaac_access=([A-Za-z0-9_-]{40,100})(?:;|$)/.exec(req.headers.cookie||'')?.[1] || ''
}
export function checkOrigin(req, publicOrigin) {
  if (!req.headers.origin) return
  const expected=publicOrigin || `http://${req.headers.host}`
  if (req.headers.origin!==expected) throw new AccessError('跨站请求被拒绝')
}
export function allowed(principal, method, pathname) {
  if (principal.role==='teacher') return true
  if (principal.role==='device') return method==='GET' && ['/api/status','/api/teleop/status','/api/config'].includes(pathname)
  if (principal.role!=='operator') return false
  if (method==='GET') return ['/api/config','/api/status','/api/catalog','/api/session','/api/challenges','/api/robot','/api/camera','/api/teleop/status','/api/policy','/api/stream.mjpg'].includes(pathname)
  return method==='POST' && ['/api/challenges/start','/api/challenges/action','/api/session/launch','/api/control','/api/robot/joints','/api/robot/reset','/api/camera','/api/stream/client-report','/api/teleop/disengage'].includes(pathname)
}
