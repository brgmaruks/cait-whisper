# Kaithos — Season Zero (MVP)

A playable slice of **Kaithos**: a daily-turn strategy game on a **golden-spiral board**.
Your Olympian kingdom vs. three AI traditions. Build, scout, strike with the golden-edge,
survive the Dissolution, and hold the **Eye** at the center to win the season.

> Zero dependencies. Pure HTML/CSS/JS (ES modules). Runs anywhere a browser can.

## Run it

```bash
cd kaithos
python3 -m http.server 8000
# open http://localhost:8000
```
(or any static server — `npx serve`, VS Code Live Server, etc.)

## How to play

1. **Select a province** on the spiral (click it).
2. On **your** provinces (gold): **Build** (+development → more gold & garrison),
   **Train** (+garrison), or **March/Strike** to an adjacent province.
3. **Strikes carry a mode** — **Martial ▲ / Shadow ✦ / Arcane ◈**. Counter the
   defender's mode for a **×φ golden edge**; get countered and you're at **×1/φ**.
   *Martial > Arcane > Shadow > Martial.* **Scout** enemy provinces to learn their mode.
4. Orders cost **Action Points** (AP, pooled to a Fibonacci cap) and resolve **at dawn**
   when you press **Advance Day** — simultaneously with the AI.
5. Each season the **Dissolution** eats the outer rings inward. Move toward the center or
   be unmade. **Hold the Eye when the spiral collapses to win.**

## Deploy (make it public)

It's a static site — deploy the `kaithos/` folder to any host:

- **Netlify / Vercel:** drag-and-drop the folder, or connect the repo (publish dir `kaithos`).
- **GitHub Pages:** enable Pages on the repo, serve from `/kaithos`.
- **Surge:** `npx surge kaithos kaithos.surge.sh`

## Layout

```
kaithos/
├── index.html        # shell
├── styles.css        # the esoteric gold theme
├── src/
│   ├── config.js     # φ, the board size, modes, factions, costs
│   ├── map.js        # phyllotaxis layout + spiral-arm adjacency
│   ├── state.js      # season setup (seeded, reproducible)
│   ├── render.js     # SVG board + HUD
│   ├── engine.js     # tick, orders, AI, golden-edge combat, Dissolution
│   └── main.js       # entry point
└── tools/
    └── snapshot.mjs  # render the board to SVG headlessly (dev tool)
```

## Status

Season Zero MVP — the core loop is **playable end to end**. Next: balance tuning,
a start/end screen, the five elements, multiplayer, and the on-chain layer (see
[`../docs/kaithos/`](../docs/kaithos/) for the full design + tokenomics).
