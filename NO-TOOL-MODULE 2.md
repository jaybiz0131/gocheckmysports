# Why gocheckmysports has no tool module

The ecosystem brief's E4 rule gives every automated article one contextual tool
module from a consumer site. Sports is the deliberate exception, and this file
exists so the exception is not "fixed" by a later session that assumes it was an
oversight.

Sports has no natural consumer-site route. Worse, its vocabulary actively
collides with the hazards the other sites are about. Measured against this
repo's own archive on 2026-08-27:

- 7 stories match "hurricane". Every one is the Carolina Hurricanes, an NHL
  team, in stories about broadcast rights and rosters.
- "Panthers" appears throughout, and is two franchises.
- "recalled" is how baseball moves a player up from Triple-A, so a recall
  checker would attach to injury stories.
- "refinancing" appears in stories about league finances.

A 48-hour hurricane readiness checklist under an NHL broadcast-rights story is
exactly the forced module the rule exists to prevent, and it would be worse than
no module at all: it reads as automated, which is the one impression the family
cannot afford.

If Sports ever earns a route, it will be because a genuine one exists, not
because the slot looked empty. `family_modules.py` is deliberately NOT copied
into this repo.
