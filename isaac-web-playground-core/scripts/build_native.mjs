import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const outfile = path.join(root, 'web', 'native-sdk.js')

let build
try {
  ;({ build } = await import('esbuild'))
} catch {
  console.error('[native-build] esbuild is not installed. Run: npm install')
  process.exit(2)
}

try {
  import.meta.resolve('@nvidia/ov-web-rtc')
} catch (err) {
  console.error('[native-build] @nvidia/ov-web-rtc is not installed or cannot be resolved.')
  console.error('[native-build] Run: npm install')
  console.error(`[native-build] ${err.message}`)
  process.exit(2)
}

await build({
  entryPoints: [path.join(root, 'src', 'native_stream_sdk.js')],
  outfile,
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: ['chrome120'],
  sourcemap: true,
  legalComments: 'eof',
})

const size = fs.statSync(outfile).size
console.log(`[native-build] wrote ${outfile} (${Math.round(size / 1024)} KiB)`)
