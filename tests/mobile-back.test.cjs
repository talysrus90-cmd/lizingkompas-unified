'use strict';
/* V5 three-dot menu integration tests without a browser dependency.
   The fake history models pushState, back and popstate. Browser/device
   verification is still required before claiming cross-browser perfection. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('lk-ui-v504.js','utf8');

function element(name){
  const values=new Set();
  const events=new Map();
  const attributes=new Map();
  return {
    name, dataset:{}, attributes, focused:false, modalOpen:false,
    classList:{
      contains:c=>values.has(c), add:c=>values.add(c), remove:c=>values.delete(c),
      toggle:c=>values.has(c)?(values.delete(c),false):(values.add(c),true)
    },
    setAttribute:(k,v)=>attributes.set(k,String(v)),
    getAttribute:k=>attributes.get(k)||null,
    addEventListener:(type,fn,opts={})=>{
      const list=events.get(type)||[];
      list.push({fn,capture:!!opts.capture});
      events.set(type,list);
    },
    emit(type,extra={}){
      const e={
        type, target:this, defaultPrevented:false,
        preventDefault(){this.defaultPrevented=true;}, ...extra
      };
      const listeners=events.get(type)||[];
      for(const item of listeners.filter(x=>x.capture))item.fn(e);
      for(const item of listeners.filter(x=>!x.capture))item.fn(e);
      return e;
    },
    contains:target=>target===this,
    closest:()=>null,
    focus(){this.focused=true;},
    showModal(){this.modalOpen=true;},
    close(){this.modalOpen=false;},
  };
}

function makeApp(){
  const menu=element('menu'),burger=element('burger'),sectionLink=element('section'),
    otherLink=element('external'),qr=element('QR'),qrDialog=element('QR dialog'),
    installMenu=element('install'),installFooter=element('install-footer'),
    installDialog=element('install dialog');
  sectionLink.attributes.set('href','#services');
  otherLink.attributes.set('href','./leasing-checklist.html');
  menu.contains=e=>e===menu||e===sectionLink||e===otherLink||e===installMenu;
  menu.querySelectorAll=q=>q==='a'?[sectionLink,otherLink]:[];
  const nodes={
    mobileMenu:menu,burgerBtn:burger,lkQrOpen:qr,lkQrDialog:qrDialog,
    lkInstallMenu:installMenu,lkInstallFooter:installFooter,lkInstallDialog:installDialog
  };
  const events=new Map();
  const window={
    addEventListener(type,fn){
      const handlers=events.get(type)||[];
      handlers.push(fn);
      events.set(type,handlers);
    },
    emit(type,ev={}){for(const fn of (events.get(type)||[]))fn(ev);}
  };
  const location={href:'https://talysrus90-cmd.github.io/lizingkompas-unified/variant-5.html?v=508',hash:''};
  const states=[null];
  let position=0, backCalls=0, exited=0;
  const history={
    get state(){return states[position];},
    pushState(state,unused,url){
      assert.equal(url,location.href,'opening the menu must not change site URL');
      states.splice(position+1);
      states.push(state);
      position++;
    },
    replaceState(state){states[position]=state;},
    back(){
      backCalls++;
      if(position===0){exited++;return;}
      position--;
      window.emit('popstate',{state:states[position]});
    },
  };
  const document={
    getElementById:id=>nodes[id]||null,
    querySelectorAll:q=>q==='[data-close-dialog]'?[]:[],
    addEventListener(type,fn){
      const handlers=events.get('document:'+type)||[];
      handlers.push(fn);
      events.set('document:'+type,handlers);
    },
    emit(type,e){for(const fn of events.get('document:'+type)||[])fn(e);}
  };
  // Legacy listener exists before the external script is loaded in V5.
  burger.addEventListener('click',()=>{
    const open=menu.classList.toggle('open');
    burger.setAttribute('aria-expanded',String(open));
  });
  for(const link of [sectionLink,otherLink]){
    link.addEventListener('click',()=>{
      menu.classList.remove('open');
      burger.setAttribute('aria-expanded','false');
    });
  }
  vm.runInNewContext(source,{document,window,history,location,Math});
  return {
    menu,burger,sectionLink,otherLink,qr,qrDialog,installMenu,installDialog,
    document,window,history,location,
    get position(){return position;},
    get exits(){return exited;},
    get backCalls(){return backCalls;}
  };
}

test('Android Back first closes three-dot menu, not the website',()=>{
  const a=makeApp();
  const url=a.location.href;
  a.burger.emit('click');
  assert.equal(a.menu.classList.contains('open'),true);
  assert.equal(a.burger.attributes.get('aria-expanded'),'true');
  assert.equal(a.position,1);
  assert.equal(a.location.href,url);
  a.history.back();
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.burger.attributes.get('aria-expanded'),'false');
  assert.equal(a.position,0);
  assert.equal(a.exits,0);
  assert.equal(a.location.href,url);
});

test('clicking three dots twice consumes temporary history entry',()=>{
  const a=makeApp();
  a.burger.emit('click');
  a.burger.emit('click');
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.position,0);
  assert.equal(a.backCalls,1);
  assert.equal(a.exits,0);
  a.burger.emit('click');
  assert.equal(a.position,1,'reopening must create exactly one entry');
});

test('same-page menu link navigates to section and does not trap Back',()=>{
  const a=makeApp();
  a.burger.emit('click');
  const event=a.sectionLink.emit('click');
  assert.equal(event.defaultPrevented,true);
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.position,0);
  assert.equal(a.location.hash,'#services');
  assert.equal(a.exits,0);
});

test('other-page and tel/download navigation keep native click',()=>{
  const a=makeApp();
  a.burger.emit('click');
  const ev=a.otherLink.emit('click');
  assert.equal(ev.defaultPrevented,false);
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.history.state,null,'no stale synthetic state after navigation');
  assert.equal(a.exits,0);
});

test('QR dialog is not closed by a pending history.back',()=>{
  const a=makeApp();
  a.burger.emit('click');
  a.qr.emit('click');
  assert.equal(a.qrDialog.modalOpen,true);
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.backCalls,0);
  assert.equal(a.history.state,null);
});

test('Escape and outside tap both close the menu without exiting',()=>{
  const a=makeApp();
  a.burger.emit('click');
  a.document.emit('keydown',{key:'Escape'});
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.burger.focused,true);
  assert.equal(a.exits,0);
  a.burger.emit('click');
  a.document.emit('click',{target:{closest:()=>null}});
  assert.equal(a.menu.classList.contains('open'),false);
  assert.equal(a.exits,0);
});

test('website markup and original menu layout stay intact',()=>{
  const h=fs.readFileSync('variant-5.html','utf8');
  assert.ok(h.includes('id="burgerBtn"'));
  assert.ok(h.includes('id="mobileMenu"'));
  assert.ok(h.includes('src="./lk-ui-v504.js"'));
  assert.match(h,/name="robots" content="noindex,nofollow"/);
});
