import { initAccessClient } from './access-client.js'
import { initChallengesUI } from './challenges-ui.js?v=20261010-manual-dice-1'
import { initChildUI, sceneLabel, sceneNotes, picture } from './child-ui.js?v=20260930-football-1'
const $ = (id) => document.getElementById(id)

function escapeHtml(value) {
  const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return String(value ?? '').replace(/[&<>"']/g, (character) => entities[character])
}

const viewerShell = $('viewerShell')
const video = $('remote-video')
const audio = $('remote-audio')
const mockCanvas = $('mockCanvas')
const mjpegSurface = $('mjpegSurface')
const robotInputShield = $('robotInputShield')
const streamOverlay = $('streamOverlay')
const streamTitle = $('streamTitle')
const streamText = $('streamText')
const streamEndpoint = $('streamEndpoint')
const connectStreamButton = $('connectStream')
const disconnectStreamButton = $('disconnectStream')
const streamWarning = $('streamWarning')
const focusHint = $('focusHint')
const mockLegend = $('mockLegend')
const sceneName = $('sceneName')
const sceneSubtitle = $('sceneSubtitle')
const sceneSummary = $('sceneSummary')
const robotSummary = $('robotSummary')
const sessionTitle = $('sessionTitle')
const modeChip = $('modeChip')
const environmentBadge = $('environmentBadge')
const surfaceStatus = $('surfaceStatus')
const robotStatus = $('robotStatus')
const previewBadge = $('previewBadge')
const diagnosticSummary = $('diagnosticSummary')
const rendererValue = $('rendererValue')
const signalEndpoint = $('signalEndpoint')
const mediaEndpoint = $('mediaEndpoint')
const bridgeEndpoint = $('bridgeEndpoint')
const sdkValue = $('sdkValue')
const captureValue = $('captureValue')
const streamSwitch = $('streamSwitch')
const useCompatStream = $('useCompatStream')
const nativeHint = $('nativeHint')
const statFps = $('statFps')
const statRtd = $('statRtd')
const statBitrate = $('statBitrate')
const statLoss = $('statLoss')
const modeHelp = $('modeHelp')
const keyboardMeaning = $('keyboardMeaning')
const robotControls = $('robotControls')
const cameraControls = $('cameraControls')
const cameraTips = document.querySelector('.camera-tips')
const robotReadyText = $('robotReadyText')
const capabilityRow = $('capabilityRow')
const lateralHint = $('lateralHint')
const keyQ = $('keyQ')
const keyE = $('keyE')
const linearSpeed = $('linearSpeed')
const lateralSpeed = $('lateralSpeed')
const angularSpeed = $('angularSpeed')
const linearValue = $('linearValue')
const lateralValue = $('lateralValue')
const angularValue = $('angularValue')
const lateralSetting = $('lateralSetting')
const linearCmd = $('linearCmd')
const lateralCmd = $('lateralCmd')
const angularCmd = $('angularCmd')
const delivery = $('delivery')
const stopButton = $('stop')
const resetRobot = $('resetRobot')
const resetView = $('resetView')
const clearLog = $('clearLog')
const eventLog = $('eventLog')
const sessionStatus = $('sessionStatus')
const adapterValue = $('adapterValue')
const launchValue = $('launchValue')
const launcher = $('launcher')
const sceneLibrary = $('sceneLibrary')
const robotLibrary = $('robotLibrary')
const sceneCount = $('sceneCount')
const robotCount = $('robotCount')
const launchSummary = $('launchSummary')
const launchError = $('launchError')
const launchSessionButton = $('launchSession')
const closeLauncher = $('closeLauncher')
const changeSetup = $('changeSetup')
const changeSetupTop = $('changeSetupTop')
const assistantPanel = $('assistantPanel')
const assistantLog = $('assistantLog')
const assistantForm = $('assistantForm')
const assistantInput = $('assistantInput')
const assistantSend = $('assistantSend')
const assistantHint = $('assistantHint')
const assistantReset = $('assistantReset')
const uploadFile = $('uploadFile')
const uploadButton = $('uploadButton')
const uploadStatus = $('uploadStatus')
const uploadList = $('uploadList')
const uploadHint = $('uploadHint')
const registerForm = $('registerForm')
const registerFileName = $('registerFileName')
const inspectSummary = $('inspectSummary')
const registerError = $('registerError')
const cancelRegister = $('cancelRegister')
const submitRegister = $('submitRegister')
const regId = $('regId')
const regName = $('regName')
const regAdapter = $('regAdapter')
const jointPicker = $('jointPicker')
const jointPickCount = $('jointPickCount')
const robotFields = $('robotFields')
const sceneFields = $('sceneFields')
const wheelFields = $('wheelFields')
const comField = $('comField')
const regWheelRadius = $('regWheelRadius')
const regWheelBase = $('regWheelBase')
const regCom = $('regCom')
const regSpawnZ = $('regSpawnZ')
const regMaxLinear = $('regMaxLinear')
const regSpawn = $('regSpawn')
const regCameraEye = $('regCameraEye')
const jointControls = $('jointControls')
const jointSliders = $('jointSliders')
const jointCount = $('jointCount')
const resetJoints = $('resetJoints')
const teleopPanel = $('teleopPanel')
const teleopState = $('teleopState')
const teleopSource = $('teleopSource')
const teleopRate = $('teleopRate')
const teleopApplied = $('teleopApplied')
const teleopDropped = $('teleopDropped')
const teleopHint = $('teleopHint')
const teleopDisengage = $('teleopDisengage')


const WORLD_PRESETS = {
  warehouse: {
    bounds: [-6.2, 6.2, -4.4, 4.4], target: [4.7, 2.9], label: 'WAREHOUSE',
    rects: [[-3.8,2.1,2.2,.72],[-.8,2.1,2.2,.72],[2.2,2.1,2.2,.72],[-3.8,-.5,2.2,.72],[-.8,-.5,2.2,.72],[2.2,-.5,2.2,.72],[-5,-3,.72,.72],[-4.15,-3,.72,.72],[4.9,-2.75,.82,.82]],
  },
  'warehouse-multi': {
    bounds: [-8, 8, -6, 6], target: [6.3, 4.5], label: 'MULTI-SHELF WAREHOUSE',
    rects: [[-6,2.8,2.5,.65],[-2.5,2.8,2.5,.65],[1,2.8,2.5,.65],[4.5,2.8,2,.65],[-6,.4,2.5,.65],[-2.5,.4,2.5,.65],[1,.4,2.5,.65],[4.5,.4,2,.65],[-6,-2,2.5,.65],[-2.5,-2,2.5,.65],[1,-2,2.5,.65],[4.5,-2,2,.65]],
  },
  'simple-room': {
    bounds: [-4.5,4.5,-3.6,3.6], target: [3.1,2.2], label: 'SIMPLE ROOM',
    rects: [[-1,-.7,2,1.4],[-3.8,1.8,1.2,.8],[2.7,-2.4,.8,.8]],
  },
  grid: { bounds: [-7,7,-5,5], target: [5.5,3.8], label: 'FLAT GRID', rects: [] },
}

const state = {
  cfg: null,
  catalog: { scenes: [], robots: [] },
  session: null,
  selectedSceneId: null,
  selectedRobotId: null,
  mode: null,
  pressed: new Set(),
  bridgeConnected: false,
  bridgeMock: false,
  robotReady: false,
  capabilities: { forward: true, lateral: false, yaw: true },
  signalConnected: false,
  streamLive: false,
  streamConnecting: false,
  nativeModule: null,
  mockStarted: false,
  surface: 'none',
  streamGeneration: 0,
  compatLive: false,
  compatHealthy: false,
  orbit: null,
  cameraInFlight: false,
  cameraDirty: false,
  mockState: { x: 0, y: 0, theta: 0, linear: 0, lateral: 0, angular: 0, watchdogStop: false, collision: false, goalReached: false },
  lastCommandKey: '',
  motionInFlight: false,
  seq: 0,
  camera: { x: 0, y: 0, yaw: 0, zoom: 1 },
  pointer: { rotating: false, lastX: 0 },
  lastFrameAt: performance.now(),
  measuredFps: 0,
  frameCounter: 0,
  fpsWindowAt: performance.now(),
  launching: false,
  uploads: [],
  registerKind: 'robot',
  inspected: null,
  pickedJoints: new Set(),
  jointState: null,
  lastRobotInfo: null,
  teleopEngaged: false,
  teleopFetching: false,
}

function badge(element, tone, text) {
  element.classList.remove('ok', 'bad', 'warn')
  if (tone) element.classList.add(tone)
  const textNode = [...element.childNodes].find((node) => node.nodeType === Node.TEXT_NODE)
  if (textNode) textNode.textContent = text
  else element.append(document.createTextNode(text))
}

function setSurfaceState(kind, detail = '') {
  if (kind === 'live') badge(surfaceStatus, 'ok', '仿真已连接')
  else if (kind === 'mock') badge(surfaceStatus, 'ok', '演示模式')
  else if (kind === 'connecting') badge(surfaceStatus, 'warn', '正在连接')
  else if (kind === 'missing') badge(surfaceStatus, 'bad', '请老师检查配置')
  else if (kind === 'error') badge(surfaceStatus, 'bad', '仿真未连接')
  else badge(surfaceStatus, null, '仿真准备中')
  if (detail) nativeHint.textContent = detail
}

function logEvent(label, detail = '') {
  if (eventLog.children.length === 1 && eventLog.firstElementChild?.classList.contains('muted-event')) eventLog.innerHTML = ''
  const row = document.createElement('div')
  row.className = 'event'
  const time = document.createElement('span')
  const name = document.createElement('strong')
  const text = document.createElement('code')
  time.textContent = new Date().toLocaleTimeString([], { hour12: false })
  name.textContent = label
  text.textContent = detail
  row.append(time, name, text)
  eventLog.prepend(row)
  while (eventLog.children.length > 18) eventLog.lastElementChild.remove()
}

function formatNumber(value, digits = 1, suffix = '') {
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(digits)}${suffix}` : '-'
}

function updateStats(stats = null) {
  statFps.textContent = stats ? formatNumber(stats.fps, 1) : '-'
  statRtd.textContent = stats ? formatNumber(stats.rtd, 0, ' ms') : '-'
  statBitrate.textContent = stats ? formatNumber(stats.currentBitrate, 1, ' Mbps') : '-'
  statLoss.textContent = stats ? formatNumber(stats.packetLoss, 0) : '-'
}

function sceneById(id) { return state.catalog.scenes.find((x) => x.id === id) || null }
function robotById(id) { return state.catalog.robots.find((x) => x.id === id) || null }
function activeScene() { return state.session?.scene || sceneById(state.session?.sceneId) || null }
function activeRobot() { return robotById(state.session?.robotId) || null }

function setBridgeBadge(connected, result = null) {
  state.bridgeConnected = connected
  state.bridgeMock = Boolean(result?.mock)
  previewBadge.textContent = connected ? (state.bridgeMock ? '演示模式' : '实时仿真') : '准备中'
  previewBadge.classList.toggle('live', connected)
  environmentBadge.textContent = connected ? (state.bridgeMock ? '演示模式' : 'ISAAC SIM 已连接') : '等待连接'
  environmentBadge.classList.toggle('live', connected)
  // Show what Isaac is actually rendering, so a trimmed deployment is visible
  // rather than something you have to go and check on the box.
  if (result?.render) {
    const live = result.stream?.livestream
    rendererValue.textContent =
      `${state.cfg?.renderer || '-'} · ${result.render.width}x${result.render.height}` +
      `${result.render.hide_ui ? ' · no UI' : ''} · webrtc ${live ? 'on' : 'off'}`
  }
  const robot = result?.robot || result?.session?.robot || state.session?.robot
  applyRobotInfo(robot, connected)
  if (result?.session && result.session.launchId !== state.session?.launchId) applySession(result.session, { quiet: true })
}

function setSignalState(info = {}) {
  state.signalConnected = Boolean(info.connected)
  diagnosticSummary.textContent = `${state.signalConnected ? 'Signal online' : 'Signal offline'} · ${state.bridgeConnected ? 'Bridge online' : 'Bridge offline'}`
  if (state.cfg?.renderer === 'native' && !state.signalConnected && !state.streamLive) {
    streamWarning.hidden = false
    streamWarning.textContent = `WebRTC signaling ${state.cfg.stream.host}:${state.cfg.stream.signalPort} is not reachable from the playground host.`
  } else streamWarning.hidden = true
}

function applyRobotInfo(info = null, bridgeConnected = state.bridgeConnected) {
  state.lastRobotInfo = info
  const ready = Boolean(bridgeConnected && info?.ready)
  state.robotReady = ready
  robotControls.classList.toggle('muted-controls', !ready)
  state.capabilities = info?.capabilities || { forward: true, lateral: false, yaw: true }
  badge(robotStatus, ready ? 'ok' : 'bad', ready ? '伙伴准备好了' : '伙伴准备中')
  robotReadyText.textContent = ready ? '准备好了' : '准备中'
  resetRobot.disabled = !ready
  adapterValue.textContent = info?.adapter || '-'
  renderCapabilities()
  renderJointControls(info)
  refreshTeleop()
}

function renderCapabilities() {
  const caps = state.capabilities || {}
  capabilityRow.innerHTML = ''
  for (const [key, label] of [['forward','forward'], ['lateral','lateral'], ['yaw','turn']]) {
    const chip = document.createElement('span')
    chip.className = `capability ${caps[key] ? 'on' : ''}`
    chip.textContent = `${caps[key] ? '✓' : '–'} ${label}`
    capabilityRow.append(chip)
  }
  // An arm has no base motion at all, so the wheel-speed controls are noise.
  const jointDriven = Boolean(caps.joints)
  document.querySelector('.keyboard-section').hidden = jointDriven && state.mode === 'robot'
  document.querySelector('.settings').hidden = jointDriven
  const lateral = Boolean(caps.lateral)
  lateralSetting.hidden = !lateral || jointDriven
  keyQ.classList.toggle('disabled', !lateral)
  keyE.classList.toggle('disabled', !lateral)
  lateralHint.hidden = jointDriven
  lateralHint.textContent = lateral ? '这个伙伴还可以向左、向右横着走。' : '这个伙伴可以前进、后退和转弯。'
  refreshModeText()
}

function applySession(session, options = {}) {
  if (!session) return
  state.session = session
  const scene = session.scene || sceneById(session.sceneId)
  const robotCatalog = robotById(session.robotId)
  const robotInfo = session.robot || null
  const sceneNameText = sceneLabel(scene)
  const robotLabel = robotInfo?.name || robotCatalog?.name || session.robotId || '-'
  sceneName.textContent = sceneNameText
  sceneSubtitle.textContent = `${robotLabel} · NVIDIA Isaac Sim`
  sceneSummary.textContent = sceneNameText
  robotSummary.textContent = robotLabel
  sessionTitle.textContent = `${sceneNameText} · ${robotLabel}`
  sessionStatus.textContent = session.status || '-'
  launchValue.textContent = session.launchId ? `#${session.launchId}` : '-'
  state.selectedSceneId = session.sceneId
  state.selectedRobotId = session.robotId
  applyRobotInfo(robotInfo, state.bridgeConnected)
  syncSpeedRanges(robotInfo || robotCatalog)
  state.camera = { x: 0, y: 0, yaw: 0, zoom: 1 }
  renderLibrarySelection()
  if (!options.quiet) logEvent('session', `${session.sceneId} + ${session.robotId} · ${session.status}`)
}

function syncSpeedRanges(robot) {
  if (!robot) return
  const maxLinear = Math.max(.1, Number(robot.max_linear_speed || .5))
  const maxLateral = Math.max(.1, Number(robot.max_lateral_speed || .4))
  const maxAngular = Math.max(.2, Number(robot.max_angular_speed || 1.5))
  linearSpeed.max = String(Math.min(2, maxLinear))
  lateralSpeed.max = String(Math.min(2, maxLateral))
  angularSpeed.max = String(Math.min(4, maxAngular))
  if (Number(linearSpeed.value) > maxLinear) linearSpeed.value = String(maxLinear)
  if (Number(lateralSpeed.value) > maxLateral) lateralSpeed.value = String(maxLateral)
  if (Number(angularSpeed.value) > maxAngular) angularSpeed.value = String(maxAngular)
  updateSpeedLabels()
}

function renderLibrary() {
  const levels=state.catalog.challenges||[]
  if (!levels.some(l=>l.id===state.selectedChallengeId)) state.selectedChallengeId=levels[0]?.id
  const selected=levels.find(l=>l.id===state.selectedChallengeId)
  if(selected){state.selectedSceneId=selected.sceneId;state.selectedRobotId=selected.robotId}
  sceneCount.textContent='2 位伙伴';robotCount.textContent=levels.filter(l=>l.track===selected?.track).length+' 个挑战'
  sceneLibrary.innerHTML='';robotLibrary.innerHTML=''
  for(const track of [{id:'so101',name:'SO-101 机械臂',icon:'🦾',note:'搬方块 · 扔骰子 · 分水果',color:'arm'},{id:'microduck',name:'MicroDuck 小鸭子',icon:'🐥',note:'走一走 · 坐下站起 · 前滚翻 · 踢足球',color:'duck'}]){
    const card=document.createElement('button');card.type='button';card.className='library-card challenge-track '+track.color
    card.dataset.sceneId=track.id==='so101'?'challenge-arm':'challenge-duck'
    card.innerHTML=`<div class="challenge-illustration" aria-hidden="true">${track.icon}</div><strong>${track.name}</strong><p>${track.note}</p>`
    card.onclick=()=>{state.selectedChallengeId=levels.find(l=>l.track===track.id)?.id;renderLibrary()}
    sceneLibrary.append(card)
  }
  levels.filter(l=>l.track===selected?.track).forEach((level,index)=>{
    const card=document.createElement('button');card.type='button';card.className='library-card challenge-level';card.dataset.levelId=level.id
    card.innerHTML=`<span class="level-number">${index+1}</span><strong>${escapeHtml(level.name)}</strong><p>${escapeHtml(level.instruction)}</p>`
    card.onclick=()=>{state.selectedChallengeId=level.id;renderLibrarySelection()}
    robotLibrary.append(card)
  })
  renderLibrarySelection()
}

function renderLibrarySelection() {
  const level=state.catalog.challenges?.find(l=>l.id===state.selectedChallengeId)
  if(level){state.selectedSceneId=level.sceneId;state.selectedRobotId=level.robotId}
  document.querySelectorAll('[data-level-id]').forEach(el=>{el.classList.toggle('selected',el.dataset.levelId===state.selectedChallengeId);el.setAttribute('aria-pressed',String(el.dataset.levelId===state.selectedChallengeId))})
  document.querySelectorAll('[data-scene-id]').forEach((el) => {const selected=el.dataset.sceneId===state.selectedSceneId;el.classList.toggle('selected',selected);el.setAttribute('aria-pressed',String(selected))})
  document.querySelectorAll('[data-robot-id]').forEach((el) => {const selected=el.dataset.robotId===state.selectedRobotId;el.classList.toggle('selected',selected);el.setAttribute('aria-pressed',String(selected))})
  const scene = sceneById(state.selectedSceneId)
  const robot = robotById(state.selectedRobotId)
  launchSummary.innerHTML = scene && robot ? `<strong>${escapeHtml(robot.name)}</strong> · <strong>${escapeHtml(level?.name || sceneLabel(scene))}</strong>` : '先选伙伴，再选一个挑战。'
  launchSessionButton.disabled = state.launching || !state.bridgeConnected || !scene || !robot
}

function openLauncher() {
  clearKeys(state.mode === 'robot')
  refreshUploads()
  state.selectedSceneId ||= state.session?.sceneId || state.cfg?.defaultSceneId || state.catalog.scenes[0]?.id
  state.selectedRobotId ||= state.session?.robotId || state.cfg?.defaultRobotId || state.catalog.robots[0]?.id
  renderLibrarySelection()
  launcher.hidden = false
  document.body.classList.add('launcher-open')
}

function closeLauncherPanel() {
  if (!state.session) return
  launcher.hidden = true
  document.body.classList.remove('launcher-open')
  if (state.cfg?.renderer === 'native') connectNativeSurface()
}

async function launchSelectedSession() {
  if (state.launching || !state.selectedSceneId || !state.selectedRobotId) return
  clearKeys(true)
  launchError.hidden = true
  launchError.textContent = ''
  state.launching = true
  jointQueue.pending={}
  document.querySelector('.workspace').inert=true
  document.querySelectorAll('.library-card').forEach(el=>el.disabled=true)
  launchSessionButton.disabled = true
  launchSessionButton.textContent = '◷ 正在准备…'
  sessionStatus.textContent = 'launching'
  launchSummary.textContent = '正在准备伙伴和关卡，请稍等…'
  childUI.guide('小芽正在准备实验室。等一等，马上就好。','calm')
  logEvent('launch', `${state.selectedSceneId} + ${state.selectedRobotId}`)
  try {
    const response = await fetch(state.selectedChallengeId ? '/api/challenges/start' : '/api/session/launch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.selectedChallengeId ? {id:state.selectedChallengeId} : { sceneId: state.selectedSceneId, robotId: state.selectedRobotId }),
    })
    const payload = await response.json()
    if (!payload.ok) throw new Error(payload.error || 'session launch failed')
    applySession(payload.session)
    state.challenge=payload.challenge||null
    if (payload.session.status !== 'ready') throw new Error(payload.session.error || 'robot adapter did not become ready')
    launcher.hidden = true
    document.body.classList.remove('launcher-open')
    if (state.cfg?.renderer === 'native') await connectNativeSurface()
    delivery.textContent = `Session ready: ${payload.session.sceneId} + ${payload.session.robotId}.`
  } catch (err) {
    launchSummary.textContent = '实验室还没准备好，请让老师帮忙看看。'
    childUI.guide('没关系，实验室需要一点帮助。请叫老师来看看吧。','calm')
    launchError.hidden = false
    launchError.textContent = '这次没能加载关卡。请再点「一起出发」，或请老师帮忙。'
    logEvent('launch-error', err.message)
  } finally {
    state.launching = false
    document.querySelector('.workspace').inert=!launcher.hidden
    document.querySelectorAll('.library-card').forEach(el=>el.disabled=false)
    launchSessionButton.textContent = '▶ 一起出发'
    renderLibrarySelection()
  }
}

function updateKeyVisuals() {
  document.querySelectorAll('.key[data-key]').forEach((el) => el.classList.toggle('pressed', state.pressed.has(el.dataset.key)))
}

function computeMotion() {
  const linearSpeedValue = Number(linearSpeed.value)
  const lateralSpeedValue = Number(lateralSpeed.value)
  const angularSpeedValue = Number(angularSpeed.value)
  let linear = 0; let lateral = 0; let angular = 0
  if (state.pressed.has('w')) linear += linearSpeedValue
  if (state.pressed.has('s')) linear -= linearSpeedValue
  if (state.pressed.has('a')) angular += angularSpeedValue
  if (state.pressed.has('d')) angular -= angularSpeedValue
  if (state.capabilities?.lateral) {
    if (state.pressed.has('q')) lateral += lateralSpeedValue
    if (state.pressed.has('e')) lateral -= lateralSpeedValue
  }
  return { linear, lateral, angular }
}

function renderMotion(command) {
  linearCmd.textContent = command.linear.toFixed(3)
  lateralCmd.textContent = command.lateral.toFixed(3)
  angularCmd.textContent = command.angular.toFixed(3)
}

async function sendMotion(command, reason = 'keyboard') {
  renderMotion(command)
  const heartbeat = reason === 'heartbeat'
  const key = `${command.linear.toFixed(3)}:${command.lateral.toFixed(3)}:${command.angular.toFixed(3)}`
  if (key === state.lastCommandKey && !heartbeat && reason !== 'stop') return
  if (heartbeat && state.motionInFlight) return
  state.lastCommandKey = key
  state.seq += 1
  if (!heartbeat) logEvent(reason === 'stop' ? 'STOP' : 'motion', `v=${command.linear.toFixed(2)} lat=${command.lateral.toFixed(2)} yaw=${command.angular.toFixed(2)}`)
  state.motionInFlight = true
  try {
    const response = await fetch('/api/control', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'motion', ...command, seq: state.seq }),
    })
    const result = await response.json()
    if (!heartbeat) {
      if (result.delivered && result.result?.accepted !== false) delivery.textContent = result.result?.mock ? 'Motion delivered to local mock adapter.' : 'Motion delivered to Isaac robot adapter.'
      else delivery.textContent = result.result?.reason || result.error || 'Robot did not accept the motion command.'
    }
  } catch {
    if (!heartbeat) delivery.textContent = 'Control endpoint unavailable.'
  } finally { state.motionInFlight = false }
}

function clearKeys(sendStop = true) {
  const hadKeys = state.pressed.size > 0
  state.pressed.clear(); updateKeyVisuals()
  if (state.mode === 'robot' && (hadKeys || sendStop)) sendMotion({ linear: 0, lateral: 0, angular: 0 }, 'stop')
}

function setMode(mode) {
  if (!['camera','robot'].includes(mode) || mode === state.mode) return
  clearKeys(state.mode === 'robot')
  state.mode = mode
  state.lastCommandKey = ''
  document.querySelectorAll('.mode').forEach((button) => button.classList.toggle('active', button.dataset.mode === mode))
  robotInputShield.hidden = mode !== 'robot'
  modeChip.textContent = mode === 'camera' ? '看看世界' : '操控伙伴'
  keyboardMeaning.textContent = mode === 'camera' ? '观察世界' : '操控伙伴'
  cameraControls.hidden = mode !== 'camera'
  robotControls.hidden = mode !== 'robot'
  renderCapabilities()
  renderJointControls(state.lastRobotInfo)
  if (mode === 'camera') {
    refreshModeText()
    delivery.textContent = 'Camera mode: robot motion is idle.'
    renderMotion({ linear:0, lateral:0, angular:0 })
  } else {
    refreshModeText()
    delivery.textContent = state.robotReady ? 'Robot mode ready.' : 'Robot commands become active when the selected adapter is ready.'
  }
  logEvent('mode', mode)
}

/** Keyboard help depends on the live surface, which can change after setMode. */
function refreshModeText() {
  const cameraMode = state.mode === 'camera'
  keyQ.classList.toggle('disabled', !cameraMode && !state.capabilities?.lateral)
  keyE.classList.toggle('disabled', !cameraMode && !state.capabilities?.lateral)
  keyQ.querySelector('small').textContent = cameraMode ? '抬高视角' : '向左平移'
  keyE.querySelector('small').textContent = cameraMode ? '降低视角' : '向右平移'
  keyQ.setAttribute('aria-label',cameraMode ? '抬高视角' : '向左平移')
  keyE.setAttribute('aria-label',cameraMode ? '降低视角' : '向右平移')
  document.querySelector('[data-key="w"] small').textContent = cameraMode ? '拉近看看' : '向前'
  document.querySelector('[data-key="s"] small').textContent = cameraMode ? '退远一点' : '向后'
  if (state.mode === 'robot') {
    const lateral = state.capabilities?.lateral ? ' · Q/E strafe' : ''
    modeHelp.textContent = state.capabilities?.joints ? '慢慢调整关节，把夹爪对准物体，再合拢。' : '按住箭头开动伙伴，松开就停下来。'
    focusHint.textContent = state.capabilities?.joints ? '调整关节 → 对准物体 → 合拢夹爪 → 抬起搬运' : '↑ 前进 · ↓ 后退 · ← → 转弯 · 红色按钮停止'
    cameraTips.hidden = true
    return
  }
  cameraTips.hidden = false
  if (state.compatLive) {
    modeHelp.textContent = '按住左右箭头转一转，上下箭头拉近或拉远。'
    focusHint.textContent = '← → 转一转 · ↑ ↓ 近一点 / 远一点'
    cameraTips.innerHTML = '<div><kbd>A / D</kbd><span>Orbit</span></div><div><kbd>W / S</kbd><span>Zoom</span></div><div><kbd>Q / E</kbd><span>Height</span></div>'
  } else if (state.cfg?.renderer === 'mock') {
    modeHelp.textContent = '这是简化演示，可以用方向键观察世界。'
    focusHint.textContent = '换个角度，看看机器人身边的世界。'
  } else {
    modeHelp.textContent = '点击画面，用鼠标和方向键观察世界。'
    focusHint.textContent = '点击画面，换个角度看看'
  }
}

function isTypingTarget(target) { return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable }

function handleKeyboard(event, isDown) {
  if (isTypingTarget(event.target)) return
  // A key-up must always be honoured, or the key sticks and the robot keeps
  // driving with no reachable STOP.
  if (!launcher.hidden || document.querySelector('dialog[open]')) { if (isDown) return; }
  const key = event.key.toLowerCase()
  const robotKeys = ['w','a','s','d','q','e']
  if (!robotKeys.includes(key)) return
  if (state.mode === 'robot') {
    if ((key === 'q' || key === 'e') && !state.capabilities?.lateral) return
    event.preventDefault(); event.stopImmediatePropagation()
    if (isDown) {
      if (event.repeat || state.pressed.has(key)) return
      state.pressed.add(key); updateKeyVisuals(); sendMotion(computeMotion(), 'keydown')
    } else {
      state.pressed.delete(key); updateKeyVisuals(); sendMotion(computeMotion(), 'keyup')
    }
    return
  }
  if (state.mode === 'camera' && state.compatLive && ['w','a','s','d','q','e'].includes(key)) {
    event.preventDefault()
    if (isDown) { if (event.repeat || state.pressed.has(key)) return; state.pressed.add(key) }
    else state.pressed.delete(key)
    updateKeyVisuals()
    return
  }
  if (state.mode === 'camera' && state.cfg?.renderer === 'mock' && ['w','a','s','d'].includes(key)) {
    event.preventDefault()
    if (isDown) { if (event.repeat || state.pressed.has(key)) return; state.pressed.add(key) }
    else state.pressed.delete(key)
    updateKeyVisuals()
  }
}

window.addEventListener('keydown', (e) => handleKeyboard(e, true), { capture: true })
window.addEventListener('keyup', (e) => handleKeyboard(e, false), { capture: true })
window.addEventListener('blur', () => clearKeys(state.mode === 'robot'))
document.addEventListener('visibilitychange', () => { if (document.hidden) clearKeys(state.mode === 'robot') })

stopButton.addEventListener('click', () => clearKeys(true))
resetRobot.addEventListener('click', async () => {
  clearKeys(true); resetRobot.disabled = true
  try {
    const result = await fetch('/api/robot/reset', { method: 'POST' }).then((r) => r.json())
    delivery.textContent = result.ok && result.result?.reset ? 'Robot reset to its spawn point.' : (result.result?.reason || result.error || 'Robot reset failed.')
    if (result.ok) logEvent('reset', 'robot returned to spawn')
  } catch (err) { delivery.textContent = `Robot reset failed: ${err.message}` }
  resetRobot.disabled = !state.robotReady
})
resetView.addEventListener('click', async () => {
  state.camera = { x:0, y:0, yaw:0, zoom:1 }
  logEvent('camera','view reset')
  if (!state.compatLive) return
  try {
    const payload = await fetch('/api/camera', { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ reset:true }) }).then((r)=>r.json())
    if (payload.ok && payload.camera?.eye) state.orbit = orbitFromView(payload.camera.eye, payload.camera.target)
  } catch {}
})
clearLog.addEventListener('click', () => { eventLog.innerHTML = '<div class="event muted-event">Waiting...</div>' })
document.querySelectorAll('.mode').forEach((button) => button.addEventListener('click', () => setMode(button.dataset.mode)))
document.querySelectorAll('.key[data-key]').forEach((button) => {
  button.addEventListener('pointerdown', (event) => {
    if (state.mode !== 'robot' && state.mode !== 'camera') return
    const key = button.dataset.key
    if (state.mode === 'robot' && (key === 'q' || key === 'e') && !state.capabilities?.lateral) return
    event.preventDefault(); state.pressed.add(key); updateKeyVisuals(); if(state.mode === 'robot') sendMotion(computeMotion(), 'pointer')
  })
  const release = () => {
    const key = button.dataset.key
    if (!state.pressed.has(key)) return
    state.pressed.delete(key); updateKeyVisuals(); if (state.mode === 'robot') sendMotion(computeMotion(), 'pointerup')
  }
  button.addEventListener('pointerup', release); button.addEventListener('pointercancel', release); button.addEventListener('pointerleave', release)
})

function updateSpeedLabels() {
  linearValue.textContent = `${Number(linearSpeed.value).toFixed(2)} m/s`
  lateralValue.textContent = `${Number(lateralSpeed.value).toFixed(2)} m/s`
  angularValue.textContent = `${Number(angularSpeed.value).toFixed(2)} rad/s`
  if (state.mode === 'robot' && state.pressed.size) sendMotion(computeMotion(), 'speed')
}
linearSpeed.addEventListener('input', updateSpeedLabels)
lateralSpeed.addEventListener('input', updateSpeedLabels)
angularSpeed.addEventListener('input', updateSpeedLabels)

changeSetup.addEventListener('click', openLauncher)
changeSetupTop.addEventListener('click', openLauncher)
closeLauncher.addEventListener('click', closeLauncherPanel)
launchSessionButton.addEventListener('click', launchSelectedSession)
launcher.addEventListener('click', (event) => { if (event.target === launcher) closeLauncherPanel() })

function resizeMockCanvas() {
  const rect = viewerShell.getBoundingClientRect(); const dpr = Math.max(1, window.devicePixelRatio || 1)
  mockCanvas.width = Math.max(1, Math.round(rect.width * dpr)); mockCanvas.height = Math.max(1, Math.round(rect.height * dpr))
}
function roundedRect(ctx,x,y,w,h,r) { ctx.beginPath(); ctx.roundRect(x,y,w,h,Math.min(r,Math.abs(w)/2,Math.abs(h)/2)) }
function worldPreset() { return WORLD_PRESETS[state.session?.sceneId] || WORLD_PRESETS.grid }

function drawWorld(ctx) {
  const world = worldPreset(); const [minX,maxX,minY,maxY] = world.bounds
  ctx.fillStyle = state.session?.sceneId === 'simple-room' ? '#17181b' : '#10161d'; ctx.fillRect(minX,minY,maxX-minX,maxY-minY)
  ctx.strokeStyle = '#1d2833'; ctx.lineWidth = .018
  for (let x=Math.ceil(minX); x<=maxX; x+=.5) { ctx.beginPath(); ctx.moveTo(x,minY); ctx.lineTo(x,maxY); ctx.stroke() }
  for (let y=Math.ceil(minY); y<=maxY; y+=.5) { ctx.beginPath(); ctx.moveTo(minX,y); ctx.lineTo(maxX,y); ctx.stroke() }
  ctx.strokeStyle='#647283'; ctx.lineWidth=.065; ctx.strokeRect(minX,minY,maxX-minX,maxY-minY)
  world.rects.forEach((rect, i) => {
    const [x,y,w,h] = rect
    ctx.fillStyle = state.session?.sceneId === 'simple-room' && i === 0 ? '#4b4035' : '#503f31'
    ctx.strokeStyle='#8b7358'; ctx.lineWidth=.035; roundedRect(ctx,x,y,w,h,.07); ctx.fill(); ctx.stroke()
  })
  ctx.fillStyle='#265b3a55'; ctx.strokeStyle='#78cc93'; ctx.lineWidth=.06
  ctx.beginPath(); ctx.arc(world.target[0],world.target[1],.5,0,Math.PI*2); ctx.fill(); ctx.stroke()
  ctx.beginPath(); ctx.arc(world.target[0],world.target[1],.16,0,Math.PI*2); ctx.stroke()
}

function drawRobot(ctx, robot) {
  const id = state.session?.robotId || 'jetbot'
  ctx.save(); ctx.translate(robot.x,robot.y); ctx.rotate(robot.theta); ctx.strokeStyle='#aeb9c6'; ctx.lineWidth=.045
  if (id === 'kaya') {
    ctx.fillStyle='#d3d9df'; ctx.beginPath(); ctx.arc(0,0,.38,0,Math.PI*2); ctx.fill(); ctx.stroke()
    ctx.fillStyle='#252d36'; for (const a of [0,2*Math.PI/3,4*Math.PI/3]) { ctx.save(); ctx.rotate(a); ctx.fillRect(.26,-.1,.22,.2); ctx.restore() }
  } else {
    const scale = id === 'nova-carter' ? 1.35 : id === 'carter-v1' ? 1.15 : .82
    ctx.scale(scale,scale); ctx.fillStyle='#0d1117'; roundedRect(ctx,-.42,-.31,.84,.62,.12); ctx.fill(); ctx.stroke()
    ctx.fillStyle=id === 'nova-carter' ? '#aeb8c2' : '#ced7e1'; roundedRect(ctx,-.27,-.20,.54,.40,.08); ctx.fill()
    ctx.fillStyle='#1c252f'; ctx.fillRect(-.26,.26,.2,.14); ctx.fillRect(.06,.26,.2,.14); ctx.fillRect(-.26,-.40,.2,.14); ctx.fillRect(.06,-.40,.2,.14)
  }
  ctx.strokeStyle='#23303b'; ctx.lineWidth=.05; ctx.beginPath(); ctx.moveTo(.05,0); ctx.lineTo(.55,0); ctx.stroke()
  ctx.fillStyle='#e4e9ee'; ctx.beginPath(); ctx.moveTo(.61,0); ctx.lineTo(.45,.10); ctx.lineTo(.45,-.10); ctx.closePath(); ctx.fill(); ctx.restore()
}

function updateMockCamera(dt) {
  if (state.mode !== 'camera' || state.cfg?.renderer !== 'mock') return
  const c=state.camera; const speed=2.5/Math.max(.75,c.zoom); let forward=0; let strafe=0
  if (state.pressed.has('w')) forward++; if (state.pressed.has('s')) forward--; if (state.pressed.has('d')) strafe++; if (state.pressed.has('a')) strafe--
  if (!forward && !strafe) return
  const mag=Math.hypot(forward,strafe)||1; forward/=mag; strafe/=mag
  const fx=Math.sin(c.yaw), fy=Math.cos(c.yaw), rx=Math.cos(c.yaw), ry=-Math.sin(c.yaw)
  c.x+=(fx*forward+rx*strafe)*speed*dt; c.y+=(fy*forward+ry*strafe)*speed*dt
}

function drawMock(now=performance.now()) {
  if (!state.mockStarted) return
  const ctx=mockCanvas.getContext('2d'); const w=mockCanvas.width; const h=mockCanvas.height
  const dt=Math.min(.05,Math.max(0,(now-state.lastFrameAt)/1000)); state.lastFrameAt=now; updateMockCamera(dt)
  state.frameCounter++
  if (now-state.fpsWindowAt>1000) { state.measuredFps=state.frameCounter*1000/(now-state.fpsWindowAt); state.frameCounter=0; state.fpsWindowAt=now; updateStats({fps:state.measuredFps,rtd:0,currentBitrate:0,packetLoss:0}) }
  ctx.clearRect(0,0,w,h); ctx.fillStyle='#070a0e'; ctx.fillRect(0,0,w,h)
  const world=worldPreset(); const worldW=world.bounds[1]-world.bounds[0]; const worldH=world.bounds[3]-world.bounds[2]
  const scale=Math.min(w/(worldW+2),h/(worldH+2))*state.camera.zoom
  ctx.save(); ctx.translate(w/2,h/2); ctx.scale(scale,-scale); ctx.rotate(-state.camera.yaw); ctx.translate(-state.camera.x,-state.camera.y); drawWorld(ctx); drawRobot(ctx,state.mockState); ctx.restore()
  ctx.fillStyle='#8f9cac'; ctx.font='10px ui-monospace, monospace'; ctx.fillText(`${world.label} · ${state.session?.robotId || '-'} · CAM ${state.camera.x.toFixed(1)}, ${state.camera.y.toFixed(1)} · ${state.camera.zoom.toFixed(2)}x`,18,h-48)
  if (state.mockState.watchdogStop) { ctx.fillStyle='#e6c17d'; ctx.fillText('ROBOT WATCHDOG STOP',18,h-30) }
  else if (state.mockState.collision) { ctx.fillStyle='#e9828d'; ctx.fillText('OBSTACLE - TURN AWAY',18,h-30) }
  if (state.mockState.goalReached) { ctx.fillStyle='#b9e6c8'; ctx.font='700 15px system-ui'; ctx.textAlign='center'; ctx.fillText('Goal reached',w/2,90); ctx.textAlign='start' }
  requestAnimationFrame(drawMock)
}

mockCanvas.addEventListener('contextmenu',(e)=>e.preventDefault())
mockCanvas.addEventListener('pointerdown',(e)=>{ if(state.mode!=='camera'||state.cfg?.renderer!=='mock'||e.button!==2)return; e.preventDefault();state.pointer.rotating=true;state.pointer.lastX=e.clientX;mockCanvas.setPointerCapture(e.pointerId) })
mockCanvas.addEventListener('pointermove',(e)=>{ if(!state.pointer.rotating)return; const dx=e.clientX-state.pointer.lastX;state.pointer.lastX=e.clientX;state.camera.yaw+=dx*.006 })
const stopRotate=(e)=>{ if(!state.pointer.rotating)return;state.pointer.rotating=false;try{mockCanvas.releasePointerCapture(e.pointerId)}catch{} }
mockCanvas.addEventListener('pointerup',stopRotate); mockCanvas.addEventListener('pointercancel',stopRotate)
mockCanvas.addEventListener('wheel',(e)=>{ if(state.mode!=='camera'||state.cfg?.renderer!=='mock')return;e.preventDefault();state.camera.zoom=Math.max(.55,Math.min(2.4,state.camera.zoom*Math.exp(-e.deltaY*.0012))) },{passive:false})

async function pollMockState() {
  while (state.mockStarted) {
    try { const result=await fetch('/api/mock/state',{cache:'no-store'}).then((r)=>r.json()); if(result.ok) state.mockState=result.state } catch {}
    await new Promise((resolve)=>setTimeout(resolve,70))
  }
}

function startMockSurface() {
  if (state.mockStarted) return
  state.mockStarted=true;video.hidden=true;mockCanvas.hidden=false;mockLegend.hidden=false;streamOverlay.hidden=true;disconnectStreamButton.disabled=true;connectStreamButton.disabled=true
  setSurfaceState('mock','Local Stage 2 mock surface: scene switching and robot adapters are simulated in this page.')
  resizeMockCanvas();new ResizeObserver(resizeMockCanvas).observe(viewerShell);state.lastFrameAt=performance.now();requestAnimationFrame(drawMock);pollMockState();logEvent('surface','local Stage 2 mock ready')
}


// --- compatibility surface -------------------------------------------------
//
// The same viewport, rendered server side and pushed as multipart JPEG over
// the HTTP port the page came from. Slower and softer than WebRTC, but it
// needs nothing beyond the connection the browser already has, so it works
// from anywhere the page itself loads - including behind a VPN that drops the
// WebRTC UDP media.

const CAMERA_POST_MS = 90

function orbitFromView(eye, target) {
  const dx = eye[0] - target[0]
  const dy = eye[1] - target[1]
  const dz = eye[2] - target[2]
  const dist = Math.hypot(dx, dy, dz) || 6
  return { target: [...target], dist, yaw: Math.atan2(dy, dx), pitch: Math.asin(Math.max(-1, Math.min(1, dz / dist))) }
}

function orbitEye(orbit) {
  const flat = orbit.dist * Math.cos(orbit.pitch)
  return [
    orbit.target[0] + flat * Math.cos(orbit.yaw),
    orbit.target[1] + flat * Math.sin(orbit.yaw),
    orbit.target[2] + orbit.dist * Math.sin(orbit.pitch),
  ]
}

async function pushCamera() {
  if (!state.orbit || state.cameraInFlight) { state.cameraDirty = Boolean(state.orbit); return }
  state.cameraInFlight = true
  state.cameraDirty = false
  try {
    await fetch('/api/camera', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ eye: orbitEye(state.orbit), target: state.orbit.target }),
    })
  } catch {} finally {
    state.cameraInFlight = false
    if (state.cameraDirty) setTimeout(pushCamera, CAMERA_POST_MS)
  }
}

async function loadCameraOrbit() {
  try {
    const payload = await fetch('/api/camera', { cache: 'no-store' }).then((r) => r.json())
    const view = payload.camera || payload.defaults
    if (view?.eye && view?.target) state.orbit = orbitFromView(view.eye, view.target)
  } catch {}
  if (!state.orbit) state.orbit = orbitFromView([4, -5, 3], [0, 0, 0.4])
}

function reconnectCompatImage() {
  state.compatRequestedAt = Date.now()
  state.compatNeedsReconnect = false
  mjpegSurface.src = `/api/stream.mjpg?t=${state.compatRequestedAt}`
}

function startCompatSurface(reason = '') {
  if (state.compatLive) return
  state.streamGeneration += 1
  teardownNativeStream().catch(() => {})
  state.surface = 'compat'
  state.compatLive = true
  state.compatHealthy = false
  video.hidden = true
  mockCanvas.hidden = true
  mockLegend.hidden = true
  mjpegSurface.hidden = false
  reconnectCompatImage()
  streamOverlay.hidden = true
  // The teardown above resolves later; make sure it cannot re-open the modal.
  setTimeout(() => { if (state.compatLive) streamOverlay.hidden = true }, 0)
  streamSwitch.hidden = false
  state.streamLive = false
  state.streamConnecting = false
  streamSwitch.textContent = '当前：MJPEG 兼容画面'
  connectStreamButton.textContent = '尝试切换到 WebRTC'
  connectStreamButton.disabled = false
  disconnectStreamButton.disabled = false
  useCompatStream.hidden = true
  $('connectionExplanation').textContent = `正在使用 MJPEG 兼容模式，不是 WebRTC。${reason ? `切换说明：${reason} ` : ''}可尝试 WebRTC；能否提升流畅度需要实际测试。`
  const size = state.cfg?.capture ? `${state.cfg.capture.width}x${state.cfg.capture.height}@${state.cfg.capture.fps}` : ''
  setSurfaceState('connecting', `Waiting for compatibility stream ${size}.${reason ? ` ${reason}` : ''}`)
  loadCameraOrbit()
  refreshModeText()
  logEvent('surface', `compatibility stream started${reason ? ` (${reason})` : ''}`)
}

function stopCompatSurface() {
  if (!state.compatLive) return
  state.compatLive = false
  state.compatHealthy = false
  state.nativeStats = null
  updateStats()
  state.surface = 'none'
  mjpegSurface.hidden = true
  mjpegSurface.removeAttribute('src')
  useCompatStream.textContent = '改用 MJPEG 兼容画面'
  useCompatStream.hidden = false
}

mjpegSurface.addEventListener('load', () => {
  if (!state.compatLive || state.compatHealthy) return
  state.compatHealthy = true
  const size = state.cfg?.capture ? `${state.cfg.capture.width}x${state.cfg.capture.height}@${state.cfg.capture.fps}` : ''
  setSurfaceState('live', `Compatibility stream ${size}: server-rendered frames over HTTP.`)
})

mjpegSurface.addEventListener('error', () => {
  if (!state.compatLive) return
  state.compatHealthy = false
  setSurfaceState('error', 'Compatibility stream dropped; retrying.')
  setTimeout(() => { if (state.compatLive) reconnectCompatImage() }, 1500)
})

mjpegSurface.addEventListener('wheel', (event) => {
  if (!state.compatLive || state.mode !== 'camera' || !state.orbit) return
  event.preventDefault()
  state.orbit.dist = Math.max(0.8, Math.min(60, state.orbit.dist * Math.exp(event.deltaY * 0.0012)))
  pushCamera()
}, { passive: false })

function toggleStreamSurface() {
  if (state.compatLive) { connectNativeSurface() }
  else startCompatSurface('手动切换至兼容画面。')
}
useCompatStream.addEventListener('click', toggleStreamSurface)
streamSwitch.title = '当前画面传输方式'


// --- uploading your own USD ------------------------------------------------
//
// A USD file alone is not enough to drive a robot: nothing in it says which
// joints are wheels and which are arm axes, and a wrong name fails later as an
// opaque "Invalid DOF name". So the flow is upload -> inspect -> pick joints.

const bytesLabel = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

function setUploadStatus(text, tone = '') {
  uploadStatus.className = `upload-status ${tone}`
  uploadStatus.textContent = text
}

async function refreshUploads() {
  try {
    const payload = await fetch('/api/assets', { cache: 'no-store' }).then((r) => r.json())
    state.uploads = payload.files || []
    uploadHint.textContent = `USD only · up to ${Math.round((payload.maxBytes || 0) / 1048576)} MB`
  } catch { state.uploads = [] }
  renderUploads()
}

function renderUploads() {
  if (!state.uploads.length) {
    uploadList.innerHTML = '<div class="inspect-summary">Nothing uploaded yet.</div>'
    return
  }
  uploadList.innerHTML = ''
  for (const file of state.uploads) {
    const row = document.createElement('div')
    row.className = 'upload-item'
    const label = document.createElement('strong')
    label.textContent = file.name
    const size = document.createElement('small')
    size.textContent = bytesLabel(file.bytes)
    const add = document.createElement('button')
    add.className = 'secondary'
    add.textContent = 'Add to library'
    add.addEventListener('click', () => beginRegister(file.name))
    const drop = document.createElement('button')
    drop.className = 'ghost-mini'
    drop.textContent = 'Delete'
    drop.addEventListener('click', async () => {
      const res = await fetch(`/api/assets/${encodeURIComponent(file.name)}`, { method: 'DELETE' }).then((r) => r.json())
      if (!res.ok) setUploadStatus(res.error, 'bad')
      else { setUploadStatus(`removed ${file.name}`, 'ok'); if (state.inspected?.file === file.name) closeRegister() }
      refreshUploads()
    })
    row.append(label, size, add, drop)
    uploadList.append(row)
  }
}

uploadButton.addEventListener('click', async () => {
  const file = uploadFile.files?.[0]
  if (!file) { setUploadStatus('choose a file first', 'bad'); return }
  uploadButton.disabled = true
  setUploadStatus(`uploading ${bytesLabel(file.size)}...`)
  try {
    const res = await fetch(`/api/assets?name=${encodeURIComponent(file.name)}&overwrite=1`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    })
    const payload = await res.json()
    if (!payload.ok) throw new Error(payload.error)
    setUploadStatus(`uploaded ${file.name}`, 'ok')
    logEvent('upload', `${file.name} (${bytesLabel(file.size)})`)
    uploadFile.value = ''
    await refreshUploads()
    beginRegister(payload.file.name)
  } catch (err) {
    setUploadStatus(err.message, 'bad')
  } finally {
    uploadButton.disabled = false
  }
})

function setRegisterKind(kind) {
  state.registerKind = kind
  document.querySelectorAll('.regkind').forEach((b) => b.classList.toggle('active', b.dataset.kind === kind))
  robotFields.hidden = kind !== 'robot'
  sceneFields.hidden = kind !== 'scene'
}
document.querySelectorAll('.regkind').forEach((b) => b.addEventListener('click', () => setRegisterKind(b.dataset.kind)))

function applyAdapterFields() {
  const adapter = regAdapter.value
  wheelFields.hidden = adapter !== 'differential-drive'
  comField.hidden = adapter !== 'holonomic-drive'
  renderJointPicker()
}
regAdapter.addEventListener('change', applyAdapterFields)

function renderJointPicker() {
  const joints = state.inspected?.joints || []
  jointPicker.innerHTML = ''
  if (!joints.length) {
    jointPicker.innerHTML = '<div class="inspect-summary">No drivable joints were found in this file.</div>'
  }
  for (const joint of joints) {
    const chip = document.createElement('button')
    chip.type = 'button'
    chip.className = `joint-chip${state.pickedJoints.has(joint.name) ? ' on' : ''}`
    chip.innerHTML = `${escapeHtml(joint.name)} <small>${escapeHtml(joint.type)}</small>`
    chip.addEventListener('click', () => {
      if (state.pickedJoints.has(joint.name)) state.pickedJoints.delete(joint.name)
      else state.pickedJoints.add(joint.name)
      renderJointPicker()
    })
    jointPicker.append(chip)
  }
  const need = regAdapter.value === 'differential-drive' ? ' (need exactly 2)'
    : regAdapter.value === 'holonomic-drive' ? ' (need 3 or more)' : ''
  jointPickCount.textContent = `${state.pickedJoints.size} selected${need}`
}

async function beginRegister(fileName) {
  registerForm.hidden = false
  registerError.textContent = ''
  registerFileName.textContent = fileName
  inspectSummary.className = 'inspect-summary'
  inspectSummary.textContent = 'Inspecting the file in Isaac Sim...'
  state.inspected = null
  state.pickedJoints = new Set()
  jointPicker.innerHTML = ''
  regId.value = fileName.replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
  regName.value = fileName.replace(/\.[^.]+$/, '')
  try {
    const payload = await fetch('/api/assets/inspect', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file: fileName }),
    }).then((r) => r.json())
    if (!payload.ok) throw new Error(payload.error)
    state.inspected = payload
    const joints = payload.joints || []
    inspectSummary.textContent =
      `${payload.prim_count} prims · ${payload.mesh_count} meshes · up axis ${payload.up_axis} · ` +
      `${joints.length} drivable joint${joints.length === 1 ? '' : 's'} · ` +
      `${payload.articulation_roots?.length ? `articulation root ${payload.articulation_roots[0]}` : 'no articulation root'}`
    setRegisterKind(payload.looks_like_robot ? 'robot' : 'scene')
    // A sensible default: arms want every joint, wheeled bases do not.
    if (payload.looks_like_robot && joints.length <= 12) joints.forEach((j) => state.pickedJoints.add(j.name))
    applyAdapterFields()
  } catch (err) {
    inspectSummary.className = 'inspect-summary bad'
    inspectSummary.textContent = `Could not inspect the file: ${err.message}`
    applyAdapterFields()
  }
}

function closeRegister() {
  registerForm.hidden = true
  state.inspected = null
  state.pickedJoints = new Set()
}
cancelRegister.addEventListener('click', closeRegister)

const triples = (text, fallback) => {
  const parts = String(text || '').split(/[\s,]+/).filter(Boolean).map(Number)
  return parts.length === 3 && parts.every(Number.isFinite) ? parts : fallback
}

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  registerError.textContent = ''
  submitRegister.disabled = true
  const kind = state.registerKind
  const body = {
    id: regId.value.trim().toLowerCase(),
    name: regName.value.trim(),
    file: registerFileName.textContent,
    replace: true,
  }
  if (kind === 'robot') {
    Object.assign(body, {
      adapter: regAdapter.value,
      wheel_dof_names: [...state.pickedJoints],
      spawn_z: Number(regSpawnZ.value),
      max_linear_speed: Number(regMaxLinear.value),
      wheel_radius: Number(regWheelRadius.value),
      wheel_base: Number(regWheelBase.value),
      com_prim_subpath: regCom.value.trim(),
    })
  } else {
    Object.assign(body, {
      spawn: triples(regSpawn.value, [0, 0, 0]),
      camera_eye: triples(regCameraEye.value, [4, -5, 3]),
    })
  }
  try {
    const payload = await fetch(`/api/catalog/${kind === 'robot' ? 'robots' : 'scenes'}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => r.json())
    if (!payload.ok) throw new Error(payload.error)
    logEvent('library', `added ${kind} ${payload.entry.id}`)
    closeRegister()
    const catalog = await fetch('/api/catalog', { cache: 'no-store' }).then((r) => r.json())
    state.catalog = { scenes: catalog.scenes || [], robots: catalog.robots || [], challenges: catalog.challenges || [] }
    if (kind === 'robot') state.selectedRobotId = payload.entry.id
    else state.selectedSceneId = payload.entry.id
    renderLibrary()
    renderLibrarySelection()
  } catch (err) {
    registerError.textContent = err.message
  } finally {
    submitRegister.disabled = false
  }
})

// --- per-joint control -----------------------------------------------------

function renderJointControls(info) {
  const names = info?.joint_names || []
  const isJointRobot = Boolean(info?.capabilities?.joints) && names.length > 0
  jointControls.hidden = !isJointRobot || state.mode !== 'robot'
  if (!isJointRobot) { state.jointState = null; return }
  const signature = names.join('|')
  if (state.jointState?.signature === signature) {
    for (const name of names) {
      const slider = state.jointState.inputs[name]
      const target = info.joint_targets?.[name]
      if (slider && target !== undefined && document.activeElement !== slider) {
        slider.value = String(target)
        state.jointState.labels[name].textContent = Number(target).toFixed(3)
      }
    }
    return
  }
  jointSliders.innerHTML = ''
  jointCount.textContent = `${names.length} 个关节`
  const inputs = {}
  const labels = {}
  for (const name of names) {
    const [low, high] = info.joint_limits?.[name] || [-3.1416, 3.1416]
    const value = info.joint_targets?.[name] ?? 0
    const wrap = document.createElement('label')
    wrap.className = 'joint-slider'
    const row = document.createElement('div')
    row.className = 'row'
    const title = document.createElement('span')
    title.textContent = ({Rotation:'↔ 底座转动',Pitch:'↕ 肩膀抬起',Elbow:'↕ 肘部弯曲',Wrist_Pitch:'↕ 手腕俯仰',Wrist_Roll:'↻ 手腕旋转',Jaw:'✋ 夹爪开合'})[name] || name
    const readout = document.createElement('strong')
    readout.textContent = Number(value).toFixed(3)
    row.append(title, readout)
    const slider = document.createElement('input')
    slider.type = 'range'
    slider.min = String(low)
    slider.max = String(high)
    slider.step = String(Math.max(0.001, (high - low) / 400))
    slider.value = String(value)
    slider.addEventListener('input', () => {
      readout.textContent = Number(slider.value).toFixed(3)
      queueJoint(name, Number(slider.value))
    })
    wrap.append(row, slider)
    jointSliders.append(wrap)
    inputs[name] = slider
    labels[name] = readout
  }
  state.jointState = { signature, inputs, labels }
}

// Sliders fire far faster than the bridge can accept; coalesce to one in flight.
const jointQueue = { pending: {}, inFlight: false }

function queueJoint(name, value) {
  jointQueue.pending[name] = value
  flushJoints()
}

async function flushJoints() {
  if (jointQueue.inFlight) return
  const positions = jointQueue.pending
  if (!Object.keys(positions).length) return
  jointQueue.pending = {}
  jointQueue.inFlight = true
  try {
    await fetch('/api/robot/joints', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ positions }),
    })
  } catch {} finally {
    jointQueue.inFlight = false
    if (Object.keys(jointQueue.pending).length) flushJoints()
  }
}

resetJoints.addEventListener('click', async () => {
  try {
    await fetch('/api/robot/reset', { method: 'POST' })
    const payload = await fetch('/api/robot', { cache: 'no-store' }).then((r) => r.json())
    if (payload.ok) { state.jointState = null; renderJointControls(payload.info) }
  } catch {}
})


// --- leader-arm status -----------------------------------------------------
//
// The leader is a separate process on whoever's machine holds the arm, so the
// page can only observe it. The one action offered here is to cut it loose.

async function refreshTeleop() {
  const jointDriven = Boolean(state.lastRobotInfo?.capabilities?.joints)
  // Never hide the panel while a leader might still be driving: the Disengage
  // button is the operator's stop control.
  const mayBeLive = state.teleopEngaged || jointDriven
  if (!mayBeLive) { teleopPanel.hidden = true; return }
  teleopPanel.hidden = false
  // Two timers drive this. Without a guard a slow reply can repaint the panel
  // with state older than what is already on screen.
  if (state.teleopFetching) return
  state.teleopFetching = true
  let info = null
  try {
    // Without a deadline a single stalled fetch latches the guard and the panel
    // freezes on stale state forever -- the opposite of what it is here for.
    const abort = new AbortController()
    const timer = setTimeout(() => abort.abort(), 4000)
    const payload = await fetch('/api/teleop/status', { cache: 'no-store', signal: abort.signal })
      .then((r) => r.json())
      .finally(() => clearTimeout(timer))
    info = payload.ok ? payload.teleop : null
    if (!payload.ok) throw new Error(payload.error || 'the bridge did not answer')
  } catch (err) {
    // The status channel is down; that says nothing about whether the arm is
    // still following. Keep the stop button, and stop claiming to know.
    teleopState.textContent = 'unknown'
    teleopPanel.className = 'teleop-panel'
    teleopHint.className = 'teleop-hint warn'
    teleopHint.textContent = `Cannot read the leader status (${err.message}). ` +
      'The arm may still be following. Disengage if you are unsure.'
    teleopDisengage.hidden = false
    teleopRate.textContent = '-'
    if (state.jointState) for (const slider of Object.values(state.jointState.inputs)) slider.disabled = false
    state.teleopFetching = false
    return
  }
  state.teleopFetching = false

  const engaged = Boolean(info?.engaged)
  const holding = Boolean(info?.holding)
  state.teleopEngaged = engaged
  teleopPanel.className = `teleop-panel${engaged ? (holding ? ' holding' : ' live') : ''}`
  teleopState.textContent = engaged ? (holding ? 'holding' : 'live') : 'idle'
  teleopSource.textContent = info?.source || '-'
  teleopRate.textContent = engaged ? `${info?.rate_hz ?? 0} Hz` : '-'
  teleopApplied.textContent = String(info?.applied ?? 0)
  teleopDropped.textContent = String(info?.dropped ?? 0)
  teleopDisengage.hidden = !engaged

  if (!engaged) {
    teleopHint.className = 'teleop-hint'
    teleopHint.textContent = 'No leader connected. Run tools/so101_leader.py on the machine the arm is plugged into.'
  } else if (holding) {
    teleopHint.className = 'teleop-hint warn'
    teleopHint.textContent = `The leader stopped sending ${info.idle_seconds}s ago. The arm is holding its last pose.`
  } else {
    const mapped = Object.keys(info?.last_positions || {}).length
    teleopHint.className = 'teleop-hint'
    teleopHint.textContent = `${mapped} joint${mapped === 1 ? '' : 's'} following the leader.` +
      (Object.keys(info?.calibration || {}).length ? ' Calibrated.' : ' Raw values, no calibration.')
  }

  // While a leader is driving, the sliders are a readout, not an input.
  if (engaged && state.mode !== 'robot') {
    teleopHint.className = 'teleop-hint warn'
    teleopHint.textContent = `A leader arm is driving the robot (${info.source}). Switch to Robot mode to see the joints.`
  }
  if (engaged && state.jointState) {
    for (const [name, value] of Object.entries(info.last_positions || {})) {
      const slider = state.jointState.inputs[name]
      if (!slider) continue
      slider.value = String(value)
      slider.disabled = true
      state.jointState.labels[name].textContent = Number(value).toFixed(3)
    }
  } else if (state.jointState) {
    for (const slider of Object.values(state.jointState.inputs)) slider.disabled = false
  }
}

teleopDisengage.addEventListener('click', async () => {
  teleopDisengage.disabled = true
  try {
    // A 503 here means the arm is still following. Saying "disengaged" anyway
    // would be the worst possible lie on this panel.
    const payload = await fetch('/api/teleop/disengage', { method: 'POST' }).then((r) => r.json())
    if (payload.ok) {
      logEvent('teleop', 'disengaged from the page')
    } else {
      logEvent('teleop-error', payload.error || 'disengage failed')
      teleopHint.className = 'teleop-hint warn'
      teleopHint.textContent = `Could not disengage: ${payload.error || 'the bridge refused'}. The arm may still be following.`
    }
  } catch (err) {
    logEvent('teleop-error', err.message)
    teleopHint.className = 'teleop-hint warn'
    teleopHint.textContent = `Could not disengage: ${err.message}. The arm may still be following.`
  } finally {
    teleopDisengage.disabled = false
    // Do NOT clear teleopFetching here: a status fetch may be legitimately in
    // flight, and clearing it produces the stale-repaint race the guard exists
    // to prevent.
    refreshTeleop()
  }
})

setInterval(refreshTeleop, 1000)


// --- the assistant ---------------------------------------------------------
//
// One shared conversation, streamed over SSE, so anyone with the page open
// watches the same work. Tool calls are rendered as they happen rather than
// summarised afterwards: seeing it call `look` and get a picture back is how
// the operator knows it checked rather than guessed.

const assistant = { busy: false, streaming: null, tools: new Map(), label: '' }

function assistantScroll() {
  assistantLog.scrollTop = assistantLog.scrollHeight
}

function assistantBubble(kind, text) {
  const node = document.createElement('div')
  node.className = `a-msg ${kind}`
  node.textContent = text
  assistantLog.append(node)
  assistantScroll()
  return node
}

function setAssistantBusy(busy, note = '') {
  assistant.busy = busy
  assistantInput.disabled = busy
  assistantSend.disabled = busy
  assistantHint.className = `assistant-hint${busy ? ' busy' : ''}`
  assistantHint.textContent = note || (busy ? 'working...' : assistant.label)
}

function renderToolCall(event) {
  const card = document.createElement('div')
  card.className = 'a-tool'
  const head = document.createElement('div')
  head.className = 'head'
  const name = document.createElement('span')
  name.textContent = event.name
  const timing = document.createElement('span')
  timing.textContent = '...'
  head.append(name, timing)
  const args = document.createElement('div')
  args.className = 'args'
  args.textContent = JSON.stringify(event.input ?? {})
  card.append(head, args)
  assistantLog.append(card)
  assistant.tools.set(event.id, { card, timing })
  assistantScroll()
}

function finishToolCall(event) {
  const entry = assistant.tools.get(event.id)
  if (!entry) return
  assistant.tools.delete(event.id)
  entry.card.classList.add(event.ok ? 'ok' : 'bad')
  entry.timing.textContent = `${event.ok ? '' : 'failed '}${event.ms ?? 0}ms`
  if (event.summary) {
    const out = document.createElement('div')
    out.className = 'out'
    out.textContent = String(event.summary)
    entry.card.append(out)
  }
  // A returned picture is the interesting part; show it inline.
  if (typeof event.preview === 'string' && event.preview.startsWith('data:image')) {
    const image = document.createElement('img')
    image.src = event.preview
    image.alt = 'what the assistant looked at'
    entry.card.append(image)
  }
  assistantScroll()
}

function handleAssistantEvent(event) {
  switch (event.type) {
    case 'hello':
      if (!event.configured) {
        assistantPanel.classList.add('off')
        assistantInput.disabled = true
        assistantSend.disabled = true
        assistantHint.className = 'assistant-hint bad'
        assistantHint.textContent = '模型服务尚未配置，请老师连接后使用。'
      } else {
        assistantPanel.classList.remove('off')
        assistant.label = `via ${event.model}`
        setAssistantBusy(Boolean(event.busy))
      }
      return
    case 'user_message':
      assistantBubble('user', event.text)
      setAssistantBusy(true)
      return
    case 'text_start':
      assistant.streaming = assistantBubble('model', '')
      return
    case 'text_delta':
      if (!assistant.streaming) assistant.streaming = assistantBubble('model', '')
      assistant.streaming.textContent += event.text
      assistantScroll()
      return
    case 'tool_input':
      assistant.streaming = null
      renderToolCall(event)
      return
    case 'tool_end':
      finishToolCall(event)
      // The scene may have changed under us; pick up the new session.
      refreshStatus()
      return
    case 'error':
      assistant.streaming = null
      assistantBubble('err', event.message)
      return
    case 'turn_end':
      assistant.streaming = null
      setAssistantBusy(false)
      return
    case 'reset':
      assistantLog.innerHTML = ''
      assistant.streaming = null
      setAssistantBusy(false)
      return
  }
}

function connectAssistant() {
  const source = new EventSource('/api/agent/events')
  source.onmessage = (message) => {
    try { handleAssistantEvent(JSON.parse(message.data)) } catch {}
  }
  source.onerror = () => {
    // EventSource reconnects on its own; say so rather than looking frozen.
    if (!assistant.busy) {
      assistantHint.className = 'assistant-hint bad'
      assistantHint.textContent = 'lost the connection to the assistant; reconnecting'
    }
  }
}

assistantForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  const text = assistantInput.value.trim()
  if (!text || assistant.busy) return
  assistantInput.value = ''
  setAssistantBusy(true)
  try {
    const payload = await fetch('/api/agent/message', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
    }).then((r) => r.json())
    if (!payload.ok) {
      assistantBubble('err', payload.error || 'the server refused the message')
      setAssistantBusy(false)
    }
  } catch (err) {
    assistantBubble('err', err.message)
    setAssistantBusy(false)
  }
})

assistantReset.addEventListener('click', async () => {
  try { await fetch('/api/agent/reset', { method: 'POST' }) } catch {}
  assistantLog.innerHTML = ''
})

function showNativeOverlay(title,text,canConnect=true) { streamTitle.textContent=title;streamText.textContent=text;streamOverlay.hidden=false;connectStreamButton.disabled=!canConnect||state.streamConnecting;disconnectStreamButton.disabled=!state.streamLive&&!state.streamConnecting }
function lifecycleDetail(evt){const raw=evt?.message?.info||evt?.message?.message||'';return `${evt?.phase||'stream'}:${evt?.status||''}${raw?` ${String(raw).slice(0,80)}`:''}`}

async function connectNativeSurface() {
  // A hidden video drops frames and can occupy the single primary stream.
  if (!launcher.hidden) return
  if (state.cfg?.renderer==='mock'||state.streamConnecting||state.streamLive)return
  if(!state.cfg.nativeBundleAvailable){
    startCompatSurface()
    $('connectionExplanation').textContent='服务器缺少 NVIDIA WebRTC 客户端组件，暂时使用 MJPEG 兼容画面。请在服务器构建组件后再试。'
    return
  }
  stopCompatSurface()
  const generation = ++state.streamGeneration
  const current = () => generation === state.streamGeneration
  streamSwitch.hidden=false;streamSwitch.textContent='WebRTC：正在连接'
  connectStreamButton.textContent='正在连接 WebRTC…'
  $('connectionExplanation').textContent='正在连接 NVIDIA Isaac Sim 的 WebRTC 服务；连接成功后才会显示已连接。'
  state.streamConnecting=true;setSurfaceState('connecting','Connecting directly through @nvidia/ov-web-rtc.');showNativeOverlay('Connecting to Isaac Sim',`${state.cfg.stream.host}:${state.cfg.stream.signalPort}`,false)
  try {
    if(!state.nativeModule)state.nativeModule=await import(`/native-sdk.js?v=${encodeURIComponent(state.cfg.version)}`)
    if(!current())return
    sdkValue.textContent='@nvidia/ov-web-rtc 6.6.0';video.hidden=false;mockCanvas.hidden=true;mockLegend.hidden=true
    await state.nativeModule.connectNativeStream({
      videoElementId:'remote-video',audioElementId:'remote-audio',signalingServer:state.cfg.stream.host,signalingPort:state.cfg.stream.signalPort,signalingPath:state.cfg.stream.signalPath||'',mediaServer:state.cfg.stream.host,mediaPort:state.cfg.stream.mediaPort,width:state.cfg.stream.width,height:state.cfg.stream.height,fps:state.cfg.stream.fps,
      callbacks:{
        onLifecycle:(evt)=>{const detail=lifecycleDetail(evt);if(evt.phase!=='update'||['error','warning','success'].includes(evt.status))logEvent('rtc',detail)},
        onLive:()=>{
          if(!current())return
          state.streamConnecting=false
          state.streamLive=true;state.surface='native';streamOverlay.hidden=true
          streamSwitch.textContent='当前：WebRTC 已连接'
          connectStreamButton.textContent='WebRTC 已连接';connectStreamButton.disabled=true
          disconnectStreamButton.disabled=false
          $('connectionExplanation').textContent='已连接 NVIDIA Isaac Sim 的 WebRTC 服务。实际清晰度与帧率以接收画面和统计为准。'
          setSurfaceState('live','Native WebRTC stream is live.');video.play().catch(()=>{});refreshModeText()
        },
        onStopped:()=>{
          if(!current()||state.compatLive)return
          state.streamLive=false;state.streamConnecting=false;state.surface='none'
          streamSwitch.textContent='画面已断开';connectStreamButton.textContent='重新连接 WebRTC'
          $('connectionExplanation').textContent='WebRTC 连接已停止。可重新连接，或改用 MJPEG 兼容画面。'
          setSurfaceState('error','WebRTC stream stopped.');showNativeOverlay('Stream disconnected','Reconnect when Isaac is ready.',true)
        },
        onError:(msg)=>{
          if(!current()||state.compatLive)return
          state.streamLive=false;state.streamConnecting=false
          logEvent('rtc-error',String(msg?.info||msg?.message||'WebRTC error'))
          startCompatSurface(`WebRTC 未收到画面，已自动回退。错误：${String(msg?.info||msg?.message||'未提供错误详情').slice(0,180)}`)
        },
        onStats:(stats)=>{if(current()){state.nativeStats=stats;updateStats(stats)}},onCustomEvent:(msg)=>logEvent('kit-event',JSON.stringify(msg).slice(0,120)),
      },
    })
  } catch(err){
    if(!current())return
    state.streamLive=false;state.streamConnecting=false;logEvent('rtc-error',err.message)
    if(current()&&!state.compatLive)startCompatSurface(`WebRTC 启动失败，已自动回退。错误：${String(err.message).slice(0,180)}`)
  }
}

async function teardownNativeStream(){
  state.streamLive=false;state.streamConnecting=false
  state.nativeStats=null;updateStats()
  video.hidden=true
  try{await state.nativeModule?.disconnectNativeStream?.()}catch{}
}

async function disconnectNativeSurface(){
  if(state.cfg?.renderer==='mock')return
  const generation = ++state.streamGeneration
  stopCompatSurface()
  await teardownNativeStream()
  if(generation !== state.streamGeneration)return
  state.surface='none'
  streamSwitch.textContent='画面已断开';connectStreamButton.textContent='连接 WebRTC'
  $('connectionExplanation').textContent='当前没有连接画面。断开画面不会关闭服务器或停止仿真。'
  setSurfaceState('idle','画面已断开');showNativeOverlay('画面已断开','可以连接 WebRTC，或改用 MJPEG 兼容画面。',true)
}
connectStreamButton.addEventListener('click',connectNativeSurface);disconnectStreamButton.addEventListener('click',disconnectNativeSurface)

async function refreshStatus() {
  try {
    const status=await fetch('/api/status',{cache:'no-store'}).then((r)=>r.json())
    setSignalState(status.signaling||{});setBridgeBadge(Boolean(status.bridge?.connected),status.bridge?.result)
    if(!status.bridge?.connected&&status.bridge?.busy)badge(previewBadge,'warn','Loading scene')
    if(status.capture)captureValue.textContent=status.capture.lastError?`error: ${String(status.capture.lastError).slice(0,40)}`:`${status.capture.clients} viewer(s) · ${status.capture.framesCaptured} frames · ${status.capture.writes} sent`
    if (state.compatLive) {
      // Some browsers finish an empty/closed MJPEG response without firing
      // error. Recover after bridge restarts and long initial scene loads.
      const frameCount = Number(status.capture?.framesCaptured || 0)
      if (!status.bridge?.connected || frameCount < (state.compatFrameCount || 0)) state.compatNeedsReconnect = true
      state.compatFrameCount = frameCount
      if (status.bridge?.connected && Date.now() - (state.compatRequestedAt || 0) > 5000 &&
          (state.compatNeedsReconnect || mjpegSurface.naturalWidth === 0)) reconnectCompatImage()
      const lastFrameAt = Number(status.capture?.lastFrameAt || 0)
      const hasRecentFrame = lastFrameAt > 0 && Date.now() - lastFrameAt < 10000
      state.compatHealthy = Boolean(status.bridge?.connected && hasRecentFrame && mjpegSurface.naturalWidth > 0)
      if (state.compatHealthy) setSurfaceState('live', 'Compatibility stream is receiving rendered frames.')
      else if (!status.bridge?.connected && !status.bridge?.busy) setSurfaceState('error', 'Isaac Sim bridge is offline; waiting for the simulation to start.')
      else setSurfaceState('connecting', 'Waiting for rendered frames from Isaac Sim.')
    }
  } catch {setSignalState({connected:false});setBridgeBadge(false)}
}

async function boot() {
  state.cfg=await fetch('/api/config',{cache:'no-store'}).then((r)=>r.json())
  const catalog=await fetch('/api/catalog',{cache:'no-store'}).then((r)=>r.json())
  state.catalog={scenes:catalog.scenes||[],robots:catalog.robots||[],challenges:catalog.challenges||[]}
  rendererValue.textContent=state.cfg.renderer;signalEndpoint.textContent=`${state.cfg.stream.host}:${state.cfg.stream.signalPort}/tcp`;mediaEndpoint.textContent=`${state.cfg.stream.host}:${state.cfg.stream.mediaPort}/udp`;bridgeEndpoint.textContent=`${state.cfg.bridgeHost}:${state.cfg.bridgePort}`;streamEndpoint.textContent=`${state.cfg.stream.host}:${state.cfg.stream.signalPort}`;sdkValue.textContent=state.cfg.renderer==='mock'?'not required in mock':(state.cfg.nativeBundleAvailable?'bundle ready':'bundle missing')
  renderLibrary();updateSpeedLabels();setMode('camera')
  try { const payload=await fetch('/api/session',{cache:'no-store'}).then((r)=>r.json()); if(payload.ok)applySession(payload.session) } catch {}
  if(!state.session){state.selectedSceneId=state.cfg.defaultSceneId;state.selectedRobotId=state.cfg.defaultRobotId;renderLibrarySelection();openLauncher()}
  else openLauncher()
  if(state.cfg.renderer==='mock')startMockSurface()
  else if(state.cfg.renderer==='mjpeg')startCompatSurface()
  else {showNativeOverlay('等待进入体验','选择伙伴和关卡后连接 WebRTC 画面。',false)}
  await refreshStatus()
  let teacher=true
  try {const response=await fetch('/platform/me',{signal:AbortSignal.timeout(3000)});if(response.ok)teacher=(await response.json()).principal.role==='teacher'} catch {}
  if(teacher)connectAssistant()
  else {assistantInput.disabled=true;assistantForm.querySelector('button[type=submit],button').disabled=true;assistantHint.textContent='此功能由老师管理'}
}

setInterval(()=>{if(state.mode==='robot'&&state.pressed.size>0)sendMotion(computeMotion(),'heartbeat')},100)
// Track actual presentation separately from received/dropped frame counters.
let presentedFrames=0,lastPresentedAt=null
if(video.requestVideoFrameCallback){
  const presented=()=>{presentedFrames++;lastPresentedAt=performance.now();video.requestVideoFrameCallback(presented)}
  video.requestVideoFrameCallback(presented)
}
// Local diagnostic feedback: decoded video, not merely successful signaling.
setInterval(()=>{
  if(state.cfg?.renderer!=='native')return
  const quality=video.getVideoPlaybackQuality?.()
  fetch('/api/stream/client-report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    visible:!document.hidden,surface:state.surface,width:video.videoWidth,height:video.videoHeight,
    frames:quality?.totalVideoFrames||0,dropped:quality?.droppedVideoFrames||0,
    time:video.currentTime,fps:state.nativeStats?.fps,mbps:state.nativeStats?.currentBitrate,rttMs:state.nativeStats?.rtd,
    presentedFrames,lastPresentedAgeMs:lastPresentedAt===null?null:performance.now()-lastPresentedAt,
  })}).catch(()=>{})
},5000)

// Camera keys in compatibility mode: A/D orbit, W/S dolly, Q/E pitch.
setInterval(() => {
  if (state.mode !== 'camera' || !state.compatLive || !state.orbit || state.pressed.size === 0) return
  const orbit = state.orbit
  if (state.pressed.has('a')) orbit.yaw += 0.05
  if (state.pressed.has('d')) orbit.yaw -= 0.05
  if (state.pressed.has('w')) orbit.dist = Math.max(0.8, orbit.dist - 0.18)
  if (state.pressed.has('s')) orbit.dist = Math.min(60, orbit.dist + 0.18)
  if (state.pressed.has('q')) orbit.pitch = Math.min(1.45, orbit.pitch + 0.035)
  if (state.pressed.has('e')) orbit.pitch = Math.max(-1.45, orbit.pitch - 0.035)
  pushCamera()
}, CAMERA_POST_MS)
setInterval(refreshStatus,3000)

// A stalled MJPEG stream does not fire an error. The connection goes away, the
// <img> keeps showing whatever arrived last, and nothing tells the page. The
// retry above only ever runs on an error event, so a stream that dies quietly
// leaves a still photograph on screen that looks like a live simulation --
// which is indistinguishable from a robot that has stopped moving.
//
// The server knows: it counts its stream clients. If it has none while this
// page believes it is watching, the connection is gone and re-attaching costs
// one request.
setInterval(async () => {
  if (!state.compatLive) return
  try {
    const status = await fetch('/api/status', { cache: 'no-store' }).then((r) => r.json())
    if ((status?.capture?.clients ?? 0) > 0) return
    logEvent('surface', 'stream had no client; reconnecting')
    mjpegSurface.src = `/api/stream.mjpg?t=${Date.now()}`
  } catch {}
}, 5000)
window.addEventListener('beforeunload',()=>{if(state.mode==='robot')clearKeys(true)})

const childUI = initChildUI({getState:()=>state,setMode,openLauncher,clearKeys})
initChallengesUI({getState:()=>state,guide:childUI.guide,launch:()=>{if(state.challenge?.level){state.selectedChallengeId=state.challenge.level.id;renderLibrary()}return launchSelectedSession()},openLauncher,clearKeys})
boot().catch((err)=>{console.error(err);logEvent('page-init-error',err.message);streamTitle.textContent='页面没有准备好';streamText.textContent='请刷新页面再试一次，也可以请老师查看操作日志。';streamOverlay.hidden=false})

// --- the legged robot's policy ----------------------------------------------
//
// A robot that walks because a network drives it needs two things the wheeled
// ones do not: a way to fire a one-shot move, and somewhere to put the ball
// back. Both existed on the bridge for hours and were reachable only by
// opening a TCP socket by hand, which is to say they did not exist.
const policyControls = document.getElementById('policyControls')
const policyName = document.getElementById('policyName')
const policyStats = document.getElementById('policyStats')
const followToggle = document.getElementById('followToggle')
let followOn = true

async function policyAction(action, extra = {}) {
  try {
    const reply = await fetch('/api/policy', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...extra }),
    }).then((r) => r.json())
    if (!reply.ok) throw new Error(reply.error || action + ' failed')
    logEvent('policy', action)
    return reply.result
  } catch (err) {
    logEvent('policy', `${action} failed: ${err.message}`)
    return null
  }
}

document.getElementById('kickRight').addEventListener('click', () => policyAction('kick', { side: 'right' }))
document.getElementById('kickLeft').addEventListener('click', () => policyAction('kick', { side: 'left' }))
document.getElementById('resetBall').addEventListener('click', () => policyAction('ball'))
followToggle.addEventListener('click', async () => {
  followOn = !followOn
  await policyAction('follow', { on: followOn })
  followToggle.textContent = followOn ? 'CAMERA: FOLLOWING' : 'CAMERA: FIXED'
})

async function refreshPolicy() {
  let policy = null
  try {
    const reply = await fetch('/api/policy', { cache: 'no-store' }).then((r) => r.json())
    policy = reply.ok ? reply.policy : null
  } catch {}
  const has = Boolean(policy?.available)
  policyControls.hidden = !has
  if (!has) return
  policyName.textContent = policy.engaged ? (policy.name || 'running') : 'stopped'
  followOn = Boolean(policy.following)
  followToggle.textContent = followOn ? 'CAMERA: FOLLOWING' : 'CAMERA: FIXED'
  const bits = []
  if (policy.realtime) bits.push(`${policy.realtime.toFixed(2)}x real time`)
  if (policy.control_hz) bits.push(`${policy.control_hz} Hz control`)
  // On a shared clock the renderer is stepping physics too, so the figure
  // above understates how fast the robot is actually running. Say so here
  // rather than let a wrong number pass for a right one.
  if (policy.engaged && policy.clock === 'shared') bits.push('shared clock: real time understated')
  if (policy.drift_mps != null) bits.push(`${(policy.drift_mps * 100).toFixed(1)} cm/s drift`)
  if (policy.error) bits.push(`error: ${policy.error}`)
  policyStats.textContent = bits.join(' · ')
}

setInterval(refreshPolicy, 2000)
refreshPolicy()

initAccessClient(async()=>{clearKeys(true);await disconnectNativeSurface()})
