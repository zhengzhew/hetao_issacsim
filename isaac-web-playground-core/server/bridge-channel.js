import net from 'node:net'

export class BridgeChannel {
  constructor(host, port) {
    this.host = host
    this.port = port
    this.socket = null
    this.connecting = null
    this.pending = new Map()
    this.nextId = 1
    this.buffer = ''
    this.connectedAt = null
    this.failures = 0
    this.retryAfter = 0
    this.connectTimeoutMs = Number(process.env.ISAAC_BRIDGE_CONNECT_TIMEOUT || 1500)
  }

  connect() {
    if (this.socket && !this.socket.destroyed) return Promise.resolve(this.socket)
    if (this.connecting) return this.connecting
    if (Date.now() < this.retryAfter) {
      return Promise.reject(new Error('bridge is unreachable; backing off'))
    }
    this.connecting = new Promise((resolve, reject) => {
      const socket = net.createConnection({ host: this.host, port: this.port })
      // Without this the OS connect timeout (minutes) applies, and send()
      // awaits connect() before arming its own timer.
      socket.setTimeout(this.connectTimeoutMs, () => socket.destroy(new Error('bridge connect timed out')))
      socket.setEncoding('utf8')
      socket.setNoDelay(true)
      const fail = (err) => {
        this.connecting = null
        // Exponential-ish backoff, capped, so a dead bridge is not hammered.
        this.failures = Math.min(this.failures + 1, 6)
        this.retryAfter = Date.now() + Math.min(2000, 50 * 2 ** this.failures)
        this.teardown(err)
        reject(err)
      }
      socket.once('error', fail)
      socket.once('connect', () => {
        socket.off('error', fail)
        this.socket = socket
        this.connecting = null
        this.connectedAt = Date.now()
        this.failures = 0
        this.retryAfter = 0
        socket.setTimeout(0)
        socket.on('data', (chunk) => { if (this.socket === socket) this.onData(chunk) })
        socket.on('error', (err) => { if (this.socket === socket) this.teardown(err) })
        socket.on('close', () => { if (this.socket === socket) this.teardown(new Error('bridge channel closed')) })
        resolve(socket)
      })
    })
    return this.connecting
  }

  onData(chunk) {
    this.buffer += chunk
    let nl
    while ((nl = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, nl)
      this.buffer = this.buffer.slice(nl + 1)
      if (!line.trim()) continue
      let msg
      try { msg = JSON.parse(line) } catch { continue }
      const waiter = this.pending.get(msg.id)
      if (!waiter) continue
      this.pending.delete(msg.id)
      clearTimeout(waiter.timer)
      if (msg.ok) waiter.resolve(msg.result ?? null)
      else waiter.reject(new Error(msg.error || 'bridge request failed'))
    }
    // A wedged bridge must not grow this without bound.
    if (this.buffer.length > 16 * 1024 * 1024) this.teardown(new Error('bridge reply too large'))
  }

  teardown(err) {
    const socket = this.socket
    this.socket = null
    this.buffer = ''
    this.connectedAt = null
    if (socket) socket.destroy()
    for (const [, waiter] of this.pending) {
      clearTimeout(waiter.timer)
      waiter.reject(err)
    }
    this.pending.clear()
  }

  async send(op, args = {}, timeoutMs = 2000) {
    const expiresAt = Date.now() + timeoutMs
    await this.connect()
    const remaining = expiresAt - Date.now()
    if (remaining <= 0) throw new Error(`${op} expired while connecting`)
    const id = `c${this.nextId++}`
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        if (op === 'teleop_sample') this.teardown(new Error('expired control channel'))
        reject(new Error(`bridge did not answer ${op} in ${timeoutMs}ms`))
      }, remaining)
      this.pending.set(id, { resolve, reject, timer })
      try {
        this.socket.write(JSON.stringify({ id, op, args, expiresAt }) + '\n')
      } catch (err) {
        this.pending.delete(id)
        clearTimeout(timer)
        reject(err)
      }
    })
  }

  get status() {
    return {
      connected: Boolean(this.socket),
      since: this.connectedAt,
      inFlight: this.pending.size,
      failures: this.failures,
      backingOffFor: Math.max(0, this.retryAfter - Date.now()),
    }
  }
}
