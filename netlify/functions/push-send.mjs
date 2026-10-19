// The evening send, hourly. A tick sends only from 7:00 PM ET on the evening before a game
// (netlify/lib/select.mjs), so the hourly schedule is a retry, not a flood: a device is sent
// one push per game and the record of it is written first. With no key it does nothing.
import { readVapid, openStore, SITE } from '../lib/config.mjs';
import { runTick } from '../lib/tick.mjs';
import { sendPush } from '../lib/webpush.mjs';

export default async () => {
  try {
    const vapid = readVapid();
    if (!vapid) { console.log('push-send: no key in the environment, nothing sent'); return; }
    const r = await fetch(new URL('/data/push-games.json', process.env.URL || SITE));
    if (!r.ok) { console.log(`push-send: the game index answered ${r.status}, nothing sent`); return; }
    const games = (await r.json()).games || [];
    const stats = await runTick({
      store: await openStore(), games, now: new Date(),
      send: (sub, msg) => sendPush(sub, msg, vapid),
    });
    console.log(`push-send: ${JSON.stringify(stats)}`);
  } catch (e) {
    console.log(`push-send: stopped (${e && e.name})`);
  }
};

export const config = { schedule: '0 * * * *' };
