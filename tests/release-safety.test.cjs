'use strict';
// Production-release safety checks for the GitHub Pages preview.
// These checks do not turn on indexing or submit customer information.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const html = fs.readFileSync('variant-5.html', 'utf8');
const handoff = fs.readFileSync('PROJECT_HANDOFF.md', 'utf8');
const manifest = JSON.parse(fs.readFileSync('lk-app.webmanifest', 'utf8'));
const permanentUrl = 'https://talysrus90-cmd.github.io/lizingkompas-unified/variant-5.html?v=508';

test('handoff preserves permanent V5 entry point and main source', () => {
  assert.ok(handoff.includes(permanentUrl));
  assert.ok(handoff.includes('variant-5.html'));
  assert.ok(handoff.includes('stable/v5.08'));
});

test('preview remains explicitly noindex,nofollow', () => {
  assert.match(html, /<meta\s+name=["']robots["']\s+content=["']noindex,nofollow["']/i);
});

test('PWA points to V5 and does not replace the permanent URL', () => {
  assert.equal(manifest.id, './variant-5.html');
  assert.equal(manifest.start_url, './variant-5.html');
  assert.equal(manifest.scope, './');
});

test('all visible forms remain local demonstration forms', () => {
  const forms = [...html.matchAll(/<form\b[^>]*>/gi)].map(match => match[0]);
  assert.ok(forms.length >= 4, 'expected the existing calculation, quiz, B2B and request forms');
  for (const form of forms) {
    assert.match(form, /onsubmit=["']submitForm\(event,/);
    assert.doesNotMatch(form, /\baction\s*=/i);
  }
  const handler = html.match(/function submitForm\([\s\S]*?\n  }/);
  assert.ok(handler, 'missing local submitForm handler');
  assert.match(handler[0], /e\.preventDefault\(\)/);
  assert.match(handler[0], /Заявка подготовлена локально, но не отправлена/);
  assert.doesNotMatch(handler[0], /\bfetch\s*\(|XMLHttpRequest|sendBeacon/i);
});
