// The subscribe route, as a pure handler over a request and a store.
import { createHash } from 'node:crypto';
import { b64u } from './webpush.mjs';

// The platform push services a browser can hand out. An endpoint anywhere else is refused,
// so the relay can never be pointed at an address inside someone's network.
const HOSTS = [
  /^fcm\.googleapis\.com$/, /^android\.googleapis\.com$/,
  /^updates\.push\.services\.mozilla\.com$/, /(^|\.)push\.services\.mozilla\.com$/,
  /^web\.push\.apple\.com$/, /(^|\.)push\.apple\.com$/,
  /(^|\.)notify\.windows\.com$/,
];
const TEAM = /^(nfl:[A-Z]{2,4}|cfb:[a-z0-9]+(-[a-z0-9]+)*)$/;
export const MAX_TEAMS = 8;
export const MAX_BODY = 8192;
export const MAX_RECORDS = 5000;               // past this a new device is told 503; a tick never reads it
const DEVICE = /^[A-Za-z0-9_-]{16,64}$/;
// Only the site's own pages post here: the apex, and its deploy previews. A browser always
// sends Origin on a cross-site POST, so a page elsewhere cannot make a reader's browser
// follow a team. (A script that is not a browser can set any header; the allow list on the
// endpoint host and the record cap are what bound that.)
const ORIGINS = [/^https:\/\/gocheckmysports\.com$/, /^https:\/\/deploy-preview-\d+--gocheckmysports\.netlify\.app$/];

const json = (status, obj) => new Response(JSON.stringify(obj), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

export const subId = (endpoint) => createHash('sha256').update(endpoint).digest('hex').slice(0, 32);
// The device number the page keeps is stored only as this hash. It is what the sent marks hang
// on, so they survive a subscription made anew on the same device.
export const devId = (device) => createHash('sha256').update(`device:${device}`).digest('hex').slice(0, 32);

export function validEndpoint(e) {
  let u;
  try { u = new URL(e); } catch { return false; }
  return u.protocol === 'https:' && !u.port && !u.username && HOSTS.some((h) => h.test(u.hostname))
    && String(e).length <= 1024;
}

// The checks that need no body and no store. Null when the request may go on.
export function preflight(req) {
  if (!req || req.method !== 'POST') return json(405, { error: 'method' });
  const origin = req.headers.get('origin') || '';
  if (!ORIGINS.some((o) => o.test(origin))) return json(403, { error: 'origin' });
  if (!(req.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) {
    return json(415, { error: 'type' });
  }
  return null;
}

// The body, never more than `max` bytes of it: a declared length over the cap is refused with
// nothing read, and a stream that runs past the cap is cancelled where it stands.
async function readBounded(req, max) {
  const declared = Number(req.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > max) return null;
  if (!req.body) return '';
  const reader = req.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > max) { try { await reader.cancel(); } catch { /* the stream is already gone */ } return null; }
    chunks.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(chunks));
}

// store: {get, set, del, list}. Returns a Response; never throws.
export async function subscribe(req, store, now = new Date()) {
  try {
    const early = preflight(req);
    if (early) return early;
    const text = await readBounded(req, MAX_BODY);
    if (text === null) return json(413, { error: 'size' });
    let b;
    try { b = JSON.parse(text); } catch { return json(400, { error: 'json' }); }
    const sub = b && b.subscription;
    const teams = Array.isArray(b && b.teams) ? [...new Set(b.teams)] : null;
    if (!sub || !validEndpoint(sub.endpoint) || !teams || teams.length > MAX_TEAMS
        || !teams.every((t) => typeof t === 'string' && TEAM.test(t))
        || typeof b.device !== 'string' || !DEVICE.test(b.device)) {
      return json(400, { error: 'shape' });
    }
    const id = subId(sub.endpoint);
    if (teams.length === 0) {                         // following nobody is no subscription at all
      await store.del(id);                            // (the device's sent marks are not touched)
      return json(200, { ok: true, teams: [] });
    }
    const p256dh = b64u.dec(sub.keys && sub.keys.p256dh);
    const auth = b64u.dec(sub.keys && sub.keys.auth);
    if (p256dh.length !== 65 || p256dh[0] !== 4 || auth.length < 16) return json(400, { error: 'keys' });
    const old = await store.get(id);
    if (!old && (await store.list()).length >= MAX_RECORDS) return json(503, { error: 'full' });
    await store.set(id, {
      endpoint: sub.endpoint, keys: { p256dh: b64u.enc(p256dh), auth: b64u.enc(auth) },
      teams, dev: devId(b.device), created: (old && old.created) || now.toISOString(), updated: now.toISOString(),
    });
    return json(200, { ok: true, teams });
  } catch {
    return json(500, { error: 'failed' });
  }
}

export { json };
