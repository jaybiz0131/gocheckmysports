// The relay's keys, read from the hosting environment and from nowhere else. A key is never
// read from a file, never written to one, never logged. Absent or malformed, the relay is off.
//   WEB_PUSH_VAPID_PUBLIC_KEY    the application server key, base64url, 65 bytes (also read by the build)
//   WEB_PUSH_VAPID_PRIVATE_KEY   the matching private key, base64url, 32 bytes (functions only)
//   WEB_PUSH_SUBJECT             optional, a mailto: or https: contact; defaults to the site
import { b64u } from './webpush.mjs';

export const SITE = 'https://gocheckmysports.com';

export function readVapid(env = process.env) {
  const publicKey = String(env.WEB_PUSH_VAPID_PUBLIC_KEY || '').trim();
  const privateKey = String(env.WEB_PUSH_VAPID_PRIVATE_KEY || '').trim();
  if (!publicKey || !privateKey) return null;
  const pub = b64u.dec(publicKey);
  const priv = b64u.dec(privateKey);
  if (pub.length !== 65 || pub[0] !== 4 || priv.length !== 32) return null;
  const subject = String(env.WEB_PUSH_SUBJECT || '').trim();
  return { publicKey, privateKey, subject: /^(mailto:|https:\/\/)/.test(subject) ? subject : SITE };
}

// The store, opened only after the keys are known to be present. Netlify Blobs is the one
// npm dependency; it is imported here and nowhere on the no-key path.
export async function openStore(name = 'push-subs') {
  const { getStore } = await import('@netlify/blobs');
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
