import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import {once} from 'node:events'
import {createRequire} from 'node:module'
import {createGateway} from '../server/platform/gateway.js'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright')
const root=path.resolve(import.meta.dirname,'..'),directory=fs.mkdtempSync(path.join(os.tmpdir(),'isaac-ui-test-'))
const gateway=createGateway({root,directory,config:{port:0,localConnector:{enabled:true,interfaces:['WLAN']},stations:[{id:'room1',name:'测试体验台',webPort:21991,bridgePort:21992,signalPort:21993,mediaPort:21994}]}})
gateway.access.bindArm({armId:'UI-test-arm',driver:'desheng-se-v401',calibrationHash:'a'.repeat(64)})
try{gateway.access.bindArm({armId:'UI-test-arm',driver:'desheng-se-v401',calibrationHash:'b'.repeat(64)})}catch{}
gateway.server.listen(0,'127.0.0.1');await once(gateway.server,'listening')
const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext(),page=await context.newPage(),errors=[]
page.on('pageerror',error=>errors.push(error.message))
try{
  const base=`http://127.0.0.1:${gateway.server.address().port}`
  await page.goto(base);await page.waitForFunction(()=>document.getElementById('connectorHelp').textContent.includes('免采集器配对码'))
  assert.equal(await page.evaluate(async()=> (await fetch('/platform/connector/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clientId:'browser-test'})})).status),403)
  await page.locator('#password').fill(fs.readFileSync(path.join(directory,'teacher-password.txt'),'utf8').trim())
  await page.locator('#teacherForm button').click();await page.locator('#manage').waitFor({state:'visible'})
  await page.getByRole('button',{name:'已核对设备与文件，使用新校准'}).click()
  await page.getByRole('button',{name:'已核对设备与文件，使用新校准'}).waitFor({state:'hidden'})
  assert.equal(gateway.access.arms()[0].calibrationHash,'b'.repeat(64))
  await page.locator('#deviceCode').click();await page.locator('#pairResult code').waitFor()
  assert.match(await page.locator('#pairResult code').innerText(),/^[A-F0-9]{12}$/)
  await page.locator('#browserCode').click();await page.waitForFunction(()=>document.getElementById('pairResult').textContent.startsWith('浏览器'))
  const code=await page.locator('#pairResult code').innerText()
  const learner=await browser.newContext(),p=await learner.newPage();await p.goto(base+'/login');await p.locator('#code').fill(code)
  // Verify redeem via browser context without opening any real simulator.
  const response=await learner.request.post(base+'/platform/pair',{data:{code}});assert.equal(response.status(),200)
  assert.equal((await learner.request.get(base+'/platform/diagnostics')).status(),403)
  assert.equal((await learner.request.get(base+'/platform/me')).status(),200)
  await learner.close();assert.deepEqual(errors,[])
  fs.mkdirSync(path.join(root,'run/platform-ui-check'),{recursive:true})
  await page.screenshot({path:path.join(root,'run/platform-ui-check/manage.png'),fullPage:true})
  console.log('Browser login, pairing, operator cookie, calibration approval and management permission: PASS')
}finally{await browser.close();gateway.close();await new Promise(r=>gateway.server.close(r));assert.ok(directory.startsWith(path.join(os.tmpdir(),'isaac-ui-test-')));fs.rmSync(directory,{recursive:true,force:true})}
