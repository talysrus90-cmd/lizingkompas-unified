'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('variant-5.html','utf8');
const localUI=fs.readFileSync('broker-local-ui.js','utf8');

test('compact dark menu is a small right-aligned popover, not full-width white list',()=>{
  assert.ok(html.includes('id="mobileMenu" aria-label="Меню сайта"'));
  assert.match(html,/header #mobileMenu\.open\{[\s\S]{0,1000}position:absolute!important/);
  assert.match(html,/width:min\(334px,calc\(100vw - 20px\)\)/);
  assert.match(html,/max-height:min\(54dvh,480px\)/);
  assert.match(html,/background:#303239!important/);
  assert.match(html,/-webkit-overflow-scrolling:touch/);
  assert.ok(!html.includes('color:#20394b;background:white;border:0;border-bottom:1px'));
});
test('menu preserves the original set of links, downloads, installation and phone',()=>{
  const nav=html.match(/<nav class="mobile-menu" id="mobileMenu"[\s\S]*?<\/nav>/)?.[0];
  assert.ok(nav,'menu exists');
  for(const href of ['#services','#calc-section','#request','#send-offer','#support-route',
                     '#cases','#b2b','#partner-tools','#blog','./leasing-checklist.html',
                     '#about','#contacts','./leasing-compass.vcf','tel:+79604844141']){
    assert.ok(nav.includes('href="'+href+'"'),'link missing: '+href);
  }
  assert.match(nav,/id="lkInstallMenu"/);
  assert.equal((nav.match(/class="lk-menu-group"/g)||[]).length,3);
  assert.match(nav,/class="lk-menu-group lk-menu-utilities"/);
  assert.match(nav,/class="lk-menu-icon"/);
});
test('public GitHub preview does not run private local UI',()=>{
  let touched=false;
  const document={get body(){touched=true;throw new Error('public page local UI active')}};
  const location={hostname:'talysrus90-cmd.github.io',protocol:'https:'};
  vm.runInNewContext(localUI,{document,location});
  assert.equal(touched,false);
});
test('ergonomic broker workspace supports light/dark without storing secrets',()=>{
  const b=fs.readFileSync('broker-preview.html','utf8');
  const j=fs.readFileSync('broker-preview.js','utf8');
  assert.match(b,/:root\[data-theme="dark"\]/);
  assert.match(b,/id="themeToggle"/);
  assert.match(j,/themeButton\.addEventListener\("click"/);
  const liveCode=localUI.replace(/\/\*[\s\S]*?\*\//g,'');
  assert.doesNotMatch(liveCode,/(?:localStorage|sessionStorage|sendBeacon|WebSocket)/);
});

test('local operator UI rejects arbitrary loopback ports and non-loopback URLs',()=>{
  const locked={get body(){throw new Error('operator UI must stay inactive')}};
  for(const location of [
    {hostname:'127.0.0.1',protocol:'http:',port:'58766'},
    {hostname:'127.0.0.1',protocol:'https:',port:'8765'},
    {hostname:'localhost',protocol:'http:',port:'8765'},
    {hostname:'talysrus90-cmd.github.io',protocol:'https:',port:''}
  ]){
    assert.doesNotThrow(()=>vm.runInNewContext(localUI,{document:locked,location}));
  }
  assert.match(localUI,/location\.port !== "8765"/);
});
