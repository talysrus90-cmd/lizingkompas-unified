'use strict';
/* Offline, synthetic brokerage preview quality gates. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const lib=require('../broker-preview.js');
const html=fs.readFileSync('broker-preview.html','utf8');
const publicSite=fs.readFileSync('variant-5.html','utf8');
const script=fs.readFileSync('broker-preview.js','utf8');

test('standalone preview remains noindex; financial forms only work on localhost',()=>{
  assert.match(html,/<meta name="robots" content="noindex,nofollow,noarchive">/);
  assert.match(html,/form-action 'none'/);
  assert.match(html,/id="view-workspace" class="section local-only"/);
  assert.ok(html.includes('id="localLoginForm"'));
  assert.ok(html.includes('id="localCaseForm"'));
  assert.ok(html.includes('id="localOfferForm"'));
  assert.ok(html.includes('src="./broker-local-ui.js"'));
  assert.doesNotMatch(html,/name="(?:phone|inn|email|client_name)"/i);
  assert.doesNotMatch(html,/<script[^>]+src="https?:/i);
  assert.doesNotMatch(script,/\b(fetch|XMLHttpRequest|sendBeacon|localStorage|sessionStorage|WebSocket)\b/);
  assert.ok(html.includes('src="./broker-preview.js"'));
  assert.ok(!publicSite.includes('broker-preview.html'), 'keep public V5 uncluttered');
});
test('every preview tab has a rendered view and selection controls',()=>{
  for(const name of ['deals','offers','documents','analytics','security']){
    assert.ok(html.includes('data-tab="'+name+'"'),name);
    assert.ok(html.includes('id="view-'+name+'"'),name);
  }
  for(const id of ['caseList','caseTitle','factPrice','comparisonRows','documentList','compareNow','openDocs'])
    assert.ok(html.includes('id="'+id+'"'),id);
});
test('all seven offers and all companies are strictly synthetic',()=>{
  assert.equal(lib.cases.length,3);
  const offers=lib.cases.flatMap(x=>x.offers);
  assert.equal(offers.length,7);
  assert.equal(offers.filter(x=>x.verified).length,6);
  assert.equal(new Set(offers.map(x=>x.doc)).size,7);
  for(const deal of lib.cases){
    assert.ok(deal.id.startsWith('DEMO-'));
    assert.ok(deal.title.includes('демонстрация'));
    assert.ok(deal.price>deal.advance);
    for(const offer of deal.offers){
      assert.match(offer.lessor,/\(пример\)$/);
      assert.match(offer.doc,/^DOC-DEMO-/);
    }
  }
});
test('first case ranks explicit total cash outflow; values match Python demo',()=>{
  const result=lib.compare(lib.cases[0]);
  assert.equal(result.comparableCount,3);
  const byId=Object.fromEntries(result.rows.map(row=>[row.offer.id,row]));
  assert.equal(byId['KP-001'].total,5454000);
  assert.equal(byId['KP-002'].total,5310000);
  assert.equal(byId['KP-003'].total,5238000);
  assert.deepEqual(result.rows.map(x=>x.rank),[1,2,3]);
  assert.equal(result.rows[0].offer.id,'KP-003');
});
test('incomplete unverified quote is shown but never ranked',()=>{
  const result=lib.compare(lib.cases[1]);
  assert.equal(result.comparableCount,1);
  assert.equal(result.rows.every(x=>x.rank===null),true);
  const bad=result.rows.find(x=>x.offer.id==='KP-005');
  assert.equal(bad.total,null);
  assert.ok(bad.blockers.includes('Не проверено брокером'));
  assert.ok(bad.blockers.some(x=>x.includes('insuranceTotal')));
});
test('expired, missing source or invalid fee excludes offer from ranking',()=>{
  const scenario=lib.cases[2];
  const base=scenario.offers[0];
  for(const override of [{validUntil:'2026-11-01'},{doc:''},{upfrontFee:-1},{monthly:NaN}]){
    const row=lib.evaluateOffer(scenario,{...base,...override});
    assert.equal(row.total,null);
    assert.equal(row.rank,null);
    assert.ok(row.blockers.length>0);
  }
});
test('public header QR and Share swap and asset cache bust stay locked',()=>{
  const head=publicSite.slice(publicSite.indexOf('<header>'),publicSite.indexOf('</header>'));
  const qr=head.indexOf('id="lkQrOpen"'),share=head.indexOf('data-lk-share="header"'),burger=head.indexOf('id="burgerBtn"');
  assert.ok(qr>0&&share>qr&&burger>share);
  assert.ok(publicSite.includes('src="./lk-ui-v504.js?rev=20261127-back-qr-v2"'));
  assert.match(publicSite,/name="robots" content="noindex,nofollow"/);
});
