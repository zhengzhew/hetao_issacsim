import {
  AppStreamer,
  EventStatus,
  LogLevel,
  StreamType,
} from '@nvidia/ov-web-rtc'

let stream = null

function statusName(message) {
  return String(message?.status ?? '').toLowerCase()
}

export async function connectNativeStream(options = {}) {
  if (stream) {
    try { await stream.terminate() } catch {}
  }

  stream = new AppStreamer()

  const callbacks = options.callbacks || {}
  const streamConfig = {
    videoElementId: options.videoElementId || 'remote-video',
    audioElementId: options.audioElementId || 'remote-audio',
    signalingServer: options.signalingServer,
    signalingPort: Number(options.signalingPort || 49100),
    signalingPath: options.signalingPath ?? '',
    mediaServer: options.mediaServer || options.signalingServer,
    ...(options.mediaPort != null ? { mediaPort: Number(options.mediaPort) } : {}),
    authenticate: false,
    autoLaunch: true,
    mic: false,
    cursor: 'free',
    nativeTouchEvents: true,
    fitStreamResolution: false,
    width: Number(options.width || 1920),
    height: Number(options.height || 1080),
    fps: Number(options.fps || 60),
    maxReconnects: Number(options.maxReconnects ?? 8),
    connectivityTimeout: Number(options.connectivityTimeout ?? 3000),
    reconnectDelay: Number(options.reconnectDelay ?? 1500),
    onStart: (message) => {
      callbacks.onLifecycle?.({ phase: 'start', status: statusName(message), message })
      if (message?.status === EventStatus.SUCCESS || statusName(message) === 'success') callbacks.onLive?.(message)
      if (message?.status === EventStatus.ERROR || statusName(message) === 'error') callbacks.onError?.(message)
    },
    onStop: (message) => {
      callbacks.onLifecycle?.({ phase: 'stop', status: statusName(message), message })
      callbacks.onStopped?.(message)
    },
    onTerminate: (message) => {
      callbacks.onLifecycle?.({ phase: 'terminate', status: statusName(message), message })
    },
    onUpdate: (message) => callbacks.onLifecycle?.({ phase: 'update', status: statusName(message), message }),
    onCustomEvent: (message) => callbacks.onCustomEvent?.(message),
    onStreamStats: (message) => callbacks.onStats?.(message?.stats || message?.data?.stats || message?.data || message),
  }

  const props = {
    streamSource: StreamType.DIRECT,
    logLevel: LogLevel.WARN,
    streamConfig,
  }

  callbacks.onLifecycle?.({ phase: 'connect', status: 'inprogress' })
  const result = await stream.connect(props)
  return result
}

export async function disconnectNativeStream() {
  if (!stream) return
  const active = stream
  stream = null
  await active.terminate()
}

export function getNativeStreamStatus() {
  return stream?.streamStatus ?? null
}

export function setFitStreamResolution(enabled) {
  if (stream) stream.setFitStreamResolution(Boolean(enabled))
}

export async function resizeNativeStream(width, height) {
  if (!stream || !stream.allowDynamicResize) return { resized: false, reason: 'dynamic resize unavailable' }
  await stream.resize(Math.max(320, Math.round(width)), Math.max(240, Math.round(height)))
  return { resized: true }
}
