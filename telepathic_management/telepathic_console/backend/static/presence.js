/* Poll the local Web Teleops Console status so the shared UI can reflect the AIVA PC heartbeat. */
(() => {
  'use strict';
  const label = document.getElementById('aivaPresence');
  const wave = document.getElementById('presenceWave');
  let stopped = false;
  let aivaOnline = false;
  let auroraOnline = false;
  let inferenceActive = false;
  let inferenceResponding = false;
  let agenticWorkActive = false;
  let inferenceTps = 0;

  function updateLabel() {
    if (!label) return;
    wave?.classList.toggle('is-active', aivaOnline && (inferenceActive || agenticWorkActive));
    if (wave) {
      const period = Math.max(0.22, Math.min(1, 1 - inferenceTps * 0.012));
      wave.style.setProperty('--presence-wave-duration', `${period}s`);
    }
    if (!aivaOnline) label.textContent = 'Grace is resting';
    else if (agenticWorkActive) label.textContent = 'Grace is working';
    else if (inferenceActive && inferenceResponding) label.textContent = 'Grace is responding';
    else if (inferenceActive) label.textContent = 'Grace is thinking';
    else label.textContent = 'Grace is waiting';
  }

  window.addEventListener('agi-grace-inference', (event) => {
    inferenceActive = event.detail?.active === true;
    inferenceResponding = event.detail?.responding === true;
    inferenceTps = Math.max(0, Number(event.detail?.tps) || 0);
    updateLabel();
  });

  window.addEventListener('agi-grace-agentic-work', (event) => {
    agenticWorkActive = event.detail?.active === true;
    updateLabel();
  });

  async function refresh() {
    try {
      const response = await fetch('/api/presence', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Presence request returned ${response.status}`);
      const status = await response.json();
      aivaOnline = status.aiva_online === true;
      auroraOnline = status.aurora_online === true;
      updateLabel();
      window.dispatchEvent(new CustomEvent('agi-aiva-presence', { detail: { online: aivaOnline } }));
      window.dispatchEvent(new CustomEvent('agi-aurora-presence', { detail: { online: auroraOnline } }));
    } catch (error) {
      aivaOnline = false;
      auroraOnline = false;
      updateLabel();
      window.dispatchEvent(new CustomEvent('agi-aiva-presence', { detail: { online: false } }));
      window.dispatchEvent(new CustomEvent('agi-aurora-presence', { detail: { online: false } }));
      console.debug('AIVA presence is not available:', error);
    }
    if (!stopped) window.setTimeout(refresh, 4000);
  }

  window.addEventListener('pagehide', () => { stopped = true; }, { once: true });
  updateLabel();
  refresh();
})();
