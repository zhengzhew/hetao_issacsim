import http from 'node:http'
import {AccessError, requestToken} from './access.js'

// Only the selected station's signaling is proxied. Video remains direct WebRTC UDP.
export function createStreamProxy({config, access}) {
  const active = new Set()
  function upgrade(req, socket, head, principal) {
    const url = new URL(req.url, 'http://gateway')
    const station = access.station(principal.stationId)
    if (!config.proxyStreaming || !['teacher', 'operator'].includes(principal.role) ||
        url.pathname !== `/platform/stream/${station.id}/sign_in`) throw new AccessError('不能连接这个体验台的画面')
    const credential = requestToken(req), stationId = station.id
    const valid = () => {
      try {
        const current = access.lookup(credential)
        return current.id === principal.id && current.stationId === stationId &&
          ['teacher', 'operator'].includes(current.role)
      } catch { return false }
    }
    const headers = {Connection: 'Upgrade', Upgrade: 'websocket'}
    for (const name of ['sec-websocket-key', 'sec-websocket-version', 'sec-websocket-protocol', 'sec-websocket-extensions'])
      if (req.headers[name]) headers[name] = req.headers[name]
    const upstream = http.request({hostname: station.signalHost || station.bridgeHost || '127.0.0.1',
      port: station.signalPort, path: '/sign_in' + url.search, method: 'GET', headers})
    let peer, timer, finished = false
    const close = () => {
      if (finished) return
      finished = true; clearInterval(timer); active.delete(close)
      upstream.destroy(); peer?.destroy(); socket.destroy()
    }
    active.add(close)
    socket.on('error', close); socket.on('close', close)
    upstream.on('error', close)
    upstream.setTimeout(5000, close)
    upstream.on('response', () => { socket.end('HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n'); upstream.destroy() })
    upstream.on('upgrade', (response, connected, buffer) => {
      peer = connected
      if (finished || !valid()) return close()
      upstream.setTimeout(0)
      const lines = ['HTTP/1.1 101 Switching Protocols']
      for (const name of ['upgrade', 'connection', 'sec-websocket-accept', 'sec-websocket-protocol', 'sec-websocket-extensions'])
        if (response.headers[name]) lines.push(`${name}: ${response.headers[name]}`)
      socket.write(lines.join('\r\n') + '\r\n\r\n')
      if (buffer.length) socket.write(buffer)
      if (head.length) peer.write(head)
      peer.on('error', close); peer.on('close', close)
      socket.pipe(peer); peer.pipe(socket)
      // Revocation, expiry and a teacher switching stations close the old stream.
      timer = setInterval(() => { if (!valid()) close() }, 1000)
      timer.unref()
    })
    upstream.end()
  }
  return {upgrade, close() { for (const close of [...active]) close() }}
}
