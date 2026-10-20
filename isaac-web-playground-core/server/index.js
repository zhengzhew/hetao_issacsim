import http from 'node:http'
import fs from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Agent } from './agent.js'
import { BridgeChannel } from './bridge-channel.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const WEB = path.join(ROOT, 'web')
const CONFIGS = path.join(ROOT, 'configs')
const VERSION = '0.2.1'

function loadDotEnv() {
  const file = path.join(ROOT, '.env')
  if (!fs.existsSync(file)) return
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const i = line.indexOf('=')
    if (i < 0) continue
    const key = line.slice(0, i).trim()
    let value = line.slice(i + 1).trim()
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1)
    if (!(key in process.env)) process.env[key] = value
  }
}
loadDotEnv()

function readCatalog(file, key) {
  const parsed = JSON.parse(fs.readFileSync(path.join(CONFIGS, file), 'utf8').replace(/^\uFEFF/, ''))
  if (!Array.isArray(parsed[key])) throw new Error(`${file} must contain array ${key}`)
  return parsed[key]
}

const scenes = readCatalog('scenes.json', 'scenes')
const robots = readCatalog('robots.json', 'robots')
const sceneById = new Map(scenes.map((item) => [item.id, item]))
const robotById = new Map(robots.map((item) => [item.id, item]))

const requestedPort = Number(process.env.PORT || 8080)
const portWasExplicit = Boolean(process.env.PORT)
const renderer = String(process.env.ISAAC_STREAM_RENDERER || 'native').toLowerCase()
if (!['native', 'mock', 'mjpeg'].includes(renderer)) throw new Error('ISAAC_STREAM_RENDERER must be native, mjpeg or mock')

const config = {
  version: VERSION,
  port: requestedPort,
  renderer,
  streamHost: process.env.ISAAC_STREAM_HOST || '127.0.0.1',
  signalHost: process.env.ISAAC_SIGNAL_HOST || process.env.ISAAC_STREAM_HOST || '127.0.0.1',
  signalPort: Number(process.env.ISAAC_SIGNAL_PORT || 49100),
  mediaPort: Number(process.env.ISAAC_MEDIA_PORT || 47998),
  signalPath: process.env.ISAAC_SIGNAL_PATH || '',
  bridgeHost: process.env.ISAAC_BRIDGE_HOST || '127.0.0.1',
  bridgePort: Number(process.env.ISAAC_BRIDGE_PORT || 8765),
  defaultSceneId: process.env.ISAAC_DEFAULT_SCENE || 'warehouse',
  defaultRobotId: process.env.ISAAC_DEFAULT_ROBOT || 'jetbot',
  streamWidth: Number(process.env.ISAAC_STREAM_WIDTH || 1920),
  streamHeight: Number(process.env.ISAAC_STREAM_HEIGHT || 1080),
  streamFps: Number(process.env.ISAAC_STREAM_FPS || 60),
  captureWidth: Number(process.env.ISAAC_CAPTURE_WIDTH || 1280),
  captureHeight: Number(process.env.ISAAC_CAPTURE_HEIGHT || 720),
  captureQuality: Number(process.env.ISAAC_CAPTURE_QUALITY || 80),
  captureFps: Number(process.env.ISAAC_CAPTURE_FPS || 12),
  captureMaxClients: Number(process.env.ISAAC_CAPTURE_MAX_CLIENTS || 16),
  // Uploads land in a directory BOTH processes can see. This server usually
  // runs in WSL and the bridge on Windows, so the same directory has two
  // different path spellings; each side is configured separately.
  uploadDir: process.env.ISAAC_UPLOAD_DIR || path.join(ROOT, 'uploads'),
  uploadMaxBytes: Number(process.env.ISAAC_UPLOAD_MAX_BYTES || 512 * 1024 * 1024),
  // The language model route. This machine reaches Claude through NVIDIA's
  // OpenAI-compatible gateway, not the Anthropic API, so the wire format
  // conversion lives in providers/gateway.js.
  gatewayBaseUrl: process.env.GATEWAY_BASE_URL || '',
  gatewayApiKey: process.env.GATEWAY_API_KEY || '',
  gatewayModel: process.env.GATEWAY_MODEL || 'opus-4-8',
}

let launchInFlight = false

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.wav': 'audio/wav',
}

function json(res, code, data) {
  const body = JSON.stringify(data)
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  })
  res.end(body)
}

async function readJsonBody(req, limit = 64 * 1024) {
  return await new Promise((resolve, reject) => {
    let total = 0
    let body = ''
    req.setEncoding('utf8')
    req.on('data', (chunk) => {
      total += Buffer.byteLength(chunk)
      if (total > limit) {
        reject(new Error('request body too large'))
        req.destroy()
        return
      }
      body += chunk
    })
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}) }
      catch { reject(new Error('invalid JSON body')) }
    })
    req.on('error', reject)
  })
}

/** Last-resort guard: no await inside the capture loop may hang indefinitely. */
function withDeadline(promise, ms, message) {
  let timer
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(message)), ms) }),
  ])
}

function bridgeRequest(op, args = {}, timeoutMs = 1200) {
  const expiresAt = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host: config.bridgeHost, port: config.bridgePort })
    let buffer = ''
    let done = false
    const finish = (err, result) => {
      if (done) return
      done = true
      socket.destroy()
      if (err) reject(err)
      else resolve(result)
    }
    socket.setEncoding('utf8')
    socket.setTimeout(timeoutMs)
    socket.on('connect', () => socket.write(JSON.stringify({ id: `${Date.now()}-${Math.random()}`, op, args, expiresAt }) + '\n'))
    socket.on('data', (chunk) => {
      buffer += chunk
      const nl = buffer.indexOf('\n')
      if (nl < 0) return
      try {
        const msg = JSON.parse(buffer.slice(0, nl))
        if (msg.ok) finish(null, msg.result ?? null)
        else finish(new Error(msg.error || 'bridge request failed'))
      } catch (err) { finish(err) }
    })
    socket.on('timeout', () => finish(new Error('timeout')))
    socket.on('error', (err) => finish(err))
    socket.on('end', () => finish(new Error('bridge closed the connection')))
    socket.on('close', () => finish(new Error('bridge connection closed before replying')))
    // A bridge that dribbles bytes with no newline must not grow without bound.
    const cap = 64 * 1024 * 1024
    socket.on('data', () => { if (buffer.length > cap) finish(new Error('bridge reply exceeded 64 MB')) })
  })
}

async function bridgeStatus() {
  try { return { connected: true, result: await bridgeRequest('ping', {}, 4000) } }
  catch (err) {
    // A busy bridge is not an absent one; the page should say so.
    return { connected: false, busy: launchInFlight, error: err.message }
  }
}

function tcpProbe(host, port, timeoutMs = 700) {
  return new Promise((resolve) => {
    const started = Date.now()
    const socket = net.createConnection({ host, port })
    let done = false
    const finish = (result) => {
      if (done) return
      done = true
      socket.destroy()
      resolve({ ...result, latencyMs: Date.now() - started, host, port })
    }
    socket.setTimeout(timeoutMs)
    socket.on('connect', () => finish({ connected: true }))
    socket.on('timeout', () => finish({ connected: false, error: 'timeout' }))
    socket.on('error', (err) => finish({ connected: false, error: err.message }))
  })
}

async function streamStatus() {
  const [signaling, bridge] = await Promise.all([
    tcpProbe(config.signalHost, config.signalPort),
    bridgeStatus(),
  ])
  return {
    renderer: config.renderer,
    nativeBundleAvailable: fs.existsSync(path.join(WEB, 'native-sdk.js')),
    signaling,
    media: {
      host: config.streamHost,
      port: config.mediaPort,
      protocol: 'udp',
      probe: 'webrtc-session',
      note: 'UDP media is proven by a live WebRTC session; a TCP-style port probe is not meaningful.',
    },
    bridge,
    capture: {
      clients: frameHub.clients.size,
      channel: captureChannel.status,
      framesCaptured: frameHub.framesCaptured,
      writes: frameHub.writes,
      lastFrameAt: frameHub.lastFrame?.at ?? null,
      lastError: frameHub.lastError,
    },
  }
}


// --- MJPEG compatibility stream --------------------------------------------
//
// The native path needs UDP 47998 to reach the browser. Behind a VPN that NATs
// the client that never happens, so this serves the same viewport as
// multipart/x-mixed-replace over the TCP port the page is already loaded from.
// One capture loop feeds every connected client, so N viewers cost the
// simulator the same as one.

const frameHub = {
  clients: new Set(),
  running: false,
  lastFrame: null,
  lastError: null,
  framesCaptured: 0,
  writes: 0,

  add(res) {
    this.clients.add(res)
    // Only if it is actually recent; an old frame makes a dead bridge look live.
    if (this.lastFrame && Date.now() - this.lastFrame.at < 2000) {
      this.writeTo(res, this.lastFrame.mime, this.lastFrame.body)
    }
    if (!this.running) this.run()
  },

  remove(res) {
    this.clients.delete(res)
  },

  async run() {
    this.running = true
    try {
      while (this.clients.size > 0) {
        // Read live settings each frame; existing streams must adopt FPS changes.
        const interval = 1000 / Math.min(60, Math.max(1, config.captureFps))
        const startedAt = Date.now()
        try {
          const frame = await withDeadline(captureChannel.send('capture_frame', {
            width: config.captureWidth,
            height: config.captureHeight,
            quality: config.captureQuality,
          }, 8000), 12000, 'capture timed out')
          const body = Buffer.from(frame.data, 'base64')
          this.lastFrame = { mime: frame.mime, body, at: Date.now() }
          this.lastError = null
          this.broadcast(frame.mime, body)
        } catch (err) {
          this.lastError = err.message
          // Keep the loop alive across scene switches, which block the bridge
          // for as long as the USD stage takes to load.
          await new Promise((resolve) => setTimeout(resolve, 500))
        }
        const elapsed = Date.now() - startedAt
        if (elapsed < interval) await new Promise((resolve) => setTimeout(resolve, interval - elapsed))
      }
    } finally {
      this.running = false
    }
  },

  writeTo(res, mime, body) {
    if (res.writableEnded || res.destroyed) {
      this.clients.delete(res)
      return false
    }
    // Skip a client that cannot keep up rather than buffering frames for it.
    if (res.writableLength > 4 * body.length) return false
    res.write(`--frame\r\nContent-Type: ${mime}\r\nContent-Length: ${body.length}\r\n\r\n`)
    res.write(body)
    res.write('\r\n')
    this.writes += 1
    return true
  },

  broadcast(mime, body) {
    this.framesCaptured += 1
    for (const res of [...this.clients]) this.writeTo(res, mime, body)
  },

}


// --- uploaded assets and the user catalog ----------------------------------

const UPLOAD_EXTENSIONS = new Set(['.usd', '.usda', '.usdc', '.usdz'])
const ID_PATTERN = /^[a-z0-9][a-z0-9-]{1,39}$/

fs.mkdirSync(config.uploadDir, { recursive: true })
const USER_CATALOG_FILE = path.join(config.uploadDir, 'catalog.json')
const MAX_CATALOG_ENTRIES = Number(process.env.ISAAC_MAX_CATALOG_ENTRIES || 200)

/** Serialise read-modify-write sections; Node is single threaded but not atomic across await. */
function makeMutex() {
  let tail = Promise.resolve()
  return (work) => {
    const run = tail.then(work, work)
    tail = run.then(() => {}, () => {})
    return run
  }
}
const catalogLock = makeMutex()
const uploadLocks = new Map()

function withUploadLock(name, work) {
  const previous = uploadLocks.get(name) || Promise.resolve()
  const run = previous.then(work, work)
  const tail = run.then(() => {}, () => {})
  uploadLocks.set(name, tail)
  // Drop the entry only if nothing queued behind us, or the map grows by one
  // per distinct file name for the life of the process.
  tail.then(() => { if (uploadLocks.get(name) === tail) uploadLocks.delete(name) })
  return run
}

// Windows reserves these as device names, extension or not: writing CON.usd
// from WSL succeeds, and the bridge on the Windows side then cannot open it.
const WINDOWS_DEVICE_NAMES = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i

/** Resolve an upload name to a path inside uploadDir, or throw. */
function uploadPath(name) {
  const raw = String(name || '').trim()
  if (raw.includes('\\')) throw new Error('file name may not contain backslashes; use / for folders')
  const cleaned = raw.replace(/^\/+/, '')
  if (!cleaned) throw new Error('a file name is required')
  if (cleaned.length > 180) throw new Error('file name is too long')
  if (!/^[A-Za-z0-9._/-]+$/.test(cleaned)) throw new Error('file name may only contain letters, digits, dot, dash, underscore and /')
  if (cleaned.split('/').some((part) => part === '' || part === '.' || part === '..')) throw new Error('file name may not contain path segments like ".."')
  for (const part of cleaned.split('/')) {
    if (WINDOWS_DEVICE_NAMES.test(part)) throw new Error(`"${part}" is a reserved name on Windows`)
    // A trailing dot or space is silently stripped by Win32, so the bridge
    // would look for a different file than the one that was written.
    if (/[. ]$/.test(part)) throw new Error('a path segment may not end with a dot or a space')
  }
  if (!UPLOAD_EXTENSIONS.has(path.extname(cleaned).toLowerCase())) {
    throw new Error(`only ${[...UPLOAD_EXTENSIONS].join(', ')} files are accepted`)
  }
  const full = path.resolve(config.uploadDir, cleaned)
  const root = path.resolve(config.uploadDir)
  if (full !== root && !full.startsWith(root + path.sep)) throw new Error('file name escapes the upload directory')
  return { cleaned, full }
}

function listUploads() {
  const out = []
  // One unreadable entry, broken symlink or deep tree must not take the whole
  // listing down; the upload directory is shared with another OS.
  const walk = (dir, prefix, depth) => {
    if (depth > 4 || out.length >= 500) return
    let entries
    try { entries = fs.readdirSync(dir, { withFileTypes: true }) }
    catch (err) { console.error('[playground] cannot list', dir, err.message); return }
    for (const entry of entries) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name
      if (entry.isDirectory()) { walk(path.join(dir, entry.name), rel, depth + 1); continue }
      if (!entry.isFile()) continue
      if (!UPLOAD_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) continue
      try {
        const stat = fs.statSync(path.join(dir, entry.name))
        out.push({ name: rel, bytes: stat.size, modified: stat.mtimeMs })
      } catch { /* vanished or unreadable between readdir and stat */ }
      if (out.length >= 500) return
    }
  }
  walk(config.uploadDir, '', 0)
  return out.sort((a, b) => b.modified - a.modified)
}

function readUserCatalog({ strict = false } = {}) {
  if (!fs.existsSync(USER_CATALOG_FILE)) return { scenes: [], robots: [] }
  try {
    const parsed = JSON.parse(fs.readFileSync(USER_CATALOG_FILE, 'utf8').replace(/^\uFEFF/, ''))
    const clean = (list) => (Array.isArray(list) ? list.filter((item) => item && typeof item === 'object' && typeof item.id === 'string') : [])
    return { scenes: clean(parsed.scenes), robots: clean(parsed.robots) }
  } catch (err) {
    console.error('[playground] user catalog unreadable', err.message)
    // Reading degrades to empty so the tool still works, but WRITING on top of
    // an unreadable file would erase every entry it holds.
    if (strict) throw new Error('the catalog file is unreadable; fix or remove catalog.json before adding entries')
    return { scenes: [], robots: [] }
  }
}

async function writeUserCatalog(next) {
  const total = next.scenes.length + next.robots.length
  if (total > MAX_CATALOG_ENTRIES) throw new Error(`the catalog is limited to ${MAX_CATALOG_ENTRIES} entries`)
  const tmp = `${USER_CATALOG_FILE}.${process.pid}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(next, null, 2))
  // The bridge reads this file from the Windows side, where a rename over an
  // open file fails. Retry with an await -- a synchronous spin would freeze the
  // capture loop, and every viewer's picture with it.
  let lastError = null
  for (let attempt = 0; attempt < 12; attempt++) {
    try { fs.renameSync(tmp, USER_CATALOG_FILE); return }
    catch (err) { lastError = err }
    await new Promise((resolve) => setTimeout(resolve, 60))
  }
  fs.rmSync(tmp, { force: true })
  const failure = new Error(`could not update the catalog file: ${lastError?.message}`)
  failure.serverFault = true
  throw failure
}

/** Built-ins plus user entries; a user entry with the same id replaces one. */
function mergedCatalog() {
  const user = readUserCatalog()
  const merge = (base, extra) => {
    const map = new Map(base.map((item) => [item.id, { ...item, source: 'builtin' }]))
    for (const item of extra) map.set(item.id, { ...item, source: 'uploaded' })
    return [...map.values()]
  }
  return { scenes: merge(scenes, user.scenes), robots: merge(robots, user.robots) }
}

const num = (value, name, { min = -1e6, max = 1e6, required = false, fallback = 0 } = {}) => {
  if (value === undefined || value === null || value === '') {
    if (required) throw new Error(`${name} is required`)
    return fallback
  }
  const parsed = Number(value)
  if (typeof value === 'boolean' || !Number.isFinite(parsed)) throw new Error(`${name} must be a number`)
  if (parsed < min || parsed > max) throw new Error(`${name} must be between ${min} and ${max}`)
  return parsed
}

const triple = (value, name, fallback) => {
  if (value === undefined) return fallback
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`${name} must be three numbers`)
  return value.map((v, i) => num(v, `${name}[${i}]`, { min: -1e4, max: 1e4, required: true }))
}

function validateId(id, kind) {
  const value = String(id || '').trim().toLowerCase()
  if (!ID_PATTERN.test(value)) {
    throw new Error(`${kind} id must be 2-40 characters of lowercase letters, digits or dashes, starting with a letter or digit`)
  }
  return value
}

/** Uploaded entries may only point at uploaded files; nothing arbitrary. */
function assetReference(body) {
  const file = String(body?.file || '').trim()
  if (!file) throw new Error('choose an uploaded file')
  const { cleaned, full } = uploadPath(file)
  if (!fs.existsSync(full)) throw new Error(`uploaded file not found: ${cleaned}`)
  return `upload://${cleaned}`
}

function validateSceneEntry(body) {
  return {
    id: validateId(body?.id, 'scene'),
    name: String(body?.name || body?.id || '').trim().slice(0, 80) || String(body?.id),
    description: String(body?.description || '').trim().slice(0, 240),
    asset_path: assetReference(body),
    category: 'uploaded',
    spawn: triple(body?.spawn, 'spawn', [0, 0, 0]),
    camera_eye: triple(body?.camera_eye, 'camera_eye', [4, -5, 3]),
    camera_target: triple(body?.camera_target, 'camera_target', [0, 0, 0.4]),
    mock_world: 'grid',
  }
}

function validateRobotEntry(body) {
  const adapter = String(body?.adapter || '').trim()
  if (!['differential-drive', 'holonomic-drive', 'joint-position'].includes(adapter)) {
    throw new Error('adapter must be differential-drive, holonomic-drive or joint-position')
  }
  const names = Array.isArray(body?.wheel_dof_names) ? body.wheel_dof_names : []
  const cleanNames = names.map((n) => String(n).trim()).filter(Boolean)
  for (const name of cleanNames) {
    // Must match what /api/robot/joints and /api/teleop accept, or the robot
    // is registered but permanently undrivable.
    if (!/^[A-Za-z0-9_.-]{1,60}$/.test(name)) throw new Error(`joint name not usable: ${name}`)
  }
  if (new Set(cleanNames).size !== cleanNames.length) throw new Error('the same joint was selected twice')
  if (cleanNames.length > 32) throw new Error('too many joints selected')
  if (adapter === 'differential-drive' && cleanNames.length !== 2) throw new Error('a differential drive needs exactly two wheel joints')
  if (adapter === 'holonomic-drive' && cleanNames.length < 3) throw new Error('a holonomic drive needs at least three wheel joints')

  const entry = {
    id: validateId(body?.id, 'robot'),
    name: String(body?.name || body?.id || '').trim().slice(0, 80) || String(body?.id),
    description: String(body?.description || '').trim().slice(0, 240),
    adapter,
    asset_path: assetReference(body),
    prim_path: '/World/WebRobot',
    wheel_dof_names: cleanNames,
    spawn_z: num(body?.spawn_z, 'spawn_z', { min: -10, max: 10, fallback: 0.05 }),
    max_linear_speed: num(body?.max_linear_speed, 'max_linear_speed', { min: 0, max: 2, fallback: 0.5 }),
    max_lateral_speed: num(body?.max_lateral_speed, 'max_lateral_speed', { min: 0, max: 2, fallback: 0 }),
    max_angular_speed: num(body?.max_angular_speed, 'max_angular_speed', { min: 0, max: 4, fallback: 1.5 }),
    max_wheel_speed: num(body?.max_wheel_speed, 'max_wheel_speed', { min: 0, max: 200, fallback: 30 }),
    source: 'uploaded',
  }
  if (adapter === 'differential-drive') {
    entry.wheel_radius = num(body?.wheel_radius, 'wheel_radius', { min: 0.001, max: 2, required: true })
    entry.wheel_base = num(body?.wheel_base, 'wheel_base', { min: 0.001, max: 5, required: true })
  }
  if (adapter === 'holonomic-drive') {
    entry.com_prim_subpath = String(body?.com_prim_subpath || '').trim().slice(0, 120)
    if (!entry.com_prim_subpath) throw new Error('a holonomic robot needs com_prim_subpath')
    if (!/^[A-Za-z0-9_][A-Za-z0-9_./-]*$/.test(entry.com_prim_subpath)) {
      throw new Error('com_prim_subpath may only contain letters, digits, underscore, dot, dash and /')
    }
  }
  if (adapter === 'joint-position') {
    // Arms go to the origin unless told otherwise; scene spawns are for bases.
    entry.spawn_at_origin = body?.spawn_at_origin === undefined ? true : Boolean(body.spawn_at_origin)
    if (body?.spawn !== undefined) entry.spawn = triple(body.spawn, 'spawn', [0, 0, 0])
    entry.drive_stiffness = num(body?.drive_stiffness, 'drive_stiffness', { min: 0, max: 1e6, fallback: 120 })
    entry.drive_damping = num(body?.drive_damping, 'drive_damping', { min: 0, max: 1e6, fallback: 25 })
    entry.drive_max_force = num(body?.drive_max_force, 'drive_max_force', { min: 0, max: 1e6, fallback: 60 })
    // A table-top arm with a free root interpenetrates the floor and PhysX
    // diverges to NaN, so anchoring is the default and opting out is explicit.
    entry.fix_root = body?.fix_root === undefined ? true : Boolean(body.fix_root)
    entry.max_depenetration_velocity = num(body?.max_depenetration_velocity, 'max_depenetration_velocity', { min: 0.1, max: 1000, fallback: 5 })
    const home = {}
    for (const [key, value] of Object.entries(body?.home_position || {})) {
      if (!cleanNames.includes(String(key))) continue
      home[String(key)] = num(value, `home_position.${key}`, { min: -100, max: 100 })
    }
    entry.home_position = home
  }
  return entry
}


// --- persistent bridge channel ---------------------------------------------
//
// bridgeRequest() opens a fresh TCP connection per call, which is fine at a few
// requests a second but not for teleoperation: a leader arm streams 30-60
// samples a second and the connection setup alone would dominate the latency.
// This keeps one socket open and matches replies to requests by id.

const teleopChannel = new BridgeChannel(config.bridgeHost, config.bridgePort)
const captureChannel = new BridgeChannel(config.bridgeHost, config.bridgePort)

// The leader may be on someone else's machine, so the stream is rate limited
// rather than trusted to behave -- per source as well as overall, so one
// misbehaving client cannot spend the whole budget and 429 the real leader.
const teleopGuard = {
  limitPerSecond: Number(process.env.ISAAC_TELEOP_MAX_HZ || 120),
  perSourcePerSecond: Number(process.env.ISAAC_TELEOP_MAX_HZ_PER_SOURCE || 80),
  windows: new Map(),
}

function teleopRateOk(source) {
  const now = Date.now()
  const bump = (key, limit) => {
    let entry = teleopGuard.windows.get(key)
    if (!entry || now - entry.start >= 1000) {
      entry = { start: now, count: 0 }
      teleopGuard.windows.set(key, entry)
    }
    entry.count += 1
    return entry.count <= limit
  }
  if (teleopGuard.windows.size > 64) {
    for (const [key, entry] of teleopGuard.windows) {
      if (key !== '*' && now - entry.start >= 2000) teleopGuard.windows.delete(key)
    }
    // A client rotating its token cannot be evicted by age alone.
    while (teleopGuard.windows.size > 256) {
      const oldest = teleopGuard.windows.keys().next().value
      if (oldest === '*') break
      teleopGuard.windows.delete(oldest)
    }
  }
  const globalOk = bump('*', teleopGuard.limitPerSecond)
  const sourceOk = bump(`s:${source}`, teleopGuard.perSourcePerSecond)
  return globalOk && sourceOk
}

function normalizeJointMap(input, label = 'positions') {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error(`${label} must be an object of joint names to numbers`)
  const entries = Object.entries(input)
  if (!entries.length) throw new Error(`${label} is empty`)
  if (entries.length > 64) throw new Error(`${label} has too many joints`)
  const out = {}
  for (const [name, value] of entries) {
    if (!/^[A-Za-z0-9_.-]{1,60}$/.test(name)) throw new Error(`bad joint name: ${name}`)
    out[name] = num(value, name, { min: -1000, max: 1000, required: true })
  }
  return out
}

function normalizeCalibration(input) {
  if (input === undefined || input === null) return undefined
  if (typeof input !== 'object' || Array.isArray(input)) throw new Error('calibration must be an object')
  const out = {}
  for (const [name, spec] of Object.entries(input)) {
    if (!/^[A-Za-z0-9_.-]{1,60}$/.test(name)) throw new Error(`bad joint name: ${name}`)
    if (!spec || typeof spec !== 'object') throw new Error(`calibration for ${name} must be an object`)
    const source = String(spec.source || name)
    if (!/^[A-Za-z0-9_.-]{1,60}$/.test(source)) throw new Error(`bad source joint name: ${source}`)
    const scale = num(spec.scale, `calibration.${name}.scale`, { min: -100, max: 100, fallback: 1 })
    if (scale === 0) throw new Error(`calibration scale for ${name} cannot be zero`)
    out[name] = {
      source,
      offset: num(spec.offset, `calibration.${name}.offset`, { min: -1000, max: 1000, fallback: 0 }),
      scale,
      invert: Boolean(spec.invert),
    }
  }
  return out
}

/** A refusal by the simulator is a conflict; anything else is an outage. */
function bridgeErrorStatus(message) {
  if (/leader arm is driving|only the engaged leader/i.test(message)) return 409
  if (/must be|bad joint|no joints|too many|not joint driven|unknown joints|is empty|required|cannot be zero/i.test(message)) return 400
  return 503
}

function round3(value) { return Math.round(value * 1000) / 1000 }

function normalizeMotion(input) {
  const linear = Number(input?.linear ?? input?.forward ?? 0)
  const lateral = Number(input?.lateral ?? 0)
  const angular = Number(input?.angular ?? input?.yaw ?? 0)
  if (![linear, lateral, angular].every(Number.isFinite)) throw new Error('linear, lateral and angular must be finite numbers')
  if (Math.abs(linear) > 2 || Math.abs(lateral) > 2 || Math.abs(angular) > 4) throw new Error('command exceeds playground safety bounds')
  return {
    linear: round3(linear),
    lateral: round3(lateral),
    angular: round3(angular),
    source: String(input?.source || 'web-keyboard'),
  }
}

/** Only eye/target, only three finite numbers each -- the bridge re-checks. */
function normalizeCamera(body) {
  const axis = (name, value) => {
    if (!Array.isArray(value) || value.length !== 3) throw new Error(`camera ${name} must be an array of three numbers`)
    return value.map((v) => {
      const n = Number(v)
      if (typeof v === 'boolean' || !Number.isFinite(n) || Math.abs(n) > 1e4) throw new Error(`camera ${name} is out of range`)
      return round3(n)
    })
  }
  const out = {}
  if (body?.eye !== undefined) out.eye = axis('eye', body.eye)
  if (body?.target !== undefined) out.target = axis('target', body.target)
  if (!out.eye && !out.target) throw new Error('camera update needs eye or target')
  return out
}

function validateLaunch(body) {
  const sceneId = String(body?.sceneId || '').trim()
  const robotId = String(body?.robotId || '').trim()
  const { scenes: allScenes, robots: allRobots } = mergedCatalog()
  if (!allScenes.some((item) => item.id === sceneId)) throw new Error(`unknown sceneId: ${sceneId}`)
  if (!allRobots.some((item) => item.id === robotId)) throw new Error(`unknown robotId: ${robotId}`)
  return { sceneId, robotId }
}

function serveStatic(pathname, res) {
  const rel = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '')
  const file = path.resolve(WEB, rel)
  if (!file.startsWith(WEB + path.sep) && file !== path.join(WEB, 'index.html')) {
    res.writeHead(403)
    return res.end('forbidden')
  }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404)
    return res.end('not found')
  }
  res.writeHead(200, {
    'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
    'Cache-Control': path.extname(file) === '.html' ? 'no-store' : (['.js', '.css'].includes(path.extname(file)) ? 'no-cache' : 'public, max-age=300'),
  })
  const stream = fs.createReadStream(file)
  stream.on('error', (err) => {
    console.error('[playground] static read failed', file, err.message)
    res.destroy()
  })
  stream.pipe(res)
}

let nativeClientReport = null
async function handle(req, res, url) {
  const workerKey = process.env.ISAAC_WORKER_KEY
  if (workerKey && req.headers['x-isaac-worker-key'] !== workerKey) return json(res, 401, {ok:false,error:'worker authentication required'})
  if (url.pathname === '/api/stream/client-report' && req.method === 'GET') {
    return json(res, 200, { report: nativeClientReport })
  }
  if (url.pathname === '/api/stream/client-report' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const report = { at: Date.now(), surface: String(body.surface || '').slice(0, 24) }
      for (const key of ['width', 'height', 'frames', 'time', 'fps', 'mbps', 'dropped']) {
        if (Number.isFinite(body[key]) && body[key] >= 0) report[key] = body[key]
      }
      nativeClientReport = report
      return json(res, 200, { ok: true })
    } catch { return json(res, 400, { ok: false }) }
  }

  if (url.pathname === '/api/config' && req.method === 'GET') {
    return json(res, 200, {
      version: config.version,
      renderer: config.renderer,
      bridgeHost: config.bridgeHost,
      bridgePort: config.bridgePort,
      defaultSceneId: config.defaultSceneId,
      defaultRobotId: config.defaultRobotId,
      stream: {
        host: config.streamHost,
        signalPort: config.signalPort,
        mediaPort: config.mediaPort,
        signalPath: config.signalPath,
        width: config.streamWidth,
        height: config.streamHeight,
        fps: config.streamFps,
      },
      nativeBundleAvailable: fs.existsSync(path.join(WEB, 'native-sdk.js')),
      agent: { configured: agent.configured, model: agent.label },
      capture: {
        path: '/api/stream.mjpg',
        width: config.captureWidth,
        height: config.captureHeight,
        fps: config.captureFps,
        quality: config.captureQuality,
        maxClients: config.captureMaxClients,
      },
      control: { maxLinear: 2, maxLateral: 2, maxAngular: 4, heartbeatMs: 100 },
    })
  }

  if (url.pathname === '/api/catalog' && req.method === 'GET') {
    return json(res, 200, { ok: true, ...mergedCatalog(), challenges: readCatalog('challenges.json', 'levels') })
  }

  if (url.pathname === '/api/status' && req.method === 'GET') {
    const status = await streamStatus()
    return json(res, 200, { web: true, ...status })
  }

  if (url.pathname === '/api/challenges' && req.method === 'GET') {
    try { return json(res, 200, { ok: true, challenge: await bridgeRequest('challenge_status', {}, 4000) }) }
    catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }
  if (url.pathname === '/api/challenges/start' && req.method === 'POST') {
    if (launchInFlight) return json(res,409,{ok:false,error:'正在准备关卡，请稍等'})
    launchInFlight=true
    try {
      const body=await readJsonBody(req)
      if (!readCatalog('challenges.json','levels').some(x=>x.id===body.id)) throw new Error('未知关卡')
      return json(res,200,{ok:true,...await bridgeRequest('challenge_start',{id:body.id},240000)})
    } catch(err) {return json(res,400,{ok:false,error:err.message})}
    finally {launchInFlight=false}
  }
  if (url.pathname === '/api/challenges/action' && req.method === 'POST') {
    if (launchInFlight) return json(res,409,{ok:false,error:'关卡正在加载'})
    try {
      const body=await readJsonBody(req)
      if (!['sit','stand','roll','kick'].includes(body.action)) throw new Error('未知动作')
      return json(res,200,{ok:true,...await bridgeRequest('challenge_action',{action:body.action},5000)})
    } catch(err) {return json(res,400,{ok:false,error:err.message})}
  }
  if (url.pathname === '/api/session' && req.method === 'GET') {
    try { return json(res, 200, { ok: true, session: await bridgeRequest('get_session', {}, 2000) }) }
    catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/session/launch' && req.method === 'POST') {
    if (launchInFlight) return json(res, 409, { ok: false, error: 'a scene is already loading; wait for it to finish' })
    launchInFlight = true
    try {
      const body = await readJsonBody(req)
      const selection = validateLaunch(body)
      const session = await bridgeRequest('launch_session', selection, 240000)
      return json(res, 200, { ok: true, session })
    } catch (err) {
      return json(res, 400, { ok: false, error: err.message })
    } finally {
      launchInFlight = false
    }
  }

  if (url.pathname === '/api/stream.mjpg' && req.method === 'GET') {
    if (frameHub.clients.size >= config.captureMaxClients) {
      return json(res, 503, { ok: false, error: `too many viewers (limit ${config.captureMaxClients})` })
    }
    res.writeHead(200, {
      'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache',
      'Connection': 'close',
    })
    req.socket.setNoDelay(true)
    // Long enough to survive a scene load (the bridge blocks for minutes), but
    // still bounded so a wedged client cannot keep the capture loop alive.
    req.socket.setTimeout(Number(process.env.ISAAC_STREAM_IDLE_TIMEOUT || 300000), () => req.socket.destroy())
    frameHub.add(res)
    const drop = () => frameHub.remove(res)
    req.on('close', drop)
    req.on('error', drop)
    res.on('error', drop)
    return
  }

  if (url.pathname === '/api/frame.jpg' && req.method === 'GET') {
    const cached = frameHub.lastFrame
    if (cached && Date.now() - cached.at < 1000) {
      res.writeHead(200, { 'Content-Type': cached.mime, 'Content-Length': cached.body.length, 'Cache-Control': 'no-store' })
      return res.end(cached.body)
    }
    try {
      const frame = await bridgeRequest('capture_frame', {
        width: config.captureWidth,
        height: config.captureHeight,
        quality: config.captureQuality,
      }, 8000)
      const body = Buffer.from(frame.data, 'base64')
      res.writeHead(200, { 'Content-Type': frame.mime, 'Content-Length': body.length, 'Cache-Control': 'no-store' })
      return res.end(body)
    } catch (err) {
      return json(res, 503, { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/camera' && req.method === 'GET') {
    try { return json(res, 200, { ok: true, ...(await bridgeRequest('get_camera', {}, 3000)) }) }
    catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/camera' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const op = body?.reset ? 'reset_camera' : 'set_camera'
      const args = op === 'reset_camera' ? {} : normalizeCamera(body)
      return json(res, 200, { ok: true, camera: await bridgeRequest(op, args, 3000) })
    } catch (err) {
      const clientFault = /^camera /.test(err.message) || /JSON|too large/i.test(err.message)
      return json(res, clientFault ? 400 : 503, { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/assets' && req.method === 'GET') {
    return json(res, 200, { ok: true, dir: config.uploadDir, maxBytes: config.uploadMaxBytes, files: listUploads() })
  }

  if (url.pathname === '/api/assets' && req.method === 'POST') {
    // Raw body upload: the file is streamed straight to disk so a large USD
    // never has to fit in memory.
    // Answer, then stop reading: the client may still be pushing hundreds of
    // megabytes that nothing will consume.
    const rejectUpload = (code, body) => { json(res, code, body); req.destroy(); }
    let target
    try { target = uploadPath(url.searchParams.get('name')) }
    catch (err) { return rejectUpload(400, { ok: false, error: err.message }) }

    const declared = Number(req.headers['content-length'] || 0)
    if (declared > config.uploadMaxBytes) {
      return rejectUpload(413, { ok: false, error: `file is larger than the ${Math.round(config.uploadMaxBytes / 1048576)} MB limit` })
    }
    if (fs.existsSync(target.full)) {
      if (url.searchParams.get('overwrite') !== '1') {
        return rejectUpload(409, { ok: false, error: `${target.cleaned} already exists; pass overwrite=1 to replace it` })
      }
      const catalog = readUserCatalog()
      const used = [...catalog.scenes, ...catalog.robots]
        .filter((item) => String(item.asset_path || '').toLowerCase() === `upload://${target.cleaned}`.toLowerCase())
        .map((item) => item.id)
      if (used.length && url.searchParams.get('force') !== '1') {
        return rejectUpload(409, { ok: false, error: `${target.cleaned} is used by ${used.join(', ')}; pass force=1 to replace it anyway` })
      }
    }

    return withUploadLock(target.cleaned, async () => {
    if (req.destroyed || req.readableEnded || res.writableEnded) {
      // The client left while this was queued behind another upload of the
      // same name. Piping a destroyed request would never emit 'end'.
      return
    }
    try { fs.mkdirSync(path.dirname(target.full), { recursive: true }) }
    catch (err) { return json(res, 400, { ok: false, error: `could not create that folder: ${err.message}` }) }
    // Per request, so two uploads of the same name cannot interleave.
    const partial = `${target.full}.${process.pid}.${Date.now().toString(36)}.part`
    const sink = fs.createWriteStream(partial)
    let written = 0
    let failed = null
    const abort = (code, message) => {
      if (failed) return
      failed = message
      sink.destroy()
      fs.rm(partial, { force: true }, () => {})
      // Answer first: destroying the request tears down the shared socket, so
      // a body written afterwards never reaches the client.
      if (!res.headersSent) json(res, code, { ok: false, error: message })
      req.destroy()
    }
    req.on('data', (chunk) => {
      written += chunk.length
      if (written > config.uploadMaxBytes) abort(413, 'upload exceeded the size limit')
    })
    req.on('error', () => abort(400, 'upload connection failed'))
    req.on('aborted', () => abort(400, 'upload was aborted before it finished'))
    sink.on('error', (err) => abort(500, `could not write the file: ${err.message}`))
    req.pipe(sink)
    await new Promise((resolve) => {
      sink.on('close', resolve)
      // If the request dies without emitting 'end', pipe never ends the sink.
      req.on('close', () => { if (!req.readableEnded) { abort(400, 'upload connection closed early'); resolve() } })
    })
    if (failed) return
    if (written === 0) { fs.rmSync(partial, { force: true }); return json(res, 400, { ok: false, error: 'the uploaded file was empty' }) }
    // A body shorter than it declared is a truncated file, not a small one.
    if (declared && written !== declared) {
      fs.rmSync(partial, { force: true })
      return json(res, 400, { ok: false, error: `upload was truncated: got ${written} of ${declared} bytes` })
    }
    try {
      fs.renameSync(partial, target.full)
    } catch (err) {
      fs.rmSync(partial, { force: true })
      return json(res, 409, { ok: false, error: `could not store the file: ${err.message}` })
    }
    return json(res, 201, { ok: true, file: { name: target.cleaned, bytes: written } })
    })
  }

  if (url.pathname.startsWith('/api/assets/') && req.method === 'DELETE') {
    try {
      let requested
      try { requested = decodeURIComponent(url.pathname.slice('/api/assets/'.length)) }
      catch { throw new Error('the file name is not valid percent-encoding') }
      const { cleaned, full } = uploadPath(requested)
      const catalog = readUserCatalog()
      const used = [...catalog.scenes, ...catalog.robots]
        .filter((item) => String(item.asset_path || '').toLowerCase() === `upload://${cleaned}`.toLowerCase())
        .map((item) => item.id)
      if (used.length) return json(res, 409, { ok: false, error: `still used by: ${used.join(', ')}` })
      fs.rmSync(full, { force: true })
      return json(res, 200, { ok: true, removed: cleaned })
    } catch (err) { return json(res, 400, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/assets/inspect' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const { cleaned, full } = uploadPath(body?.file)
      if (!fs.existsSync(full)) return json(res, 404, { ok: false, error: `not found: ${cleaned}` })
      // Must stay under the bridge's own op timeout, or the reply is an empty
      // queue.Empty string and the real cause is lost.
      const result = await bridgeRequest('inspect_asset', { asset_path: `upload://${cleaned}` }, 45000)
      return json(res, 200, { ok: true, file: cleaned, ...result })
    } catch (err) {
      const clientFault = /file name|not found|only .* accepted|required/i.test(err.message)
      return json(res, clientFault ? 400 : 503, { ok: false, error: err.message })
    }
  }

  if ((url.pathname === '/api/catalog/scenes' || url.pathname === '/api/catalog/robots') && req.method === 'POST') {
    const kind = url.pathname.endsWith('scenes') ? 'scenes' : 'robots'
    try {
      const body = await readJsonBody(req)
      const entry = kind === 'scenes' ? validateSceneEntry(body) : validateRobotEntry(body)
      const outcome = await catalogLock(async () => {
        // Read, modify and write with nothing else interleaving, or two
        // concurrent adds each drop the other.
        const current = readUserCatalog({ strict: true })
        const existing = current[kind].findIndex((item) => item.id === entry.id)
        if (existing >= 0 && !body?.replace) {
          return { conflict: `${entry.id} already exists; set replace to overwrite it` }
        }
        if (existing >= 0) current[kind][existing] = entry
        else current[kind].push(entry)
        await writeUserCatalog(current)
        return { ok: true }
      })
      if (outcome.conflict) return json(res, 409, { ok: false, error: outcome.conflict })
      let reloaded = null
      try { reloaded = await bridgeRequest('reload_catalog', {}, 10000) } catch (err) { reloaded = { error: err.message } }
      return json(res, 200, { ok: true, entry, reloaded })
    } catch (err) { return json(res, err.serverFault ? 503 : 400, { ok: false, error: err.message }) }
  }

  if ((url.pathname.startsWith('/api/catalog/scenes/') || url.pathname.startsWith('/api/catalog/robots/')) && req.method === 'DELETE') {
    const kind = url.pathname.startsWith('/api/catalog/scenes/') ? 'scenes' : 'robots'
    let id
    try { id = decodeURIComponent(url.pathname.split('/').pop() || '') }
    catch { return json(res, 400, { ok: false, error: 'the id is not valid percent-encoding' }) }
    try {
      const outcome = await catalogLock(async () => {
        const current = readUserCatalog({ strict: true })
        const next = current[kind].filter((item) => item.id !== id)
        if (next.length === current[kind].length) return { missing: true }
        current[kind] = next
        await writeUserCatalog(current)
        return { ok: true }
      })
      if (outcome.missing) return json(res, 404, { ok: false, error: `no uploaded ${kind.slice(0, -1)} with id ${id}` })
    } catch (err) { return json(res, err.serverFault ? 503 : 400, { ok: false, error: err.message }) }
    try { await bridgeRequest('reload_catalog', {}, 10000) } catch {}
    return json(res, 200, { ok: true, removed: id })
  }

  if (url.pathname === '/api/stream/settings' && req.method === 'GET') {
    return json(res, 200, {
      ok: true,
      width: config.captureWidth, height: config.captureHeight,
      fps: config.captureFps, quality: config.captureQuality,
      estimatedKbPerFrame: Math.round(config.captureWidth * config.captureHeight * 0.09 * (config.captureQuality / 60) / 1024),
    })
  }

  if (url.pathname === '/api/stream/settings' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const next = {
        width: body.width === undefined ? config.captureWidth : num(body.width, 'width', { min: 320, max: 1920, required: true }),
        height: body.height === undefined ? config.captureHeight : num(body.height, 'height', { min: 240, max: 1080, required: true }),
        fps: body.fps === undefined ? config.captureFps : num(body.fps, 'fps', { min: 1, max: 60, required: true }),
        quality: body.quality === undefined ? config.captureQuality : num(body.quality, 'quality', { min: 20, max: 95, required: true }),
      }
      config.captureWidth = Math.round(next.width)
      config.captureHeight = Math.round(next.height)
      config.captureFps = Math.round(next.fps)
      config.captureQuality = Math.round(next.quality)
      console.log(`[playground] stream now ${config.captureWidth}x${config.captureHeight}@${config.captureFps} q=${config.captureQuality}`)
      return json(res, 200, {
        ok: true,
        width: config.captureWidth, height: config.captureHeight,
        fps: config.captureFps, quality: config.captureQuality,
      })
    } catch (err) {
      return json(res, 400, { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/robot/gains' && req.method === 'POST') {
    // Tuning stiffness and damping by editing a config and restarting Isaac is
    // a two minute loop; this makes it a second.
    try {
      const body = await readJsonBody(req)
      const raw = body?.gains
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('gains must be an object of joint names to settings')
      const gains = {}
      for (const [name, spec] of Object.entries(raw)) {
        if (name !== '*' && !/^[A-Za-z0-9_.-]{1,60}$/.test(name)) throw new Error(`bad joint name: ${name}`)
        if (!spec || typeof spec !== 'object') throw new Error(`gains for ${name} must be an object`)
        const clean = {}
        for (const key of ['stiffness', 'damping', 'max_force']) {
          if (spec[key] !== undefined) clean[key] = num(spec[key], `${name}.${key}`, { min: 0, max: 1e6, required: true })
        }
        if (!Object.keys(clean).length) throw new Error(`gains for ${name} is empty`)
        gains[name] = clean
      }
      return json(res, 200, { ok: true, ...(await bridgeRequest('set_drive_gains', { gains }, 8000)) })
    } catch (err) {
      return json(res, bridgeErrorStatus(err.message), { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/robot/joints' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const positions = body?.positions || body?.joints
      if (!positions || typeof positions !== 'object' || Array.isArray(positions)) throw new Error('positions must be an object of joint names to values')
      const cleaned = {}
      for (const [name, value] of Object.entries(positions)) {
        if (!/^[A-Za-z0-9_.-]{1,60}$/.test(name)) throw new Error(`bad joint name: ${name}`)
        cleaned[name] = num(value, name, { min: -100, max: 100, required: true })
      }
      if (!Object.keys(cleaned).length) throw new Error('no joints given')
      if (Object.keys(cleaned).length > 64) throw new Error('too many joints in one command')
      const result = await bridgeRequest('set_joints', { positions: cleaned, relative: Boolean(body?.relative) }, 3000)
      return json(res, 200, { ok: true, result })
    } catch (err) {
      return json(res, bridgeErrorStatus(err.message), { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/teleop/engage' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const args = { source: String(body?.source || 'leader').slice(0, 120).replace(/[^\x20-\x7e]/g, ''), requestId: String(body?.requestId || '').slice(0, 64) }
      const calibration = normalizeCalibration(body?.calibration)
      if (calibration) args.calibration = calibration
      return json(res, 200, { ok: true, teleop: await teleopChannel.send('teleop_engage', args, 5000) })
    } catch (err) {
      return json(res, bridgeErrorStatus(err.message), { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/teleop/disengage' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req).catch(() => ({}))
      const token = String(body?.token || '').slice(0, 40)
      return json(res, 200, { ok: true, teleop: await teleopChannel.send('teleop_disengage', token ? { token } : {}, 5000) })
    } catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/teleop/calibrate' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const calibration = normalizeCalibration(body?.calibration)
      if (!calibration) throw new Error('calibration is required')
      const token = String(body?.token || '').slice(0, 40)
      return json(res, 200, { ok: true, ...(await teleopChannel.send('teleop_calibrate', token ? { calibration, token } : { calibration }, 5000)) })
    } catch (err) {
      return json(res, bridgeErrorStatus(err.message), { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/teleop/status' && req.method === 'GET') {
    try { return json(res, 200, { ok: true, channel: teleopChannel.status, teleop: await bridgeRequest('teleop_status', {}, 1000) }) }
    catch (err) { return json(res, 503, { ok: false, channel: teleopChannel.status, error: err.message }) }
  }

  if (url.pathname === '/api/teleop' && req.method === 'POST') {
    // The hot path. Keep the work per sample to validation plus one write on
    // the connection that is already open.
    try {
      const body = await readJsonBody(req, 16 * 1024)
      const token = String(body?.token || '').slice(0, 40)
      if (!teleopRateOk(`${req.socket.remoteAddress || 'anon'}|${token}`)) {
        return json(res, 429, { ok: false, error: `teleop is limited to ${teleopGuard.perSourcePerSecond} samples per second per leader` })
      }
      const positions = normalizeJointMap(body?.positions || body?.joints)
      const seq = Math.max(0, Math.min(2 ** 31, Number(body?.seq) || 0))
      const remaining = body.expiresAt == null ? 250 : Math.min(250, Number(body.expiresAt) - Date.now())
      if (!Number.isFinite(remaining) || remaining <= 0) return json(res, 408, {ok:false,error:'sample expired'})
      const result = await teleopChannel.send('teleop_sample', { positions, seq, token }, remaining)
      return json(res, 200, { ok: true, ...result })
    } catch (err) {
      const clientFault = /must be|bad joint|is empty|too many/i.test(err.message)
      return json(res, clientFault ? 400 : 503, { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/agent/events' && req.method === 'GET') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-store',
      Connection: 'keep-alive',
    })
    res.write(`data: ${JSON.stringify({ type: 'hello', configured: agent.configured, model: agent.label, busy: agent.busy })}\n\n`)
    agentClients.add(res)
    const drop = () => agentClients.delete(res)
    req.on('close', drop)
    req.on('error', drop)
    return
  }

  if (url.pathname === '/api/agent/status' && req.method === 'GET') {
    return json(res, 200, {
      ok: true,
      configured: agent.configured,
      model: agent.label,
      busy: agent.busy,
      turns: agent.messages.length,
      listeners: agentClients.size,
    })
  }

  if (url.pathname === '/api/agent/message' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const text = String(body?.text || '').trim()
      if (!text) return json(res, 400, { ok: false, error: 'say something' })
      if (text.length > 4000) return json(res, 400, { ok: false, error: 'that message is too long' })
      if (agent.busy) return json(res, 409, { ok: false, error: 'the assistant is still working on the previous message' })
      if (!agent.configured) {
        return json(res, 503, { ok: false, error: 'no language model is configured on the server' })
      }
      // Accepted, not awaited: the work streams over /api/agent/events.
      agent.send(text).catch((err) => emitAgentEvent({ type: 'error', message: err.message }))
      return json(res, 202, { ok: true })
    } catch (err) {
      return json(res, 400, { ok: false, error: err.message })
    }
  }

  if (url.pathname === '/api/agent/reset' && req.method === 'POST') {
    agent.reset()
    emitAgentEvent({ type: 'reset' })
    return json(res, 200, { ok: true })
  }

  if (url.pathname === '/api/mock/state' && req.method === 'GET') {
    if (config.renderer !== 'mock' || !globalThis.__ISAAC_MOCK_STATE__) return json(res, 404, { ok: false, error: 'mock renderer is not active' })
    return json(res, 200, { ok: true, state: globalThis.__ISAAC_MOCK_STATE__ })
  }

  if (url.pathname === '/api/scene' && req.method === 'GET') {
    try { return json(res, 200, { ok: true, result: await bridgeRequest('get_scene_info', {}, 5000) }) }
    catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/robot' && req.method === 'GET') {
    try {
      const info = await bridgeRequest('get_robot_info')
      const pose = await bridgeRequest('get_robot_pose')
      return json(res, 200, { ok: true, info, pose: pose?.pose ?? null })
    } catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/robot/reset' && req.method === 'POST') {
    try { return json(res, 200, { ok: true, result: await bridgeRequest('reset_robot') }) }
    catch (err) { return json(res, bridgeErrorStatus(err.message), { ok: false, error: err.message }) }
  }

  // --- the legged robot's policies ------------------------------------------
  //
  // Everything here has been reachable only over raw TCP to the bridge, which
  // means it has been unavailable to anyone actually using the page.
  if (url.pathname === '/api/policy' && req.method === 'GET') {
    try { return json(res, 200, { ok: true, policy: await bridgeRequest('policy_status', {}, 3000) }) }
    catch (err) { return json(res, 503, { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/policy' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      const action = String(body.action || '')
      const ops = {
        engage: ['policy_engage', {}],
        disengage: ['policy_disengage', {}],
        kick: ['policy_kick', { side: body.side === 'left' ? 'left' : 'right' }],
        ball: ['reset_ball', {}],
        pitch: ['spawn_arena', { side: num(body.side ?? 2.5, 'side', { min: 0.5, max: 40 }) }],
        follow: ['camera_follow', { on: body.on !== false }],
        select: ['policy_select', { file: String(body.file || '') }],
      }
      if (!(action in ops)) return json(res, 400, { ok: false, error: `unknown policy action: ${action}` })
      const [op, args] = ops[action]
      // A kick is half a second of robot; the rest answer immediately.
      const result = await bridgeRequest(op, args, action === 'select' ? 20000 : 8000)
      return json(res, 200, { ok: true, result })
    } catch (err) { return json(res, bridgeErrorStatus(err.message), { ok: false, error: err.message }) }
  }

  if (url.pathname === '/api/control' && req.method === 'POST') {
    try {
      const body = await readJsonBody(req)
      if (!['teleop', 'motion'].includes(body.type)) return json(res, 400, { ok: false, error: 'unsupported control type' })
      const command = normalizeMotion(body)
      try {
        const result = await bridgeRequest('motion', command, 800)
        return json(res, 200, { ok: true, delivered: true, command, result })
      } catch (err) {
        return json(res, 503, { ok: false, delivered: false, command, error: err.message, hint: 'Command generation is working; the Isaac bridge or selected robot adapter is unavailable.' })
      }
    } catch (err) { return json(res, 400, { ok: false, error: err.message }) }
  }

  return serveStatic(url.pathname, res)
}


// --- the assistant ----------------------------------------------------------
//
// One conversation, shared by whoever has the page open -- the same shape as
// the simulation itself, which is also singular. Events are broadcast over SSE
// so every viewer sees the same work happening.

const agentClients = new Set()

function emitAgentEvent(event) {
  const frame = `data: ${JSON.stringify(event)}\n\n`
  for (const res of [...agentClients]) {
    if (res.writableEnded || res.destroyed) { agentClients.delete(res); continue }
    try { res.write(frame) } catch { agentClients.delete(res) }
  }
}

/** One capture, shared with the MJPEG loop when it is recent enough. */
async function captureFrameForAgent() {
  const cached = frameHub.lastFrame
  if (cached && Date.now() - cached.at < 1500) {
    return {
      mime: cached.mime,
      data: cached.body.toString('base64'),
      width: config.captureWidth,
      height: config.captureHeight,
    }
  }
  const frame = await bridgeRequest('capture_frame', {
    width: config.captureWidth,
    height: config.captureHeight,
    quality: config.captureQuality,
  }, 20000)
  return { mime: frame.mime, data: frame.data, width: frame.width, height: frame.height }
}

const agent = new Agent({
  config,
  emit: emitAgentEvent,
  deps: { bridgeRequest, captureFrame: captureFrameForAgent, mergedCatalog, config },
})

const server = http.createServer((req, res) => {
  let url
  try {
    url = new URL(req.url, `http://${req.headers.host || 'localhost'}`)
  } catch {
    res.writeHead(400, { 'Content-Type': 'text/plain' })
    return res.end('bad request')
  }
  handle(req, res, url).catch((err) => {
    console.error('[playground] request failed', req.method, url.pathname, err)
    if (res.headersSent) return res.destroy()
    res.writeHead(500, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: false, error: 'internal error' }))
  })
})

// Nothing above should be able to take the process down, but a detached
// capture loop or a socket error can still reject with no one listening.
process.on('unhandledRejection', (err) => console.error('[playground] unhandled rejection', err))
process.on('uncaughtException', (err) => console.error('[playground] uncaught exception', err))

function listen(port, attemptsLeft = 20) {
  const onError = (err) => {
    server.off('listening', onListening)
    if (err.code === 'EADDRINUSE' && !portWasExplicit && attemptsLeft > 0) {
      console.warn(`[playground] port ${port} is busy; trying ${port + 1}`)
      setTimeout(() => listen(port + 1, attemptsLeft - 1), 40)
      return
    }
    throw err
  }
  const onListening = () => {
    server.off('error', onError)
    const actual = server.address().port
    config.port = actual
    console.log(`isaac-web-playground http://0.0.0.0:${actual}`)
    console.log(`version=${config.version}`)
    console.log(`renderer=${config.renderer}`)
      console.log(`webrtc=${config.streamHost}:${config.signalPort}/tcp + ${config.mediaPort}/udp`)
    console.log(`mjpeg=/api/stream.mjpg ${config.captureWidth}x${config.captureHeight}@${config.captureFps} q=${config.captureQuality}`)
    console.log(`bridge=${config.bridgeHost}:${config.bridgePort}`)
      const merged = mergedCatalog()
    console.log(`catalog=${merged.scenes.length} scenes + ${merged.robots.length} robots ` +
      `(${merged.scenes.filter((s) => s.source === 'uploaded').length}+${merged.robots.filter((r) => r.source === 'uploaded').length} uploaded)`)
    console.log(`uploads=${config.uploadDir} limit=${Math.round(config.uploadMaxBytes / 1048576)}MB`)
    console.log(`teleop=/api/teleop max=${teleopGuard.limitPerSecond}Hz over a persistent bridge channel`)
    console.log(`assistant=${agent.configured ? agent.label : 'not configured (set GATEWAY_BASE_URL / GATEWAY_API_KEY)'}`)
    if (config.renderer === 'native') console.log(`native_sdk_bundle=${fs.existsSync(path.join(WEB, 'native-sdk.js')) ? 'ready' : 'missing (run npm install && npm run build:native)'}`)
  }
  server.once('error', onError)
  server.once('listening', onListening)
  server.listen(port, process.env.ISAAC_WEB_HOST || '127.0.0.1')
}

listen(config.port)
