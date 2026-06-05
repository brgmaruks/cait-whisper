// The board is a phyllotaxis spiral: seeds sown at the golden angle.
// Adjacency runs along the spiral arms — which, in phyllotaxis, are exactly
// each seed's nearest neighbours (the Fibonacci parastichies). We compute the
// arms by geometric proximity, which IS the golden-angle arm structure.

import { GOLDEN_ANGLE, N_PROVINCES, CENTER, SCALE } from './config.js';

export function layout(n = N_PROVINCES) {
  const provs = [];
  for (let i = 0; i < n; i++) {
    const r = SCALE * Math.sqrt(i);
    const a = i * GOLDEN_ANGLE;
    provs.push({
      i,
      x: CENTER + r * Math.cos(a),
      y: CENTER + r * Math.sin(a),
      radius: r,           // distance from the Monad
      ring: ringOf(i),     // coarse ring index, for the Dissolution
    });
  }
  return provs;
}

// Group provinces into Fibonacci-sized rings from the centre outward:
// ring 0 = {0}, ring 1 = next 2, ring 2 = next 3, then 5, 8, 13 …
function ringOf(index) {
  let ring = 0, start = 0, size = 1, a = 1, b = 1;
  while (true) {
    if (index < start + size) return ring;
    start += size;
    ring++;
    [a, b] = [b, a + b]; // next Fibonacci
    size = b;
  }
}

// k nearest neighbours = the spiral-arm connections.
export function adjacency(provs, k = 6) {
  const adj = provs.map(() => []);
  for (let i = 0; i < provs.length; i++) {
    const d = [];
    for (let j = 0; j < provs.length; j++) {
      if (i === j) continue;
      const dx = provs[i].x - provs[j].x;
      const dy = provs[i].y - provs[j].y;
      d.push([j, dx * dx + dy * dy]);
    }
    d.sort((p, q) => p[1] - q[1]);
    adj[i] = d.slice(0, k).map((p) => p[0]);
  }
  // make symmetric
  for (let i = 0; i < adj.length; i++) {
    for (const j of adj[i]) {
      if (!adj[j].includes(i)) adj[j].push(i);
    }
  }
  return adj;
}

export const maxRing = (provs) => Math.max(...provs.map((p) => p.ring));
