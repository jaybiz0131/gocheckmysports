// S-3b.4: the web push relay, tested with node alone (no dependency, no network, no key on disk).
// Run:  node netlify/test/push.test.mjs   (exit 0 when every check holds). Each line names its check.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  createECDH, createDecipheriv, createPublicKey, verify, randomBytes,
} from 'node:crypto';
import { selectSends, messageFor, etParts } from '../lib/select.mjs';
import { runTick, EXPIRE_MS } from '../lib/tick.mjs';
import { encryptPayload, vapidToken, sendPush, hkdf, b64u } from '../lib/webpush.mjs';
import { readVapid, openStore } from '../lib/config.mjs';
import * as SUB from '../lib/subscribe.mjs';
const { subscribe, subId } = SUB;
import pushHandler from '../functions/push.mjs';
import sendHandler from '../functions/push-send.mjs';

const FIX = JSON.parse(readFileSync(new URL('../../fixtures/push_fixture.json', import.meta.url)));
let failed = 0;
async function check(name, fn) {
  try { await fn(); console.log(`ok   ${name}`); } catch (e) {
    failed++; console.log(`FAIL ${name}: ${e && e.message ? e.message.split("\n").slice(0,6).join(" / ") : e}`);
  }
}

function memStore(subs) {
  const m = new Map(subs.map((s) => { const { id, ...r } = s; return [id, { endpoint: `https://fcm.googleapis.com/${id}`, updated: '2026-10-20T00:00:00Z', ...r }]; }));
  return {
    m,
    list: async () => [...m.keys()],
    get: async (k) => (m.has(k) ? structuredClone(m.get(k)) : null),
    set: async (k, v) => { m.set(k, structuredClone(v)); },
    del: async (k) => { m.delete(k); },
  };
}

// A relay's two stores: the subscriptions and, apart from them, the sent marks kept per device.
// A fixture sub gets a device of its own, and a mark it carries is moved to its device's record.
function world(subs) {
  const store = memStore(subs.map(({ sent, ...s }) => ({ dev: `dev-${s.id}`, ...s })));
  const marks = memStore([]);
  for (const s of subs) if (s.sent) marks.m.set(`dev-${s.id}`, { sent: { ...s.sent } });
  return { store, marks };
}

const ua = createECDH('prime256v1'); ua.generateKeys();
const uaPub = ua.getPublicKey(); const uaPriv = ua.getPrivateKey(); const auth = randomBytes(16);
const DEV = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';
const devIdOf = (d) => SUB.devId(d);
const ORIGIN = 'https://gocheckmysports.com';
const goodSub = { endpoint: 'https://fcm.googleapis.com/fcm/send/abc', keys: { p256dh: b64u.enc(uaPub), auth: b64u.enc(auth) } };
// A browser POST: the page's own Origin, the JSON type, the device number the page keeps.
const post = (b, ct = 'application/json', origin = ORIGIN) => new Request('https://gocheckmysports.com/api/push', {
  method: 'POST', headers: { 'content-type': ct, ...(origin ? { origin } : {}) },
  body: typeof b === 'string' ? b : JSON.stringify(b && b.subscription && !('device' in b) ? { ...b, device: DEV } : b) });

function hours(from, to) {
  const out = [];
  for (let t = Date.parse(from); t < Date.parse(to); t += 3600e3) out.push(new Date(t));
  return out;
}

// ---- the one-push rule ------------------------------------------------------------------
await check('one-push: hourly ticks send each device each game once, at 7 PM ET the evening before', async () => {
  const { store, marks } = world(FIX.subs);
  const delivered = [];
  for (const now of hours(FIX.ticks_from, FIX.ticks_to)) {
    await runTick({ store, marks, games: FIX.games, now, send: async (sub, msg) => {
      delivered.push([sub.id, msg.tag.replace('game-', ''), now.toISOString().replace('.000Z', 'Z')]); return 201; } });
  }
  assert.deepEqual(delivered.sort(), FIX.expected.map((e) => [...e]).sort());
});

await check('one-push: a second pass over the same hours sends nothing', async () => {
  const { store, marks } = world(FIX.subs);
  const send = async () => 201;
  for (const now of hours(FIX.ticks_from, FIX.ticks_to)) await runTick({ store, marks, games: FIX.games, now, send });
  let again = 0;
  for (const now of hours(FIX.ticks_from, FIX.ticks_to)) await runTick({ store, marks, games: FIX.games, now, send: async () => { again++; return 201; } });
  assert.equal(again, 0);
});

// U-9: this is the check that fails when the mark is written after the send. The stub reads the
// marks store at the moment the push leaves, which is the only moment the order can be seen.
await check('one-push: the mark is already stored when the push leaves (written before the send)', async () => {
  const { store, marks } = world(FIX.subs);
  const now = new Date('2026-10-24T23:00:00Z');
  const atSend = [];                                  // recorded, not asserted: the tick swallows a throw from send
  await runTick({ store, marks, games: FIX.games, now, send: async (sub, msg) => {
    const rec = marks.m.get(sub.dev);
    atSend.push([sub.id, msg.tag, Boolean(rec && rec.sent[msg.tag.replace('game-', '')])]);
    return 201;
  } });
  assert.ok(atSend.length > 0);
  assert.deepEqual(atSend.filter((x) => !x[2]), [], 'a push left before its mark was stored');
});

await check('one-push: a send that throws leaves its mark, the tick goes on, and no later hour sends it again', async () => {
  const { store, marks } = world([{ id: 'a', teams: ['nfl:KC'] }, { id: 'b', teams: ['nfl:KC'] }]);
  const now = new Date('2026-10-24T23:00:00Z');
  const g = FIX.games.filter((x) => x.id === 'g1');
  const seen = [];
  const st = await runTick({ store, marks, games: g, now, send: async (sub) => { seen.push(sub.id); if (sub.id === 'a') throw new Error('boom'); return 201; } });
  assert.deepEqual(seen, ['a', 'b']);
  assert.equal(st.sent, 1); assert.equal(st.lost, 1);
  assert.deepEqual(Object.keys(marks.m.get('dev-a').sent), ['g1']);
  let again = 0;
  await runTick({ store, marks, games: g, now: new Date('2026-10-25T00:00:00Z'), send: async () => { again++; return 201; } });
  assert.equal(again, 0);
});

await check('one-push: two runs in the same hour send once', async () => {
  const { store, marks } = world(FIX.subs);
  let n = 0;
  const now = new Date('2026-10-24T23:00:00Z');
  const send = async () => { n++; return 201; };
  await runTick({ store, marks, games: FIX.games, now, send });
  const first = n;
  await runTick({ store, marks, games: FIX.games, now, send });
  assert.equal(n, first);
  assert.ok(first > 0);
});

// The reviewer's count of 2: a reader turns the team off and on again the same evening. The
// subscription is deleted and a new one is made, but the marks belong to the device, not to it.
await check('one-push: a team turned off and on again the same evening is not sent the same game twice', async () => {
  const store = memStore([]), marks = memStore([]);
  const g = FIX.games.filter((x) => x.id === 'g1');
  const dev = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';
  const sub1 = { ...goodSub, endpoint: 'https://fcm.googleapis.com/fcm/send/one' };
  const sub2 = { ...goodSub, endpoint: 'https://fcm.googleapis.com/fcm/send/two' };
  const on = (s) => subscribe(post({ subscription: s, teams: ['nfl:KC'], device: dev }), store, new Date('2026-10-24T20:00:00Z'));
  let n = 0;
  const send = async () => { n++; return 201; };
  assert.equal((await on(sub1)).status, 200);
  await runTick({ store, marks, games: g, now: new Date('2026-10-24T23:00:00Z'), send });
  assert.equal(n, 1);
  assert.equal((await subscribe(post({ subscription: sub1, teams: [], device: dev }), store)).status, 200);   // off
  assert.equal(store.m.size, 0);
  assert.equal((await on(sub2)).status, 200);                                                                   // on, a new endpoint
  await runTick({ store, marks, games: g, now: new Date('2026-10-25T01:00:00Z'), send });
  assert.equal(n, 1, 'the same game was sent again to the same device');
  // another device is its own reader and is still sent the game
  assert.equal((await subscribe(post({ subscription: { ...goodSub, endpoint: 'https://fcm.googleapis.com/fcm/send/three' }, teams: ['nfl:KC'], device: 'ffffffffffffffffffffffffffffffff' }), store)).status, 200);
  await runTick({ store, marks, games: g, now: new Date('2026-10-25T02:00:00Z'), send });
  assert.equal(n, 2);
});

await check('one-push: a gone device (410) hands its mark back so the same device on a new endpoint is still sent', async () => {
  const store = memStore([{ id: 'old', dev: 'dev-x', teams: ['nfl:KC'] }, { id: 'new', dev: 'dev-x', teams: ['nfl:KC'] }]);
  const marks = memStore([]);
  const g = FIX.games.filter((x) => x.id === 'g1');
  const landed = [];
  await runTick({ store, marks, games: g, now: new Date('2026-10-24T23:00:00Z'), send: async (sub) => {
    if (sub.id === 'old') return 410; landed.push(sub.id); return 201; } });
  assert.deepEqual(landed, ['new']);
  assert.equal(store.m.has('old'), false);
});

await check('one-push: two records of one device are sent the game once', async () => {
  const store = memStore([{ id: 'p', dev: 'dev-y', teams: ['nfl:KC'] }, { id: 'q', dev: 'dev-y', teams: ['nfl:KC'] }]);
  const marks = memStore([]);
  let n = 0;
  await runTick({ store, marks, games: FIX.games.filter((x) => x.id === 'g1'), now: new Date('2026-10-24T23:00:00Z'), send: async () => { n++; return 201; } });
  assert.equal(n, 1);
});

await check('storage: a device mark expires by itself 21 days after the last push and holds nothing but game ids and dates', async () => {
  const { store, marks } = world([{ id: 'a', teams: ['nfl:KC'] }]);
  const g = FIX.games.filter((x) => x.id === 'g1');
  await runTick({ store, marks, games: g, now: new Date('2026-10-24T23:00:00Z'), send: async () => 201 });
  assert.deepEqual(Object.keys(marks.m.get('dev-a')).sort(), ['sent', 'updated']);
  await runTick({ store, marks, games: [], now: new Date('2026-11-14T22:00:00Z'), send: async () => 201 });   // 20 days 23 hours
  assert.equal(marks.m.size, 1);
  await runTick({ store, marks, games: [], now: new Date('2026-11-14T23:00:00Z'), send: async () => 201 });   // 21 days
  assert.equal(marks.m.size, 0);
});

await check('one-push: nothing before 7 PM ET, nothing on the game day, nothing after kickoff', () => {
  const g = FIX.games.find((x) => x.id === 'g1');
  const subs = [{ id: 'a', teams: ['nfl:KC'], sent: {} }];
  const at = (iso) => selectSends({ subs, games: [g], now: new Date(iso) }).length;
  assert.equal(at('2026-10-24T22:59:00Z'), 0);   // 6:59 PM EDT Saturday
  assert.equal(at('2026-10-24T23:00:00Z'), 1);   // 7:00 PM EDT Saturday
  assert.equal(at('2026-10-25T03:59:00Z'), 1);   // 11:59 PM EDT Saturday
  assert.equal(at('2026-10-25T04:00:00Z'), 0);   // midnight Sunday: the game day
  assert.equal(at('2026-10-25T17:30:00Z'), 0);   // after kickoff
  assert.equal(at('2026-10-23T23:00:00Z'), 0);   // two evenings before
});

await check('one-push: the evening is the Eastern calendar day, not the UTC day', () => {
  assert.deepEqual(etParts(new Date('2026-10-26T00:20:00Z')), { day: '2026-10-25', hour: 20 });
  assert.deepEqual(etParts(new Date('2026-11-02T00:00:00Z')), { day: '2026-11-01', hour: 19 });
  assert.deepEqual(etParts(new Date('2026-10-31T23:00:00Z')), { day: '2026-10-31', hour: 19 });
});

await check('one-push: a push the service refuses is retried on a later hour and still lands once', async () => {
  const { store, marks } = world([{ id: 'r1', teams: ['nfl:KC'] }]);
  const g = FIX.games.filter((x) => x.id === 'g1');
  const answers = [503, 503, 201];
  let attempts = 0, landed = 0;
  for (const now of hours('2026-10-24T22:00:00Z', '2026-10-25T05:00:00Z')) {
    await runTick({ store, marks, games: g, now, send: async () => {
      attempts++; const a = answers.shift() ?? 201; if (a === 201) landed++; return a; } });
  }
  assert.equal(attempts, 3);
  assert.equal(landed, 1);
});

await check('one-push: a device the push service reports gone (410) is forgotten and not tried again', async () => {
  const { store, marks } = world([{ id: 'x1', teams: ['nfl:KC'] }]);
  let attempts = 0;
  for (const now of hours('2026-10-24T22:00:00Z', '2026-10-25T05:00:00Z')) {
    await runTick({ store, marks, games: FIX.games, now, send: async () => { attempts++; return 410; } });
  }
  assert.equal(attempts, 1);
  assert.equal(store.m.size, 0);
});

await check('storage: a record not renewed in 180 days is deleted and never sent to', async () => {
  const old = new Date(Date.parse('2026-10-24T23:00:00Z') - EXPIRE_MS - 1000).toISOString();
  const { store, marks } = world([{ id: 'o1', teams: ['nfl:KC'], updated: old }]);
  let n = 0;
  await runTick({ store, marks, games: FIX.games, now: new Date('2026-10-24T23:00:00Z'), send: async () => { n++; return 201; } });
  assert.equal(n, 0);
  assert.equal(store.m.size, 0);
});

// ---- the line ---------------------------------------------------------------------------
await check('message: kickoff line first, conditions only while the build reading is fresh, nothing hyped', () => {
  const g = FIX.games.find((x) => x.id === 'g1');
  const m = messageFor(g, new Date('2026-10-24T23:00:00Z'));
  assert.equal(m.title, 'Tomorrow: Kansas City Chiefs at Buffalo Bills');
  assert.equal(m.body, 'Kickoff 1:00 PM ET on CBS. 52°, wind 12 mph, rain 20%.');
  assert.equal(m.url, '/games/g1.html');
  const stale = messageFor(FIX.games.find((x) => x.id === 'g3'), new Date('2026-10-31T23:00:00Z'));
  assert.equal(stale.body, 'Kickoff 1:00 PM ET on FOX.');          // reading 11 days old: left out
  const none = messageFor(FIX.games.find((x) => x.id === 'g2'), new Date('2026-10-24T23:00:00Z'));
  assert.equal(none.body, 'Kickoff 8:20 PM ET on NBC.');
  for (const t of [m.title, m.body, stale.body]) {
    assert.ok(!/\u2014|\u2013/.test(t) && !/\blive\b/i.test(t) && !/!/.test(t), t);
  }
});

// ---- the crypto -------------------------------------------------------------------------
function receive(body, uaPriv, uaPub, auth) {            // the reader's side of RFC 8291, section 3.4
  const salt = body.subarray(0, 16);
  const idlen = body[20];
  const asPub = body.subarray(21, 21 + idlen);
  const ct = body.subarray(21 + idlen);
  const ua = createECDH('prime256v1'); ua.setPrivateKey(uaPriv);
  const secret = ua.computeSecret(asPub);
  const ikm = hkdf(auth, secret, Buffer.concat([Buffer.from('WebPush: info\0'), uaPub, asPub]), 32);
  const cek = hkdf(salt, ikm, Buffer.from('Content-Encoding: aes128gcm\0'), 16);
  const nonce = hkdf(salt, ikm, Buffer.from('Content-Encoding: nonce\0'), 12);
  const d = createDecipheriv('aes-128-gcm', cek, nonce);
  d.setAuthTag(ct.subarray(ct.length - 16));
  const plain = Buffer.concat([d.update(ct.subarray(0, ct.length - 16)), d.final()]);
  assert.equal(plain[plain.length - 1], 2);
  return { text: plain.subarray(0, plain.length - 1).toString(), rs: body.readUInt32BE(16), idlen };
}
const vk = createECDH('prime256v1'); vk.generateKeys();
const VAPID = { publicKey: b64u.enc(vk.getPublicKey()), privateKey: b64u.enc(vk.getPrivateKey()), subject: 'https://gocheckmysports.com' };

await check('crypto: a message encrypted for a device decrypts to the same text (RFC 8291)', () => {
  const msg = JSON.stringify({ title: 'Tomorrow: A at B', body: 'Kickoff 1:00 PM ET on CBS.', url: '/games/1.html' });
  const r = receive(encryptPayload(msg, uaPub, auth), uaPriv, uaPub, auth);
  assert.equal(r.text, msg); assert.equal(r.rs, 4096); assert.equal(r.idlen, 65);
});

await check('crypto: a message encrypted for one device does not decrypt for another', () => {
  const other = createECDH('prime256v1'); other.generateKeys();
  const body = encryptPayload('secret', uaPub, auth);
  assert.throws(() => receive(body, other.getPrivateKey(), other.getPublicKey(), auth));
});

await check('crypto: the VAPID token verifies under the public key and names the push service origin', () => {
  const now = Date.parse('2026-10-24T23:00:00Z');
  const tok = vapidToken('https://fcm.googleapis.com/fcm/send/abc', VAPID, now);
  const [h, b, s] = tok.split('.');
  const pk = createPublicKey({ key: { kty: 'EC', crv: 'P-256', x: b64u.enc(vk.getPublicKey().subarray(1, 33)), y: b64u.enc(vk.getPublicKey().subarray(33, 65)) }, format: 'jwk' });
  assert.ok(verify('sha256', Buffer.from(`${h}.${b}`), { key: pk, dsaEncoding: 'ieee-p1363' }, b64u.dec(s)));
  const claims = JSON.parse(b64u.dec(b));
  assert.equal(claims.aud, 'https://fcm.googleapis.com');
  assert.equal(claims.sub, 'https://gocheckmysports.com');
  assert.ok(claims.exp > now / 1000 && claims.exp - now / 1000 <= 24 * 3600);
  assert.equal(JSON.parse(b64u.dec(h)).alg, 'ES256');
});

await check('crypto: sendPush posts the headers the push service requires, with the key in the request only', async () => {
  let seen;
  const st = await sendPush({ endpoint: 'https://fcm.googleapis.com/fcm/send/abc', keys: { p256dh: b64u.enc(uaPub), auth: b64u.enc(auth) } },
    { title: 't', body: 'b', url: '/x', tag: 'game-1' }, VAPID, async (u, o) => { seen = { u, o }; return { status: 201 }; });
  assert.equal(st, 201);
  assert.equal(seen.o.headers['Content-Encoding'], 'aes128gcm');
  assert.match(seen.o.headers.Authorization, /^vapid t=[\w-]+\.[\w-]+\.[\w-]+, k=/);
  assert.ok(!JSON.stringify(seen.o.headers).includes(VAPID.privateKey));
  assert.equal(await sendPush({ endpoint: 'https://fcm.googleapis.com/x', keys: { p256dh: 'bad', auth: 'bad' } }, {}, VAPID, async () => { throw new Error('no'); }), 0);
});

// ---- the absent key ---------------------------------------------------------------------
function withEnv(env, fn) {
  const keep = { ...process.env };
  for (const k of Object.keys(process.env)) if (k.startsWith('WEB_PUSH_')) delete process.env[k];
  Object.assign(process.env, env);
  const done = () => { for (const k of Object.keys(process.env)) if (!(k in keep)) delete process.env[k]; Object.assign(process.env, keep); };
  return Promise.resolve(fn()).finally(done);
}

await check('absent key: the subscribe function answers 503 with a JSON body and does not throw', async () => {
  await withEnv({}, async () => {
    const r = await pushHandler(new Request('https://gocheckmysports.com/api/push', { method: 'POST', body: '{}', headers: { 'content-type': 'application/json' } }));
    assert.equal(r.status, 503);
    assert.equal((await r.json()).error, 'push is not enabled');
    assert.equal((await pushHandler(undefined)).status, 503);        // even a call with no request
  });
});

await check('absent key: a half-set or malformed key is the same as no key', async () => {
  for (const env of [{ WEB_PUSH_VAPID_PUBLIC_KEY: VAPID.publicKey }, { WEB_PUSH_VAPID_PRIVATE_KEY: VAPID.privateKey },
    { WEB_PUSH_VAPID_PUBLIC_KEY: 'x', WEB_PUSH_VAPID_PRIVATE_KEY: 'y' }]) {
    await withEnv(env, async () => {
      assert.equal(readVapid(), null);
      assert.equal((await pushHandler(new Request('https://gocheckmysports.com/api/push', { method: 'POST', body: '{}' }))).status, 503);
    });
  }
});

await check('absent key: the evening send does nothing, reaches for no network and no store', async () => {
  await withEnv({}, async () => {
    const realFetch = globalThis.fetch;
    let reached = 0;
    globalThis.fetch = () => { reached++; throw new Error('the send reached for the network with no key'); };
    try { assert.equal(await sendHandler(), undefined); } finally { globalThis.fetch = realFetch; }
    assert.equal(reached, 0);
  });
});

await check('key present: readVapid reads the environment and defaults the subject to the site', async () => {
  await withEnv({ WEB_PUSH_VAPID_PUBLIC_KEY: VAPID.publicKey, WEB_PUSH_VAPID_PRIVATE_KEY: VAPID.privateKey }, async () => {
    const v = readVapid();
    assert.equal(v.publicKey, VAPID.publicKey); assert.equal(v.subject, 'https://gocheckmysports.com');
  });
});

await check('store: the committed Blobs client loads with no install and refuses, by name, to open outside Netlify', async () => {
  await withEnv({}, async () => {
    const keep = process.env.NETLIFY_BLOBS_CONTEXT; delete process.env.NETLIFY_BLOBS_CONTEXT;
    try { await assert.rejects(() => openStore(), (e) => e && e.name === 'MissingBlobsEnvironmentError'); }
    finally { if (keep !== undefined) process.env.NETLIFY_BLOBS_CONTEXT = keep; }
  });
});

// ---- the subscribe route ----------------------------------------------------------------

await check('subscribe: a device is stored with its endpoint, keys, teams and a hash of its device number, and nothing else about it', async () => {
  const store = memStore([]);
  const r = await subscribe(post({ subscription: goodSub, teams: ['nfl:KC', 'cfb:ohio-state'] }), store, new Date('2026-10-20T12:00:00Z'));
  assert.equal(r.status, 200);
  const rec = store.m.get(subId(goodSub.endpoint));
  assert.deepEqual(Object.keys(rec).sort(), ['created', 'dev', 'endpoint', 'keys', 'teams', 'updated']);
  assert.deepEqual(rec.teams, ['nfl:KC', 'cfb:ohio-state']);
  assert.match(rec.dev, /^[0-9a-f]{32}$/);
  assert.ok(!JSON.stringify(rec).includes(DEV), 'the raw device number is stored');
});

await check('subscribe: a second post replaces the teams, and none teams deletes the subscription but not the device marks', async () => {
  const store = memStore([]);
  const id = subId(goodSub.endpoint);
  await subscribe(post({ subscription: goodSub, teams: ['nfl:KC'] }), store);
  await subscribe(post({ subscription: goodSub, teams: ['nfl:KC', 'nfl:BUF'] }), store);
  assert.deepEqual(store.m.get(id).teams, ['nfl:KC', 'nfl:BUF']);
  const r = await subscribe(post({ subscription: goodSub, teams: [] }), store);
  assert.equal(r.status, 200); assert.equal(store.m.size, 0);
});

await check('subscribe: a post with no device number, or a malformed one, is refused', async () => {
  const store = memStore([]);
  for (const device of [undefined, '', 'short', 'x'.repeat(65), 'has space in it 0123456789ab', 42]) {
    assert.equal((await subscribe(post({ subscription: goodSub, teams: ['nfl:KC'], device }), store)).status, 400, String(device));
  }
  assert.equal(store.m.size, 0);
});

await check('subscribe: refuses an endpoint that is not a platform push service, bad teams, bad keys, wrong method', async () => {
  const store = memStore([]);
  const code = async (b, ct) => (await subscribe(post(b, ct), store)).status;
  assert.equal(await code({ subscription: { ...goodSub, endpoint: 'https://example.com/x' }, teams: ['nfl:KC'] }), 400);
  assert.equal(await code({ subscription: { ...goodSub, endpoint: 'http://fcm.googleapis.com/x' }, teams: ['nfl:KC'] }), 400);
  assert.equal(await code({ subscription: { ...goodSub, endpoint: 'https://127.0.0.1/x' }, teams: ['nfl:KC'] }), 400);
  assert.equal(await code({ subscription: goodSub, teams: ['kc'] }), 400);
  assert.equal(await code({ subscription: goodSub, teams: Array.from({ length: 9 }, (_, i) => `cfb:t${i}`) }), 400);
  assert.equal(await code({ subscription: { ...goodSub, keys: { p256dh: 'AAAA', auth: 'AAAA' } }, teams: ['nfl:KC'] }), 400);
  assert.equal(await code('not json'), 400);
  assert.equal(await code({ subscription: goodSub, teams: ['nfl:KC'] }, 'text/plain'), 415);
  assert.equal((await subscribe(new Request('https://gocheckmysports.com/api/push'), store)).status, 405);
  assert.equal(store.m.size, 0);
});

// U-9: removing the no-port rule from validEndpoint left the whole suite green.
await check('subscribe: an endpoint with a port, or with credentials, is refused even on an allowed host', async () => {
  const store = memStore([]);
  for (const endpoint of ['https://fcm.googleapis.com:8443/fcm/send/abc', 'https://fcm.googleapis.com:443@evil.example/x',
    'https://user:pw@fcm.googleapis.com/fcm/send/abc', 'https://user@fcm.googleapis.com/fcm/send/abc']) {
    assert.equal((await subscribe(post({ subscription: { ...goodSub, endpoint }, teams: ['nfl:KC'] }), store)).status, 400, endpoint);
  }
  assert.equal(SUB.validEndpoint('https://fcm.googleapis.com/fcm/send/abc'), true);
  assert.equal(SUB.validEndpoint('https://fcm.googleapis.com:8443/fcm/send/abc'), false);
  assert.equal(store.m.size, 0);
});

await check('subscribe: a store that throws is a 500 answer, not an exception', async () => {
  const bad = { get: async () => { throw new Error('down'); }, set: async () => { throw new Error('down'); }, del: async () => {}, list: async () => [] };
  assert.equal((await subscribe(post({ subscription: goodSub, teams: ['nfl:KC'] }), bad)).status, 500);
});

// ---- the route's guards: origin, size, count ---------------------------------------------
await check('origin: only the site and its deploy previews may post; no Origin, another site, a look-alike are refused', async () => {
  const store = memStore([]);
  const body = { subscription: goodSub, teams: ['nfl:KC'] };
  const code = async (origin) => (await subscribe(post(body, 'application/json', origin), store)).status;
  assert.equal(await code('https://gocheckmysports.com'), 200);
  assert.equal(await code('https://deploy-preview-103--gocheckmysports.netlify.app'), 200);
  for (const bad of [null, '', 'null', 'https://evil.example', 'http://gocheckmysports.com',
    'https://gocheckmysports.com.evil.example', 'https://evil.example/https://gocheckmysports.com',
    'https://www.gocheckmysports.com', 'https://gocheckmysports.com:8443', 'https://deploy-preview-x--gocheckmysports.netlify.app',
    'https://deploy-preview-1--other-site.netlify.app', 'https://deploy-preview-1--gocheckmysports.netlify.app.evil.example']) {
    assert.equal(await code(bad), 403, String(bad));
  }
  const st2 = memStore([]);
  assert.equal((await subscribe(post(body, 'application/json', 'https://evil.example'), st2)).status, 403);
  assert.equal(st2.m.size, 0);
});

await check('origin: the function answers a cross-site post 403 and does not touch the store', async () => {
  await withEnv({ WEB_PUSH_VAPID_PUBLIC_KEY: VAPID.publicKey, WEB_PUSH_VAPID_PRIVATE_KEY: VAPID.privateKey }, async () => {
    const r = await pushHandler(post({ subscription: goodSub, teams: ['nfl:KC'] }, 'application/json', 'https://evil.example'));
    assert.equal(r.status, 403);
  });
});

// A request stand-in whose body counts the bytes pulled from it.
function streamReq({ chunks, chunkSize, length }) {
  const pulled = { bytes: 0 };
  let sent = 0;
  const body = new ReadableStream({
    pull(c) {
      if (sent >= chunks) { c.close(); return; }
      sent++; pulled.bytes += chunkSize; c.enqueue(new Uint8Array(chunkSize).fill(32));
    },
  }, { highWaterMark: 0 });
  const h = new Map([['content-type', 'application/json'], ['origin', ORIGIN]]);
  if (length !== undefined) h.set('content-length', String(length));
  return { req: { method: 'POST', headers: { get: (k) => h.get(k.toLowerCase()) ?? null }, body }, pulled };
}

await check('size: a declared length over 8 KB is refused 413 before any of the body is read', async () => {
  const { req, pulled } = streamReq({ chunks: 1000, chunkSize: 65536, length: 65536 * 1000 });
  assert.equal((await subscribe(req, memStore([]))).status, 413);
  assert.equal(pulled.bytes, 0);
});

await check('size: a body that lies about its length, or declares none, is cut off at 8 KB, not read to the end', async () => {
  for (const length of [undefined, 10]) {
    const { req, pulled } = streamReq({ chunks: 100000, chunkSize: 4096, length });
    assert.equal((await subscribe(req, memStore([]))).status, 413);
    assert.ok(pulled.bytes <= SUB.MAX_BODY + 3 * 4096, `read ${pulled.bytes} bytes`);
  }
});

await check('size: a body of exactly 8 KB is read in full and judged on its content', async () => {
  const pad = ' '.repeat(SUB.MAX_BODY - 2);
  const r = await subscribe(post(`{}${pad}`.slice(0, SUB.MAX_BODY)), memStore([]));
  assert.equal(r.status, 400);
});

await check('count: at the cap a new device is told 503 and nothing is stored; a known device can still update or leave', async () => {
  const full = Array.from({ length: SUB.MAX_RECORDS }, (_, i) => ({ id: `r${i}`, dev: `d${i}`, teams: ['nfl:KC'] }));
  const store = memStore(full);
  assert.equal((await subscribe(post({ subscription: goodSub, teams: ['nfl:KC'] }), store)).status, 503);
  assert.equal(store.m.size, SUB.MAX_RECORDS);
  const known = { ...goodSub, endpoint: 'https://fcm.googleapis.com/fcm/send/known' };
  store.m.set(subId(known.endpoint), { endpoint: known.endpoint, keys: known.keys, teams: ['nfl:KC'], dev: devIdOf(DEV), created: 'x', updated: 'x' });
  assert.equal((await subscribe(post({ subscription: known, teams: ['nfl:BUF'] }), store)).status, 200);
  assert.deepEqual(store.m.get(subId(known.endpoint)).teams, ['nfl:BUF']);
  assert.equal((await subscribe(post({ subscription: known, teams: [] }), store)).status, 200);
  assert.equal((await subscribe(post({ subscription: goodSub, teams: ['nfl:KC'] }), store)).status, 503);   // still full
  store.m.delete('r0');
  assert.equal((await subscribe(post({ subscription: goodSub, teams: ['nfl:KC'] }), store)).status, 200);   // a slot is free again
});

await check('count: with the store at the cap the evening send still runs', async () => {
  const full = Array.from({ length: SUB.MAX_RECORDS }, (_, i) => ({ id: `r${i}`, dev: `d${i}`, teams: i === 0 ? ['nfl:KC'] : ['nfl:ZZ'] }));
  const store = memStore(full), marks = memStore([]);
  let n = 0;
  await runTick({ store, marks, games: FIX.games.filter((x) => x.id === 'g1'), now: new Date('2026-10-24T23:00:00Z'), send: async () => { n++; return 201; } });
  assert.equal(n, 1);
});

console.log(failed ? `${failed} check(s) failed` : 'all push checks passed');
process.exit(failed ? 1 : 0);
