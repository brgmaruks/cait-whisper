# Kaithos — Tokenomics

**A capped, fairly-mined, golden-ratio game token. Earned by playing. Never sold for power.**

> Status: **v0.1 — locked in principle.** Numbers may shift slightly as we playtest,
> but the structure below is the foundation we build on. This document covers the
> *economy only*. World, mechanics, and gameplay design live in separate docs.

---

## The two-token firewall

Kaithos lives inside the CAIT ecosystem, but it does **not** share a token with it.

| Token | Role | Scope |
|---|---|---|
| **$CAIT** | Governance of the wider CaitOS / cait-whisper ecosystem | Ecosystem-wide |
| **Game token** *(working name: `$KAI`, provisional)* | The in-game scarce asset, mined through play | Kaithos only |

This separation is deliberate. The game's economy can experiment, wobble, or be
exploited in a bad season **without ever threatening the integrity of the governance
token**. How (or whether) the two tokens bridge later is an explicitly separate
decision, made when both have proven themselves. We keep the firewall up by default.

---

## Supply — capped, Fibonacci, immutable

| Parameter | Value |
|---|---|
| Total supply | **24,157,817** (fixed, hard cap) |
| Why this number | The Fibonacci number nearest Bitcoin's 21M — it is **F(37)** |
| Mint after genesis | **None.** No admin mint. No inflation. No levers. |
| Premine | **Zero.** Every token is mined through play. |

Bitcoin's 21,000,000 already nods to the sequence — **21 is F(8)**. Kaithos makes the
golden ratio the whole identity: a supply that *is* a Fibonacci number, on a contract
that is immutable from genesis. Anyone can verify, at any time, that circulating
supply never exceeds the cap and that emission follows the published schedule below.
We lock it in and walk away — Bitcoin-style.

---

## Emission — 10% of the remaining supply, every season

A **season is a real season**: three months, four per year, riding
Spring → Summer → Autumn → Winter. Kaithos is built to run for many years.

Each season mints **10% of whatever supply remains unmined.** That single rule gives
us everything we wanted:

- **Disinflationary and exponentially harder over time** — every season pays less, in
  absolute terms, than the one before it. Forever.
- **A long, meaningful earning window** — earning stays substantial for ~3 years, then
  visibly tightens.
- **It never fully ends** — like Bitcoin, the tail asymptotes. There is always *some*
  reward, just diminishing. No hard wall where mining stops.
- **Supply halves roughly every ~6.6 seasons (~1.6 years)** — a gentle halving, not a
  genesis gold rush.

### Emission schedule

`Season n pool = S × 0.10 × 0.9^(n-1)`, where `S = 24,157,817`.

| Season | Year | Pool (tokens) | Pool % of supply | Cumulative mined | Cum. % |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 2,415,782 | 10.00% | 2,415,782 | 10.0% |
| 4 | 1 | 1,761,105 | 7.29% | 8,307,873 | 34.4% |
| 8 | 2 | 1,155,461 | 4.78% | 13,758,669 | 57.0% |
| 12 | 3 | 758,098 | 3.14% | 17,334,936 | **71.8%** |
| 16 | 4 | 497,388 | 2.06% | 19,681,325 | 81.5% |
| 20 | 5 | 326,336 | 1.35% | 21,220,790 | 87.8% |

By the end of year 3, ~72% is mined and the season pool has fallen from 10% to ~3% of
supply — earning is now genuinely harder, exactly as intended, but never zero.

---

## Distribution — earned within a season, by skill

A season's pool is **not** a faucet that pays per action (that just gets botted and
inflates nothing real). It is a **fixed pool distributed by competitive performance**
among the season's active players. Consequences:

- **Minting requires beating other humans**, not clicking. Bots can't inflate supply —
  they can only compete for a slice that already exists.
- **More players = each share is smaller.** A fixed pool split among `N` competitors is
  a self-adjusting difficulty curve, automatically, with no artificial knob. This is the
  game's equivalent of Bitcoin's difficulty adjustment.
- **Fair within your cohort, scarce across time.** A newcomer in Season 30 competes on a
  perfectly level field against their actual opponents. They earned less than a genesis
  player only because Season 1 had a bigger pool and fewer miners — exactly Bitcoin.

## The Golden Distribution

The cap is a Fibonacci number — the *static* φ. The distribution is where φ does
*work*: a season's pool is shared as a **self-similar golden cascade** that repeats the
same golden cut at every scale (season → individual-vs-kingdom → tiers → per-player →
within-kingdom). The payout structure is itself a golden spiral — *as above, so below*,
the same shape the cosmology is built on.

φ governs **how the pool is shared**, never **how fast it unlocks** — emission stays at
10%-of-remaining for the 3-year horizon (a φ-based decay would burn out in under two
years). The cascade has three levels.

### Level 1 — individual vs. kingdom

Each season's pool splits by the golden ratio:

| Slice | Share | Goes to |
|---|---|---|
| Individual ladders | **61.8%** (1/φ) | Solo performance — keeps the mid-pack logging in |
| Kingdom pools | **38.2%** (1/φ²) | Team victory — the headline collective prize |

### Level 2 — Fibonacci tiers with a golden taper

Players are sorted by performance and bracketed into tiers whose **populations grow by
Fibonacci** (1, 2, 3, 5, 8, 13, 21, 34…), while each tier's **total pool decays by 1/φ**.
The two φ-forces multiply: per-player reward falls by **φ² (≈2.618×) each tier**, and
~90 players earn every season instead of the prize evaporating after 4th place.

| Tier | Players | Tier pool | Per-player | Per-player drop |
|---:|---:|---:|---:|---:|
| 1 | 1 | 39.0% | 39.03% | — |
| 2 | 2 | 24.1% | 12.06% | ÷2.62 |
| 3 | 3 | 14.9% | 4.97% | ÷2.43 |
| 4 | 5 | 9.2% | 1.84% | ÷2.70 |
| 5 | 8 | 5.7% | 0.71% | ÷2.59 |
| 6 | 13 | 3.5% | 0.27% | ÷2.63 |
| 7 | 21 | 2.2% | 0.10% | ÷2.61 |
| 8 | 34 | 1.3% | 0.04% | ÷2.62 |

(Shares normalize over the actual active field each season. The top prize is ≈1/φ²;
the top two tiers together ≈1/φ — the Fibonacci retracement levels, falling straight
out of the math.)

### Level 3 — within a kingdom

A kingdom's 38.2% slice is distributed to its own members by the **same golden ladder**,
on internal contribution. The structure is now self-similar top to bottom — a fractal
of the golden ratio.

### The fairness knob

φ rewards excellence steeply (the top tier takes ~39%). If playtest shows that's too
cutthroat, the tuning knob is the **decay ratio**: drop from 1/φ (0.618) to **1/√φ
(0.786)** — the other Fibonacci retracement level — and the curve flattens while staying
a golden constant. Even the fairness dial is golden.

---

## Genesis — purist, community-gated

There is no insider allocation at genesis. The token does **not** go live until:

1. The **first season completes**, and
2. **UAT passes** and the **community agrees it's time to go.**

Until then, Kaithos runs in **pre-token ledger mode** — the same pattern cait-whisper
already uses for `rewards.json`. Season 1's earnings are *recorded* on an auditable
ledger; only when the community pulls the trigger does that ledger become claimable
on-chain. The genesis cohort isn't granted tokens — they **earn** them by showing up
first and proving the game works.

---

## The circular economy — a blended, self-funding loop

Kaithos pays for its own prizes. Players spend on **aesthetics only**, and that spend
recycles back to the community as rewards.

> Players buy cosmetics → **treasury wallet** → treasury funds prize pools → prizes go
> back to the community as season rewards.

**Rules of the loop:**

- **Cosmetics only.** Banners, hero skins, kingdom crests, victory animations. **Zero
  power. No gachas. No pay-to-win.** Money never buys an advantage on the field.
- **Blended payment:**
  - **Fiat storefront** for everyday cosmetics — zero crypto friction, anyone can play
    and spend with a card.
  - **Game token** reserved for the high-end **prestige sinks** — naming a kingdom into
    the Hall of Fame, permanent titles, inscriptions. This is where token demand should
    live, and it keeps the everyday experience light on crypto.
- **A whale buying a gold crest is literally funding the prize an underdog might win.**
  The output of all spending is rewards for everyone who competes.
- **Minting stays purist.** Cosmetics are not tokens, so real-money spending never
  creates new supply. The play-mined token and the cosmetic storefront stay clean and
  separate.

---

## What touches the chain (and what doesn't)

Kaithos is ~95% an ordinary, fast game and ~5% on-chain — chain only where permanence
and trustlessness genuinely earn their place.

| On-chain | Off-chain (normal fast backend) |
|---|---|
| Token balances & emission | Daily-turn gameplay (build, train, spy, attack) |
| Season results / settlement | In-season resources & power (gold, units, hero levels) |
| Hall of Fame (champions, kingdoms, titles) | Diplomacy, messaging, the moment-to-moment loop |
| Treasury & prize disbursement | Cosmetic storefront catalog |

In-season **power** — the stuff that wins battles — lives entirely off-chain and
**resets every season**. It can never be bought with the token. The chain records what
you *achieved* and what you *own*, never the power you wield this season.

---

## Prestige without NFTs

Owning your achievement does **not** require a tradeable collectible. The meaningful
version is a **permanent, public, auditable record**: an on-chain **Hall of Fame** that
inscribes season champions, victorious kingdoms, top spies and warriors — owned by your
wallet's *history* rather than a JPEG you flip. Permanence without speculation. If we
ever revisit NFTs, it will be because they add something this can't — not because the
space expects them.

---

## Principles

- **Proof of play, not pay-to-win.** The token represents what you *earned* on the
  field. Money buys vanity, never advantage.
- **Capped and immutable.** 24,157,817, forever. No mint, no levers, no premine.
- **Fair within a cohort, scarce across time.** Every season is winnable by newcomers.
- **Self-funding, not extractive.** The treasury recycles cosmetic spend into prizes.
- **We will not hype this.** A token that represents real competition is worth
  defending. One that represents speculation is not.

---

*Companion to the ecosystem's [`$CAIT` economy](../economy/ECONOMY.md). Game design,
world, and mechanics are documented separately.*
