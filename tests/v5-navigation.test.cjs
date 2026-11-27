'use strict';
// Navigation + versioned-sharing regression checks for the V5 GitHub Pages preview.
// Run with: node --test tests/v5-navigation.test.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { shareData } = require('../lk-share-v3.js');
const growth = require('../lk-growth-v2.js');

const html = fs.readFileSync(path.join(__dirname, '..', 'variant-5.html'), 'utf8');
const base = path.join(__dirname, '..');
const preview = 'https://talysrus90-cmd.github.io/lizingkompas-unified/variant-5.html?v=508';

test('V5 sharing keeps the established permanent address', () => {
  const site = new URL(shareData(preview + '&private=remove-me#contacts', 'header').url);
  assert.equal(site.pathname, '/lizingkompas-unified/variant-5.html');
  assert.equal(site.searchParams.get('v'), '508');
  assert.equal(site.searchParams.has('private'), false);
  assert.equal(site.hash, '');
  const data = { price: 4500000, advance: 900000, term: 36, type: 0 };
  const calc = new URL(growth.calcLink(data, preview));
  assert.equal(calc.searchParams.get('v'), '508');
  assert.deepEqual(growth.decode(calc.hash), data);
  const partner = new URL(growth.partnerLink('dealer-1', preview));
  assert.equal(partner.searchParams.get('v'), '508');
  assert.equal(partner.searchParams.get('utm_content'), 'dealer-1');
});

test('production sharing never receives a preview-only v parameter', () => {
  for (const url of [shareData('https://leasingcompass.ru/', 'floating').url,
    growth.calcLink({ price: 4500000, advance: 900000, term: 36, type: 0 }, 'https://leasingcompass.ru/')]) {
    const parsed = new URL(url);
    assert.equal(parsed.origin, 'https://leasingcompass.ru');
    assert.equal(parsed.searchParams.has('v'), false);
  }
});

test('all same-page anchor targets exist and IDs are unique', () => {
  const ids = [...html.matchAll(/\bid=["']([^"']+)["']/gi)].map(m => m[1]);
  const known = new Set(ids);
  assert.equal(known.size, ids.length, 'duplicate HTML IDs');
  for (const [, target] of html.matchAll(/\bhref=["']#([^"']+)["']/gi)) {
    assert.ok(known.has(decodeURIComponent(target)), 'missing anchor: ' + target);
  }
});

test('local links and image/script assets in V5 resolve to existing files', () => {
  // max and tg are deliberate data-bind placeholders, replaced by site configuration.
  const placeholders = new Set(['max', 'tg']);
  for (const [, raw] of html.matchAll(/\b(?:href|src)=["']([^"']+)["']/gi)) {
    if (!raw || raw.startsWith('#') || /^(?:https?:|mailto:|tel:|data:|javascript:|\/\/)/i.test(raw) || placeholders.has(raw)) continue;
    const relative = decodeURIComponent(raw.split(/[?#]/, 1)[0]).replace(/^\.\//, '');
    if (!relative) continue;
    const resolved = path.resolve(base, relative);
    assert.ok(resolved.startsWith(base + path.sep), 'path leaves repository: ' + raw);
    assert.ok(fs.existsSync(resolved), 'missing local resource: ' + raw);
  }
});

test('inline event handlers reference implemented functions', () => {
  const defined = new Set([...html.matchAll(/function\s+([\w$]+)\s*\(/g)].map(m => m[1]));
  for (const [, expression] of html.matchAll(/\bon(?:click|change|submit|input|keydown|keyup)=["']([^"']+)["']/gi)) {
    const call = /^([A-Za-z_$][\w$]*)\s*\(/.exec(expression);
    if (call) assert.ok(defined.has(call[1]), 'missing handler: ' + call[1]);
  }
});
