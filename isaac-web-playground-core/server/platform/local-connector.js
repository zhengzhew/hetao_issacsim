import os from 'node:os'
import {AccessError} from './access.js'

export function peerAddress(req) {
  const address = req.socket?.remoteAddress || ''
  return address.startsWith('::ffff:') ? address.slice(7) : address
}
function ipv4(address) {
  const parts = String(address).split('.')
  if (parts.length !== 4 || parts.some(p => !/^\d{1,3}$/.test(p) || Number(p) > 255)) return null
  return parts.reduce((value, part) => ((value << 8) | Number(part)) >>> 0, 0)
}
export function assertLocalConnector(req, config, interfaces = os.networkInterfaces()) {
  const policy = config.localConnector
  if (!policy?.enabled || config.publicOrigin) throw new AccessError('此服务器未启用局域网免配对', 403)
  // Native clients only. A browser must retain its existing role and station.
  if (req.headers.origin || Object.keys(req.headers).some(key => key.startsWith('sec-fetch-'))) {
    throw new AccessError('浏览器请使用原有登录和体验台配对', 403)
  }
  if (Object.keys(req.headers).some(key => key === 'forwarded' || key.startsWith('x-forwarded-') || key === 'x-real-ip')) {
    throw new AccessError('免配对连接仅接受直接局域网连接', 403)
  }
  const peer = peerAddress(req)
  if (peer === '127.0.0.1' || peer === '::1') return peer
  const remote = ipv4(peer)
  if (remote === null) throw new AccessError('免配对连接仅支持本机或指定 WLAN 同一 IPv4 子网', 403)
  for (const name of policy.interfaces || []) {
    for (const item of interfaces[name] || []) {
      if (item.internal || !['IPv4', 4].includes(item.family)) continue
      const address = ipv4(item.address), mask = ipv4(item.netmask)
      if (address === null || mask === null || mask === 0 || item.address.startsWith('169.254.')) continue
      // Reject malformed masks and network/broadcast addresses.
      const inverse = (~mask) >>> 0
      if ((inverse & (inverse + 1)) !== 0) continue
      if (((remote & mask) >>> 0) === ((address & mask) >>> 0)
          && (remote & inverse) !== 0 && ((remote & inverse) >>> 0) !== inverse) return peer
    }
  }
  throw new AccessError('这台电脑不在服务器允许的 WLAN 同一子网内', 403)
}
export function checkLanCredential(req, principal, config) {
  if (principal.accessMode === 'lan') {
    const peer = assertLocalConnector(req, config)
    if (peer !== principal.peer) throw new AccessError('连接电脑地址已变化，请重新连接', 403)
  }
}
