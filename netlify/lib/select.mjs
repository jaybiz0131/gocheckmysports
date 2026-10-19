// Who gets which push, decided from data alone: no clock of its own, no network, no store.
// The one-push rule is here and in tick.mjs, and both are tested from a fixture.
//
// THE RULE. A device that follows a team is sent one push for each of that team's games, on
// the evening before the game by the Eastern calendar (from 7:00 PM ET to the end of that
// day), and never a second for the same game: the device's record of what it was sent is
// checked first and written before the send. The evening is read in ET, not UTC, because a
// Sunday 8:15 PM ET kickoff is Monday in UTC and its evening before is still Saturday.

export const SEND_FROM_HOUR_ET = 19;
const TZ = 'America/New_York';

const FMT = new Intl.DateTimeFormat('en-US', {
  timeZone: TZ, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit',
});

// The Eastern calendar date (YYYY-MM-DD) and hour of an instant.
export function etParts(date) {
  const p = {};
  for (const x of FMT.formatToParts(date)) p[x.type] = x.value;
  return { day: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) };
}

// The calendar day before a YYYY-MM-DD date.
export function dayBefore(day) {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d - 1)).toISOString().slice(0, 10);
}

// True when `now` is inside the game's evening-before window.
export function inWindow(game, now) {
  const kick = new Date(game.kick);
  if (Number.isNaN(kick.getTime()) || kick.getTime() <= now.getTime()) return false;
  const n = etParts(now);
  return n.day === dayBefore(etParts(kick).day) && n.hour >= SEND_FROM_HOUR_ET;
}

// subs: [{id, teams: [...], sent: {gameId: iso}}]; games: [{id, kick, teams: [...]}].
// Returns [{subId, gameId}], one per device per game, in game then device order.
export function selectSends({ subs, games, now }) {
  const out = [];
  const seen = new Set();
  for (const g of games || []) {
    if (!g || !g.id || seen.has(g.id)) continue;
    seen.add(g.id);
    if (!inWindow(g, now)) continue;
    const teams = new Set(g.teams || []);
    for (const s of subs || []) {
      if (s.sent && s.sent[g.id]) continue;
      if ((s.teams || []).some((t) => teams.has(t))) out.push({ subId: s.id, gameId: g.id });
    }
  }
  return out;
}

// The conditions line is as old as the build that read it. Past this age it is left out.
export const COND_MAX_AGE_MS = 36 * 3600 * 1000;

// The notification: the title names the game, the body is the kickoff line and, when the
// build's reading is fresh enough, the conditions line. Information only.
export function messageFor(game, now) {
  const at = new Date(game.cond_at).getTime();
  const fresh = game.cond && Number.isFinite(at) && now.getTime() - at <= COND_MAX_AGE_MS;
  return {
    title: `Tomorrow: ${game.title}`,
    body: fresh ? `${game.lead} ${game.cond}.` : game.lead,
    url: game.path,
    tag: `game-${game.id}`,
  };
}
