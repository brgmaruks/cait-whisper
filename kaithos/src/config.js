// Kaithos — core constants. The golden ratio is the physics of this world.

export const PHI = (1 + Math.sqrt(5)) / 2;          // 1.6180339887…
export const INV_PHI = 1 / PHI;                      // 0.6180339887…
export const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5)); // ~137.5° in radians

export const N_PROVINCES = 34;   // F(9) — a Fibonacci board
export const SEASON_DAYS = 24;   // ticks in Season Zero
export const VIEW = 900;         // svg viewBox size
export const CENTER = VIEW / 2;
export const SCALE = 72;         // radius = SCALE * sqrt(index)

// Contraction schedule: the Dissolution claims the outermost live ring on these days.
export const CONTRACTION_DAYS = [8, 12, 16, 19, 21, 23];

// The three combat modes — the offensive triangle.
//  Martial(Force) > Arcane(Power) > Shadow(Subtlety) > Martial …
export const MODES = {
  martial: { name: 'Martial', sym: '▲', beats: 'arcane' },  // the Square / phalanx
  shadow:  { name: 'Shadow',  sym: '✦', beats: 'martial' }, // the Pentagram / the knife
  arcane:  { name: 'Arcane',  sym: '◈', beats: 'shadow' },  // the Spiral / aether
};

export const FACTIONS = {
  you:    { id: 'you',    name: 'Olympian', color: 'var(--f-you)',    hex: '#e8b84b', lean: 'martial', ai: false },
  orphic: { id: 'orphic', name: 'Orphic',   color: 'var(--f-orphic)', hex: '#9b6cf0', lean: 'shadow',  ai: true  },
  norse:  { id: 'norse',  name: 'Norse',    color: 'var(--f-norse)',  hex: '#5bc8e8', lean: 'martial', ai: true  },
  egypt:  { id: 'egypt',  name: 'Egyptian', color: 'var(--f-egypt)',  hex: '#3fb98c', lean: 'arcane',  ai: true  },
};

export const ORDER_COSTS = {
  build: { ap: 1, gold: 8 },   // raise development
  train: { ap: 1, gold: 5 },   // +army to garrison
  scout: { ap: 1, gold: 0 },   // reveal an adjacent province
  march: { ap: 2, gold: 0 },   // move/strike to an adjacent province
};
