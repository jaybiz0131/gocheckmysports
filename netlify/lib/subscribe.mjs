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
const MAX_BODY = 8192;

const json = (status, obj) => new Response(JSON.stringify(obj), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

export const subId = (endpoint) => createHash('sha256').update(endpoint).digest('hex').slice(0, 32);

export function validEndpoint(e) {
  let u;
  try { u = new URL(e); } catch { return false; }
  return u.protocol === 'https:' && !u.port && !u.username && HOSTS.some((h) => h.test(u.hostname))
    && String(e).length <= 1024;
}

// store: {get, set, del}. Returns a Response; never throws.
export async function subscribe(req, store, now = new Date()) {
  try {
    if (req.method !== 'POST') return json(405, { error: 'method' });
    if (!(req.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) {
      return json(415, { error: 'type' });
    }
    const text = await req.text();
    if (text.length > MAX_BODY) return json(413, { error: 'size' });
    let b;
    try { b = JSON.parse(text); } catch { return json(400, { error: 'json' }); }
    const sub = b && b.subscription;
    const teams = Array.isArray(b && b.teams) ? [...new Set(b.teams)] : null;
    if (!sub || !validEndpoint(sub.endpoint) || !teams || teams.length > MAX_TEAMS
        || !teams.every((t) => typeof t === 'string' && TEAM.test(t))) {
      return json(400, { error: 'shape' });
    }
    const id = subId(sub.endpoint);
    if (teams.length === 0) {                         // following nobody is no record at all
      await store.del(id);
      return json(200, { ok: true, teams: [] });
    }
    const p256dh = b64u.dec(sub.keys && sub.keys.p256dh);
    const auth = b64u.dec(sub.keys && sub.keys.auth);
    if (p256dh.length !== 65 || p256dh[0] !== 4 || auth.length < 16) return json(400, { error: 'keys' });
    const old = (await store.get(id)) || {};
    await store.set(id, {
      endpoint: sub.endpoint, keys: { p256dh: b64u.enc(p256dh), auth: b64u.enc(auth) },
      teams, created: old.created || now.toISOString(), updated: now.toISOString(), sent: old.sent || {},
    });
    return json(200, { ok: true, teams });
  } catch {
    return json(500, { error: 'failed' });
  }
}

export { json };
