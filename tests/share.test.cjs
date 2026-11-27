const test = require('node:test');
const assert = require('node:assert/strict');
const {shareData, links} = require('../lk-share-v1.js');
test('preview stays in variant five, drops private query and fragment', () => {
  const d = shareData('https://talysrus90-cmd.github.io/lizingkompas-unified/variant-5.html?inn=123&phone=private#request', 'header');
  const u = new URL(d.url);
  assert.equal(u.pathname, '/lizingkompas-unified/variant-5.html');
  assert.equal(u.hash, '');
  assert.equal(u.searchParams.has('inn'), false);
  assert.equal(u.searchParams.has('phone'), false);
  assert.equal(u.searchParams.get('utm_content'), 'header');
  assert.match(d.text, /предпросмотр/);
});
test('floating attribution and production root', () => {
  const d = shareData('https://leasingcompass.ru/?callback=1#contacts', 'floating');
  const u = new URL(d.url);
  assert.equal(u.origin, 'https://leasingcompass.ru');
  assert.equal(u.pathname, '/');
  assert.equal(u.searchParams.get('utm_content'), 'floating');
  assert.equal(u.searchParams.has('callback'), false);
  assert.doesNotMatch(d.text, /предпросмотр/);
});
test('unknown origin cannot be shared', () => {
  assert.equal(new URL(shareData('https://evil.example/?key=secret','x').url).hostname, 'talysrus90-cmd.github.io');
});
test('official MAX link and mail do not auto-send', () => {
  const d = shareData('file:///index.html','header');
  const l = links(d), m = new URL(l.max);
  assert.equal(m.origin, 'https://max.ru');
  assert.equal(m.pathname, '/:share');
  assert.equal(m.searchParams.get('text'), d.text+'\n'+d.url);
  assert.equal(new URL(l.mail).searchParams.get('body'), d.text+'\n'+d.url);
  assert.match(l.mail,/^mailto:\?/);
});
