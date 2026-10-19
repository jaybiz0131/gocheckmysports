// One pass of the evening send. The store, the games and the sender are handed in, so the
// same code runs against Netlify Blobs in production and an in-memory store in the test.
import { selectSends, messageFor } from './select.mjs';

export const EXPIRE_MS = 180 * 24 * 3600 * 1000;   // a record not renewed in 180 days is deleted
export const KEEP_SENT_MS = 21 * 24 * 3600 * 1000; // a sent mark older than this is pruned, and an idle record with it

// store: {list() -> [key], get(key) -> obj|null, set(key, obj), del(key)}, the subscriptions.
// marks: the same interface, the sent marks, one record per DEVICE ({sent: {gameId: iso}, updated}),
//   kept apart from the subscriptions so that turning a team off (which deletes the subscription)
//   and on again (a new endpoint on the same device) does not forget what was sent.
// send: async (sub, message) -> HTTP status, 0 when unreachable.
export async function runTick({ store, marks, games, now, send }) {
  const stats = { subs: 0, sent: 0, gone: 0, retry: 0, lost: 0, expired: 0 };
  const t = now.getTime();
  const subs = [];
  for (const key of await store.list()) {
    const s = await store.get(key);
    if (!s || !s.endpoint) continue;
    if (t - new Date(s.updated).getTime() > EXPIRE_MS) {
      await store.del(key); stats.expired++; continue;
    }
    subs.push({ ...s, id: key });
  }
  stats.subs = subs.length;
  // A mark record whose newest mark is past the keep window expires by itself.
  for (const key of await marks.list()) {
    const rec = await marks.get(key);
    const newest = Math.max(0, ...Object.values((rec && rec.sent) || {}).map((v) => new Date(v).getTime() || 0));
    if (!newest || t - newest >= KEEP_SENT_MS) await marks.del(key);
  }
  const byId = new Map(games.map((g) => [g.id, g]));
  const byKey = new Map(subs.map((s) => [s.id, s]));
  for (const { subId, gameId } of selectSends({ subs, games, now })) {
    const sub = byKey.get(subId);
    const game = byId.get(gameId);
    const dev = sub.dev || subId;
    // CLAIM FIRST. The device's mark is stored before the push leaves, so a crash or an
    // overlapping run can lose a push and cannot send a second one. It is read again here,
    // not taken from the selection, because two records of one device may be in this pass.
    const rec = (await marks.get(dev)) || { sent: {} };
    if (rec.sent[gameId]) continue;
    const sent = {};
    for (const [k, v] of Object.entries(rec.sent)) {
      if (t - new Date(v).getTime() < KEEP_SENT_MS) sent[k] = v;
    }
    sent[gameId] = now.toISOString();
    await marks.set(dev, { sent, updated: now.toISOString() });
    let status = 0;
    try { status = await send(sub, messageFor(game, now)); } catch { status = 0; }
    const handBack = async () => {                     // nothing was delivered: give the mark back
      delete sent[gameId];
      if (Object.keys(sent).length) await marks.set(dev, { sent, updated: now.toISOString() });
      else await marks.del(dev);
    };
    if (status === 404 || status === 410) {           // the endpoint is gone: forget it
      await store.del(subId); await handBack(); stats.gone++;
    } else if (status === 429 || status >= 500) {     // the service refused it: let a later tick retry
      await handBack(); stats.retry++;
    } else if (status >= 200 && status < 300) {
      stats.sent++;
    } else {                                           // unreachable or refused for good: the mark stays
      stats.lost++;
    }
  }
  return stats;
}
