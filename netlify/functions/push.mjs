// POST /api/push: a device follows a team (or stops). With no key in the environment this
// answers 503 and does nothing else. It does not throw.
import { readVapid, openStore } from '../lib/config.mjs';
import { subscribe, json } from '../lib/subscribe.mjs';

export default async (req) => {
  try {
    if (!readVapid()) return json(503, { error: 'push is not enabled' });
    return await subscribe(req, await openStore());
  } catch {
    return json(503, { error: 'push is not available' });
  }
};

export const config = { path: '/api/push' };
