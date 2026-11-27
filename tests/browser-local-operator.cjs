'use strict';
/* Real Chromium integration QA of the private loopback financial workspace.
 * Synthetic numbers only. Python 3.12+, Node 22+, Edge/Chrome, no npm.
 * Starts a disposable 127.0.0.1:8765 backend and removes its test SQLite DB.
 * Never opens a network port, uploads customer data or alters browser profiles.
 */
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const cp=require('node:child_process');
const net=require('node:net');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const root=path.resolve(__dirname,'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'lk-browser-operator-'));
const password='synthetic-only-local-operator-test-2026';
const browserCandidates=[
  process.env.CHROME_BIN,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  '/usr/bin/chromium','/usr/bin/google-chrome','/usr/bin/chromium-browser'
];
const browserBin=browserCandidates.find(p=>p&&fs.existsSync(p));
if(!browserBin)throw Error('Missing Chromium');
let server,chrome,socket;
let id=1;
const pending=new Map();
const deadline=setTimeout(()=>{
  console.error('Operator browser test exceeded 75 seconds');
  try{chrome?.kill();server?.kill();}catch(_){}
  process.exit(1);
},75000);

function check(result,description){
  if(!result)throw Error('OPERATOR BROWSER FAILURE: '+description);
}
async function waitFor(checkFn,description,max=70){
  for(let i=0;i<max;i++){
    if(await checkFn())return;
    await sleep(150);
  }
  throw Error('Timeout: '+description);
}
async function checkPortFree(){
  await new Promise((resolve,reject)=>{
    const s=net.createServer();
    s.once('error',reject);
    s.listen(8765,'127.0.0.1',()=>s.close(resolve));
  });
}
async function launch(){
  await checkPortFree();
  const python=process.platform==='win32'?'python':'python3';
  server=cp.spawn(python,['broker/local_server.py'],{
    cwd:root,stdio:'ignore',
    env:{...process.env,LK_LOCAL_PASSWORD:password,
      LK_LOCAL_DB:path.join(temp,'qa.sqlite3')}
  });
  await waitFor(async()=>{
    if(server.exitCode!==null)throw Error('Local Python server failed to start');
    try{
      const r=await fetch('http://127.0.0.1:8765/api/session');
      return r.status===200;
    }catch(_){return false;}
  },'loopback operator server',60);
  chrome=cp.spawn(browserBin,[
    '--headless=new','--no-sandbox','--disable-gpu','--disable-extensions',
    '--no-first-run','--no-default-browser-check','--disable-background-networking',
    '--remote-allow-origins=*','--remote-debugging-port=0',
    '--user-data-dir='+path.join(temp,'chrome-profile'),
    'about:blank'
  ],{stdio:'ignore'});
  const activeFile=path.join(temp,'chrome-profile','DevToolsActivePort');
  await waitFor(()=>fs.existsSync(activeFile),'Chrome debugger port',60);
  const port=Number(fs.readFileSync(activeFile,'utf8').split(/\r?\n/)[0]);
  const tabs=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  const page=tabs.find(x=>x.type==='page');
  check(page&&page.webSocketDebuggerUrl,'CDP browser tab');
  socket=new WebSocket(page.webSocketDebuggerUrl);
  socket.onmessage=ev=>{
    const msg=JSON.parse(String(ev.data));
    const item=pending.get(msg.id);
    if(!item)return;
    pending.delete(msg.id);
    clearTimeout(item.timer);
    msg.error?item.reject(Error(msg.error.message)):item.resolve(msg.result);
  };
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('CDP open timeout')),7000);
    socket.onopen=()=>{clearTimeout(timer);resolve();};
    socket.onerror=()=>{clearTimeout(timer);reject(Error('CDP failure'));};
  });
}
function cdp(method,params={}){
  return new Promise((resolve,reject)=>{
    const next=id++;
    const timer=setTimeout(()=>{pending.delete(next);reject(Error('CDP timeout '+method));},12000);
    pending.set(next,{resolve,reject,timer});
    try{socket.send(JSON.stringify({id:next,method,params}));}
    catch(error){clearTimeout(timer);pending.delete(next);reject(error);}
  });
}
async function js(expression){
  const result=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error('JS exception '+result.exceptionDetails.text);
  return result.result?.value;
}
async function waitJs(expression,label){
  await waitFor(async()=>Boolean(await js(expression)),label);
}
async function qa(){
  await launch();
  await cdp('Runtime.enable');
  await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{
    width:1365,height:920,screenWidth:1365,screenHeight:920,
    deviceScaleFactor:1,mobile:false
  });
  await cdp('Page.navigate',{url:'http://127.0.0.1:8765/'});
  await waitJs('document.readyState==="complete"&&document.body?.dataset.localActive==="true"',
    'operator UI activates on trusted loopback only');
  await waitJs('!document.getElementById("localAuth").hidden','password gate');
  check(await js('document.getElementById("localWorkArea").hidden'),
    'private data visible before login');
  await js(`(()=>{
    const f=document.getElementById('localLoginForm');
    f.elements.password.value='synthetic-only-local-operator-test-2026';
    f.requestSubmit();
  })()`);
  await waitJs('!document.getElementById("localWorkArea").hidden','login via actual UI');
  check(await js(`[...document.querySelectorAll(
    '.nav button[data-tab="deals"],.nav button[data-tab="offers"],.nav button[data-tab="documents"],.nav button[data-tab="analytics"]'
  )].every(x=>getComputedStyle(x).display==='none')`),
    'synthetic sample tabs must not appear as operational in private mode');
  check(await js(`document.querySelector('#view-workspace').classList.contains('active')`),
    'local workspace is not the initial private page');
  await js(`document.getElementById('localCaseForm').requestSubmit()`);
  await waitJs('document.querySelectorAll("#localCaseList button").length===1',
    'create persisted case from form');
  await js(`document.getElementById('localNextStage').click()`);
  await waitJs('document.getElementById("localSelectedDescription").textContent.includes("collecting")',
    'advance workflow stage');
  for(const [ident,money] of [['001','120000'],['002','110000']]){
    await js(`(()=>{
      const f=document.getElementById('localOfferForm');
      f.elements.offer_id.value='off-${ident}';
      f.elements.lessor.value='Synthetic finance company ${ident}';
      f.elements.source_document_id.value='doc-${ident}';
      f.elements.monthly_payment.value='${money}';
      f.elements.verified_by_broker.value='true';
      f.requestSubmit();
    })()`);
    await waitJs(`document.getElementById('localCaseList').textContent.includes('${Number(ident)} КП')`,
      'save original quote '+ident);
  }
  check(await js(`document.getElementById('metricCasesNote').textContent==='в базе этого ПК' &&
             document.getElementById('metricCases').textContent==='1' &&
             document.getElementById('metricOffers').textContent==='2'`),
    'local KPI cards must reflect actual persisted finance records');
  await js(`document.getElementById('localCompare').click()`);
  await waitJs('document.querySelectorAll("#localResults tbody tr").length===2',
    'live comparison table');
  const rows=await js(`[...document.querySelectorAll('#localResults tbody tr')].map(tr=>tr.textContent)`);
  check(rows.some(x=>x.includes('off-002')&&x.includes('1')),'lower payment ranked first');
  const snap=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const screenshot=path.join(os.tmpdir(),'lk-local-operator-browser-qa.png');
  fs.writeFileSync(screenshot,Buffer.from(snap.data,'base64'));
  await js(`document.getElementById('localAudit').click()`);
  await waitJs('document.querySelector("#localResults th")?.textContent==="Версия"',
    'audit log button');
  const audit=await js('document.querySelectorAll("#localResults tbody tr").length');
  check(audit>=4,'missing persisted audit events');
  await js(`document.getElementById('localLogout').click()`);
  await waitJs('document.getElementById("localWorkArea").hidden','logout hides private workspace');
  console.log(JSON.stringify({ok:true,case_count:1,quotes:2,audit_events:audit,
    rows,screenshot,local_only:true},null,2));
}
(async()=>{
  try{await qa();}
  catch(error){console.error(error.stack||String(error));process.exitCode=1;}
  finally{
    clearTimeout(deadline);
    for(const item of pending.values()){clearTimeout(item.timer);item.reject(Error('shutting down'));}
    pending.clear();
    if(socket&&socket.readyState<=1)socket.close();
    try{chrome?.kill();}catch(_){}
    try{server?.kill();}catch(_){}
    await sleep(200);
    try{fs.rmSync(temp,{recursive:true,force:true,maxRetries:3,retryDelay:150});}catch(_){}
  }
})();
