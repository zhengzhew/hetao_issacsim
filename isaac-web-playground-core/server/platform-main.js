import fs from 'node:fs'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawn} from 'node:child_process'
import {createGateway,validateConfig} from './platform/gateway.js'
import {runtimePaths, readWorkerKey, stationEnvironment, prepareStationAssets} from './platform/runtime.js'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const locations=runtimePaths(root)
const config=validateConfig(JSON.parse(fs.readFileSync(locations.config,'utf8')))
const directory=locations.data
const mode=process.env.ISAAC_PLATFORM_MODE||'managed'
if(!['managed','external'].includes(mode))throw Error('ISAAC_PLATFORM_MODE must be managed or external')
const workerKey=readWorkerKey()
if(mode==='external'&&!workerKey)throw Error('External mode requires ISAAC_WORKER_KEY_FILE or ISAAC_WORKER_KEY')
const gateway=createGateway({config,root,directory,workerKey})
const children=new Set(),records=new Map()
let stopping=false
const isaacDir=process.env.ISAAC_DIR||(process.platform==='win32'?'D:\\IsaacSim\\6.0.1':'/isaac-sim')
const streamHost=process.env.ISAAC_STREAM_HOST||'127.0.0.1'
function logLine(file,chunk){
  try{
    if(fs.existsSync(file)&&fs.statSync(file).size>10*1024*1024){
      for(let n=3;n>=1;n--){const old=file+'.'+n;if(fs.existsSync(old)){if(n===3)fs.unlinkSync(old);else fs.renameSync(old,file+'.'+(n+1))}}
      fs.renameSync(file,file+'.1')
    }
    fs.appendFileSync(file,chunk)
  }catch(error){console.error('Log write failed:',error.message)}
}
function launch(name,command,args,env,cwd=root,options={}){
  const state={restarts:0,process:null,timer:null};records.set(name,state)
  function start(){
    if(stopping)return
    const child=spawn(command,args,{cwd,env,windowsHide:true,stdio:['ignore','pipe','pipe'],...options})
    state.process=child;children.add(child)
    const log=path.join(directory,name+'.log')
    child.stdout.on('data',chunk=>logLine(log,chunk));child.stderr.on('data',chunk=>logLine(log,chunk))
    child.on('error',error=>logLine(log,Buffer.from(error.message+'\n')))
    child.on('exit',()=>{
      children.delete(child)
      if(!stopping&&++state.restarts<=5)state.timer=setTimeout(start,Math.min(30000,1000*2**state.restarts))
      else if(!stopping)console.error(`${name} repeatedly exited; inspect ${log}`)
    })
  }
  start()
}
function copyAssets(source,destination){
  fs.mkdirSync(destination,{recursive:true})
  for(const entry of fs.readdirSync(source,{withFileTypes:true})){
    const src=path.join(source,entry.name),dst=path.join(destination,entry.name)
    if(entry.isSymbolicLink())throw Error('Asset symlinks require explicit deployment handling')
    if(entry.isDirectory())copyAssets(src,dst)
    else if(entry.isFile())fs.copyFileSync(src,dst)
  }
}
function prepare(station){
  const stationDir=path.join(directory,station.id);fs.mkdirSync(stationDir,{recursive:true})
  const uploads=path.join(stationDir,'uploads');fs.mkdirSync(uploads,{recursive:true})
  const source=path.join(root,'uploads/challenges'),destination=path.join(uploads,'challenges')
  const marker=path.join(stationDir,'assets-ready.json')
  if(process.env.ISAAC_CHALLENGE_ASSETS_DIR)prepareStationAssets(root,directory,station)
  else if(!fs.existsSync(marker)&&fs.existsSync(source)){copyAssets(source,destination);fs.writeFileSync(marker,JSON.stringify({at:Date.now()}))}
  const env=stationEnvironment(root,directory,station,workerKey||gateway.access.data.workerKey)
  launch(station.id+'-web',process.execPath,[path.join(root,'server/index.js')],env)
  if(process.env.ISAAC_PLATFORM_NO_KIT==='1')return
  if(process.platform==='win32'){
    const python=path.join(isaacDir,'python.bat')
    if(!fs.existsSync(python))throw Error(`Isaac Sim not found: ${python}`)
    const batch=path.join(stationDir,'bridge.cmd')
    const entry=path.join(root,'bridge/isaac_playground.py')
    if(/["\r\n]/.test(python+entry))throw Error('Unsupported launch path')
    fs.writeFileSync(batch,`@echo off\r\nchcp 65001 >nul\r\ncall "${python}" "${entry}" --host 127.0.0.1 --port ${station.bridgePort} --livestream --hide-ui --idle-after 0 --no-multi-gpu --gpu ${station.gpu||0}\r\nexit /b %errorlevel%\r\n`)
    launch(station.id+'-kit',process.env.ComSpec||'cmd.exe',['/d','/s','/c',`""${batch}""`],env,isaacDir,{windowsVerbatimArguments:true})
  }else{
    launch(station.id+'-kit',path.join(isaacDir,'python.sh'),[path.join(root,'bridge/isaac_playground.py'),'--host','127.0.0.1','--port',String(station.bridgePort),'--livestream','--hide-ui','--idle-after','0','--no-multi-gpu','--gpu',String(station.gpu||0)],env,isaacDir)
  }
}
function stop(){
  if(stopping)return;stopping=true
  for(const r of records.values())clearTimeout(r.timer)
  gateway.close();gateway.server.close()
  for(const child of children){
    if(process.platform==='win32')spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'})
    else child.kill('SIGTERM')
  }
  setTimeout(()=>process.exit(0),1500).unref()
}
process.on('SIGINT',stop);process.on('SIGTERM',stop)
gateway.server.once('error',error=>{console.error(error.message);stop();process.exitCode=1})
gateway.server.listen(config.port,config.host||'0.0.0.0',()=>{
  console.log(`Platform ${config.publicOrigin||`http://${streamHost}:${config.port}`}/ · Teacher password: ${path.join(directory,'teacher-password.txt')}`)
  try {if(mode==='managed')for(const station of config.stations)prepare(station)}catch(error){console.error(error.message);stop()}
})
