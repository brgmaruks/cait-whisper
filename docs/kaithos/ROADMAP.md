# Kaithos — Roadmap & Gap Analysis

**Where the project stands, what's missing, and the phased path to launch.**

> Status: v0.1 — written after the Season Zero MVP build. Companions:
> [`WORLD.md`](WORLD.md) · [`TOKENOMICS.md`](TOKENOMICS.md).

---

## Where we are

| Area | State |
|---|---|
| Name & domain | **Kaithos** · kaithos.com (to be registered by owner) |
| Tokenomics | **Locked in principle** — F(37) cap, 10%-of-remaining emission, Golden Distribution, purist genesis, circular economy |
| World & cosmology | **Locked in principle** — Monad/spiral cosmology, syncretic pantheons, phyllotaxis map, Dissolution, five elements, offensive triangle |
| Daily loop | **Drafted** — AP economy, order of the day, golden-edge combat |
| MVP (Season Zero) | **Playable end to end** — solo vs 3 AI factions, full element economy |
| Standalone repo | `brgmaruks/kaithos` created (private) — migration pending |

---

## Known issues (MVP)

1. **The climax never lands.** In 30 simulated seasons, the Eye was taken **zero**
   times — every season ended by attrition/fallback scoring. The Convergence needs
   teeth: AI must assault the Eye in the endgame, the Eye's garrison should be
   winnable, and "nobody holds the Eye at collapse" needs a designed resolution
   (not an undefined-winner edge case, which is currently possible if all
   provinces dissolve).
2. **Player-death ends the season** (`!you.alive` → game over) — correct for solo,
   but the rule must change for multiplayer (spectate / kingdom continues).
3. **No persistence** — refresh = new season. localStorage save is a quick win.
4. **Desktop-only layout** — the 320px side panel will break on phones. The target
   audience plays from phones; a responsive pass is high-value.
5. **MVP season is 24 days** (compressed for testing) vs. the real 90-day design.

## Design gaps (not yet specced)

- **Heroes** — classes/paths (Strategos / Mystagogue / Geometer), skill trees,
  Aether-fueled abilities. *Next design thread.*
- **Units** — the army is a single "garrison" number; needs a roster.
- **Town** — "dev level" placeholder; needs a building tree (Fibonacci tiers).
- **Espionage** — only Scout exists; sabotage, counter-intel, false-intel ops are
  designed in principle but not specced.
- **Kingdoms (the social core!)** — teams of real players, shared treasury,
  coordinated ops, internal contribution ladder, betrayal mechanics. The MVP is
  solo; the *game* is social. This is the largest gap between MVP and vision.
- **Scoring formula** — how in-season performance maps to rankings → Golden
  Distribution shares. Needs exact spec before any token season.
- **Season ↔ real-season binding** — elemental wax/wane is in (Summer), but the
  full wheel-of-the-year rotation isn't.

## Technical gaps

- **Multiplayer backend** — server-authoritative tick engine, accounts, order
  submission API, kingdom chat/diplomacy. The MVP is client-only by design;
  the real game needs a backend (architecture doc not yet written).
- **Deployment** — no public URL yet. Note: **GitHub Pages doesn't serve private
  repos on the free plan** — Netlify/Vercel free tiers do. One-click configs not
  yet added.
- **Anti-sybil / bot posture** — designed economically (pool-not-faucet, staked
  ranked seasons); no technical enforcement spec yet.

## Token & ops gaps

- **Ticker unconfirmed** — `$KAI` is provisional (owner to confirm; alternatives
  considered: $PHI (collision risk), $AUR).
- **Emission rounding** — integer token amounts per season need a defined rounding
  rule (recommend: floor, remainder stays in the unmined pool).
- **Treasury custody** — the treasury wallet needs a custody model (multisig?)
  before any real-money cosmetics flow.
- **Pre-token ledger artifact** — the `rewards.json`-style season ledger format
  isn't drafted yet.
- **Compliance review** — real-money cosmetics + a tradeable token will need a
  jurisdiction/compliance pass before public launch. Not urgent; not skippable.

---

## The phased path

**Phase 0 — Foundation (now)**
Migrate to the standalone private repo · fix the Convergence/Eye endgame ·
responsive/mobile pass · localStorage persistence · deploy config (Netlify or
Vercel) · play it with friends as hot-seat/solo testers.

**Phase 1 — Multiplayer Season Zero**
Backend tick engine + accounts + kingdoms of real players · the social layer
(kingdom chat, shared ops) · Heroes/Units/Town/Espionage depth · 90-day season ·
friends-and-family UAT season. **This UAT season is the genesis gate** — per
TOKENOMICS, the token doesn't exist until this completes and the community
agrees.

**Phase 2 — The Ledger**
Implement the scoring formula + Golden Distribution · pre-token season ledger
(auditable, `rewards.json` pattern) · Hall of Fame (off-chain first).

**Phase 3 — The Chain**
$KAI contract on Base (capped F(37), emission schedule baked in) · Merkle claims
from the season ledgers · on-chain Hall of Fame inscription · treasury multisig.

**Phase 4 — The Circular Economy**
Cosmetic storefront (fiat) · prestige sinks ($KAI) · treasury → prize-pool
recycling · governance hooks back to the $CAIT ecosystem.

---

*The spiral unwinds one whorl at a time.*
