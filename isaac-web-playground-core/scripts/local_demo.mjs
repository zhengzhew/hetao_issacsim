import fs from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const scenes = JSON.parse(fs.readFileSync(path.join(ROOT, 'configs/scenes.json'), 'utf8')).scenes
const robots = JSON.parse(fs.readFileSync(path.join(ROOT, 'configs/robots.json'), 'utf8')).robots
const sceneById = new Map(scenes.map((x) => [x.id, x]))
const robotById = new Map(robots.map((x) => [x.id, x]))

function findFreePort(start, host = '127.0.0.1', span = 50) {
  return new Promise(async (resolve, reject) => {
    for (let port = start; port < start + span; port += 1) {
      const free = await new Promise((done) => {
        const probe = net.createServer()
        probe.once('error', () => done(false))
        probe.once('listening', () => probe.close(() => done(true)))
        probe.listen(port, host)
      })
      if (free) return resolve(port)
    }
    reject(new Error(`no free port found from ${start}`))
  })
}

const bridgePort = await findFreePort(Number(process.env.ISAAC_DEMO_BRIDGE_PORT || 18765))
const signalPort = await findFreePort(Number(process.env.ISAAC_DEMO_SIGNAL_PORT || 49110))
const webPort = await findFreePort(Number(process.env.ISAAC_DEMO_WEB_PORT || 18081), '0.0.0.0')
const mediaPort = 47998

process.env.ISAAC_STREAM_RENDERER = 'mock'
process.env.ISAAC_STREAM_HOST = '127.0.0.1'
process.env.ISAAC_SIGNAL_PORT = String(signalPort)
process.env.ISAAC_MEDIA_PORT = String(mediaPort)
process.env.ISAAC_BRIDGE_HOST = '127.0.0.1'
process.env.ISAAC_BRIDGE_PORT = String(bridgePort)
process.env.ISAAC_DEFAULT_SCENE = 'warehouse'
process.env.ISAAC_DEFAULT_ROBOT = 'jetbot'
process.env.PORT = String(webPort)

const WORLD_DEFS = {
  warehouse: {
    bounds: [-6.2, 6.2, -4.4, 4.4], target: [4.7, 2.9],
    rects: [[-3.8,2.1,2.2,.72],[-.8,2.1,2.2,.72],[2.2,2.1,2.2,.72],[-3.8,-.5,2.2,.72],[-.8,-.5,2.2,.72],[2.2,-.5,2.2,.72],[-5,-3,.72,.72],[-4.15,-3,.72,.72],[4.9,-2.75,.82,.82]],
  },
  'warehouse-multi': {
    bounds: [-8, 8, -6, 6], target: [6.3, 4.5],
    rects: [[-6,2.8,2.5,.65],[-2.5,2.8,2.5,.65],[1,2.8,2.5,.65],[4.5,2.8,2.0,.65],[-6,.4,2.5,.65],[-2.5,.4,2.5,.65],[1,.4,2.5,.65],[4.5,.4,2.0,.65],[-6,-2,2.5,.65],[-2.5,-2,2.5,.65],[1,-2,2.5,.65],[4.5,-2,2.0,.65]],
  },
  'simple-room': {
    bounds: [-4.5, 4.5, -3.6, 3.6], target: [3.1, 2.2],
    rects: [[-1.0,-.7,2.0,1.4],[-3.8,1.8,1.2,.8],[2.7,-2.4,.8,.8]],
  },
  grid: { bounds: [-7,7,-5,5], target: [5.5,3.8], rects: [] },
}

const state = {
  x: -1.5, y: -1.5, theta: 0, linear: 0, lateral: 0, angular: 0,
  updatedAt: Date.now(), lastMotionAt: 0, watchdogStop: false, collision: false, goalReached: false,
  session: null,
}
globalThis.__ISAAC_MOCK_STATE__ = state

const WATCHDOG_MS = 450

function currentScene() { return sceneById.get(state.session?.sceneId) || scenes[0] }
function currentRobot() { return robotById.get(state.session?.robotId) || robots[0] }
function currentWorld() { return WORLD_DEFS[currentScene().mock_world] || WORLD_DEFS.grid }

function spawnFor(scene, robot) {
  const s = scene.spawn || [0, 0, 0]
  return [Number(s[0] || 0), Number(s[1] || 0), Number(robot.spawn_z || 0)]
}

function robotInfo(robot = currentRobot()) {
  const lateral = robot.adapter === 'holonomic-drive'
  return {
    configured: true, ready: true, id: robot.id, name: robot.name,
    adapter: `mock-${robot.adapter}`, prim_path: '/World/MockRobot', wheel_dof_names: robot.wheel_dof_names,
    max_linear_speed: robot.max_linear_speed, max_lateral_speed: robot.max_lateral_speed, max_angular_speed: robot.max_angular_speed,
    capabilities: { forward: true, lateral, yaw: true }, mock: true,
  }
}

function sessionInfo() {
  return {
    status: 'ready', sceneId: state.session.sceneId, robotId: state.session.robotId,
    launchId: state.session.launchId, launchedAt: state.session.launchedAt, error: null,
    scene: currentScene(), robot: robotInfo(), sceneUrl: currentScene().asset_path, mock: true,
  }
}

function launchSession(sceneId, robotId) {
  if (!sceneById.has(sceneId)) throw new Error(`unknown scene id: ${sceneId}`)
  if (!robotById.has(robotId)) throw new Error(`unknown robot id: ${robotId}`)
  const previousId = state.session?.launchId || 0
  state.session = { sceneId, robotId, launchId: previousId + 1, launchedAt: Date.now() / 1000 }
  const [x,y] = spawnFor(currentScene(), currentRobot())
  Object.assign(state, { x, y, theta: 0, linear: 0, lateral: 0, angular: 0, lastMotionAt: 0, watchdogStop: false, collision: false, goalReached: false })
  return sessionInfo()
}

launchSession('warehouse', 'jetbot')

setInterval(() => {
  const now = Date.now()
  const dt = Math.min(0.1, (now - state.updatedAt) / 1000)
  state.updatedAt = now
  if (state.lastMotionAt && now - state.lastMotionAt > WATCHDOG_MS && (state.linear || state.lateral || state.angular)) {
    state.linear = 0; state.lateral = 0; state.angular = 0; state.watchdogStop = true
  }
  state.theta += state.angular * dt
  const fx = Math.cos(state.theta); const fy = Math.sin(state.theta)
  const lx = -Math.sin(state.theta); const ly = Math.cos(state.theta)
  const nextX = state.x + (fx * state.linear + lx * state.lateral) * dt
  const nextY = state.y + (fy * state.linear + ly * state.lateral) * dt
  const world = currentWorld()
  const radius = currentRobot().id === 'nova-carter' ? .55 : currentRobot().id === 'carter-v1' ? .50 : .36
  const [minX,maxX,minY,maxY] = world.bounds
  const hitsRect = (x, y, rect) => {
    const [rx, ry, rw, rh] = rect
    const nx = Math.max(rx, Math.min(x, rx + rw)); const ny = Math.max(ry, Math.min(y, ry + rh))
    return Math.hypot(x - nx, y - ny) < radius
  }
  const hitsWall = nextX < minX + radius || nextX > maxX - radius || nextY < minY + radius || nextY > maxY - radius
  const hitsObstacle = world.rects.some((rect) => hitsRect(nextX, nextY, rect))
  state.collision = hitsWall || hitsObstacle
  if (!state.collision) { state.x = nextX; state.y = nextY }
  state.goalReached = Math.hypot(state.x - world.target[0], state.y - world.target[1]) < .65
}, 40)

const signal = net.createServer((socket) => { socket.on('error', () => {}); socket.end() })
const bridge = net.createServer((socket) => {
  socket.setEncoding('utf8')
  let buffer = ''
  socket.on('data', (chunk) => {
    buffer += chunk
    while (true) {
      const nl = buffer.indexOf('\n')
      if (nl < 0) break
      const line = buffer.slice(0, nl); buffer = buffer.slice(nl + 1)
      if (!line.trim()) continue
      let message
      try {
        message = JSON.parse(line)
        let result
        if (message.op === 'ping') result = { service: 'local-mock-isaac-stage2', playing: true, mock: true, session: sessionInfo(), robot: robotInfo(), watchdog_seconds: WATCHDOG_MS / 1000 }
        else if (message.op === 'get_catalog') result = { scenes, robots }
        else if (message.op === 'get_session') result = sessionInfo()
        else if (message.op === 'launch_session') result = launchSession(String(message.args?.sceneId || ''), String(message.args?.robotId || ''))
        else if (message.op === 'get_scene_info') result = { scene: currentScene(), sceneUrl: currentScene().asset_path, prim_count: 12, prims: [{ path: '/World', type: 'Xform' }, { path: `/World/${currentScene().id}`, type: 'Xform' }, { path: '/World/MockRobot', type: 'Xform' }] }
        else if (message.op === 'get_robot_info') result = robotInfo()
        else if (message.op === 'get_robot_pose') result = { pose: { position: [state.x, state.y, currentRobot().spawn_z || 0], yaw: state.theta } }
        else if (message.op === 'reset_robot') {
          const [x,y] = spawnFor(currentScene(), currentRobot())
          Object.assign(state, { x, y, theta: 0, linear: 0, lateral: 0, angular: 0, watchdogStop: false, collision: false, goalReached: false })
          result = { reset: true, pose: { position: [x,y,currentRobot().spawn_z || 0], yaw: 0 } }
        } else if (message.op === 'motion' || message.op === 'teleop') {
          const robot = currentRobot()
          const lateral = Number(message.args?.lateral || 0)
          if (robot.adapter !== 'holonomic-drive' && Math.abs(lateral) > 1e-4) {
            result = { accepted: false, mock: true, reason: 'selected differential robot does not support lateral motion', unsupported_axis: 'lateral' }
          } else {
            state.linear = Number(message.args?.linear || 0); state.lateral = lateral; state.angular = Number(message.args?.angular || 0)
            state.lastMotionAt = Date.now(); state.watchdogStop = false
            result = { accepted: true, adapter: `mock-${robot.adapter}`, mock: true, command: message.args }
          }
        } else result = { accepted: false, mock: true, reason: `unsupported mock op: ${message.op}` }
        socket.write(JSON.stringify({ id: message.id, ok: true, result }) + '\n')
      } catch (err) {
        socket.write(JSON.stringify({ id: message?.id ?? null, ok: false, error: err.message }) + '\n')
      }
    }
  })
})

await new Promise((resolve, reject) => signal.once('error', reject).listen(signalPort, '127.0.0.1', resolve))
await new Promise((resolve, reject) => bridge.once('error', reject).listen(bridgePort, '127.0.0.1', resolve))
console.log('Stage 2 local mock: multi-scene + multi-robot + universal motion API')
console.log(`local mock WebRTC signal 127.0.0.1:${signalPort}`)
console.log(`local mock bridge 127.0.0.1:${bridgePort}`)
console.log(`local playground http://127.0.0.1:${webPort}`)
console.log(`catalog ${scenes.length} scenes + ${robots.length} robots`)
console.log('starting playground...')
await import('../server/index.js')
