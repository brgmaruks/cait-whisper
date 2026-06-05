// The engine: issuing orders, the daily tick (Order of the Day), AI, and the
// golden-edge combat that fuses the offensive triangle with φ.

import { PHI, INV_PHI, MODES, ORDER_COSTS, FACTIONS, SEASON_DAYS, CONTRACTION_DAYS } from './config.js';
import { isRevealed } from './state.js';

const pname = (p) => (p.isEye ? 'the Eye' : 'P' + p.i);
const fname = (id) => (id ? FACTIONS[id].name : 'Neutral');
const heroBonus = (pl) => 1 + 0.12 * (pl.hero.level - 1);

function modeMult(atk, def) {
  if (MODES[atk].beats === def) return PHI;       // counter → golden edge
  if (MODES[def].beats === atk) return INV_PHI;   // countered
  return 1;
}

export function attachEngine(state, handlers, rerender) {
  const log = (text, cls) => state.log.push({ text, cls });

  // ---- order issuing (AP + gold deducted on commit, refunded on cancel) ----
  function canAfford(pl, cost) { return pl.ap >= cost.ap && pl.gold >= (cost.gold || 0); }
  function pay(pl, cost) { pl.ap -= cost.ap; pl.gold -= cost.gold || 0; }
  function refund(pl, cost) { pl.ap += cost.ap; pl.gold += cost.gold || 0; }

  function issue(order) {
    const me = state.players.you;
    const cost = ORDER_COSTS[order.kind];
    if (!canAfford(me, cost)) return;
    pay(me, cost);
    order.cost = cost;
    state.orders.push(order);
    rerender();
  }
  function cancel(idx) {
    const o = state.orders[idx];
    if (!o) return;
    refund(state.players.you, o.cost);
    state.orders.splice(idx, 1);
    rerender();
  }

  // ---- the side-panel order UI for the selected province ----
  handlers.renderOrders = (st, p, ord) => {
    const me = st.players.you;
    const mine = p.owner === 'you';
    const adjMine = st.adj[p.i].some((j) => st.provinces[j].owner === 'you' && !st.provinces[j].dissolved);
    let html = '';

    if (mine) {
      const bc = ORDER_COSTS.build, tc = ORDER_COSTS.train;
      html += `<h3>Orders · ${pname(p)}</h3>`;
      html += orderBtn('Build', '+1 development', bc, me, `build:${p.i}`);
      html += orderBtn('Train', '+2 garrison', tc, me, `train:${p.i}`);

      if (p.garrison > 1) {
        html += `<div class="muted" style="margin:.5rem 0 .25rem">March / Strike · mode:</div>`;
        html += `<div class="mode-row">` + Object.keys(MODES).map((m) =>
          `<button data-mode="${m}" class="${st.attackMode === m ? 'active' : ''}">${MODES[m].sym} ${MODES[m].name}</button>`).join('') + `</div>`;
        html += `<div class="stat-row"><span class="k">Troops</span><input id="troops" type="number" min="1" max="${p.garrison - 1}" value="${p.garrison - 1}" style="width:64px;background:var(--panel-2);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:.2rem .4rem"></div>`;
        html += `<div class="muted" style="margin:.4rem 0 .25rem">to (${ORDER_COSTS.march.ap} AP):</div>`;
        for (const j of st.adj[p.i]) {
          const q = st.provinces[j]; if (q.dissolved) continue;
          const known = isRevealed(st, q);
          const tag = q.owner === 'you' ? 'reinforce' : (known ? `${fname(q.owner)} · ${q.garrison}` : `${fname(q.owner)} · ?`);
          html += `<button class="order-btn" data-march="${j}" ${me.ap < ORDER_COSTS.march.ap ? 'disabled' : ''}><span>${q.isEye ? 'the Eye ◉' : '▸ P' + j}</span><span class="cost">${tag}</span></button>`;
        }
      }
    } else if (adjMine) {
      html += `<h3>Orders · ${pname(p)}</h3>`;
      html += orderBtn('Scout', 'reveal garrison & mode', ORDER_COSTS.scout, me, `scout:${p.i}`);
      html += `<p class="muted" style="margin-top:.4rem">To strike here, select an adjacent province you hold and march.</p>`;
    } else {
      html += `<p class="muted">No orders — not adjacent to your dominion.</p>`;
    }

    // pending orders
    if (st.orders.length) {
      html += `<h3 style="margin-top:1rem">Pending — resolves at dawn</h3>`;
      st.orders.forEach((o, idx) => {
        html += `<div class="order-btn" style="cursor:default"><span>${describe(o)}</span><span class="cost" data-cancel="${idx}" style="cursor:pointer;color:var(--coral)">✕</span></div>`;
      });
    }
    ord.innerHTML = html;

    // wire events
    ord.querySelectorAll('[data-order]').forEach((b) =>
      b.addEventListener('click', () => onOrderBtn(b.dataset.order)));
    ord.querySelectorAll('[data-mode]').forEach((b) =>
      b.addEventListener('click', () => { st.attackMode = b.dataset.mode; rerender(); }));
    ord.querySelectorAll('[data-march]').forEach((b) =>
      b.addEventListener('click', () => {
        const troops = Math.max(1, Math.min(p.garrison - 1, parseInt(ord.querySelector('#troops')?.value || '1', 10)));
        issue({ kind: 'march', from: p.i, to: +b.dataset.march, troops, mode: st.attackMode });
      }));
    ord.querySelectorAll('[data-cancel]').forEach((b) =>
      b.addEventListener('click', () => cancel(+b.dataset.cancel)));
  };

  function orderBtn(label, desc, cost, me, token) {
    const dis = me.ap < cost.ap || me.gold < (cost.gold || 0);
    const c = `${cost.ap} AP${cost.gold ? ' · ' + cost.gold + 'g' : ''}`;
    return `<button class="order-btn" data-order="${token}" ${dis ? 'disabled' : ''}><span>${label} <span class="cost">${desc}</span></span><span class="cost">${c}</span></button>`;
  }
  function onOrderBtn(token) {
    const [kind, i] = token.split(':');
    issue({ kind, prov: +i });
  }
  function describe(o) {
    if (o.kind === 'build') return `Build · P${o.prov}`;
    if (o.kind === 'train') return `Train · P${o.prov}`;
    if (o.kind === 'scout') return `Scout · P${o.prov}`;
    if (o.kind === 'march') return `${MODES[o.mode].sym} March P${o.from}→${o.to === 0 ? 'Eye' : 'P' + o.to} (${o.troops})`;
    return o.kind;
  }

  // ---------------- the daily tick ----------------
  handlers.onAdvance = () => {
    if (state.over) return;
    log(`Day ${state.day} resolves.`, 'day');

    // 1. Production
    for (const id in state.players) produce(state.players[id], id);

    // 2. Construction (player + AI build/train)
    const ai = collectAiOrders();
    const all = [...state.orders, ...ai];
    for (const o of all) if (o.kind === 'build' || o.kind === 'train') applyBuild(o, ownerOf(o));
    // 3. Espionage
    for (const o of all) if (o.kind === 'scout') applyScout(o, ownerOf(o));
    // 4. Movement + Combat
    const marches = all.filter((o) => o.kind === 'march');
    for (const o of marches) resolveMarch(o, ownerOf(o));

    // hero leveling
    for (const id in state.players) levelUp(state.players[id]);

    // 5. Dissolution
    if (CONTRACTION_DAYS.includes(state.day)) contract();

    // 6. Settlement — new day, AP grant, phase, win check
    state.orders = [];
    state.day++;
    for (const id in state.players) {
      const pl = state.players[id];
      pl.ap = Math.min(pl.apMax, pl.ap + 4 + pl.hero.level);
    }
    updatePhase();
    checkEnd();
    state.selectedId = null;
    rerender();
  };

  const ownerOf = (o) => (o.owner || 'you');

  function produce(pl, id) {
    let gold = 0, aether = 0;
    for (const p of state.provinces) {
      if (p.owner !== id || p.dissolved) continue;
      gold += p.dev * 2;
      if (p.ring <= 1) aether += p.dev;
    }
    pl.gold += gold; pl.aether += aether;
  }

  function applyBuild(o, id) {
    const p = state.provinces[o.prov];
    if (!p || p.owner !== id || p.dissolved) return;
    if (o.kind === 'build') p.dev = Math.min(6, p.dev + 1);
    else p.garrison += 2;
  }

  function applyScout(o, id) {
    const p = state.provinces[o.prov];
    if (!p || p.dissolved) return;
    p.revealedBy.add(id);
    if (id === 'you') log(`Scouts reach <b>${pname(p)}</b>: ${fname(p.owner)}, garrison ${p.garrison}, posture ${MODES[p.mode].name}.`);
  }

  function resolveMarch(o, id) {
    const src = state.provinces[o.from], dst = state.provinces[o.to];
    if (!src || !dst || src.owner !== id || src.dissolved || dst.dissolved) return;
    const troops = Math.min(o.troops, src.garrison - 1);
    if (troops <= 0) return;
    src.garrison -= troops;

    if (dst.owner === id) { dst.garrison += troops; return; } // reinforce

    const atkPl = state.players[id];
    const mult = modeMult(o.mode, dst.mode);
    const eff = troops * mult * heroBonus(atkPl);
    dst.revealedBy.add(id);

    if (eff > dst.garrison) {
      const survivors = Math.max(1, Math.round(troops * (1 - dst.garrison / eff)));
      const wasEye = dst.isEye, prevOwner = dst.owner;
      dst.owner = id; dst.garrison = survivors; dst.mode = FACTIONS[id].lean;
      atkPl.hero.xp += 4 + dst.dev * 2 + (wasEye ? 12 : 0);
      if (id === 'you' || prevOwner === 'you')
        log(`${MODES[o.mode].sym} <b>${fname(id)}</b> seizes <b>${pname(dst)}</b> from ${fname(prevOwner)}${mult > 1 ? ' (golden edge ×φ)' : mult < 1 ? ' (countered)' : ''}.`,
          id === 'you' ? 'good' : 'bad');
    } else {
      const before = dst.garrison;
      dst.garrison = Math.max(1, Math.round(dst.garrison - eff * 0.6));
      if (id === 'you' || dst.owner === 'you')
        log(`${MODES[o.mode].sym} ${fname(id)}'s strike on <b>${pname(dst)}</b> is repelled (${before}→${dst.garrison})${mult < 1 ? ' — wrong mode' : ''}.`,
          dst.owner === 'you' ? 'good' : 'bad');
    }
  }

  function levelUp(pl) {
    while (pl.hero.xp >= 8 * pl.hero.level) {
      pl.hero.xp -= 8 * pl.hero.level;
      pl.hero.level++;
      if (pl.id === 'you') log(`Your hero rises to <b>level ${pl.hero.level}</b>.`, 'good');
    }
  }

  // ---- AI: simple, but it grows, attacks the weak, and pushes inward late ----
  function collectAiOrders() {
    const orders = [];
    const lateGame = state.day >= CONTRACTION_DAYS[0];
    for (const id in state.players) {
      const pl = state.players[id];
      if (id === 'you' || !pl.alive) continue;
      let ap = pl.ap, gold = pl.gold;
      const mine = state.provinces.filter((p) => p.owner === id && !p.dissolved);
      // train up the strongest frontier holding
      for (const p of mine) {
        if (ap >= 1 && gold >= 5 && p.garrison < 12 && Math.random() < 0.5) {
          orders.push({ kind: 'train', prov: p.i, owner: id }); ap -= 1; gold -= 5;
        } else if (ap >= 1 && gold >= 8 && p.dev < 4 && Math.random() < 0.4) {
          orders.push({ kind: 'build', prov: p.i, owner: id }); ap -= 1; gold -= 8;
        }
      }
      // attack weak adjacent provinces (bias inward in the late game)
      for (const p of mine) {
        if (ap < 2 || p.garrison < 5) continue;
        const targets = state.adj[p.i]
          .map((j) => state.provinces[j])
          .filter((q) => q.owner !== id && !q.dissolved)
          .filter((q) => q.garrison * (lateGame ? 1.2 : 1.4) < p.garrison)
          .sort((a, b) => (lateGame ? a.radius - b.radius : a.garrison - b.garrison));
        if (targets.length) {
          const q = targets[0];
          orders.push({ kind: 'march', from: p.i, to: q.i, troops: p.garrison - 2, mode: FACTIONS[id].lean, owner: id });
          ap -= 2;
        }
      }
      pl.ap = ap; pl.gold = gold;
    }
    return orders;
  }

  function contract() {
    const live = state.provinces.filter((p) => !p.dissolved);
    const maxRing = Math.max(...live.map((p) => p.ring));
    let claimed = 0;
    for (const p of state.provinces) {
      if (!p.dissolved && p.ring === maxRing && !p.isEye) {
        p.dissolved = true; p.owner = null; p.garrison = 0; claimed++;
      }
    }
    log(`<b>The Dissolution</b> claims the outer ring — ${claimed} provinces unmade. The spiral tightens.`, 'bad');
  }

  function updatePhase() {
    if (state.day < CONTRACTION_DAYS[0]) state.phase = 'Emanation';
    else if (state.day >= SEASON_DAYS - 4) state.phase = 'Convergence';
    else state.phase = 'Contraction';
  }

  function checkEnd() {
    for (const id in state.players) {
      const pl = state.players[id];
      pl.alive = state.provinces.some((p) => p.owner === id && !p.dissolved);
    }
    const aliveIds = Object.keys(state.players).filter((id) => state.players[id].alive);
    const you = state.players.you;
    const seasonOver = state.day > SEASON_DAYS || aliveIds.length <= 1 || !you.alive;
    if (!seasonOver) return;

    state.over = true;
    const eye = state.provinces[0];
    let winner = eye.owner && !eye.dissolved ? eye.owner
      : aliveIds.sort((a, b) => provCount(b) - provCount(a))[0];
    state.winner = winner;
    state.phase = 'Ended';
    if (winner === 'you') log(`<b>You hold the spiral.</b> The Eye is yours — you ascend. Season Zero is won. ◉`, 'good');
    else log(`<b>${fname(winner)} ascends.</b> The Monad closes around them. Season Zero ends.`, 'bad');
  }
  const provCount = (id) => state.provinces.filter((p) => p.owner === id && !p.dissolved).length;
}
