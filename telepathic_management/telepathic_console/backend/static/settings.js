(() => {
  'use strict';
  const state = document.getElementById('saveState');
  const runtimeRoot = document.getElementById('runtimeSettings');
  async function load() {
    try {
      const response = await fetch('/api/settings', {cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not load settings');
      document.getElementById('applyNote').textContent = data.apply_note;
      document.getElementById('runtimeNote').textContent = data.read_only_note;
      for (const item of data.runtime || []) {
        const card = document.createElement('article');
        card.className = 'runtime-card';
        for (const [tag, text] of [['strong', item.name], ['span', item.value], ['small', item.source]]) {
          const element = document.createElement(tag);
          element.textContent = text;
          card.appendChild(element);
        }
        runtimeRoot.appendChild(card);
      }
      state.textContent = 'Read-only runtime configuration';
    } catch (error) {
      state.textContent = error.message;
    }
  }
  load();
})();
