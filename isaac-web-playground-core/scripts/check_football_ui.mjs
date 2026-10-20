// Runs against real Isaac Sim and changes the shared virtual scene.
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createRequire } from 'node:module'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright')
const base=process.env.TEST_BASE||'http://127.0.0.1:8080'
const out='run/football-browser'
await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
const errors=[],checks=[]
const record=(name,result)=>{checks.push({name,result});console.log(name,JSON.stringify(result))}
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 page.on('pageerror',e=>errors.push(e.message))
 async function status(){return (await (await page.request.get(base+'/api/challenges')).json()).challenge}
 async function waitFor(check,seconds,message){
  const deadline=Date.now()+seconds*1000
  while(Date.now()<deadline){const value=await check();if(value)return value;await page.waitForTimeout(150)}
  throw Error(message)
 }
 await page.goto(base,{waitUntil:'domcontentloaded'})
 await page.locator('#launcher').waitFor({state:'visible'})
 await page.locator('#childSound').click()
 assert.equal(await page.locator('#robotLibrary button').count(),3)
 await page.locator('[data-scene-id="challenge-duck"]').click()
 assert.equal(await page.locator('#robotLibrary button').count(),4)
 assert.equal(await page.locator('#robotCount').textContent(),'4 个挑战')
 await page.locator('#nextStep').click()
 await page.locator('[data-level-id="duck-football"]').click()
 await page.screenshot({path:out+'/fourth-level.png',fullPage:true})
 const launch=page.waitForResponse(r=>r.url().endsWith('/api/challenges/start')&&r.request().method()==='POST',{timeout:120000})
 await page.locator('#launchSession').click()
 const loaded=await(await launch).json()
 assert.equal(loaded.ok,true);assert.equal(loaded.challenge.level.id,'duck-football')
 await page.locator('#launcher').waitFor({state:'hidden'})
 await page.locator('#challengeActions button').filter({hasText:'右脚踢球'}).waitFor({state:'visible'})
 await page.waitForTimeout(2200)
 const before=await status()
 assert.equal(before.complete,false);assert.equal(before.error,null);assert.equal(before.telemetry.objects.length,1)
 assert(Math.abs(before.telemetry.objects[0].p[0]-.09)<.01,'Ball moved before a kick')
 record('fourth level ready',{ball:before.telemetry.objects[0].p,robot:loaded.session.robotId,goal:before.level.goal})
 const kick=page.waitForResponse(r=>r.url().endsWith('/api/challenges/action')&&r.request().method()==='POST')
 await page.locator('#challengeActions button').filter({hasText:'右脚踢球'}).click()
 assert.equal((await(await kick).json()).accepted,true)
 const scored=await waitFor(async()=>{const s=await status();assert.equal(s.error,null);return s.complete&&s},10,'The physical kick did not score')
 assert(scored.telemetry.objects[0].p[0]>.58)
 await waitFor(async()=>(await page.locator('#challengeProgress').textContent()).includes('进球'),4,'UI did not show the goal')
 record('goal via browser click',{complete:scored.complete,ball:scored.telemetry.objects[0].p,robot:scored.telemetry.robot.p})
 try{await page.waitForFunction(()=>document.querySelector('#remote-video').videoWidth>0,{},{timeout:12000})}catch{}
 record('WebRTC sample',await page.locator('#remote-video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,time:v.currentTime,frames:v.getVideoPlaybackQuality?.().totalVideoFrames||0})))
 await page.screenshot({path:out+'/scored.png',fullPage:true})
 const retry=page.waitForResponse(r=>r.url().endsWith('/api/challenges/start')&&r.request().method()==='POST',{timeout:120000})
 await page.locator('#retryChallenge').click()
 assert.equal((await(await retry).json()).ok,true)
 await page.waitForTimeout(1500)
 const reset=await status()
 assert.equal(reset.complete,false);assert(Math.abs(reset.telemetry.objects[0].p[0]-.09)<.01)
 record('retry resets ball and score',{complete:reset.complete,ball:reset.telemetry.objects[0].p})
 assert.deepEqual(errors,[])
 record('PASS',{errors})
} catch(e){record('FAIL',{error:e.message,errors});throw e}
finally {await fs.writeFile(out+'/results.json',JSON.stringify({checks,errors},null,2));await browser.close()}
