// The tools the language model can use. This is the whole surface: there is no
// other way for it to touch the simulation.
//
// Two things shape this list.
//
// First, `look` exists because the model cannot see. Everything else it does is
// blind unless it takes a picture, and a model that cannot check its own work
// will confidently report a scene it never verified.
//
// Second, `drive` takes a duration. The bridge stops the robot 0.4 s after the
// last command (the motion watchdog), so a single call moves it a few
// centimetres. Making the model send its own heartbeat would be an absurd use
// of a round trip per 100 ms, so the duration is handled here.

export const TOOL_DEFINITIONS = [
  {
    name: 'get_session',
    description:
      'What is loaded right now: scene, robot, whether the robot is ready, its adapter type, and for an arm its joint names, limits and current targets. Call this before acting on "the robot" so you are not guessing.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'list_catalog',
    description: 'Every scene and robot available to load, including anything the operator has uploaded.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'launch_session',
    description:
      'Load a scene and a robot together. SLOW: the scene is fetched and composed, which can take one to four minutes, and it drops any teleoperation session. Only call this when the operator wants a different scene or robot.',
    input_schema: {
      type: 'object',
      properties: {
        sceneId: { type: 'string', description: 'id from list_catalog' },
        robotId: { type: 'string', description: 'id from list_catalog' },
      },
      required: ['sceneId', 'robotId'],
      additionalProperties: false,
    },
  },
  {
    name: 'look',
    description:
      'Take a picture of the simulation and look at it. This is your only eye. Use it to check what a change actually did rather than assuming, and to answer questions about what is in the scene.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'drive',
    description:
      'Drive a wheeled robot for a set time, then stop. linear is metres per second forward (negative reverses), angular is radians per second turning left, lateral only works on a holonomic base. Fails on an arm.',
    input_schema: {
      type: 'object',
      properties: {
        linear: { type: 'number', description: 'forward m/s, -2 to 2' },
        angular: { type: 'number', description: 'turn rad/s, -4 to 4' },
        lateral: { type: 'number', description: 'sideways m/s, holonomic only' },
        seconds: { type: 'number', description: 'how long to hold it, 0.1 to 10' },
      },
      required: ['seconds'],
      additionalProperties: false,
    },
  },
  {
    name: 'set_joints',
    description:
      'Move an arm. Give joint names from get_session mapped to target positions in radians. Values outside the joint limits are clamped. Fails on a wheeled robot, and while a leader arm is driving.',
    input_schema: {
      type: 'object',
      properties: {
        positions: {
          type: 'object',
          description: 'joint name to radians, e.g. {"Rotation": 0.5, "Elbow": -0.2}',
          additionalProperties: { type: 'number' },
        },
      },
      required: ['positions'],
      additionalProperties: false,
    },
  },
  {
    name: 'home_robot',
    description: 'Return the robot to its starting pose. On an arm this is the home joint position; on a base it stops and resets the pose.',
    input_schema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'move_camera',
    description:
      'Move the viewpoint. Use frame_robot to point it at the robot, or orbit/zoom/raise to adjust from where it is. The operator sees exactly what this camera sees.',
    input_schema: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ['frame_robot', 'orbit_left', 'orbit_right', 'zoom_in', 'zoom_out', 'raise', 'lower', 'reset'],
        },
        amount: { type: 'number', description: 'how much, 0.1 to 3, default 1. For frame_robot this is how much room to leave around the robot: 1 is snug, 0.6 is a close-up, 2 pulls back.' },
      },
      required: ['action'],
      additionalProperties: false,
    },
  },
]

const clamp = (value, low, high) => Math.max(low, Math.min(high, Number(value) || 0))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Run one tool.
 *
 * `deps` supplies the same primitives the HTTP routes use, so the model can do
 * nothing a person at the page could not do.
 */
export async function runAgentTool(name, input, deps) {
  const { bridgeRequest, captureFrame, mergedCatalog, config } = deps
  const args = input && typeof input === 'object' ? input : {}

  switch (name) {
    case 'get_session': {
      const session = await bridgeRequest('get_session', {}, 5000)
      const robot = session?.robot ?? {}
      return {
        content: JSON.stringify({
          scene: session?.scene?.name ?? session?.sceneId,
          sceneId: session?.sceneId,
          robotId: session?.robotId,
          status: session?.status,
          error: session?.error ?? null,
          robot: {
            name: robot.name,
            ready: robot.ready,
            adapter: robot.adapter,
            capabilities: robot.capabilities,
            joint_names: robot.joint_names,
            joint_limits: robot.joint_limits,
            joint_targets: robot.joint_targets,
            wheel_dof_names: robot.wheel_dof_names,
          },
        }),
      }
    }

    case 'list_catalog': {
      const { scenes, robots } = mergedCatalog()
      return {
        content: JSON.stringify({
          scenes: scenes.map((s) => ({ id: s.id, name: s.name, description: s.description, source: s.source })),
          robots: robots.map((r) => ({ id: r.id, name: r.name, adapter: r.adapter, description: r.description, source: r.source })),
        }),
      }
    }

    case 'launch_session': {
      const { scenes, robots } = mergedCatalog()
      const sceneId = String(args.sceneId || '')
      const robotId = String(args.robotId || '')
      if (!scenes.some((s) => s.id === sceneId)) throw new Error(`no scene "${sceneId}"; call list_catalog`)
      if (!robots.some((r) => r.id === robotId)) throw new Error(`no robot "${robotId}"; call list_catalog`)
      const session = await bridgeRequest('launch_session', { sceneId, robotId }, 240000)
      if (session?.status === 'error') throw new Error(session.error || 'the launch failed')
      return { content: `loaded ${sceneId} with ${robotId}; robot ready: ${Boolean(session?.robot?.ready)}` }
    }

    case 'look': {
      const frame = await captureFrame()
      return {
        // Handed back as an image block so the model actually sees it rather
        // than being told about it.
        content: [
          { type: 'text', text: `viewport, ${frame.width}x${frame.height}` },
          { type: 'image', source: { type: 'base64', media_type: frame.mime, data: frame.data } },
        ],
        preview: `data:${frame.mime};base64,${frame.data}`,
      }
    }

    case 'drive': {
      const seconds = clamp(args.seconds ?? 1, 0.1, 10)
      const command = {
        linear: clamp(args.linear ?? 0, -2, 2),
        lateral: clamp(args.lateral ?? 0, -2, 2),
        angular: clamp(args.angular ?? 0, -4, 4),
        source: 'agent',
      }
      if (!command.linear && !command.lateral && !command.angular) {
        throw new Error('give at least one of linear, lateral or angular')
      }
      // Re-send inside the watchdog window, then stop deliberately.
      const deadline = Date.now() + seconds * 1000
      let sent = 0
      let refusal = null
      while (Date.now() < deadline) {
        const result = await bridgeRequest('motion', command, 1500)
        sent += 1
        if (result && result.accepted === false) { refusal = result.reason || 'the robot refused the command'; break }
        await sleep(100)
      }
      await bridgeRequest('motion', { linear: 0, lateral: 0, angular: 0, source: 'agent' }, 1500).catch(() => {})
      if (refusal) throw new Error(refusal)
      return { content: `drove for ${seconds}s (${sent} commands) then stopped` }
    }

    case 'set_joints': {
      const positions = args.positions
      if (!positions || typeof positions !== 'object' || Array.isArray(positions)) {
        throw new Error('positions must be an object of joint names to radians')
      }
      const cleaned = {}
      for (const [joint, value] of Object.entries(positions)) {
        if (!/^[A-Za-z0-9_.-]{1,60}$/.test(joint)) throw new Error(`bad joint name: ${joint}`)
        const number = Number(value)
        if (!Number.isFinite(number)) throw new Error(`${joint} must be a number`)
        cleaned[joint] = Math.max(-100, Math.min(100, number))
      }
      if (!Object.keys(cleaned).length) throw new Error('no joints given')
      const result = await bridgeRequest('set_joints', { positions: cleaned }, 5000)
      return { content: JSON.stringify(result) }
    }

    case 'home_robot': {
      const result = await bridgeRequest('reset_robot', {}, 10000)
      return { content: JSON.stringify(result) }
    }

    case 'move_camera': {
      const action = String(args.action || '')
      const amount = clamp(args.amount ?? 1, 0.1, 3)
      if (action === 'frame_robot') {
        // Not reset_camera: that used to mean "the scene's authored view",
        // which is framed for the scene and not for the robot in it.
        // amount is how much room to leave: 1 is snug, below 1 is tighter.
        const margin = clamp(1.15 * (args.amount ?? 1), 0.6, 6)
        const result = await bridgeRequest('frame_robot', { margin }, 8000)
        return { content: `camera framed on the robot at margin ${margin.toFixed(2)}: ${JSON.stringify(result)}` }
      }
      if (action === 'reset') {
        const result = await bridgeRequest('reset_camera', { scene_view: true }, 5000)
        return { content: `camera reset to the scene view: ${JSON.stringify(result)}` }
      }
      const view = await bridgeRequest('get_camera', {}, 5000)
      const eye = view?.camera?.eye ?? [4, -5, 3]
      const target = view?.camera?.target ?? [0, 0, 0.4]
      const dx = eye[0] - target[0]
      const dy = eye[1] - target[1]
      const dz = eye[2] - target[2]
      let distance = Math.hypot(dx, dy, dz) || 4
      let yaw = Math.atan2(dy, dx)
      let pitch = Math.asin(Math.max(-1, Math.min(1, dz / distance)))

      if (action === 'orbit_left') yaw += 0.4 * amount
      else if (action === 'orbit_right') yaw -= 0.4 * amount
      else if (action === 'zoom_in') distance = Math.max(0.4, distance * (1 - 0.25 * amount))
      else if (action === 'zoom_out') distance = Math.min(80, distance * (1 + 0.25 * amount))
      else if (action === 'raise') pitch = Math.min(1.4, pitch + 0.25 * amount)
      else if (action === 'lower') pitch = Math.max(-1.4, pitch - 0.25 * amount)
      else throw new Error(`unknown camera action: ${action}`)

      const flat = distance * Math.cos(pitch)
      const next = [
        target[0] + flat * Math.cos(yaw),
        target[1] + flat * Math.sin(yaw),
        target[2] + distance * Math.sin(pitch),
      ]
      await bridgeRequest('set_camera', { eye: next, target }, 5000)
      return { content: `camera ${action} by ${amount}` }
    }

    default:
      throw new Error(`unknown tool: ${name}`)
  }
}
