// Kaithos — Season Zero. Entry point.

import { createState } from './state.js';
import { renderAll } from './render.js';
import { attachEngine } from './engine.js';

const state = createState();
state.log.push({ text: '<b>The spiral unwinds.</b> Season Zero begins. Four traditions, one Monad.', cls: 'day' });

const rerender = () => renderAll(state, handlers);

const handlers = {
  onSelect(i) {
    state.selectedId = (state.selectedId === i) ? null : i;
    rerender();
  },
  // renderOrders + onAdvance are attached by attachEngine below.
};

attachEngine(state, handlers, rerender);

document.getElementById('advance-btn').addEventListener('click', () => {
  if (handlers.onAdvance) handlers.onAdvance();
});

renderAll(state, handlers);

// expose for the engine module + console tinkering
window.__kaithos = { state, handlers, render: () => renderAll(state, handlers) };
