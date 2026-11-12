// Drives sach/pwa.py's service worker source in Node with a mocked Cache API and network.
// Usage: node tests/sw_harness.js < sw.js     (run by tests/test_pwa.py; skipped when node is missing)
const assert = require('assert');
const src = require('fs').readFileSync(0, 'utf8');
const ORIGIN = 'http://sach.test';
const abs = k => new URL(typeof k === 'string' ? k : k.url, ORIGIN).href;

const stores = new Map();
const mkCache = name => ({
  async match(k) { const r = stores.get(name).get(abs(k)); return r ? r.clone() : undefined; },
  async put(k, r) { stores.get(name).set(abs(k), r); },
  async add(k) { stores.get(name).set(abs(k), await net({url: abs(k), method: 'GET'})); },
  async keys() { return [...stores.get(name).keys()].map(url => ({url})); },
});
const caches = {
  async open(name) { if (!stores.has(name)) stores.set(name, new Map()); return mkCache(name); },
  async keys() { return [...stores.keys()]; },
  async delete(name) { return stores.delete(name); },
  async match(k) { for (const m of stores.values()) if (m.has(abs(k))) return m.get(abs(k)).clone(); },
};

let online = true, hang = false, noStore = false, fetched = [];
const net = async req => {
  fetched.push(req.url);
  if (hang) return new Promise(() => {});
  if (!online) throw new TypeError('offline');
  const r = new Response('net:' + req.url, {status: 200, headers: {'Cache-Control': noStore ? 'no-store' : 'public, max-age=60'}});
  Object.defineProperty(r, 'type', {value: 'basic'});
  return r;
};

const listeners = {};
const self = {addEventListener: (t, f) => { listeners[t] = f; }, location: {origin: ORIGIN}, skipWaiting: async () => {}, clients: {claim: async () => {}}};
new Function('self', 'caches', 'fetch', 'Response', 'URL', 'setTimeout', src)(self, caches, net, Response, URL, f => setTimeout(f, 20));

const lifecycle = async type => { const p = []; listeners[type]({waitUntil: x => p.push(x)}); await Promise.all(p); };
const run = async (method, path, mode = 'cors') => {
  const e = {request: {method, url: ORIGIN + path, mode}, responded: undefined, respondWith(p) { this.responded = Promise.resolve(p); }};
  listeners.fetch(e);
  return e.responded ? e.responded : null;       // null = the worker did not intercept: the browser goes to the network by itself
};
const text = async r => (await r).text();
const cacheKeys = () => [].concat(...[...stores.values()].map(m => [...m.keys()].map(u => u.replace(ORIGIN, ''))));

(async () => {
  await caches.open('sach-shell-v0'); await caches.open('other-site-cache');
  await lifecycle('install');
  assert.deepStrictEqual(cacheKeys().filter(k => k === '/').length, 1, 'install precaches only the plain home page');
  await lifecycle('activate');
  assert.deepStrictEqual([...stores.keys()].sort(), ['other-site-cache', 'sach-shell-v1', 'sach-static-v1'].filter(k => stores.has(k)).sort(), 'old sach caches deleted, foreign caches kept');

  // navigations
  online = true;
  assert.strictEqual(await text(await run('GET', '/', 'navigate')), 'net:' + ORIGIN + '/');
  online = false;
  assert.strictEqual(await text(await run('GET', '/', 'navigate')), 'net:' + ORIGIN + '/', 'offline plain home falls back to the cached copy');
  const off = await run('GET', '/?text=secret%20forward', 'navigate');
  const body = await off.text();
  assert.ok(off.status === 503 && body.includes('You\'re offline') && body.includes('Your text is still here'), 'other navigations get the offline page');
  assert.ok(!body.includes('secret'), 'offline page never echoes the query');
  assert.ok((await run('GET', '/?view=ledger', 'navigate')).status === 503);

  // slow network with a saved home page: fall back after the timeout
  online = true; hang = true;
  assert.strictEqual(await text(await run('GET', '/', 'navigate')), 'net:' + ORIGIN + '/');
  hang = false;

  // never intercepted / never stored
  for (const [m, p, mode] of [['POST', '/', 'navigate'], ['POST', '/?api=rzp-order', 'cors'], ['GET', '/?api=rzp-verify', 'cors'], ['GET', '/?view=tipqr&fmt=png', 'no-cors'],
                              ['GET', '/?go=tip&amt=50', 'cors'], ['GET', '/?view=ledger', 'cors'], ['GET', '/?view=sw', 'cors']]) {
    assert.strictEqual(await run(m, p, mode), null, m + ' ' + p + ' must not be intercepted');
  }
  fetched = [];
  online = true;
  for (const p of ['/?view=pay&amt=30', '/?go=tip', '/?text=hello', '/?title=a&text=b&url=c', '/?view=ledger', '/?view=privacy', '/?view=icon&size=192&text=x', '/?view=manifest&go=tip']) {
    const r = await run('GET', p, 'navigate');
    assert.strictEqual(await text(r), 'net:' + ORIGIN + p, 'goes to the network: ' + p);
  }

  // static: cache first, only manifest and icons
  online = true;
  for (const p of ['/?view=manifest', '/?view=icon&size=192', '/?view=icon&size=512&maskable=1']) {
    assert.strictEqual(await text(await run('GET', p, 'no-cors')), 'net:' + ORIGIN + p);
  }
  online = false;
  for (const p of ['/?view=manifest', '/?view=icon&size=192', '/?view=icon&size=512&maskable=1']) {
    assert.strictEqual(await text(await run('GET', p, 'no-cors')), 'net:' + ORIGIN + p, 'served from cache offline: ' + p);
  }
  assert.strictEqual(await run('GET', '/?view=icon&size=192&text=x', 'no-cors'), null, 'extra params are not a static asset');

  // no-store responses are never stored, even for the plain home page
  online = true; noStore = true;
  stores.get('sach-shell-v1').clear();
  await text(await run('GET', '/', 'navigate'));
  assert.ok(!cacheKeys().includes('/'), 'no-store response not cached');

  // everything stored is on the allow-list
  const allowed = /^(\/|\/\?view=manifest|\/\?view=icon&size=\d+(&maskable=1)?)$/;
  const bad = cacheKeys().filter(k => !allowed.test(k));
  assert.deepStrictEqual(bad, [], 'only allow-listed URLs are cached');
  console.log('SW_OK');
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
