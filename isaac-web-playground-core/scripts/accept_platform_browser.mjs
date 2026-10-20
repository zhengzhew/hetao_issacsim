// Real gateway + operator browser smoke. Changes only the virtual level to arm-dice.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import {createRequire} from 'node:module'
const require=createRequire(import.meta.url),{chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright')
const root=path.resolve(import.meta.dirname,'..'),base=process.env.TEST_BASE||'http://127.0.0.1:8080',out=path.join(root,'run/platform-browser-live')
fs.mkdirSync(out,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=no-user-gesture-required']})
const teacher=await browser.newContext(),learner=await browser.newContext({viewport:{width:1440,height:1000}}),page=await learner.newPage(),errors=[]
page.on('pageerror',e=>errors.push(e.message));let principal
const api=async(route,data)=>{const r=data===undefined?await teacher.request.get(base+route):await teacher.request.post(base+route,{data});assert.ok(r.ok(),route+' '+r.status());return r.json()}
try{
  await api('/platform/login',{password:fs.readFileSync(path.join(root,'run/platform/teacher-password.txt'),'utf8').trim()})
  const me=await api('/platform/me'),stationId=me.stations[0].id
  const diagnostics=await api('/platform/diagnostics');assert.ok(!diagnostics.clients.some(c=>c.role==='operator'&&c.stationId===stationId),'Station has a paired operator; leave their session alone')
  const {code}=await api('/platform/codes',{stationId,role:'operator'})
  await page.goto(base+'/login');await page.locator('#code').fill(code)
  await page.locator('#pairForm button').click();await page.waitForURL(base+'/');principal=(await(await learner.request.get(base+'/platform/me')).json()).principal
  await page.locator('#launcher').waitFor({state:'visible',timeout:20000})
  await page.locator('[data-scene-id="challenge-arm"]').click();await page.locator('#nextStep').click();await page.locator('[data-level-id="arm-dice"]').click()
  const launched=page.waitForResponse(r=>r.url().endsWith('/api/challenges/start'),{timeout:120000});await page.locator('#launchSession').click();assert.equal((await(await launched).json()).ok,true)
  await page.locator('#launcher').waitFor({state:'hidden',timeout:20000});await page.locator('#challengeName').filter({hasText:'幸运骰子'}).waitFor()
  assert.equal(await page.getByRole('button',{name:/抛出骰子/}).count(),0)
  assert.equal((await learner.request.post(base+'/api/assets',{data:{}})).status(),403)
  await page.waitForFunction(()=>document.getElementById('remote-video').videoWidth>0,null,{timeout:45000})
  const sample=()=>page.locator('#remote-video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,frames:v.getVideoPlaybackQuality().totalVideoFrames,dropped:v.getVideoPlaybackQuality().droppedVideoFrames,time:v.currentTime,paused:v.paused}))
  const first=await sample();await page.waitForTimeout(3500);const last=await sample()
  assert.ok(last.time>first.time+.5,'Video time did not advance');assert.ok(last.frames>first.frames,'No new decoded video frames')
  assert.deepEqual(errors,[])
  await page.screenshot({path:path.join(out,'arm-dice.png'),fullPage:true})
  const result={at:new Date().toISOString(),realGateway:true,role:principal.role,manualDiceOnly:true,operatorAdminDenied:true,first,last,errors}
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result))
}finally{
  if(!principal){try{principal=(await(await learner.request.get(base+'/platform/me')).json()).principal}catch{}}
  if(principal?.role==='operator')await api('/platform/revoke',{id:principal.id})
  await api('/platform/logout',{}).catch(()=>{});await browser.close()
}
