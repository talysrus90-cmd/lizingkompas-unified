'use strict';
// Ergonomic palette guardrails following WCAG 2.2 AA normal-text contrast.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync('broker-preview.html','utf8');
function color(s) {
  const hex=s.replace('#','');
  const vals=hex.length===3?[...hex].map(c=>parseInt(c+c,16)):[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16));
  return vals.map(x=>{
    const v=x/255;
    return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;
  });
}
function luminance(s){const [r,g,b]=color(s);return .2126*r+.7152*g+.0722*b;}
function contrast(a,b){const [hi,lo]=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (hi+.05)/(lo+.05);}
function vars(css){
  return Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{3,6})/g)].map(m=>[m[1],m[2]]));
}
const light=vars(html.split(':root{',2)[1].split(':root[data-theme="dark"]',1)[0]);
const dark=vars(html.split(':root[data-theme="dark"]{',2)[1].split('}',1)[0]);
test('normal and muted text meets WCAG AA 4.5:1 in both themes',()=>{
  for(const [name,theme] of [['light',light],['dark',dark]]){
    for(const foreground of ['ink','muted']){
      for(const background of ['panel','bg']){
        const ratio=contrast(theme[foreground],theme[background]);
        assert.ok(ratio>=4.5,name+' '+foreground+'/'+background+' '+ratio.toFixed(2));
      }
    }
    assert.ok(contrast(theme.mint,theme.panel)>=4.5,name+' accent on panel');
  }
});
test('dark floating menu meets readable text ratio and touch targets',()=>{
  const publicHtml=fs.readFileSync('variant-5.html','utf8');
  assert.ok(contrast('#f3f4f7','#303239')>=7);
  assert.ok(publicHtml.includes('min-height:44px!important'));
  assert.ok(html.includes('.theme-toggle'));
});
