import fs from 'node:fs'
import path from 'node:path'
import net from 'node:net'

export function workerOrigin(station) {
  return validateOrigin(station.workerOrigin || `http://127.0.0.1:${station.webPort}`, 'workerOrigin')
}

export function validateOrigin(value, label) {
  let url
  try { url = new URL(value) } catch { throw Error(`Invalid ${label}`) }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) throw Error(`Invalid ${label}: use an HTTP(S) origin`)
  return url.origin
}

export function validHost(value) {
  return typeof value === 'string' && (net.isIP(value) > 0 ||
    /^(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$/.test(value))
}

export function runtimePaths(root, env = process.env) {
  return {
    config: path.resolve(env.ISAAC_PLATFORM_CONFIG || path.join(root, 'configs/platform.json')),
    data: path.resolve(env.ISAAC_PLATFORM_DATA_DIR || path.join(root, 'run/platform')),
  }
}

export function readWorkerKey(env = process.env) {
  const key = env.ISAAC_WORKER_KEY_FILE
    ? fs.readFileSync(env.ISAAC_WORKER_KEY_FILE, 'utf8').trim()
    : env.ISAAC_WORKER_KEY
  if (key && !/^[A-Za-z0-9_-]{40,100}$/.test(key)) throw Error('Invalid worker key')
  return key || ''
}

export function stationEnvironment(root, directory, station, key, env = process.env) {
  const streamHost = station.streamHost || env.ISAAC_STREAM_HOST || '127.0.0.1'
  const fps = String(env.ISAAC_STREAM_FPS || station.fps || 30)
  return {
    ...env, PORT: String(station.webPort),
    ISAAC_WEB_HOST: station.webHost || '127.0.0.1', ISAAC_WORKER_KEY: key,
    ISAAC_BRIDGE_HOST: station.bridgeHost || '127.0.0.1', ISAAC_BRIDGE_PORT: String(station.bridgePort),
    ISAAC_STREAM_RENDERER: 'native', ISAAC_STREAM_HOST: streamHost,
    ISAAC_SIGNAL_HOST: station.signalHost || station.bridgeHost || '127.0.0.1',
    ISAAC_PUBLIC_IP: station.publicIp || env.ISAAC_PUBLIC_IP || streamHost,
    ISAAC_SIGNAL_PORT: String(station.signalPort), ISAAC_MEDIA_PORT: String(station.mediaPort),
    ISAAC_STREAM_WIDTH: String(station.width || 1920), ISAAC_STREAM_HEIGHT: String(station.height || 1080),
    ISAAC_STREAM_FPS: fps, ISAAC_RENDER_WIDTH: String(station.width || 1920),
    ISAAC_RENDER_HEIGHT: String(station.height || 1080),
    ISAAC_UPLOAD_DIR: path.join(directory, station.id, 'uploads'),
    ISAAC_CATALOG_DIR: path.join(root, 'configs'),
    ISAAC_DEFAULT_SCENE: 'challenge-arm', ISAAC_DEFAULT_ROBOT: 'so101',
  }
}

// Assets are published as immutable versions by the image build. User uploads
// live alongside this directory and are never removed or replaced.
export function prepareStationAssets(root, directory, station, env = process.env) {
  const uploads = path.join(directory, station.id, 'uploads')
  fs.mkdirSync(uploads, {recursive: true})
  const source = path.resolve(env.ISAAC_CHALLENGE_ASSETS_DIR || path.join(root, 'uploads/challenges'))
  const manifest = path.join(source, 'sha256.json')
  if (!fs.existsSync(manifest)) {
    if (env.ISAAC_CHALLENGE_ASSETS_DIR) throw Error('Configured challenge asset manifest is missing')
    return uploads // Existing Windows installs may not have a manifest.
  }
  const rawChecks = JSON.parse(fs.readFileSync(manifest, 'utf8'))
  if (!rawChecks || Array.isArray(rawChecks) || typeof rawChecks !== 'object') throw Error('Invalid asset manifest')
  const checks = Object.create(null)
  for (const [rawName, hash] of Object.entries(rawChecks)) {
    // Early Windows asset fetchers wrote backslashes into this JSON.
    const name = rawName.replaceAll('\\', '/')
    if (Object.hasOwn(checks, name)) throw Error('Duplicate asset path')
    checks[name] = hash
  }
  const destination = path.join(uploads, 'challenges')
  for (const [name, hash] of Object.entries(checks)) {
    if (!name || name.split('/').some(p => !p || p === '.' || p === '..') ||
        /[\\:\x00-\x1f]/.test(name) || !/^[a-f0-9]{64}$/.test(hash)) throw Error('Invalid asset manifest')
  }
  const marker = path.join(directory, station.id, 'assets-version.json')
  const version = JSON.stringify(checks)
  if (fs.existsSync(marker) && fs.readFileSync(marker, 'utf8') === version &&
      Object.keys(checks).every(name => fs.existsSync(path.join(destination, name)))) return uploads
  // Validate the complete source before replacing any managed asset.
  return copyCheckedAssets(source, destination, checks, marker, version, uploads)
}

import {createHash} from 'node:crypto'
function copyCheckedAssets(source, destination, checks, marker, version, uploads) {
  for (const [name, expected] of Object.entries(checks)) {
    const file = path.join(source, name)
    if (!fs.realpathSync(file).startsWith(fs.realpathSync(source) + path.sep)) throw Error('Asset escapes source')
    if (createHash('sha256').update(fs.readFileSync(file)).digest('hex') !== expected) throw Error(`Asset checksum mismatch: ${name}`)
  }
  fs.mkdirSync(destination, {recursive: true})
  for (const name of Object.keys(checks)) {
    const target = path.join(destination, name)
    fs.mkdirSync(path.dirname(target), {recursive: true})
    if (!fs.realpathSync(path.dirname(target)).startsWith(fs.realpathSync(destination) + path.sep) &&
        fs.realpathSync(path.dirname(target)) !== fs.realpathSync(destination)) throw Error('Asset escapes destination')
    fs.copyFileSync(path.join(source, name), target + '.installing')
    fs.renameSync(target + '.installing', target)
  }
  fs.writeFileSync(marker + '.tmp', version)
  fs.renameSync(marker + '.tmp', marker)
  return uploads
}
