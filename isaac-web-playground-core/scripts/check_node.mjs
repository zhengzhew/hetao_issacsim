import fs from 'node:fs'
import path from 'node:path'
import {spawnSync} from 'node:child_process'
const root=path.resolve(import.meta.dirname,'..')
function check(dir){for(const item of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,item.name);if(item.isDirectory())check(p);else if(/\.(js|mjs)$/.test(p)&&!p.endsWith('native-sdk.js')){const result=spawnSync(process.execPath,['--check',p],{stdio:'inherit'});if(result.status!==0)process.exit(result.status||1)}}}
for(const dir of ['server','web','src','scripts','deploy/cloud'])check(path.join(root,dir))
console.log('JavaScript syntax passed')
