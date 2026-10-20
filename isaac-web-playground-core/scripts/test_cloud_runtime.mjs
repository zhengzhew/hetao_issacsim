import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import {once} from 'node:events'
import {spawn} from 'node:child_process'
import {createHash} from 'node:crypto'
import {createGateway, validateConfig} from '../server/platform/gateway.js'
import {runtimePaths, readWorkerKey, stationEnvironment, prepareStationAssets} from '../server/platform/runtime.js'
const root = path.resolve(import.meta.dirname, '..')
const room = (id = 'cloud-1') => ({id, name: id, webPort: 18081, bridgePort: 18765, signalPort: 19100, mediaPort: 17998})
const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'isaac-cloud-test-'))
function cleanup(p) {
  assert.ok(p.startsWith(path.join(os.tmpdir(), 'isaac-cloud-test-')))
  fs.rmSync(p, {recursive: true, force: true})
}

test('remote workers may reuse ports on different hosts, but not on the same host', () => {
  const a = {...room(), workerOrigin: 'http://10.8.0.2:18081'}
  const b = {...room('cloud-2'), workerOrigin: 'http://10.8.0.3:18081'}
  validateConfig({port: 8080, stations: [a, b]})
  assert.throws(() => validateConfig({port: 8080, stations: [a, {...b, workerOrigin: a.workerOrigin}]}), /duplicate port/)
  for (const value of ['file:///tmp/a', 'http://user:pass@host', 'http://host/path', 'http://host/?token=x']) {
    assert.throws(() => validateConfig({port: 8080, stations: [{...a, workerOrigin: value}]}), /Invalid workerOrigin/)
  }
  assert.throws(() => validateConfig({port: 8080, stations: [{...a, streamHost: 'http://host/path'}]}), /Invalid streamHost/)
})

test('per-station video routing is independent of private bridge and data paths', () => {
  const station = {...room(), streamHost: '10.8.0.9', publicIp: '10.8.0.9', bridgeHost: '127.0.0.1', fps: 30}
  const env = stationEnvironment(root, '/persistent', station, 'x'.repeat(43), {ISAAC_STREAM_HOST: 'old-host'})
  assert.equal(env.ISAAC_STREAM_HOST, '10.8.0.9')
  assert.equal(env.ISAAC_SIGNAL_HOST, '127.0.0.1')
  assert.equal(env.ISAAC_BRIDGE_HOST, '127.0.0.1')
  assert.equal(env.ISAAC_STREAM_FPS, '30')
  assert.equal(env.ISAAC_UPLOAD_DIR, path.join('/persistent', 'cloud-1', 'uploads'))
  assert.equal(runtimePaths(root, {}).data, path.join(root, 'run/platform'))
  assert.equal(readWorkerKey({ISAAC_WORKER_KEY: 'x'.repeat(43)}), 'x'.repeat(43))
  assert.throws(() => readWorkerKey({ISAAC_WORKER_KEY: 'short'}), /Invalid worker key/)
})

test('managed assets update by version without deleting user uploads and reject corrupt downloads', () => {
  const directory = temp()
  try {
    const source = path.join(directory, 'assets'), data = path.join(directory, 'data')
    fs.mkdirSync(source)
    const env = {ISAAC_CHALLENGE_ASSETS_DIR: source}
    const publish = (text, override) => {
      fs.writeFileSync(path.join(source, 'robot.usd'), text)
      fs.writeFileSync(path.join(source, 'sha256.json'), JSON.stringify({'robot.usd': override || createHash('sha256').update(text).digest('hex')}))
    }
    publish('version one')
    const uploads = prepareStationAssets(root, data, room(), env)
    fs.writeFileSync(path.join(uploads, 'personal.usd'), 'keep me')
    publish('version two')
    prepareStationAssets(root, data, room(), env)
    assert.equal(fs.readFileSync(path.join(uploads, 'challenges/robot.usd'), 'utf8'), 'version two')
    assert.equal(fs.readFileSync(path.join(uploads, 'personal.usd'), 'utf8'), 'keep me')
    publish('broken', 'a'.repeat(64))
    assert.throws(() => prepareStationAssets(root, data, room(), env), /checksum mismatch/)
    assert.equal(fs.readFileSync(path.join(uploads, 'challenges/robot.usd'), 'utf8'), 'version two')
    fs.writeFileSync(path.join(source, 'sha256.json'), JSON.stringify({'../escape': 'a'.repeat(64)}))
    assert.throws(() => prepareStationAssets(root, data, room(), env), /Invalid asset manifest/)
  } finally { cleanup(directory) }
})

test('Windows asset manifest separators remain portable', () => {
  const directory = temp()
  try {
    const source = path.join(directory, 'assets')
    fs.mkdirSync(path.join(source, 'models'), {recursive: true})
    fs.writeFileSync(path.join(source, 'models/robot.usd'), 'model')
    fs.writeFileSync(path.join(source, 'sha256.json'), JSON.stringify({
      'models\\robot.usd': createHash('sha256').update('model').digest('hex'),
    }))
    const uploads = prepareStationAssets(root, path.join(directory, 'data'), room(), {ISAAC_CHALLENGE_ASSETS_DIR: source})
    assert.equal(fs.readFileSync(path.join(uploads, 'challenges/models/robot.usd'), 'utf8'), 'model')
  } finally { cleanup(directory) }
})

test('configured worker endpoint and key are used for proxy and diagnostics; callers cannot override them', async () => {
  const directory = temp(), calls = []
  const worker = http.createServer((req, res) => {
    calls.push({url: req.url, key: req.headers['x-isaac-worker-key']})
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify({ok: true, from: 'configured-worker'}))
  }).listen(0, '127.0.0.1')
  await once(worker, 'listening')
  let gateway
  try {
    const workerKey = 's'.repeat(43)
    const station = {...room(), workerOrigin: `http://127.0.0.1:${worker.address().port}`}
    gateway = createGateway({root, directory, workerKey, config: {port: 0, stations: [station]}})
    gateway.server.listen(0, '127.0.0.1')
    await once(gateway.server, 'listening')
    const token = gateway.access.issue('operator', station.id).token
    const base = `http://127.0.0.1:${gateway.server.address().port}`
    const result = await fetch(base + '/api/config?workerOrigin=http://attacker.invalid', {
      headers: {Authorization: `Bearer ${token}`, 'X-Isaac-Worker-Key': 'forged'},
    })
    assert.equal((await result.json()).from, 'configured-worker')
    await gateway.diagnostics()
    assert.equal(calls.length, 3)
    assert.ok(calls.every(c => c.key === workerKey))
  } finally {
    if (gateway) { gateway.close(); await new Promise(resolve => gateway.server.close(resolve)) }
    await new Promise(resolve => worker.close(resolve))
    cleanup(directory)
  }
})

test('standalone worker boots without Kit, requires its secret and advertises configured video address', {timeout: 15000}, async () => {
  const directory = temp()
  const portServer = http.createServer().listen(0, '127.0.0.1')
  await once(portServer, 'listening')
  const port = portServer.address().port
  await new Promise(resolve => portServer.close(resolve))
  const station = {...room(), webPort: port, streamHost: '10.8.0.9'}
  const configFile = path.join(directory, 'platform.json'), keyFile = path.join(directory, 'key')
  fs.writeFileSync(configFile, JSON.stringify({port: 8080, stations: [station]}))
  fs.writeFileSync(keyFile, 's'.repeat(43))
  const assets = path.join(directory, 'assets')
  fs.mkdirSync(assets)
  fs.writeFileSync(path.join(assets, 'sha256.json'), '{}')
  const child = spawn(process.execPath, ['server/station-main.js'], {cwd: root, windowsHide: true,
    env: {...process.env, ISAAC_PLATFORM_CONFIG: configFile, ISAAC_PLATFORM_DATA_DIR: path.join(directory, 'data'),
      ISAAC_STATION_ID: station.id, ISAAC_WORKER_KEY_FILE: keyFile,
      ISAAC_CHALLENGE_ASSETS_DIR: assets, ISAAC_DIR: 'nonexistent-no-kit-expected'}, stdio: ['ignore', 'pipe', 'pipe']})
  let errors = ''; child.stderr.on('data', value => { errors += value })
  child.stdout.resume()
  const exited = once(child, 'exit')
  try {
    const base = `http://127.0.0.1:${port}`
    let response
    for (let n = 0; n < 60; n++) {
      if (child.exitCode !== null) throw Error(errors || 'Worker exited')
      try { response = await fetch(base + '/api/config', {signal: AbortSignal.timeout(200)}); break } catch {}
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    assert.ok(response, errors || 'Worker did not start')
    assert.equal(response.status, 401)
    const cfg = await (await fetch(base + '/api/config', {headers: {'X-Isaac-Worker-Key': 's'.repeat(43)}})).json()
    assert.equal(cfg.stream.host, station.streamHost)
    assert.equal(cfg.defaultRobotId, 'so101')
    assert.equal(cfg.stream.fps, 30)
  } finally {
    child.kill()
    await exited
    cleanup(directory)
  }
})

test('external gateway restarts with persisted access state and never spawns a station', {timeout: 15000}, async () => {
  const directory = temp()
  const portServer = http.createServer().listen(0, '127.0.0.1')
  await once(portServer, 'listening')
  const port = portServer.address().port
  await new Promise(resolve => portServer.close(resolve))
  const configFile = path.join(directory, 'platform.json'), keyFile = path.join(directory, 'key')
  const data = path.join(directory, 'persistent')
  fs.writeFileSync(configFile, JSON.stringify({host: '127.0.0.1', port, stations: [room()]}))
  fs.writeFileSync(keyFile, 's'.repeat(43))
  let saved
  try {
    for (let pass = 0; pass < 2; pass++) {
      const child = spawn(process.execPath, ['server/platform-main.js'], {cwd: root, windowsHide: true,
        env: {...process.env, ISAAC_PLATFORM_CONFIG: configFile, ISAAC_PLATFORM_DATA_DIR: data,
          ISAAC_PLATFORM_MODE: 'external', ISAAC_WORKER_KEY_FILE: keyFile, ISAAC_DIR: 'not-installed'},
        stdio: ['ignore', 'pipe', 'pipe']})
      child.stdout.resume()
      let errors = ''; child.stderr.on('data', value => { errors += value })
      const exited = once(child, 'exit')
      try {
        let response
        for (let n = 0; n < 60; n++) {
          if (child.exitCode !== null) throw Error(errors || 'Gateway exited')
          try { response = await fetch(`http://127.0.0.1:${port}/health`, {signal: AbortSignal.timeout(200)}); break } catch {}
          await new Promise(resolve => setTimeout(resolve, 100))
        }
        assert.equal(response?.status, 200, errors || 'Gateway did not start')
        const accessFile = path.join(data, 'access.json')
        const access = JSON.parse(fs.readFileSync(accessFile, 'utf8'))
        if (pass === 0) {
          // A persisted device binding must survive a new gateway process.
          access.credentials['p'.repeat(64)] = {id: 'persist-test', role: 'device', stationId: 'cloud-1', expires: Date.now() + 60000}
          fs.writeFileSync(accessFile, JSON.stringify(access))
          saved = access.passwordHash
        } else {
          assert.equal(access.passwordHash, saved)
          assert.equal(access.credentials['p'.repeat(64)].stationId, 'cloud-1')
        }
        assert.equal(fs.existsSync(path.join(data, 'cloud-1')), false)
        assert.equal(fs.existsSync(path.join(data, 'cloud-1-web.log')), false)
      } finally { child.kill(); await exited }
    }
  } finally { cleanup(directory) }
})
