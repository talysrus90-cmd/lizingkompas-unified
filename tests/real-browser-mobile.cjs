'use strict';
/*
 * Real Chromium mobile smoke test using native Node 22 WebSocket and CDP.
 * No npm dependencies. Separate temporary headless profile; no cookies from
 * the user's everyday browser, no form submissions, no customer data.
 *
 * Run: node tests/real-browser-mobile.cjs
 * Optional: CHROME_BIN=<path to Chromium> node tests/real-browser-mobile.cjs
 *
 * Tests the actually published site, not fake DOM mocks.
 */
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const cp=require('node:child_process');
const assert=require('node:assert/strict');

const RAW_BASE=process.env.LK_BROWSER_BASE||'https://talysrus90-cmd.github.io/lizingkompas-unified/';
const BASE=RAW_BASE.endsWith('/')?RAW_BASE:RAW_BASE+'/';
const URL_V5=BASE+'variant-5.html?v=508&qa=mobile-headless-20261127';
const URL_BROKER=BASE+'broker-preview.html?qa=mobile-headless-20261127';
const candidates=[
  process.env.CHROME_BIN,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  '/usr/bin/chromium','/usr/bin/google-chrome','/usr/bin/chromium-browser'
];
const BROWSER=candidates.find(p=>p&&fs.existsSync(p));
if(!BROWSER)throw Error('Chromium/Edge not found; set CHROME_BIN');
const folder=fs.mkdtempSync(path.join(os.tmpdir(),'lk-v5-cdp-'));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const chrome=cp.spawn(BROWSER,[
  '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
  '--disable-extensions','--disable-background-networking','--no-sandbox',
  '--remote-allow-origins=*','--remote-debugging-port=0',
  '--user-data-dir='+folder,'about:blank'
],{stdio:'ignore'});
const printed=[];
let socket;
let nextId=1;
const pending=new Map();

async function connect(){
  let port;
  for(let tries=0;tries<80;tries++){
    const file=path.join(folder,'DevToolsActivePort');
    if(fs.existsSync(file)){
      const text=fs.readFileSync(file,'utf8').trim();
      port=Number(text.split(/\r?\n/)[0]);
      if(Number.isInteger(port)&&port>0)break;
    }
    if(chrome.exitCode!==null)throw Error('Chromium exited before CDP opened');
    await sleep(100);
  }
  if(!port)throw Error('CDP port timeout');
  let page;
  for(let tries=0;tries<30;tries++){
    const response=await fetch('http://127.0.0.1:'+port+'/json/list');
    const targets=await response.json();
    page=targets.find(x=>x.type==='page'&&x.webSocketDebuggerUrl);
    if(page)break;
    await sleep(100);
  }
  if(!page)throw Error('No CDP tab');
  socket=new WebSocket(page.webSocketDebuggerUrl);
  socket.onmessage=event=>{
    const payload=JSON.parse(String(event.data));
    if(!payload.id)return;
    const entry=pending.get(payload.id);
    if(!entry)return;
    pending.delete(payload.id);
    payload.error?entry.reject(Error(payload.error.message)):entry.resolve(payload.result||{});
  };
  await new Promise((resolve,reject)=>{
    socket.onopen=resolve;
    socket.onerror=reject;
  });
}
function command(method,params={}){
  const id=nextId++;
  return new Promise((resolve,reject)=>{
    pending.set(id,{resolve,reject});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression){
  const out=await command('Runtime.evaluate',{
    expression,returnByValue:true,awaitPromise:true
  });
  if(out.exceptionDetails)throw Error('Evaluation error: '+out.exceptionDetails.text);
  return out.result?.value;
}
async function waitReady(url){
  await command('Page.navigate',{url});
  for(let i=0;i<90;i++){
    const ready=await evaluate('document.readyState==="complete"&&!!document.body');
    if(ready)break;
    await sleep(120);
    if(i===89)throw Error('Timeout loading '+url);
  }
  await sleep(900);
}
async function shot(filename){
  const result=await command('Page.captureScreenshot',{
    format:'png',captureBeyondViewport:false,fromSurface:true
  });
  if(!result.data)throw Error('Missing screenshot');
  const output=path.join(os.tmpdir(),filename);
  fs.writeFileSync(output,Buffer.from(result.data,'base64'));
  printed.push(output);
}
function check(condition,message){
  if(!condition)throw Error('SMOKE FAIL: '+message);
}
async function smoke(){
  await connect();
  await command('Page.enable');
  await command('Runtime.enable');
  await command('Emulation.setDeviceMetricsOverride',{
    width:393,height:851,deviceScaleFactor:1,mobile:true,
    screenWidth:393,screenHeight:851
  });
  await command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
  await waitReady(URL_V5);
  const initial=await evaluate(`({
    url:location.href,
    innerWidth:innerWidth,documentWidth:document.documentElement.scrollWidth,
    menuDisplay:getComputedStyle(document.getElementById('mobileMenu')).display,
    burgerExists:!!document.getElementById('burgerBtn'),
    scripts:[...document.scripts].map(x=>x.src).filter(x=>x.includes('lk-ui-v504'))
  })`);
  check(initial.burgerExists,'menu toggle missing');
  check(initial.innerWidth===393,'mobile viewport emulation not active');
  check(initial.menuDisplay==='none','menu visible by default');
  await shot('lk-v5-mobile-closed-cdp.png');

  const before=await command('Page.getNavigationHistory');
  await evaluate('document.getElementById("burgerBtn").click()');
  await sleep(200);
  const opened=await evaluate(`(()=>{
    const el=document.getElementById('mobileMenu'),r=el.getBoundingClientRect(),c=getComputedStyle(el);
    return {open:el.classList.contains('open'),
      width:r.width,height:r.height,left:r.left,right:r.right,top:r.top,
      computedBg:c.backgroundColor,position:c.position,
      scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,
      scrollable:el.scrollHeight>el.clientHeight,
      bodyWidth:document.documentElement.scrollWidth,
      aria:document.getElementById('burgerBtn').getAttribute('aria-expanded'),
      menuEntries:el.querySelectorAll('a').length};
  })()`);
  check(opened.open,'menu not opened');
  check(opened.aria==='true','aria-expanded mismatch');
  check(opened.width<=335&&opened.width>=280,'menu not compact: '+opened.width);
  check(opened.height<=851*.54+3,'menu too tall: '+opened.height);
  check(opened.left>=0&&opened.right<=393+1,'menu extends outside viewport');
  check(opened.position==='absolute','menu is not floating popover');
  check(opened.computedBg==='rgb(48, 50, 57)','menu background not dark');
  check(opened.menuEntries>=14,'menu links missing');
  await shot('lk-v5-mobile-open-cdp.png');

  const during=await command('Page.getNavigationHistory');
  check(during.currentIndex===before.currentIndex+1,'temporary Back entry missing');
  await command('Page.navigateToHistoryEntry',{entryId:during.entries[during.currentIndex-1].id});
  await sleep(300);
  const closed=await evaluate(`({
    open:document.getElementById('mobileMenu').classList.contains('open'),
    aria:document.getElementById('burgerBtn').getAttribute('aria-expanded'),
    url:location.href
  })`);
  check(!closed.open,'Android Back did not close menu');
  check(closed.aria==='false','aria-expanded not reset');
  check(closed.url.includes('variant-5.html'),'Back left the site');

  await waitReady(URL_BROKER);
  const broker=await evaluate(`({
    title:document.title,
    theme:document.documentElement.dataset.theme,
    nav:document.querySelectorAll('[data-tab]').length,
    loginVisibility:getComputedStyle(document.getElementById('view-workspace')).display,
    publicApiUsed:document.body.dataset.localActive==='true',
    bodyWidth:document.documentElement.scrollWidth,
    viewportWidth:innerWidth,
    shellWidth:document.querySelector('.shell').getBoundingClientRect().width,
    contentWidth:document.querySelector('.content').getBoundingClientRect().width,
    metricWidth:document.querySelector('.metric').getBoundingClientRect().width,
    navClientWidth:document.querySelector('.nav').clientWidth,
    navScrollWidth:document.querySelector('.nav').scrollWidth,
    metricsWidth:document.querySelector('.metrics').getBoundingClientRect().width,
    metricsCols:getComputedStyle(document.querySelector('.metrics')).gridTemplateColumns,
    gridCss:getComputedStyle(document.querySelector('.shell')).gridTemplateColumns,
    mq760:matchMedia('(max-width:760px)').matches,
    shellScrollWidth:document.querySelector('.shell').scrollWidth
  })`);
  check(broker.bodyWidth<=395,
      'broker has horizontal page overflow: '+broker.bodyWidth+' for 393px device');
  check(broker.contentWidth<=395,
      'broker content wider than 393px mobile screen: '+broker.contentWidth);
  console.log('BROKER_LAYOUT',JSON.stringify(broker));
  check(broker.metricWidth<=220,
      'broker KPI cards are oversized on mobile: '+broker.metricWidth);
  check(!broker.publicApiUsed,'public GitHub page incorrectly enabled local backend');
  check(broker.theme==='light','broker not opening in calm light theme');
  await shot('lk-v5-broker-light-cdp.png');
  await evaluate('document.getElementById("themeToggle").click()');
  check(await evaluate('document.documentElement.dataset.theme')==='dark','theme button failed');
  const selected=await evaluate(`(()=>{
    const el=document.querySelector('.case[aria-pressed="true"]'), style=getComputedStyle(el);
    return {color:style.color,background:style.backgroundColor,width:el.getBoundingClientRect().width};
  })()`);
  const lum=color=>{
    const vals=color.match(/\\d+(?:\\.\\d+)?/g)?.slice(0,3).map(Number)||[];
    const rgb=vals.map(x=>{const v=x/255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
    return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];
  };
  const ratio=(a,b)=>{const vals=[lum(a),lum(b)].sort((x,y)=>y-x);return (vals[0]+.05)/(vals[1]+.05);};
  const selectedContrast=ratio(selected.color,selected.background);
  check(selectedContrast>=4.5,'dark selected deal contrast too low: '+selectedContrast.toFixed(2));
  await shot('lk-v5-broker-dark-cdp.png');
  console.log(JSON.stringify({ok:true,browser:BROWSER,initial,opened,closed,broker,selected,selectedContrast,screenshots:printed},null,2));
}
(async()=>{
  try{await smoke();}
  catch(error){console.error(error.stack||String(error));process.exitCode=1;}
  finally{
    for(const entry of pending.values())entry.reject(Error('Browser shutting down'));
    pending.clear();
    if(socket&&socket.readyState<=1)socket.close();
    try{await command('Browser.close');}catch(_){}
    chrome.kill();
    await sleep(200);
    try{fs.rmSync(folder,{recursive:true,force:true,maxRetries:3,retryDelay:100});}catch(_){}
  }
})();
