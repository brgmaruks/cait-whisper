// Game state for Season Zero. Power resets each season; everyone starts equal.

import { FACTIONS, MODES } from './config.js';
import { layout, adjacency } from './map.js';

// small seeded RNG so a season is reproducible (mulberry32)
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function createState(seed = Date.now() % 100000) {
  const rand = rng(seed);
  const provs = layout();
  const adj = adjacency(provs);

  const provinces = provs.map((p) => ({
    i: p.i, x: p.x, y: p.y, radius: p.radius, ring: p.ring,
    owner: null,            // faction id or null (neutral)
    garrison: 3 + Math.floor(rand() * 4),
    dev: 1,
    mode: pickMode(rand),   // defensive posture
    revealedBy: new Set(['neutral']),
    dissolved: false,
  }));

  // The Monad / the Eye — the centre, the prize.
  const eye = provinces[0];
  eye.garrison = 12; eye.dev = 3; eye.isEye = true; eye.mode = 'arcane';

  // Seed the four factions on the outer rings, spread by angle.
  const ids = Object.keys(FACTIONS);
  const outer = provinces.filter((p) => p.ring >= 2 && p.i !== 0);
  const sectors = ids.map((_, k) => (k / ids.length) * Math.PI * 2);
  ids.forEach((id, k) => {
    // nearest outer province to this faction's sector angle
    let best = null, bestD = Infinity;
    for (const p of outer) {
      if (p.owner) continue;
      const ang = Math.atan2(p.y - 450, p.x - 450);
      let d = Math.abs(angDiff(ang, sectors[k] - Math.PI));
      d -= p.radius / 2000; // bias slightly outward
      if (d < bestD) { bestD = d; best = p; }
    }
    if (!best) return;
    claim(best, id, FACTIONS[id].lean);
    // grant two nearby provinces too
    const near = adj[best.i].filter((j) => !provinces[j].owner && provinces[j].i !== 0)
      .sort((a, b) => provinces[a].radius - provinces[b].radius).slice(0, 2);
    near.forEach((j) => claim(provinces[j], id, FACTIONS[id].lean));
  });

  function claim(p, id, mode) {
    p.owner = id; p.dev = 2; p.garrison = 6 + Math.floor(rand() * 3); p.mode = mode;
    p.revealedBy.add(id);
    if (id === 'you') p.revealedBy.add('you');
  }

  const players = {};
  for (const id of ids) {
    players[id] = {
      id, faction: FACTIONS[id], gold: 30, aether: 0,
      ap: 5, apMax: 13, hero: { level: 1, xp: 0 }, alive: true,
    };
  }

  // reveal neighbours of your starting provinces
  const yours = provinces.filter((p) => p.owner === 'you');
  for (const p of yours) for (const j of adj[p.i]) provinces[j].revealedBy.add('you');

  return {
    seed, day: 1, phase: 'Emanation', over: false, winner: null,
    provinces, adj, players,
    selectedId: null, attackMode: 'martial', orders: [], log: [],
  };
}

function pickMode(rand) {
  const keys = Object.keys(MODES);
  return keys[Math.floor(rand() * keys.length)];
}
function angDiff(a, b) {
  let d = a - b;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return d;
}

export const isRevealed = (state, p, who = 'you') => p.revealedBy.has(who) || p.owner === who;
