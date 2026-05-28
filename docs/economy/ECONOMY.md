# $CAIT Token Economy

**Proof of useful work for open source AI tooling.**

$CAIT is the contribution token for the cait-whisper ecosystem. It rewards real work: code, docs, tests, ports. Not speculation - output.

---

## What $CAIT Is

A utility token on Base (Ethereum L2). Earned by contributing to cait-whisper and related open-source CaitOS modules. Not sold. Not airdropped. Mined through work.

**Current phase:** Pre-token ledger. All contributions are tracked on-chain in `rewards.json`. When the token contract deploys, recorded contributions are claimable.

---

## How to Earn $CAIT

| Contribution | Reward | Notes |
|---|---|---|
| Bug fix (confirmed + merged) | 50 $CAIT | Must include reproduction case |
| Feature (merged) | 100-500 $CAIT | Scope-dependent, agreed in issue |
| macOS / Linux port | 1,000 $CAIT | Biggest gap. Full port unlocks this. |
| Test coverage (per module) | 50 $CAIT | Must achieve >80% branch coverage |
| Documentation improvement | 25 $CAIT | Substantive - not typo fixes |
| Issue triage (labeled + responded) | 10 $CAIT | Active maintainer track |
| New ASR engine integration | 200 $CAIT | Merged and stable |

**Multipliers:**
- First contributor to a new platform (macOS, Linux): 1.5x
- Contributions that close a ROADMAP item: 1.25x

---

## How Claims Work

1. Open a PR or issue. In the body, include your wallet address (Base network).
2. When merged/confirmed, a maintainer records the reward in `rewards.json` via a signed commit.
3. Pre-token: entry is created with status `pending_claim`.
4. Post-deploy: you call the claim function on the $CAIT contract. It reads the Merkle proof from the repo.

No account needed. No sign-up. Just work, wallet, and a merged PR.

---

## Token Details (Phase 2 - pending deploy)

| Parameter | Value |
|---|---|
| Name | CaitOS Contribution Token |
| Symbol | $CAIT |
| Network | Base (Ethereum L2) |
| Standard | ERC-20 |
| Total supply | 10,000,000 $CAIT |
| Distribution | 60% contributor rewards, 20% ecosystem treasury, 20% liquidity |
| Contract | TBD on deploy |

Supply is fixed. No mint after genesis. Every token in circulation was earned or allocated for liquidity.

---

## What $CAIT Will Do

**Phase 1 (now):** Track contributions in `rewards.json`. No gas. No friction. Just a ledger.

**Phase 2 (contract deploy):** ERC-20 goes live on Base. Ledger entries become claimable.

**Phase 3 (utility):**
- Governance votes on roadmap priorities
- Access to private beta features
- Priority review queue for PRs from token holders
- Optional Uniswap pool for contributors who want liquidity

---

## Principles

**Proof of useful work.** A token that represents real open-source contribution is worth defending. One that represents speculation is not. We will not hype this.

**No lock-ins.** The repo is MIT. The token is a reward, not a gate. You can contribute without a wallet. The work matters more than the incentive.

**Transparency.** `rewards.json` is the canonical record. Every allocation is in a signed commit. If you disagree with an allocation, open an issue.

---

## Status

| Item | Status |
|---|---|
| Contribution ledger (`rewards.json`) | Live |
| $CAIT contract deploy | Pending |
| Claim portal | Pending contract deploy |
| Uniswap pool | Phase 3 |

Watch this file and `rewards.json` for updates. No newsletter, no Discord, no hype. Just commits.
