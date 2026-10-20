import fs from 'node:fs'
const config = JSON.parse(fs.readFileSync(process.env.ISAAC_PLATFORM_CONFIG, 'utf8'))
const station = config.stations.find(s => s.id === process.env.ISAAC_STATION_ID)
const worker = process.argv[2] === 'worker'
const base = worker ? (station.workerOrigin || `http://127.0.0.1:${station.webPort}`) :
  `http://${config.host === '0.0.0.0' ? '127.0.0.1' : config.host}:${config.port}`
const headers = worker ? {'X-Isaac-Worker-Key': fs.readFileSync(process.env.ISAAC_WORKER_KEY_FILE, 'utf8').trim()} : {}
const response = await fetch(base + (worker ? '/api/config' : '/health'), {headers, signal: AbortSignal.timeout(3000)})
if (!response.ok) throw Error('Service health check failed')
// This checks the HTTP service only. GPU/scene/received video readiness is
// deliberately reported separately by manage.py ready and the browser.
