// Standalone worker for Compose or a separate GPU host. No gateway/Kit spawning.
import fs from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {validateConfig} from './platform/gateway.js'
import {runtimePaths, readWorkerKey, stationEnvironment, prepareStationAssets} from './platform/runtime.js'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const locations = runtimePaths(root)
const config = validateConfig(JSON.parse(fs.readFileSync(locations.config, 'utf8')))
const station = config.stations.find(s => s.id === process.env.ISAAC_STATION_ID)
if (!station) throw Error('ISAAC_STATION_ID must identify a configured station')
const key = readWorkerKey()
if (!key) throw Error('Standalone workers require ISAAC_WORKER_KEY_FILE or ISAAC_WORKER_KEY')
prepareStationAssets(root, locations.data, station)
Object.assign(process.env, stationEnvironment(root, locations.data, station, key))
await import('./index.js')
