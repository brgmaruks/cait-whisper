// Dev tool: render the real board state to an SVG (no browser needed).
// Usage: node tools/snapshot.mjs [seed] [days]  ->  writes tools/board.svg
import { writeFileSync } from 'fs';
import { createState } from '../src/state.js';
import { attachEngine } from '../src/engine.js';
import { ORDER_COSTS, FACTIONS, ELEMENTS, GOLDEN_ANGLE, SCALE, CENTER, N_PROVINCES } from '../src/config.js';

const seed = parseInt(process.argv[2] || '7', 10);
const days = parseInt(process.argv[3] || '0', 10);
const s = createState(seed);

// optionally evolve a few days so the board looks lived-in
if (days > 0) {
  const h = {}; attachEngine(s, h, () => {});
  for (let d = 0; d < days && !s.over; d++) {
    const me = s.players.you;
    const mine = s.provinces.filter((p) => p.owner === 'you' && !p.dissolved);
    // train the thin garrisons (the forge — Fire)
    for (const p of mine) {
      if (me.ap >= 1 && me.res.fire >= ORDER_COSTS.train.fire && p.garrison < 9) {
        me.ap -= 1; me.res.fire -= ORDER_COSTS.train.fire; s.orders.push({ kind: 'train', prov: p.i });
      }
    }
    // strike inward with the strongest holding (provisions — Water)
    const strong = mine.filter((p) => p.garrison > 4).sort((a, b) => b.garrison - a.garrison)[0];
    if (strong && me.ap >= 2 && me.res.water >= ORDER_COSTS.march.water) {
      const t = s.adj[strong.i].map((j) => s.provinces[j])
        .filter((q) => q.owner !== 'you' && !q.dissolved)
        .sort((a, b) => a.radius - b.radius)[0];
      if (t) { me.ap -= 2; me.res.water -= ORDER_COSTS.march.water; s.orders.push({ kind: 'march', from: strong.i, to: t.i, troops: strong.garrison - 1, mode: 'shadow', cost: ORDER_COSTS.march }); }
    }
    h.onAdvance();
  }
}

const C = (p) => p.dissolved ? '#221f30' : (p.owner ? FACTIONS[p.owner].hex : '#5a5470');
let svg = '';
const W = 900, H = 980, TOP = 80;

svg += `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`;
svg += `<rect width="${W}" height="${H}" fill="#0b0a12"/>`;
svg += `<radialGradient id="bg" cx="50%" cy="42%" r="62%"><stop offset="0" stop-color="#161228"/><stop offset="1" stop-color="#0b0a12"/></radialGradient>`;
svg += `<rect width="${W}" height="${H}" fill="url(#bg)"/>`;
// title
svg += `<text x="36" y="48" fill="#e8b84b" font-family="Georgia,serif" font-size="30" letter-spacing="8">𝛗  KAITHOS</text>`;
svg += `<text x="40" y="68" fill="#8d86a3" font-family="sans-serif" font-size="13" letter-spacing="4">SEASON ZERO  ·  DAY ${s.day}  ·  ${s.phase.toUpperCase()}</text>`;

const g = (x, y) => `${(x).toFixed(1)} ${(y + TOP).toFixed(1)}`;
// spiral guide
let d = '';
for (let t = 0; t <= N_PROVINCES; t += 0.25) {
  const r = SCALE * Math.sqrt(t), a = t * GOLDEN_ANGLE;
  d += (t === 0 ? 'M' : 'L') + g(CENTER + r * Math.cos(a), CENTER + r * Math.sin(a)) + ' ';
}
svg += `<path d="${d}" fill="none" stroke="rgba(232,184,75,0.12)" stroke-width="1.5"/>`;
// edges
const drawn = new Set();
for (const p of s.provinces) {
  if (p.dissolved) continue;
  for (const j of s.adj[p.i]) {
    const q = s.provinces[j]; if (q.dissolved) continue;
    const key = p.i < j ? `${p.i}-${j}` : `${j}-${p.i}`; if (drawn.has(key)) continue; drawn.add(key);
    svg += `<line x1="${p.x.toFixed(1)}" y1="${(p.y + TOP).toFixed(1)}" x2="${q.x.toFixed(1)}" y2="${(q.y + TOP).toFixed(1)}" stroke="#2a2540" stroke-width="1" opacity="0.5"/>`;
  }
}
// provinces
for (const p of s.provinces) {
  const rad = 8 + p.dev * 2.4, y = p.y + TOP;
  if (p.isEye && !p.dissolved) {
    svg += `<circle cx="${p.x}" cy="${y}" r="${rad + 13}" fill="#fff7e0" opacity="0.08"/>`;
    svg += `<circle cx="${p.x}" cy="${y}" r="${rad + 6}" fill="#fff7e0" opacity="0.13"/>`;
  }
  svg += `<circle cx="${p.x}" cy="${y}" r="${rad}" fill="${C(p)}" fill-opacity="${p.owner === 'you' ? 0.95 : 0.82}" stroke="${p.isEye ? '#fff7e0' : 'rgba(0,0,0,0.45)'}" stroke-width="${p.isEye ? 2 : 1.2}"/>`;
  if (!p.dissolved && !p.isEye && ELEMENTS[p.element]) svg += `<circle cx="${p.x}" cy="${y}" r="${rad + 3}" fill="none" stroke="${ELEMENTS[p.element].hex}" stroke-width="2" stroke-opacity="0.85"/>`;
  if (!p.dissolved) svg += `<text x="${p.x}" y="${y + 4}" fill="#fff" font-family="sans-serif" font-size="11" font-weight="700" text-anchor="middle">${p.garrison}</text>`;
}
// element legend (rings)
let ex = 40, ey = H - 54;
svg += `<text x="${ex}" y="${ey + 4}" fill="#8d86a3" font-family="sans-serif" font-size="12">rings:</text>`;
ex += 48;
for (const k of ['air', 'fire', 'earth', 'water']) {
  const e = ELEMENTS[k];
  svg += `<circle cx="${ex}" cy="${ey}" r="6" fill="none" stroke="${e.hex}" stroke-width="2"/>`;
  svg += `<text x="${ex + 12}" y="${ey + 4}" fill="#ece7da" font-family="sans-serif" font-size="12">${e.name}${k === 'fire' ? ' ▲' : k === 'water' ? ' ▼' : ''}</text>`;
  ex += 42 + e.name.length * 7;
}
// faction legend
let lx = 40, ly = H - 28;
for (const id in FACTIONS) {
  const f = FACTIONS[id];
  svg += `<circle cx="${lx}" cy="${ly}" r="7" fill="${f.hex}"/>`;
  svg += `<text x="${lx + 13}" y="${ly + 4}" fill="#ece7da" font-family="sans-serif" font-size="13">${f.name}${id === 'you' ? ' (you)' : ''}</text>`;
  lx += 60 + f.name.length * 8;
}
svg += `<circle cx="${lx}" cy="${ly}" r="7" fill="#fff7e0"/><text x="${lx + 13}" y="${ly + 4}" fill="#ece7da" font-family="sans-serif" font-size="13">the Eye</text>`;
svg += `</svg>`;

writeFileSync(new URL('./board.svg', import.meta.url), svg);
console.log('wrote tools/board.svg  (seed ' + seed + ', day ' + s.day + ', phase ' + s.phase + ')');
