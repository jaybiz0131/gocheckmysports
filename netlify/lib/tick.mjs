// One pass of the evening send. The store, the games and the sender are handed in, so the
// same code runs against Netlify Blobs in production and an in-memory store in the test.
import { selectSends, messageFor } from './select.mjs';

export const EXPIRE_MS = 180 * 24 * 3600 * 1000;   // a record not renewed in 180 days is deleted
const KEEP_SENT_MS = 21 * 24 * 3600 * 1000;        // a sent mark older than this is pruned

// store: {list() -> [key], get(key) -> obj|null, set(key, obj), del(key)}
// send: async (sub, message) -> HTTP status, 0 when unreachable.
export async function runTick({ store, games, now, send }) {
  const stats = { subs: 0, sent: 0, gone: 0, retry: 0, lost: 0, expired: 0 };
  const subs = [];
  for (const key of await store.list()) {
    const s = await store.get(key);
    if (!s || !s.endpoint) continue;
    if (now.getTime() - new Date(s.updated).getTime() > EXPIRE_MS) {
      await store.del(key); stats.expired++; continue;
    }
    subs.push({ ...s, id: key });
  }
  stats.subs = subs.length;
  const byId = new Map(games.map((g) => [g.id, g]));
  const byKey = new Map(subs.map((s) => [s.id, s]));
  for (const { subId, gameId } of selectSends({ subs, games, now })) {
    const sub = byKey.get(subId);
    const game = byId.get(gameId);
    // CLAIM FIRST. The mark is stored before the push leaves, so a crash or an overlapping
    // run can lose a push and cannot send a second one.
    const sent = {};
    for (const [k, v] of Object.entries(sub.sent || {})) {
      if (now.getTime() - new Date(v).getTime() < KEEP_SENT_MS) sent[k] = v;
    }
    sent[gameId] = now.toISOString();
    sub.sent = sent;
    const { id, ...rec } = sub;
    await store.set(subId, rec);
    const status = await send(sub, messageFor(game, now));
    if (status === 404 || status === 410) {           // the device is gone: forget it
      await store.del(subId); stats.gone++;
    } else if (status === 429 || status >= 500) {     // the service refused it: let a later tick retry
      delete rec.sent[gameId];
      await store.set(subId, rec); stats.retry++;
    } else if (status >= 200 && status < 300) {
      stats.sent++;
    } else {                                           // unreachable or refused for good: the mark stays
      stats.lost++;
    }
  }
  return stats;
}
