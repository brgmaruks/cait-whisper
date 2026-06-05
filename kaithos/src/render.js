// Rendering: the spiral board (SVG) + the side panel (DOM).

import { FACTIONS, MODES, ORDER_COSTS, GOLDEN_ANGLE, SCALE, CENTER, N_PROVINCES } from './config.js';
import { isRevealed } from './state.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs = {}) => {
  const n = document.createElementNS(SVGNS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
};

function colorFor(p) {
  if (p.dissolved) return 'var(--dissolved)';
  if (!p.owner) return 'var(--neutral)';
  return FACTIONS[p.owner].hex;
}

export function renderMap(state, handlers) {
  const svg = document.getElementById('map');
  svg.innerHTML = '';

  // golden spiral guide
  let d = '';
  for (let t = 0; t <= N_PROVINCES; t += 0.25) {
    const r = SCALE * Math.sqrt(t), a = t * GOLDEN_ANGLE;
    const x = CENTER + r * Math.cos(a), y = CENTER + r * Math.sin(a);
    d += (t === 0 ? 'M' : 'L') + x.toFixed(1) + ' ' + y.toFixed(1) + ' ';
  }
  svg.appendChild(el('path', { d, class: 'spiral-guide' }));

  // edges (spiral arms)
  const drawn = new Set();
  state.provinces.forEach((p) => {
    for (const j of state.adj[p.i]) {
      const key = p.i < j ? `${p.i}-${j}` : `${j}-${p.i}`;
      if (drawn.has(key)) continue;
      drawn.add(key);
      const q = state.provinces[j];
      if (p.dissolved || q.dissolved) continue;
      svg.appendChild(el('line', { x1: p.x, y1: p.y, x2: q.x, y2: q.y, class: 'edge' }));
    }
  });

  // provinces
  state.provinces.forEach((p) => {
    const g = el('g', { class: 'province' + (state.selectedId === p.i ? ' selected' : '') + (p.dissolved ? ' dissolved' : '') });
    const rad = 8 + p.dev * 2.4;

    if (p.isEye && !p.dissolved) {
      svg.appendChild(el('circle', { cx: p.x, cy: p.y, r: rad + 12, fill: 'var(--eye)', opacity: .08 }));
      svg.appendChild(el('circle', { cx: p.x, cy: p.y, r: rad + 6, fill: 'var(--eye)', opacity: .12 }));
    }

    g.appendChild(el('circle', {
      cx: p.x, cy: p.y, r: rad,
      fill: colorFor(p), 'fill-opacity': p.owner === 'you' ? .92 : .8,
      stroke: p.isEye ? 'var(--eye)' : 'rgba(0,0,0,.45)', 'stroke-width': p.isEye ? 2 : 1.2,
    }));

    if (!p.dissolved) {
      const known = isRevealed(state, p);
      const t = el('text', { x: p.x, y: p.y + 4, class: 'garrison-label' });
      t.textContent = known ? p.garrison : '?';
      g.appendChild(t);
    }

    g.addEventListener('click', () => handlers.onSelect(p.i));
    svg.appendChild(g);
  });
}

export function renderPanel(state, handlers) {
  const me = state.players.you;

  // hero
  const hero = document.getElementById('hero-block');
  hero.innerHTML = `
    <h3>Your Hero — ${FACTIONS.you.name}</h3>
    <div class="stat-row"><span class="k">Path</span><span class="v">${MODES[FACTIONS.you.lean].name} ${MODES[FACTIONS.you.lean].sym}</span></div>
    <div class="stat-row"><span class="k">Level</span><span class="v">${me.hero.level}</span></div>
    <div class="stat-row"><span class="k">Action Points</span><span class="v" style="color:var(--gold)">${me.ap} / ${me.apMax}</span></div>`;

  // resources
  const res = document.getElementById('resource-block');
  const provs = state.provinces.filter((p) => p.owner === 'you' && !p.dissolved).length;
  res.innerHTML = `
    <h3>Dominion</h3>
    <div class="stat-row"><span class="k">Gold</span><span class="v">${me.gold}</span></div>
    <div class="stat-row"><span class="k">Aether</span><span class="v" style="color:var(--f-orphic)">${me.aether}</span></div>
    <div class="stat-row"><span class="k">Provinces</span><span class="v">${provs}</span></div>`;

  renderSelection(state, handlers);
  renderLog(state);
}

function renderSelection(state, handlers) {
  const sel = document.getElementById('selection-block');
  const ord = document.getElementById('orders-block');
  const p = state.selectedId != null ? state.provinces[state.selectedId] : null;

  if (!p) {
    sel.innerHTML = `<h3>The Spiral</h3><p class="muted">Select a province. The Dissolution eats inward each season — there is nowhere to hide but the centre.</p>`;
    ord.innerHTML = '';
    return;
  }

  const mine = p.owner === 'you';
  const known = isRevealed(state, p);
  const ownerName = p.owner ? FACTIONS[p.owner].name : 'Neutral';
  sel.innerHTML = `
    <h3>${p.isEye ? 'The Eye · the Monad' : 'Province ' + p.i}</h3>
    <div class="stat-row"><span class="k">Holder</span><span class="v" style="color:${p.owner ? FACTIONS[p.owner].hex : 'var(--muted)'}">${ownerName}</span></div>
    <div class="stat-row"><span class="k">Garrison</span><span class="v">${known ? p.garrison : 'unknown'}</span></div>
    <div class="stat-row"><span class="k">Development</span><span class="v">${p.dev}</span></div>
    <div class="stat-row"><span class="k">Ring</span><span class="v">${p.ring}${p.isEye ? ' · centre' : ''}</span></div>`;

  if (p.dissolved) { ord.innerHTML = `<p class="muted">Claimed by the Dissolution.</p>`; return; }

  // orders depend on context (filled in by engine stage)
  if (handlers.renderOrders) handlers.renderOrders(state, p, ord);
  else ord.innerHTML = '';
}

export function renderLog(state) {
  const stream = document.getElementById('log-stream');
  stream.innerHTML = state.log.slice(-40).map((e) =>
    `<div class="entry ${e.cls || ''}">${e.text}</div>`).join('');
  stream.scrollTop = stream.scrollHeight;
}

export function renderTop(state) {
  document.getElementById('day-num').textContent = state.day;
  document.getElementById('phase-label').textContent = state.phase;
  const btn = document.getElementById('advance-btn');
  btn.disabled = state.over;
  btn.textContent = state.over ? 'Season Ended' : 'Advance Day ›';
}

export function renderAll(state, handlers) {
  renderTop(state);
  renderMap(state, handlers);
  renderPanel(state, handlers);
}
