// Web Push from the platform's crypto alone: RFC 8291 (aes128gcm message encryption) and
// RFC 8292 (VAPID, an ES256 token). No npm dependency: node:crypto does every step, and the
// test decrypts what this encrypts with an independent reader written from the RFC.
import {
  createECDH, createHmac, createCipheriv, createPrivateKey, randomBytes, sign,
} from 'node:crypto';

export const b64u = {
  enc: (buf) => Buffer.from(buf).toString('base64url'),
  dec: (s) => Buffer.from(String(s || ''), 'base64url'),
};

// HKDF with SHA-256, one output block (every length used here is 32 bytes or fewer).
export function hkdf(salt, ikm, info, len) {
  const prk = createHmac('sha256', salt).update(ikm).digest();
  return createHmac('sha256', prk).update(Buffer.concat([info, Buffer.from([1])])).digest().subarray(0, len);
}

// The message body for one subscription: salt, record size, the sender's key, then the
// encrypted record. `uaPublic` is the 65 byte p256dh key, `authSecret` the 16 byte auth.
export function encryptPayload(payload, uaPublic, authSecret, opts = {}) {
  const plain = Buffer.concat([Buffer.from(payload), Buffer.from([2])]); // 0x02 ends the only record
  if (plain.length > 3900) throw new Error('payload too large');
  const as = createECDH('prime256v1');
  if (opts.asPrivate) as.setPrivateKey(opts.asPrivate); else as.generateKeys();
  const asPublic = as.getPublicKey();
  const secret = as.computeSecret(uaPublic);
  const ikm = hkdf(authSecret, secret,
    Buffer.concat([Buffer.from('WebPush: info\0'), uaPublic, asPublic]), 32);
  const salt = opts.salt || randomBytes(16);
  const cek = hkdf(salt, ikm, Buffer.from('Content-Encoding: aes128gcm\0'), 16);
  const nonce = hkdf(salt, ikm, Buffer.from('Content-Encoding: nonce\0'), 12);
  const c = createCipheriv('aes-128-gcm', cek, nonce);
  const ct = Buffer.concat([c.update(plain), c.final(), c.getAuthTag()]);
  const rs = Buffer.alloc(4); rs.writeUInt32BE(4096);
  return Buffer.concat([salt, rs, Buffer.from([asPublic.length]), asPublic, ct]);
}

// The VAPID token: ES256 over {aud, exp, sub}, signed with the 32 byte private key.
export function vapidToken(endpoint, vapid, nowMs = Date.now()) {
  const pub = b64u.dec(vapid.publicKey);
  const jwk = {
    kty: 'EC', crv: 'P-256', d: b64u.enc(b64u.dec(vapid.privateKey)),
    x: b64u.enc(pub.subarray(1, 33)), y: b64u.enc(pub.subarray(33, 65)),
  };
  const head = b64u.enc(JSON.stringify({ typ: 'JWT', alg: 'ES256' }));
  const body = b64u.enc(JSON.stringify({
    aud: new URL(endpoint).origin,
    exp: Math.floor(nowMs / 1000) + 12 * 3600,
    sub: vapid.subject,
  }));
  const sig = sign('sha256', Buffer.from(`${head}.${body}`),
    { key: createPrivateKey({ key: jwk, format: 'jwk' }), dsaEncoding: 'ieee-p1363' });
  return `${head}.${body}.${b64u.enc(sig)}`;
}

// One push. Returns the push service's HTTP status, or 0 when it could not be reached.
export async function sendPush(sub, message, vapid, fetchFn = fetch, nowMs = Date.now()) {
  try {
    const body = encryptPayload(JSON.stringify(message), b64u.dec(sub.keys.p256dh), b64u.dec(sub.keys.auth));
    const r = await fetchFn(sub.endpoint, {
      method: 'POST',
      headers: {
        'Content-Encoding': 'aes128gcm',
        'Content-Type': 'application/octet-stream',
        'Content-Length': String(body.length),
        TTL: String(12 * 3600),
        Urgency: 'normal',
        Authorization: `vapid t=${vapidToken(sub.endpoint, vapid, nowMs)}, k=${vapid.publicKey}`,
      },
      body,
    });
    return r.status;
  } catch {
    return 0;
  }
}
