// The relay's keys, read from the hosting environment and from nowhere else. A key is never
// read from a file, never written to one, never logged. Absent or malformed, the relay is off.
//   WEB_PUSH_VAPID_PUBLIC_KEY    the application server key, base64url, 65 bytes (also read by the build)
//   WEB_PUSH_VAPID_PRIVATE_KEY   the matching private key, base64url, 32 bytes (functions only)
//   WEB_PUSH_SUBJECT             optional, a mailto: or https: contact; defaults to the site
import { b64u } from './webpush.mjs';

export const SITE = 'https://gocheckmysports.com';

// A real calendar date written YYYY-MM-DD, nothing else.
export function validSince(v) {
  const t = String(v || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(t)) return false;
  const d = new Date(`${t}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === t;
}

export function readVapid(env = process.env) {
  const publicKey = String(env.WEB_PUSH_VAPID_PUBLIC_KEY || '').trim();
  const privateKey = String(env.WEB_PUSH_VAPID_PRIVATE_KEY || '').trim();
  if (!publicKey || !privateKey || !validSince(env.WEB_PUSH_SINCE)) return null;
  const pub = b64u.dec(publicKey);
  const priv = b64u.dec(privateKey);
  if (pub.length !== 65 || pub[0] !== 4 || priv.length !== 32) return null;
  const subject = String(env.WEB_PUSH_SUBJECT || '').trim();
  return { publicKey, privateKey, subject: /^(mailto:|https:\/\/)/.test(subject) ? subject : SITE };
}

// The store, opened only after the keys are known to be present. Netlify Blobs is the one
// third-party piece, and it is a single committed file (netlify/vendor/netlify-blobs.mjs, its
// own header names the version), so the deploy has no install step to fail. It is imported
// here and nowhere on the no-key path.
// 'push-subs' holds a record per subscription; 'push-sent' holds the sent marks per device.
export async function openStore(name) {
  if (!name || typeof name !== 'string') throw new Error('a store must be named');
  const { getStore } = await import('../vendor/netlify-blobs.mjs');
  const s = getStore({ name, consistency: 'strong' });
  return {
    async list() {
      const out = [];
      const r = await s.list();
      for (const b of r.blobs || []) out.push(b.key);
      return out;
    },
    get: (k) => s.get(k, { type: 'json' }),
    set: (k, v) => s.setJSON(k, v),
    del: (k) => s.delete(k),
  };
}
